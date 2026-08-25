"""Windows 依存の処理（DPI 設定・キー送出・ウィンドウ操作）。

Windows 以外でも import はできる（テスト用）。実際に呼ぶと RuntimeError になる。
"""

from __future__ import annotations

import sys
import time
from typing import Iterator, NamedTuple, Optional

IS_WINDOWS = sys.platform.startswith("win")

# 送出できるキーの名前 -> 仮想キーコード
VK_CODES = {
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "pageup": 0x21,
    "pagedown": 0x22,
    "home": 0x24,
    "end": 0x23,
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "backspace": 0x08,
    "escape": 0x1B,
}
# 単独のアルファベット・数字もそのまま使えるようにしておく
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    VK_CODES.setdefault(_c.lower(), ord(_c))

# テンキーではない矢印・PageUp/Down などは拡張キー扱いにする必要がある
_EXTENDED_KEYS = {"left", "up", "right", "down", "pageup", "pagedown", "home", "end"}

VK_ESCAPE = 0x1B


class WindowInfo(NamedTuple):
    hwnd: int
    title: str


def key_names() -> list[str]:
    """送出できるキー名の一覧（説明表示用）。"""
    return sorted(VK_CODES)


def normalize_key(name: str) -> str:
    """キー名を正規化する。未知のキーなら ValueError。"""
    key = name.strip().lower()
    aliases = {
        "→": "right",
        "←": "left",
        "↑": "up",
        "↓": "down",
        "pgdn": "pagedown",
        "pgup": "pageup",
        "return": "enter",
        "esc": "escape",
    }
    key = aliases.get(key, key)
    if key not in VK_CODES:
        raise ValueError(f"未知のキー名です: {name}")
    return key


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise RuntimeError("この機能は Windows でのみ使えます。")


if IS_WINDOWS:  # pragma: no cover - Windows 実機でのみ通る
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    ULONG_PTR = ctypes.c_size_t

    INPUT_KEYBOARD = 1
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002

    SW_RESTORE = 9

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT

    def enable_dpi_awareness() -> None:
        """DPI スケーリング環境でも実ピクセル座標で扱えるようにする。

        これを呼ばないと、拡大率 150% の環境で Tkinter の座標と
        実際の画面ピクセルがずれ、キャプチャ範囲が想定とずれる。
        """
        try:
            # PER_MONITOR_AWARE_V2
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    def _make_key_input(vk: int, key_up: bool, extended: bool) -> INPUT:
        flags = 0
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        if key_up:
            flags |= KEYEVENTF_KEYUP
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
        return inp

    def send_key(name: str, hold: float = 0.02) -> None:
        """キーを 1 回押して離す。"""
        key = normalize_key(name)
        vk = VK_CODES[key]
        extended = key in _EXTENDED_KEYS
        down = _make_key_input(vk, key_up=False, extended=extended)
        up = _make_key_input(vk, key_up=True, extended=extended)
        if user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT)) != 1:
            raise OSError(ctypes.get_last_error(), "SendInput に失敗しました")
        time.sleep(max(0.0, hold))
        if user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT)) != 1:
            raise OSError(ctypes.get_last_error(), "SendInput に失敗しました")

    def get_foreground_window() -> int:
        return int(user32.GetForegroundWindow())

    def get_window_title(hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
        """(left, top, width, height) を返す。"""
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise OSError(ctypes.get_last_error(), "GetWindowRect に失敗しました")
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def list_windows() -> list[WindowInfo]:
        """タイトルを持つ可視ウィンドウの一覧。"""
        results: list[WindowInfo] = []
        proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                title = get_window_title(hwnd)
                if title:
                    results.append(WindowInfo(int(hwnd), title))
            return True

        user32.EnumWindows(proto(_cb), 0)
        return results

    def find_window(substring: str) -> Optional[WindowInfo]:
        """タイトルに部分一致するウィンドウを 1 つ返す。"""
        needle = substring.lower()
        for info in list_windows():
            if needle in info.title.lower():
                return info
        return None

    def focus_window(hwnd: int) -> bool:
        """指定ウィンドウを前面に出す。成功したかどうかを返す。

        Windows はフォアグラウンドの横取りを制限しているため、
        対象スレッドに入力状態を一時的にくっつけてから前面化する。
        """
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        if get_foreground_window() == hwnd:
            return True
        cur_thread = kernel32.GetCurrentThreadId()
        tgt_thread = user32.GetWindowThreadProcessId(hwnd, None)
        attached = bool(user32.AttachThreadInput(cur_thread, tgt_thread, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(cur_thread, tgt_thread, False)
        return get_foreground_window() == hwnd

    def is_escape_pressed() -> bool:
        """他のウィンドウが前面でも Esc の押下を拾えるようにする（緊急停止用）。"""
        return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)

    def virtual_screen_rect() -> tuple[int, int, int, int]:
        """マルチモニタ全体を覆う矩形 (left, top, width, height)。"""
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
        return (
            user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
        )

else:  # Windows 以外では呼べないスタブ

    def enable_dpi_awareness() -> None:
        return None

    def send_key(name: str, hold: float = 0.02) -> None:
        normalize_key(name)
        _require_windows()

    def get_foreground_window() -> int:
        _require_windows()
        raise AssertionError

    def get_window_title(hwnd: int) -> str:
        _require_windows()
        raise AssertionError

    def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
        _require_windows()
        raise AssertionError

    def list_windows() -> list[WindowInfo]:
        _require_windows()
        raise AssertionError

    def find_window(substring: str) -> Optional[WindowInfo]:
        _require_windows()
        raise AssertionError

    def focus_window(hwnd: int) -> bool:
        _require_windows()
        raise AssertionError

    def is_escape_pressed() -> bool:
        return False

    def virtual_screen_rect() -> tuple[int, int, int, int]:
        _require_windows()
        raise AssertionError


def countdown(seconds: float, on_tick=None) -> Iterator[int]:
    """1 秒ずつカウントダウンする。on_tick には残り秒数が渡る。"""
    remaining = int(seconds)
    while remaining > 0:
        if on_tick:
            on_tick(remaining)
        yield remaining
        time.sleep(1.0)
        remaining -= 1
