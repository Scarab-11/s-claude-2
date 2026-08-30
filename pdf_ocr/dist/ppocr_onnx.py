# -*- coding: utf-8 -*-
"""PP-OCRv5（mobile / server）を onnxruntime だけで動かす、最小限の検出＋認識。

paddlepaddle（同梱すると 721 MB）を丸ごと入れずに済むよう、模型は
あらかじめ ONNX に変換したものを使う（`paddle2onnx` で変換、実測ずみ。
`pdf_ocr/README.md` の「① 枠組みの 721 MB → 理由になりません」を参照）。

検出（DB＝Differentiable Binarization）の後処理 `DBPostProcess` と、
認識の文字列への変換 `CTCLabelDecode` / `BaseRecLabelDecode` は、
PaddleOCR（Apache License 2.0, Copyright (c) 2020 PaddlePaddle Authors）
の実装にそのまま沿っている。前処理・切り出し・呼び出しの流れも、
PaddleOCR の推論パイプラインと同じ手順を踏む（模型自体が PaddleOCR の
学習済み模型なので、前処理がずれると精度が落ちる）。
参考: https://github.com/PaddlePaddle/PaddleOCR （Apache License 2.0）
"""
import math

import numpy as np


# --------------------------------------------------------------------------
# 検出の後処理（DB）。PaddleOCR の db_postprocess.py に沿った実装。
# --------------------------------------------------------------------------
class DBPostProcess(object):
    """Differentiable Binarization の後処理。確率マップから文字の四角形を作る。"""

    def __init__(self, thresh=0.3, box_thresh=0.6, max_candidates=1000,
                unclip_ratio=1.5, min_size=3):
        self.thresh = thresh
        self.box_thresh = box_thresh
        self.max_candidates = max_candidates
        self.unclip_ratio = unclip_ratio
        self.min_size = min_size

    def __call__(self, prob_map, src_h, src_w):
        import cv2

        height, width = prob_map.shape
        bitmap = (prob_map > self.thresh).astype(np.uint8)
        contours, _ = cv2.findContours(bitmap * 255, cv2.RETR_LIST,
                                       cv2.CHAIN_APPROX_SIMPLE)
        boxes, scores = [], []
        for contour in contours[:self.max_candidates]:
            points, short_side = self.get_mini_boxes(contour)
            if short_side < self.min_size:
                continue
            points = np.array(points)
            score = self.box_score_fast(prob_map, points)
            if score < self.box_thresh:
                continue
            box = self.unclip(points, self.unclip_ratio)
            if box is None:
                continue
            box, short_side = self.get_mini_boxes(box.reshape(-1, 1, 2))
            if short_side < self.min_size + 2:
                continue
            box = np.array(box, dtype=np.float64)
            box[:, 0] = np.clip(np.round(box[:, 0] / width * src_w), 0, src_w)
            box[:, 1] = np.clip(np.round(box[:, 1] / height * src_h), 0, src_h)
            boxes.append(box.astype(np.float32))
            scores.append(score)
        return boxes, scores

    def unclip(self, box, ratio):
        import pyclipper
        from shapely.geometry import Polygon

        poly = Polygon(box)
        if poly.length == 0:
            return None
        distance = poly.area * ratio / poly.length
        offset = pyclipper.PyclipperOffset()
        offset.AddPath(box, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        expanded = offset.Execute(distance)
        if len(expanded) != 1:
            return None
        return np.array(expanded[0])

    def get_mini_boxes(self, contour):
        import cv2

        bounding_box = cv2.minAreaRect(contour)
        points = sorted(cv2.boxPoints(bounding_box), key=lambda p: p[0])
        if points[1][1] > points[0][1]:
            i1, i4 = 0, 1
        else:
            i1, i4 = 1, 0
        if points[3][1] > points[2][1]:
            i2, i3 = 2, 3
        else:
            i2, i3 = 3, 2
        box = [points[i1], points[i2], points[i3], points[i4]]
        return box, min(bounding_box[1])

    def box_score_fast(self, prob_map, box):
        import cv2

        h, w = prob_map.shape
        xmin = int(np.clip(np.floor(box[:, 0].min()), 0, w - 1))
        xmax = int(np.clip(np.ceil(box[:, 0].max()), 0, w - 1))
        ymin = int(np.clip(np.floor(box[:, 1].min()), 0, h - 1))
        ymax = int(np.clip(np.ceil(box[:, 1].max()), 0, h - 1))
        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        shifted = box.copy()
        shifted[:, 0] -= xmin
        shifted[:, 1] -= ymin
        cv2.fillPoly(mask, shifted.reshape(1, -1, 2).astype(np.int32), 1)
        return cv2.mean(prob_map[ymin:ymax + 1, xmin:xmax + 1], mask)[0]


# --------------------------------------------------------------------------
# 認識の後処理（CTC）。PaddleOCR の rec_postprocess.py に沿った実装。
# --------------------------------------------------------------------------
class CTCLabelDecode(object):
    """認識モデルが出す 1 文字ずつの確率列を、文字列に変換する。"""

    def __init__(self, dict_path):
        with open(dict_path, "rb") as f:
            chars = [line.decode("utf-8").strip("\r\n") for line in f]
        self.character = ["blank"] + chars + [" "]

    def __call__(self, preds):
        # preds: (T, num_classes) の 1 枚ぶん
        idx = preds.argmax(axis=1)
        prob = preds.max(axis=1)
        keep = np.ones(len(idx), dtype=bool)
        keep[1:] = idx[1:] != idx[:-1]     # 同じ字の連続はまとめる（CTC の作法）
        keep &= idx != 0                   # blank を捨てる
        chars = [self.character[i] for i in idx[keep]]
        confs = prob[keep]
        text = "".join(chars)
        conf = float(confs.mean()) if len(confs) else 0.0
        return text, conf


# --------------------------------------------------------------------------
# 前処理・切り出し
# --------------------------------------------------------------------------
def resize_for_det(image, limit_side_len=960, limit_type="max"):
    """検出モデルに入れる大きさに変える（32 の倍数、長辺 limit_side_len）。"""
    h, w = image.shape[:2]
    if limit_type == "max":
        ratio = float(limit_side_len) / max(h, w) if max(h, w) > limit_side_len \
            else 1.0
    else:
        ratio = float(limit_side_len) / min(h, w) if min(h, w) < limit_side_len \
            else 1.0
    resize_h = max(int(round(h * ratio / 32) * 32), 32)
    resize_w = max(int(round(w * ratio / 32) * 32), 32)
    import cv2
    resized = cv2.resize(image, (resize_w, resize_h))
    return resized, resize_h / float(h), resize_w / float(w)


DET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
DET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)


