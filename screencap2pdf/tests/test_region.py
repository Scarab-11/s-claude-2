"""範囲選択オーバーレイの座標計算。tkinter / 画面が無い環境ではスキップ。"""

from types import SimpleNamespace

import pytest

tk = pytest.importorskip("tkinter")

from s2pdf import region as region_module  # noqa: E402
from s2pdf.config import Region  # noqa: E402


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"画面が使えないためスキップ: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def _drag(overlay, x0, y0, x1, y1):
    overlay._on_press(SimpleNamespace(x=x0, y=y0))
    overlay._on_drag(SimpleNamespace(x=(x0 + x1) // 2, y=(y0 + y1) // 2))
    overlay._on_release(SimpleNamespace(x=x1, y=y1))


def test_drag_produces_region(root, monkeypatch):
    monkeypatch.setattr(region_module, "_virtual_screen", lambda _m: (0, 0, 1920, 1080))
    overlay = region_module._RegionOverlay(root)
    _drag(overlay, 100, 200, 400, 600)
    assert overlay.result == Region(100, 200, 300, 400)


def test_drag_in_any_direction_normalizes(root, monkeypatch):
    monkeypatch.setattr(region_module, "_virtual_screen", lambda _m: (0, 0, 1920, 1080))
    overlay = region_module._RegionOverlay(root)
    _drag(overlay, 400, 600, 100, 200)  # 右下から左上へ引く
    assert overlay.result == Region(100, 200, 300, 400)


def test_multi_monitor_offset_is_applied(root, monkeypatch):
    # 左側にサブモニタがある構成（仮想デスクトップの原点が負）
    monkeypatch.setattr(region_module, "_virtual_screen", lambda _m: (-1920, -100, 3840, 1180))
    overlay = region_module._RegionOverlay(root)
    _drag(overlay, 100, 100, 300, 400)
    assert overlay.result == Region(-1820, 0, 200, 300)


def test_tiny_drag_is_ignored(root, monkeypatch):
    monkeypatch.setattr(region_module, "_virtual_screen", lambda _m: (0, 0, 1920, 1080))
    overlay = region_module._RegionOverlay(root)
    _drag(overlay, 100, 100, 103, 102)
    assert overlay.result is None
    assert overlay.window.winfo_exists()  # やり直せるように閉じない


def test_escape_cancels(root, monkeypatch):
    monkeypatch.setattr(region_module, "_virtual_screen", lambda _m: (0, 0, 1920, 1080))
    overlay = region_module._RegionOverlay(root)
    overlay._finish(None)
    assert overlay.result is None
