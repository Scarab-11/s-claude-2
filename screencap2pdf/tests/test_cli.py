import pytest
from PIL import Image

from s2pdf import cli
from s2pdf.config import Profile, ProfileStore, Region


@pytest.fixture(autouse=True)
def isolated_profiles(tmp_path, monkeypatch):
    """テスト中は利用者の設定ファイルを触らない。"""
    monkeypatch.setenv("S2PDF_HOME", str(tmp_path / "config"))


def test_build_command_creates_pdf(tmp_path, capsys):
    directory = tmp_path / "capture"
    directory.mkdir()
    for i in range(1, 4):
        Image.new("RGB", (60, 80), (i * 60, i * 60, i * 60)).save(directory / f"page_{i}.png")
    output = tmp_path / "book.pdf"

    assert cli.main(["build", str(directory), "-o", str(output)]) == 0
    assert output.exists()
    assert "3 ページ" in capsys.readouterr().out


def test_build_command_without_images_fails(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.main(["build", str(empty), "-o", str(tmp_path / "x.pdf")]) == 1
    assert "画像が見つかりません" in capsys.readouterr().out


def test_profiles_command_lists_saved_entries(tmp_path, capsys):
    store = ProfileStore()
    store.save(Profile(name="book", region=Region(0, 0, 800, 1000), key="right"))

    assert cli.main(["profiles"]) == 0
    out = capsys.readouterr().out
    assert "book" in out
    assert "800x1000" in out


def test_profiles_delete(capsys):
    ProfileStore().save(Profile(name="tmp"))
    assert cli.main(["profiles", "--delete", "tmp"]) == 0
    assert cli.main(["profiles", "--delete", "tmp"]) == 1


def test_region_override_is_parsed():
    args = cli.build_parser().parse_args(["run", "--region", "1,2,3,4", "--key", "pagedown"])
    profile = cli._apply_overrides(Profile(), args)
    assert profile.region.as_tuple() == (1, 2, 3, 4)
    assert profile.key == "pagedown"


def test_key_aliases_are_normalized():
    args = cli.build_parser().parse_args(["run", "--key", "→"])
    assert cli._apply_overrides(Profile(region=Region(0, 0, 1, 1)), args).key == "right"


def test_overrides_leave_unspecified_fields_alone():
    original = Profile(region=Region(9, 9, 9, 9), pages=50, output_dir="keep", trim=True)
    args = cli.build_parser().parse_args(["run", "--pages", "10"])
    updated = cli._apply_overrides(original, args)
    assert updated.pages == 10
    assert updated.output_dir == "keep"
    assert updated.trim is True
    assert updated.region.as_tuple() == (9, 9, 9, 9)


def test_window_capture_flag_switches_mode():
    args = cli.build_parser().parse_args(["run", "--window-capture", "--window", "アプリ"])
    profile = cli._apply_overrides(Profile(), args)
    assert profile.uses_window_capture
    assert profile.window_title == "アプリ"


def test_screen_capture_flag_switches_back():
    args = cli.build_parser().parse_args(["run", "--screen-capture"])
    profile = cli._apply_overrides(Profile(capture_mode="window"), args)
    assert not profile.uses_window_capture


def test_capture_mode_is_left_alone_when_not_given():
    args = cli.build_parser().parse_args(["run", "--pages", "3"])
    profile = cli._apply_overrides(Profile(capture_mode="window", window_title="アプリ"), args)
    assert profile.uses_window_capture


def test_window_capture_without_window_reports_error(capsys):
    assert cli.main(["run", "--window-capture"]) == 1
    assert "対象ウィンドウ" in capsys.readouterr().err


def test_no_trim_flag_turns_trim_off():
    args = cli.build_parser().parse_args(["run", "--no-trim"])
    updated = cli._apply_overrides(Profile(region=Region(0, 0, 1, 1), trim=True), args)
    assert updated.trim is False


def test_invalid_region_reports_error(capsys):
    assert cli.main(["run", "--region", "1,2,3"]) == 1
    assert "エラー" in capsys.readouterr().err


def test_run_without_region_reports_error(capsys):
    assert cli.main(["run"]) == 1
    assert "キャプチャ範囲" in capsys.readouterr().err


def test_doctor_reports_environment(capsys):
    from s2pdf import deps

    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "Python:" in out
    assert "Pillow" in out
    assert code == (1 if deps.missing() else 0)


def test_parser_requires_a_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])
