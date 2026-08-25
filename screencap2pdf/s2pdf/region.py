"""画面全体に半透明の膜をかけて、ドラッグでキャプチャ範囲を選ばせる。"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from . import winput
from .config import Region

HINT = "ドラッグで範囲を選択　/　Esc で中止"
MIN_SIZE = 8  # これ未満の選択は誤操作とみなす


def _virtual_screen(root: tk.Misc) -> tuple[int, int, int, int]:
    """マルチモニタ全体を覆う矩形。取得できなければ主モニタのみ。"""
    if winput.IS_WINDOWS:
        try:
            return winput.virtual_screen_rect()
        except Exception:
            pass
    return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())


class _RegionOverlay:
    def __init__(self, master: tk.Misc, initial: Optional[Region] = None) -> None:
        self.result: Optional[Region] = None
        self._start: Optional[tuple[int, int]] = None

        vx, vy, vw, vh = _virtual_screen(master)
        self._offset = (vx, vy)

        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-alpha", 0.28)
        except tk.TclError:
            pass
        self.window.configure(bg="black")
        self.window.config(cursor="crosshair")

        self.canvas = tk.Canvas(
            self.window, bg="black", highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.create_text(
            vw // 2,
            40,
            text=HINT,
            fill="white",
            font=("Meiryo UI", 18),
            tags="hint",
        )
        self._rect = self.canvas.create_rectangle(
            0, 0, 0, 0, outline="#00d0ff", width=2, dash=(4, 2), state="hidden"
        )
        self._label = self.canvas.create_text(
            0, 0, text="", fill="#00d0ff", font=("Consolas", 14), state="hidden"
        )

        if initial is not None:
            self._draw(
                initial.left - vx,
                initial.top - vy,
                initial.left - vx + initial.width,
                initial.top - vy + initial.height,
            )

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.window.bind("<Escape>", lambda _e: self._finish(None))
        self.window.focus_force()
        self.window.grab_set()

    def _draw(self, x0: int, y0: int, x1: int, y1: int) -> None:
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        self.canvas.coords(self._rect, left, top, right, bottom)
        self.canvas.itemconfigure(self._rect, state="normal")
        self.canvas.coords(self._label, left + 4, max(12, top - 14))
        self.canvas.itemconfigure(
            self._label,
            text=f"{right - left} x {bottom - top}",
            state="normal",
            anchor="w",
        )

    def _on_press(self, event: "tk.Event") -> None:
        self._start = (event.x, event.y)
        self.canvas.itemconfigure("hint", state="hidden")
        self._draw(event.x, event.y, event.x, event.y)

    def _on_drag(self, event: "tk.Event") -> None:
        if self._start is None:
            return
        self._draw(self._start[0], self._start[1], event.x, event.y)

    def _on_release(self, event: "tk.Event") -> None:
        if self._start is None:
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        width, height = right - left, bottom - top
        if width < MIN_SIZE or height < MIN_SIZE:
            # 小さすぎる選択はやり直し
            self._start = None
            self.canvas.itemconfigure(self._rect, state="hidden")
            self.canvas.itemconfigure(self._label, state="hidden")
            self.canvas.itemconfigure("hint", state="normal")
            return
        ox, oy = self._offset
        self._finish(Region(left + ox, top + oy, width, height))

    def _finish(self, region: Optional[Region]) -> None:
        self.result = region
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()


def pick_region(
    master: Optional[tk.Misc] = None, initial: Optional[Region] = None
) -> Optional[Region]:
    """ドラッグで範囲を選ばせる。中止されたら None。

    ``master`` を渡すと既存の Tk アプリの中で動く。渡さない場合は
    このモジュールが一時的に Tk を起こす（CLI 用）。
    """
    winput.enable_dpi_awareness()

    owns_root = master is None
    root = tk.Tk() if owns_root else master
    if owns_root:
        root.withdraw()

    overlay = _RegionOverlay(root, initial)
    if owns_root:
        root.wait_window(overlay.window)
        root.destroy()
    else:
        master.wait_window(overlay.window)
    return overlay.result
