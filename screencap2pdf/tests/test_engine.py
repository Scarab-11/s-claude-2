"""キャプチャループの検証。画面キャプチャとキー送出は差し替えて動かす。"""

import pytest
from PIL import Image

from s2pdf import engine
from s2pdf.config import Profile, Region


class FakeScreen:
    """ページ送りのたびに次の画像を返す、画面の代わり。"""

    def __init__(self, pages):
        self.pages = list(pages)
        self.index = 0
        self.keys_sent = []

    def grab(self, _region):
        return self.pages[min(self.index, len(self.pages) - 1)]

    def send_key(self, name, hold=0.02):
        self.keys_sent.append(name)
        self.index += 1


def make_page(shade, size=(60, 80)):
    return Image.new("RGB", size, (shade, shade, shade))


@pytest.fixture
def profile(tmp_path):
    return Profile(
        region=Region(0, 0, 60, 80),
        output_dir=str(tmp_path / "capture"),
        start_delay=0,
        settle_delay=0,
        after_shot_delay=0,
    )


@pytest.fixture
def screen(monkeypatch):
    def _install(pages):
        fake = FakeScreen(pages)
        monkeypatch.setattr(engine, "_grab_region", fake.grab)
        monkeypatch.setattr(engine.winput, "send_key", fake.send_key)
        monkeypatch.setattr(engine.winput, "is_escape_pressed", lambda: False)
        return fake

    return _install


def test_captures_requested_number_of_pages(profile, screen):
    fake = screen([make_page(s) for s in (10, 60, 110, 160, 210)])
    profile.pages = 4
    profile.stop_on_duplicate = False

    report = engine.Capturer(profile).run()

    assert report.page_count == 4
    assert fake.keys_sent == ["right", "right", "right"]  # 最終ページの後は送らない
    names = sorted(p.name for p in report.saved)
    assert names == ["page_0001.png", "page_0002.png", "page_0003.png", "page_0004.png"]
    assert all(p.exists() for p in report.saved)


def test_stops_when_screen_stops_changing(profile, screen):
    # 3 ページ分だけ中身があり、そのあとは同じ画面が続く
    pages = [make_page(10), make_page(90), make_page(170)] + [make_page(170)] * 10
    screen(pages)
    profile.pages = 0
    profile.duplicate_limit = 3

    report = engine.Capturer(profile).run()

    assert report.page_count == 3
    assert len(report.removed) == 3
    assert "終端" in report.reason
    assert not any(p.exists() for p in report.removed)


def test_page_limit_wins_over_auto_stop(profile, screen):
    screen([make_page(10)] * 10)
    profile.pages = 2

    report = engine.Capturer(profile).run()

    assert report.page_count == 2
    assert "2 ページ" in report.reason


def test_resume_skips_existing_images(profile, screen):
    screen([make_page(s) for s in (10, 60, 110, 160)])
    profile.pages = 2
    profile.stop_on_duplicate = False
    for index in (1, 2, 3):
        path = profile.image_path(index)
        path.parent.mkdir(parents=True, exist_ok=True)
        make_page(0).save(path)

    report = engine.Capturer(profile).run(resume=True)

    assert [p.name for p in report.saved] == ["page_0004.png", "page_0005.png"]


def test_start_index_is_respected(profile, screen):
    screen([make_page(s) for s in (10, 60)])
    profile.pages = 2
    profile.stop_on_duplicate = False

    report = engine.Capturer(profile).run(start_index=11)

    assert [p.name for p in report.saved] == ["page_0011.png", "page_0012.png"]


def test_should_stop_aborts_the_loop(profile, screen):
    screen([make_page(s) for s in range(10, 200, 20)])
    profile.pages = 100
    profile.stop_on_duplicate = False
    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 3

    report = engine.Capturer(profile, should_stop=should_stop).run()

    assert 0 < report.page_count < 100
    assert "中止" in report.reason


def test_escape_key_aborts_the_loop(profile, monkeypatch):
    fake = FakeScreen([make_page(s) for s in range(10, 200, 20)])
    monkeypatch.setattr(engine, "_grab_region", fake.grab)
    monkeypatch.setattr(engine.winput, "send_key", fake.send_key)
    pressed = {"n": 0}

    def escape():
        pressed["n"] += 1
        return pressed["n"] > 2

    monkeypatch.setattr(engine.winput, "is_escape_pressed", escape)
    profile.pages = 100
    profile.stop_on_duplicate = False

    report = engine.Capturer(profile).run()

    assert "Esc" in report.reason


def test_image_options_are_applied_to_saved_pages(profile, screen):
    page = Image.new("RGB", (200, 200), (255, 255, 255))
    page.paste(Image.new("RGB", (100, 100), (0, 0, 0)), (50, 50))
    screen([page])
    profile.pages = 1
    profile.stop_on_duplicate = False
    profile.trim = True
    profile.grayscale = True

    report = engine.Capturer(profile).run()

    with Image.open(report.saved[0]) as saved:
        assert saved.size == (100, 100)
        assert saved.mode == "L"


def test_jpg_format_is_saved_as_jpeg(profile, screen):
    screen([make_page(10)])
    profile.pages = 1
    profile.image_format = "jpg"
    profile.stop_on_duplicate = False

    report = engine.Capturer(profile).run()

    assert report.saved[0].suffix == ".jpg"
    with Image.open(report.saved[0]) as saved:
        assert saved.format == "JPEG"


def test_capturer_rejects_invalid_profile(tmp_path):
    with pytest.raises(ValueError):
        engine.Capturer(Profile(output_dir=str(tmp_path)))


def test_missing_window_is_reported(profile, screen, monkeypatch):
    screen([make_page(10)])
    profile.window_title = "存在しないウィンドウ"
    monkeypatch.setattr(engine.winput, "find_window", lambda _t: None)

    with pytest.raises(engine.CaptureError, match="ウィンドウが見つかりません"):
        engine.Capturer(profile).run()


def test_save_preview_writes_one_image(profile, screen, tmp_path):
    screen([make_page(10)])
    path = engine.Capturer(profile).save_preview(tmp_path / "preview.png")
    assert path.exists()
