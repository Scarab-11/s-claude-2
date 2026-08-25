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
    removed: list[Path] = field(default_factory=list)
    reason: str = ""

    @property
    def page_count(self) -> int:
        return len(self.saved)


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

    # ---- 部品 -------------------------------------------------------

    def message(self, text: str) -> None:
        self._on_message(text)

    def grab(self) -> Image.Image:
        """加工前の生キャプチャ。"""
        assert self.profile.region is not None
        return _grab_region(self.profile.region)

    def capture_page(self, index: int) -> Path:
        """1 ページ分を撮って保存し、保存先を返す。"""
        image = imaging.apply_options(self.grab(), self.profile.image_options())
        path = self.profile.image_path(index)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in (".jpg", ".jpeg"):
            image.convert("RGB").save(path, quality=95, optimize=True)
        else:
            image.save(path)
        return path

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
        """対象ウィンドウを前面にしてページ送りキーを送る。"""
        if self._hwnd is not None and not winput.focus_window(self._hwnd):
            self.message("警告: 対象ウィンドウを前面にできませんでした。")
        winput.send_key(self.profile.key)

    # ---- 本体 -------------------------------------------------------

    def run(self, start_index: int = 1, resume: bool = False) -> CaptureReport:
        """連続キャプチャを実行する。"""
        profile = self.profile
        report = CaptureReport()
        self._hwnd = self.resolve_window()

        index = start_index
        if resume:
            while profile.image_path(index).exists():
                index += 1
            if index != start_index:
                self.message(f"{index - 1} ページ目まで既にあるので {index} ページ目から続けます。")

        total = profile.pages if profile.pages > 0 else 0
        if profile.start_delay > 0:
            self.message(
                f"{profile.start_delay:.0f} 秒後に開始します。対象のウィンドウを前面にしてください。"
            )
            if self._sleep(profile.start_delay):
                report.reason = "開始前に中止しました。"
                return report

        previous_fp: Optional[bytes] = None
        duplicate_streak = 0
        captured_this_run = 0

        while True:
            if self._should_stop():
                report.reason = "中止しました。"
                break
            if winput.is_escape_pressed():
                report.reason = "Esc キーで中止しました。"
                break

            path = self.capture_page(index)
            report.saved.append(path)
            captured_this_run += 1
            self._on_progress(captured_this_run, total)
            self.message(f"{index} ページ目を保存: {path.name}")

            if profile.stop_on_duplicate:
                with Image.open(path) as img:
                    current_fp = imaging.fingerprint(img)
                if previous_fp is not None and imaging.looks_same(
                    previous_fp, current_fp, profile.duplicate_threshold
                ):
                    duplicate_streak += 1
                    if duplicate_streak >= profile.duplicate_limit:
                        report.reason = (
                            f"同じ画面が {profile.duplicate_limit} 回続いたので終端と判断しました。"
                        )
                        report.removed = self._drop_trailing(report, duplicate_streak)
                        break
                else:
                    duplicate_streak = 0
                previous_fp = current_fp

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

        if not report.reason:
            report.reason = "終了しました。"
        return report

    def _drop_trailing(self, report: CaptureReport, count: int) -> list[Path]:
        """終端判定で余分に撮れた同一ページを消す。"""
        removed: list[Path] = []
        for path in report.saved[-count:]:
            try:
                path.unlink()
                removed.append(path)
            except OSError:
                pass
        del report.saved[-count:]
        return removed

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
