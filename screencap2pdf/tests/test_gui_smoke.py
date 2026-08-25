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

    # 起動時のライブラリ不足の警告はモーダルなので、テストでは出さない
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **k: None)

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
    """ワーカーが終わり、完了処理まで済むまで Tk のイベントループを回す。

    完了メッセージはキュー経由で受け取るので、スレッドの終了だけでは足りない。
    ボタンが戻ったことをもって完了とみなす。
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        finished = app._worker is not None and not app._worker.is_alive()
        if finished and str(app.btn_start["state"]) == "normal":
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


def _fill_capture_folder(directory, count=3):
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        Image.new("RGB", (20, 20), (i * 40, 0, 0)).save(directory / f"page_{i:04d}.png")
    return directory


def _prepare_second_run(app, tmp_path, choice):
    """1 回目の画像がある状態で 2 回目を始めようとしたときの流れ。"""
    directory = _fill_capture_folder(tmp_path / "capture")
    app._region = Region(0, 0, 80, 100)
    app.var_outdir.set(str(directory))
    app.var_pdf.set(str(tmp_path / "book.pdf"))
    app.var_resume.set(False)
    app._ask_about_existing = lambda *_a, **_k: choice
    return directory, app._resolve_output_collision(app._build_profile())


def test_second_run_can_go_to_a_new_folder(app, tmp_path):
    directory, profile = _prepare_second_run(app, tmp_path, "new")

    assert profile is not None
    assert profile.output_dir == str(tmp_path / "capture_2")
    assert len(list(directory.glob("*.png"))) == 3  # 1 回目はそのまま残る
    assert app.var_pdf.get() == str(tmp_path / "book.pdf")  # まだ PDF が無いので変えない


def test_second_run_renames_the_pdf_when_it_exists(app, tmp_path):
    (tmp_path / "book.pdf").write_bytes(b"%PDF-old")
    _directory, profile = _prepare_second_run(app, tmp_path, "new")

    assert profile is not None
    assert app.var_pdf.get() == str(tmp_path / "book_2.pdf")


def test_second_run_can_clear_the_folder(app, tmp_path):
    directory, profile = _prepare_second_run(app, tmp_path, "clear")

    assert profile is not None
    assert profile.output_dir == str(directory)
    assert list(directory.glob("*.png")) == []


def test_second_run_can_append(app, tmp_path):
    directory, profile = _prepare_second_run(app, tmp_path, "append")

    assert profile is not None
    assert profile.output_dir == str(directory)
    assert len(list(directory.glob("*.png"))) == 3


def test_second_run_can_be_cancelled(app, tmp_path):
    _directory, profile = _prepare_second_run(app, tmp_path, None)

    assert profile is None


def test_resume_skips_the_collision_dialog(app, tmp_path):
    directory = _fill_capture_folder(tmp_path / "capture")
    app._region = Region(0, 0, 80, 100)
    app.var_outdir.set(str(directory))
    app.var_resume.set(True)
    app._ask_about_existing = lambda *_a, **_k: pytest.fail("確認は出さない")

    profile = app._resolve_output_collision(app._build_profile())

    assert profile is not None
    assert profile.output_dir == str(directory)


def test_window_list_is_loaded_without_pressing_refresh(app, monkeypatch):
    from s2pdf import winput

    monkeypatch.setattr(
        winput,
        "list_windows",
        lambda *a, **k: [winput.WindowInfo(1, "メモ帳"), winput.WindowInfo(2, "ブラウザ")],
    )
    app._load_window_list_at_startup()

    assert list(app.combo_window["values"]) == ["ブラウザ", "メモ帳"]  # 名前順


def test_window_list_failure_does_not_crash(app, monkeypatch):
    from s2pdf import winput

    def boom(*_a, **_k):
        raise RuntimeError("この機能は Windows でのみ使えます。")

    monkeypatch.setattr(winput, "list_windows", boom)

    assert app._reload_window_list() == []
    assert "取得できませんでした" in app.log.get("1.0", "end")


def test_changing_capture_mode_clears_the_region(app):
    app._region = Region(10, 20, 300, 400)
    app.var_region.set(str(app._region))
    app.var_window_capture.set(True)
    app._on_capture_mode_changed()

    assert app._region is None
    assert "選び直" in app.var_region.get()


def test_window_capture_mode_reaches_the_profile(app):
    app._region = Region(0, 0, 100, 100)
    app.var_window_capture.set(True)
    app.var_window.set("対象アプリ")

    profile = app._build_profile()

    assert profile.uses_window_capture
    assert profile.window_title == "対象アプリ"


def test_window_capture_mode_needs_a_window(app):
    app._region = Region(0, 0, 100, 100)
    app.var_window_capture.set(True)
    app.var_window.set("")

    with pytest.raises(ValueError, match="対象ウィンドウ"):
        app._build_profile()


def test_gui_rejects_non_numeric_input(app, monkeypatch):
    app._region = Region(0, 0, 10, 10)
    app.var_maxwidth.set("ひろめ")
    with pytest.raises(ValueError, match="横幅"):
        app._build_profile()
