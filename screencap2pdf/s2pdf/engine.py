"""キャプチャのループ本体。CLI からも GUI からも同じものを使う。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from . import deps, imaging, winput
from .config import Profile, Region

# 進捗メッセージ・進捗率の通知先
MessageHook = Callable[[str], None]
ProgressHook = Callable[[int, int], None]
StopCheck = Callable[[], bool]


class CaptureError(RuntimeError):
    """キャプチャを続けられないときに投げる。"""


@dataclass
class CaptureReport:
    """1 回の実行結果。"""

    saved: list[Path] = field(default_factory=list)
    reason: str = ""

    @property
    def page_count(self) -> int:
        return len(self.saved)


def to_window_region(region: Region, window_title: str) -> Region:
    """画面座標で選んだ範囲を、ウィンドウ内の相対座標に直す。

    ウィンドウ直接キャプチャではウィンドウを動かしても同じ場所を撮りたいので、
    範囲はウィンドウの左上を原点にして持つ。
    """
    info = winput.find_window(window_title)
    if info is None:
        raise CaptureError(f"ウィンドウが見つかりません: {window_title}")
    left, top, _width, _height = winput.get_window_rect(info.hwnd)
    return region.relative_to(left, top)


def _grab_region(region: Region) -> Image.Image:
    """指定範囲を 1 枚キャプチャする。"""
    try:
        import mss  # 遅延 import（GUI を開くだけなら不要）
    except ImportError as exc:
        mss_dep = [d for d in deps.DEPENDENCIES if d.module == "mss"]
        raise CaptureError(
            "画面キャプチャに必要な " + deps.missing_message(mss_dep)
        ) from exc

    with mss.mss() as sct:
        shot = sct.grab(region.as_bbox())
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


class Capturer:
    """プロファイルに従って画面を撮り続ける。"""

    def __init__(
        self,
        profile: Profile,
        on_message: Optional[MessageHook] = None,
        on_progress: Optional[ProgressHook] = None,
        should_stop: Optional[StopCheck] = None,
    ) -> None:
        profile.validate()
        self.profile = profile
        self._on_message = on_message or (lambda _msg: None)
        self._on_progress = on_progress or (lambda _done, _total: None)
        self._should_stop = should_stop or (lambda: False)
        self._hwnd: Optional[int] = None
        self._page_turn_method = "input"  # "post" = 前面を奪わない送り方

    # ---- 部品 -------------------------------------------------------

    def message(self, text: str) -> None:
        self._on_message(text)

    def grab(self) -> Image.Image:
        """加工前の生キャプチャ。"""
        if self.profile.uses_window_capture:
            return self._grab_window()
        assert self.profile.region is not None
        return _grab_region(self.profile.region)

    def _grab_window_full(self) -> Image.Image:
        """ウィンドウ全体を直接取り込む（他のウィンドウに隠れていても撮れる）。"""
        hwnd = self._hwnd if self._hwnd is not None else self.resolve_window()
        if hwnd is None:
            raise CaptureError("対象ウィンドウが指定されていません。")
        self._hwnd = hwnd
        return winput.capture_window_image(hwnd)

    def _grab_window(self) -> Image.Image:
        """ウィンドウの中身のうち、指定された範囲だけを取り込む。"""
        image = self._grab_window_full()
        region = self.profile.region
        if region is None:
            return image
        return image.crop(region.crop_box(image.width, image.height))

    def capture_image(self) -> Image.Image:
        """撮って、設定どおりに加工した 1 枚。"""
        return imaging.apply_options(self.grab(), self.profile.image_options())

    def save_image(self, image: Image.Image, index: int) -> Path:
        """加工済みの画像をページ番号のファイル名で保存する。"""
        path = self.profile.image_path(index)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in (".jpg", ".jpeg"):
            image.convert("RGB").save(path, quality=95, optimize=True)
        else:
            image.save(path)
        return path

    def capture_page(self, index: int) -> Path:
        """1 ページ分を撮って保存し、保存先を返す。"""
        return self.save_image(self.capture_image(), index)

    def check_window_capture(self) -> None:
        """ウィンドウ直接キャプチャが効くアプリかどうかを、撮り始める前に確かめる。

        判定はウィンドウ全体で行う。切り出した範囲だけを見ると、
        余白や白紙のページを「取り込めていない」と誤判定してしまう。
        """
        if imaging.is_uniform(self._grab_window_full()):
            raise CaptureError(
                "ウィンドウの中身を取り込めませんでした（画像が 1 色になります）。\n"
                "・対象ウィンドウが最小化されていないか確認してください\n"
                "・このアプリが対応していない場合は、"
                "「画面をそのまま撮る」モードに戻してください"
            )

    def save_preview(self, path: Path) -> Path:
        """範囲確認用に 1 枚だけ保存する。"""
        image = imaging.apply_options(self.grab(), self.profile.image_options())
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return path

    def resolve_window(self) -> Optional[int]:
        """ページ送り先のウィンドウを解決する（タイトル未指定なら None）。"""
        title = (self.profile.window_title or "").strip()
        if not title:
            return None
        info = winput.find_window(title)
        if info is None:
            raise CaptureError(f"ウィンドウが見つかりません: {title}")
        self.message(f"対象ウィンドウ: {info.title}")
        return info.hwnd

    def turn_page(self) -> None:
        """ページ送りキーを送る。

        ウィンドウ直接キャプチャのときは前面に出さずにメッセージで送るので、
        他のウィンドウで作業していても邪魔されない。
        メッセージでは反応しないアプリのために、前面に出す方式へ切り替えられる。
        """
        if self._page_turn_method == "post" and self._hwnd is not None:
            winput.post_key(self._hwnd, self.profile.key)
            return
        if self._hwnd is not None and not winput.focus_window(self._hwnd):
            self.message("警告: 対象ウィンドウを前面にできませんでした。")
        winput.send_key(self.profile.key)

    def _wait_for_change(self, previous_fp: bytes, timeout: float) -> bool:
        """画面が変わるまで待つ。変わったら True、時間切れ・中止なら False。"""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self._should_stop() or winput.is_escape_pressed():
                return False
            # 保存するものと同じ加工を通してから比べる（切り抜きや縮小で見え方が変わるため）
            current = imaging.fingerprint(self.capture_image())
            if not imaging.looks_same(
                previous_fp, current, self.profile.duplicate_threshold
            ):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.15)

    def _retry_page_turn(self, previous_fp: bytes) -> bool:
        """ページが変わらなかったときに、送り方を変えながらやり直す。"""
        profile = self.profile
        self.message("ページが変わりません。もう一度キーを送ります。")
        self.turn_page()
        if self._wait_for_change(previous_fp, profile.change_timeout):
            return True

        if self._page_turn_method == "post":
            # メッセージを受け取らない作りのアプリ向けに、前面に出す方式へ切り替える
            self.message(
                "メッセージ送信では反応しないため、"
                "対象ウィンドウを前面に出してキーを送る方式に切り替えます。"
            )
            self._page_turn_method = "input"
            self.turn_page()
            if self._wait_for_change(previous_fp, profile.change_timeout):
                return True
        return False

    PAGE_NOT_CHANGING = (
        "ページが変わらないので終了しました。\n"
        "最後まで到達したのなら問題ありません。そうでない場合は次を確認してください:\n"
        "・ページ送りのキーが合っているか（right / left / pagedown / space など）\n"
        "・対象ウィンドウを指定しているか（未指定だと前面のウィンドウにキーが送られます）\n"
        "・「ページ送り後の待ち」「変化を待つ最大」を長くする必要がないか"
    )

    NO_TARGET_WINDOW = (
        "対象ウィンドウが未指定です。前面にあるウィンドウにキーを送ります。"
        "開始までの待ち時間の間に、対象のアプリをクリックして前面にしてください。"
    )

    # ---- 本体 -------------------------------------------------------

    def run(self, start_index: int = 1, resume: bool = False) -> CaptureReport:
        """連続キャプチャを実行する。"""
        profile = self.profile
        report = CaptureReport()
        self._hwnd = self.resolve_window()
        # ウィンドウ直接キャプチャなら、まずは前面を奪わない送り方から試す
        self._page_turn_method = "post" if profile.uses_window_capture else "input"
        if profile.uses_window_capture:
            self.check_window_capture()

        index = start_index
        if resume:
            while profile.image_path(index).exists():
                index += 1
            if index != start_index:
                self.message(f"{index - 1} ページ目まで既にあるので {index} ページ目から続けます。")

        if self._hwnd is None:
            self.message(self.NO_TARGET_WINDOW)

        total = profile.pages if profile.pages > 0 else 0
        if profile.start_delay > 0:
            self.message(
                f"{profile.start_delay:.0f} 秒後に開始します。対象のウィンドウを前面にしてください。"
            )
            if self._sleep(profile.start_delay):
                report.reason = "開始前に中止しました。"
                return report

        previous_fp: Optional[bytes] = None
        captured_this_run = 0

        while True:
            if self._should_stop():
                report.reason = "中止しました。"
                break
            if winput.is_escape_pressed():
                report.reason = "Esc キーで中止しました。"
                break

            image = self.capture_image()
            current_fp = imaging.fingerprint(image)
            unchanged = previous_fp is not None and imaging.looks_same(
                previous_fp, current_fp, profile.duplicate_threshold
            )
            if unchanged:
                # ページ送りを試したのに画面が変わっていない。
                # 同じ絵を何十枚も残しても意味がないので、ここでは保存しない。
                if profile.stop_on_duplicate:
                    report.reason = self.PAGE_NOT_CHANGING
                    break
                self.message("警告: ページが変わっていませんが、設定により続けます。")

            path = self.save_image(image, index)
            report.saved.append(path)
            captured_this_run += 1
            previous_fp = current_fp
            self._on_progress(captured_this_run, total)
            self.message(f"{index} ページ目を保存: {path.name}")

            # 最後の 1 枚を撮ったあとは、余計なページ送りをせずに終わる
            if profile.pages > 0 and captured_this_run >= profile.pages:
                report.reason = f"指定した {profile.pages} ページを撮り終えました。"
                break

            index += 1

            if profile.after_shot_delay > 0 and self._sleep(profile.after_shot_delay):
                report.reason = "中止しました。"
                break
            try:
                self.turn_page()
            except OSError as exc:
                raise CaptureError(f"キー送出に失敗しました: {exc}") from exc
            if profile.settle_delay > 0 and self._sleep(profile.settle_delay):
                report.reason = "中止しました。"
                break

            if profile.verify_page_turn and not self._wait_for_change(
                current_fp, profile.change_timeout
            ):
                if self._should_stop() or winput.is_escape_pressed():
                    report.reason = "中止しました。"
                    break
                if not self._retry_page_turn(current_fp) and profile.stop_on_duplicate:
                    report.reason = self.PAGE_NOT_CHANGING
                    break

        if not report.reason:
            report.reason = "終了しました。"
        return report

    def _sleep(self, seconds: float) -> bool:
        """細かく分けて待つ。中止要求があれば True を返す。"""
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self._should_stop() or winput.is_escape_pressed():
                return True
            time.sleep(min(0.05, remaining))