def normalize_chw(image, mean, std, scale=1.0 / 255.0):
    normed = (image.astype(np.float32) * scale - mean) / std
    return normed.transpose(2, 0, 1)


def get_rotate_crop_image(image, box):
    """4 点の四角形の場所を、まっすぐな画像として切り出す。"""
    import cv2

    width = int(max(np.linalg.norm(box[0] - box[1]),
                    np.linalg.norm(box[2] - box[3])))
    height = int(max(np.linalg.norm(box[0] - box[3]),
                     np.linalg.norm(box[1] - box[2])))
    width, height = max(width, 1), max(height, 1)
    dst = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    matrix = cv2.getPerspectiveTransform(box.astype(np.float32), dst)
    crop = cv2.warpPerspective(image, matrix, (width, height),
                               borderMode=cv2.BORDER_REPLICATE,
                               flags=cv2.INTER_CUBIC)
    vertical = (crop.shape[0] / float(crop.shape[1])) >= 1.5
    if vertical:
        crop = np.rot90(crop)
    return crop, vertical


def resize_norm_rec(crop, img_h=48, img_w_max=None):
    """認識モデルに入れる大きさに変える（縦 48 に合わせ、横は比率で伸縮）。"""
    import cv2

    h, w = crop.shape[:2]
    ratio = w / float(h)
    resized_w = min(int(math.ceil(img_h * ratio)),
                    img_w_max) if img_w_max else int(math.ceil(img_h * ratio))
    resized_w = max(resized_w, 1)
    resized = cv2.resize(crop, (resized_w, img_h))
    normed = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
    normed = (normed - 0.5) / 0.5
    if img_w_max and resized_w < img_w_max:
        padded = np.zeros((3, img_h, img_w_max), dtype=np.float32)
        padded[:, :, :resized_w] = normed
        return padded
    return normed


class PPOCREngine(object):
    """1 枚の画像を渡すと、(box, text, conf, vertical) の一覧を返す。"""

    def __init__(self, det_path, rec_path, dict_path, det_side=960,
                det_limit="max"):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.det = ort.InferenceSession(det_path, sess_options=opts,
                                        providers=["CPUExecutionProvider"])
        self.rec = ort.InferenceSession(rec_path, sess_options=opts,
                                        providers=["CPUExecutionProvider"])
        self.det_input = self.det.get_inputs()[0].name
        self.rec_input = self.rec.get_inputs()[0].name
        self.decode = CTCLabelDecode(dict_path)
        self.det_side = det_side
        self.det_limit = det_limit
        self.post = DBPostProcess()

    def detect(self, image):
        resized, ratio_h, ratio_w = resize_for_det(image, self.det_side,
                                                    self.det_limit)
        feed = normalize_chw(resized, DET_MEAN, DET_STD)[np.newaxis]
        out = self.det.run(None, {self.det_input: feed})[0]
        prob_map = out[0, 0]
        h, w = image.shape[:2]
        boxes, scores = self.post(prob_map, h, w)
        return boxes, scores

    def recognize_crop(self, crop):
        normed = resize_norm_rec(crop)[np.newaxis]
        out = self.rec.run(None, {self.rec_input: normed})[0]
        return self.decode(out[0])

    def read_image(self, image):
        """image: cv2 形式（BGR の numpy 配列）または画像ファイルの場所。"""
        import cv2

        if isinstance(image, str):
            image = cv2.imread(image)
        boxes, det_scores = self.detect(image)
        results = []
        for box, det_score in zip(boxes, det_scores):
            crop, vertical = get_rotate_crop_image(image, box)
            if crop.shape[0] < 2 or crop.shape[1] < 2:
                continue
            text, rec_conf = self.recognize_crop(crop)
            if not text:
                continue
            results.append((box, text, rec_conf, vertical))
        return results
