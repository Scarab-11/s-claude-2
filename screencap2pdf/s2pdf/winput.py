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
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    ULONG_PTR = ctypes.c_size_t

    INPUT_KEYBOARD = 1
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002

    SW_RESTORE = 9

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    MAPVK_VK_TO_VSC = 0

    PW_RENDERFULLCONTENT = 0x0002
    BI_RGB = 0
    DIB_RGB_COLORS = 0

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

    def focused_control(hwnd: int) -> int:
        """対象ウィンドウの中で実際に入力を受け取っている子ウィンドウ。

        アプリによっては親ウィンドウではなく中の子ウィンドウがキーを処理するため、
        メッセージの送り先としてはこちらの方が当たりやすい。
        """
        cur_thread = kernel32.GetCurrentThreadId()
        tgt_thread = user32.GetWindowThreadProcessId(hwnd, None)
        if cur_thread == tgt_thread:
            return int(user32.GetFocus() or hwnd)
        if not user32.AttachThreadInput(cur_thread, tgt_thread, True):
            return hwnd
        try:
            focus = user32.GetFocus()
        finally:
            user32.AttachThreadInput(cur_thread, tgt_thread, False)
        return int(focus or hwnd)

    def post_key(hwnd: int, name: str) -> None:
        """前面に出さずにキーを送る（裏で動かすとき用）。

        SendInput と違って前面のウィンドウを奪わないので、他の作業と並行できる。
        ただしメッセージを直接受け取らない作りのアプリには効かない。
        """
        key = normalize_key(name)
        vk = VK_CODES[key]
        extended = 1 if key in _EXTENDED_KEYS else 0
        scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)

        target = focused_control(hwnd)
        down = 1 | (scan << 16) | (extended << 24)
        up = down | (1 << 30) | (1 << 31)
        user32.PostMessageW(target, WM_KEYDOWN, vk, down)
        user32.PostMessageW(target, WM_KEYUP, vk, up)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
    user32.PrintWindow.restype = wintypes.BOOL

    def capture_window_image(hwnd: int):
        """ウィンドウの中身を、他のウィンドウに隠れていても取り込む。

        画面をそのまま撮るのではなく、ウィンドウ自身に描画させる（PrintWindow）ので、
        裏に回っていても撮れる。ただし描画方法によっては真っ黒な画像が返る。
        """
        from PIL import Image  # winput 単体では PIL に依存させない

        _left, _top, width, height = get_window_rect(hwnd)
        if width <= 0 or height <= 0:
            raise OSError("ウィンドウの大きさを取得できませんでした。")

        window_dc = user32.GetWindowDC(hwnd)
        if not window_dc:
            raise OSError("ウィンドウのデバイスコンテキストを取得できませんでした。")
        mem_dc = gdi32.CreateCompatibleDC(window_dc)
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        try:
            if not user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT):
                # 古いアプリ向けのフォールバック
                user32.PrintWindow(hwnd, mem_dc, 0)

            info = BITMAPINFO()
            info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height  # 上下反転させずに取り出す
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = BI_RGB

            buffer = ctypes.create_string_buffer(width * height * 4)
            copied = gdi32.GetDIBits(
                mem_dc, bitmap, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS
            )
            if not copied:
                raise OSError("ウィンドウの画像を取り出せませんでした。")
            return Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1)
        finally:
            gdi32.SelectObject(mem_dc, old_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, window_dc)

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

    def focused_control(hwnd: int) -> int:
        _require_windows()
        raise AssertionError

    def post_key(hwnd: int, name: str) -> None:
        normalize_key(name)
        _require_windows()

    def capture_window_image(hwnd: int):
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
