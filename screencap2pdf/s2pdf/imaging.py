"""画像の後処理（余白除去・縮小・グレースケール化）と、同一ページ判定。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageChops

# 同じページとみなす差分のしきい値（0.0 = 完全一致, 1.0 = 全画素が真逆）
DEFAULT_SIMILARITY_THRESHOLD = 0.004


@dataclass
class ImageOptions:
    """キャプチャ後にかける処理の設定。"""

    trim: bool = False
    trim_tolerance: int = 10
    trim_padding: int = 0
    grayscale: bool = False
    max_width: Optional[int] = None

    def describe(self) -> str:
        parts = []
        if self.trim:
            parts.append(f"余白除去(許容差{self.trim_tolerance})")
        if self.grayscale:
            parts.append("グレースケール")
        if self.max_width:
            parts.append(f"横幅{self.max_width}pxに縮小")
        return " / ".join(parts) if parts else "そのまま"


def auto_trim(
    image: Image.Image, tolerance: int = 10, padding: int = 0
) -> Image.Image:
    """周囲の均一な余白を切り落とす。

    四隅の色の平均を「背景色」とみなし、そこから ``tolerance`` を超えて
    離れている画素の外接矩形で切り抜く。全面が背景色なら元画像を返す。
    """
    rgb = image.convert("RGB")
    w, h = rgb.size
    if w < 2 or h < 2:
        return image

    corners = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((w - 1, 0)),
        rgb.getpixel((0, h - 1)),
        rgb.getpixel((w - 1, h - 1)),
    ]
    bg = tuple(sum(c[i] for c in corners) // len(corners) for i in range(3))

    background = Image.new("RGB", rgb.size, bg)
    diff = ImageChops.difference(rgb, background).convert("L")
    # tolerance 以下を 0、超えたら 255 にして外接矩形を求める
    mask = diff.point(lambda v: 255 if v > tolerance else 0)
    bbox = mask.getbbox()
    if not bbox:
        return image

    left, top, right, bottom = bbox
    if padding:
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(w, right + padding)
        bottom = min(h, bottom + padding)
    if (left, top, right, bottom) == (0, 0, w, h):
        return image
    return image.crop((left, top, right, bottom))


def apply_options(image: Image.Image, options: ImageOptions) -> Image.Image:
    """設定に従って画像を加工する。"""
    result = image
    if options.trim:
        result = auto_trim(result, options.trim_tolerance, options.trim_padding)
    if options.max_width and result.width > options.max_width:
        ratio = options.max_width / result.width
        new_size = (options.max_width, max(1, round(result.height * ratio)))
        result = result.resize(new_size, Image.LANCZOS)
    if options.grayscale:
        result = result.convert("L")
    elif result.mode not in ("RGB", "L"):
        # PDF 化のためにアルファチャンネルを落としておく
        result = result.convert("RGB")
    return result


def fingerprint(image: Image.Image, size: int = 32) -> bytes:
    """ページの同一判定に使う小さな指紋。"""
    small = image.convert("L").resize((size, size), Image.BILINEAR)
    return small.tobytes()


def difference(a: bytes, b: bytes) -> float:
    """2 つの指紋の平均差（0.0〜1.0）。"""
    if len(a) != len(b) or not a:
        return 1.0
    total = sum(abs(x - y) for x, y in zip(a, b))
    return total / (len(a) * 255.0)


def looks_same(a: bytes, b: bytes, threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> bool:
    """同じページとみなせるか。"""
    return difference(a, b) <= threshold
