"""GUI の通し確認。画面キャプチャとキー送出は差し替えて動かす。

tkinter が無い環境、画面が無い環境では自動的にスキップされる。
"""

import time

import pytest
from PIL import Image

tk = pytest.importorskip("tkinter")

from s2pdf import engine  # noqa: E402
from s2pdf.config import Region  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("S2PDF_HOME", str(tmp_path / "config"))
    try:
        root_check = tk.Tk()
    except tk.TclError as exc:  # 画面が無い環境
        pytest.skip(f"画面が使えないためスキップ: {exc}")
    root_check.destroy()

    from s2pdf.gui import App

    application = App()
    application.withdraw()
    try:
        yield application
    finally:
        application.destroy()


class FakeScreen:
    def __init__(self, pages):
        self.pages = pages
        self.index = 0

    def grab(self, _region):
        return self.pages[min(self.index, len(self.pages) - 1)]

    def send_key(self, _name, hold=0.02):
        self.index += 1


def _pump(app, seconds=10.0):
    """ワーカーが終わるまで Tk のイベントループを回す。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        if app._worker is not None and not app._worker.is_alive():
            app.update()  # 完了メッセージを処理させる
            app.update()
            return True
        time.sleep(0.02)
    return False


def test_gui_run_captures_and_builds_pdf(app, tmp_path, monkeypatch):
    pages = [Image.new("RGB", (80, 100), (s, s, s)) for s in (20, 90, 160)]
    fake = FakeScreen(pages)
    monkeypatch.setattr(engine, "_grab_region", fake.grab)
    monkeypatch.setattr(engine.winput, "send_key", fake.send_key)
    monkeypatch.setattr(engine.winput, "is_escape_pressed", lambda: False)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)

    out_dir = tmp_path / "capture"
    pdf_path = tmp_path / "book.pdf"

    app._region = Region(0, 0, 80, 100)
    app.var_region.set(str(app._region))
    app.var_pages.set("3")
    app.var_start_delay.set("0")
    app.var_settle_delay.set("0")
    app.var_outdir.set(str(out_dir))
    app.var_pdf.set(str(pdf_path))
    app.var_autopdf.set(True)

    app.on_start()
    assert _pump(app), "ワーカーが終わりませんでした"

    assert sorted(p.name for p in out_dir.glob("*.png")) == [
        "page_0001.png",
        "page_0002.png",
        "page_0003.png",
    ]
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert str(app.btn_start["state"]) == "normal"
    assert str(app.btn_stop["state"]) == "disabled"


def test_gui_reports_missing_region(app, monkeypatch):
    errors = []
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: errors.append(a))
    app._region = None
    app.on_start()
    assert errors, "範囲未設定のときはエラーを出すはず"


def test_gui_form_round_trip(app, tmp_path):
    from s2pdf.config import Profile

    profile = Profile(
        name="default",
        region=Region(10, 20, 300, 400),
        key="pagedown",
        pages=7,
        output_dir=str(tmp_path / "img"),
        trim=True,
        grayscale=True,
        max_width=900,
    )
    app._load_profile_into_form(profile)
    rebuilt = app._build_profile()

    assert rebuilt.region.as_tuple() == (10, 20, 300, 400)
    assert rebuilt.key == "pagedown"
    assert rebuilt.pages == 7
    assert rebuilt.trim is True
    assert rebuilt.grayscale is True
    assert rebuilt.max_width == 900


def test_gui_rejects_non_numeric_input(app, monkeypatch):
    app._region = Region(0, 0, 10, 10)
    app.var_maxwidth.set("ひろめ")
    with pytest.raises(ValueError, match="横幅"):
        app._build_profile()
