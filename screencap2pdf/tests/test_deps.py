import sys

from s2pdf import deps


def _fake(module="_s2pdf_missing_module_", required=True):
    return deps.Dependency(module, "fakepkg", "テスト用", required)


def test_installed_detects_present_and_absent_modules():
    assert deps.Dependency("json", "json", "標準ライブラリ", True).installed
    assert not _fake().installed


def test_missing_lists_only_required_by_default(monkeypatch):
    monkeypatch.setattr(
        deps, "DEPENDENCIES", (_fake("_missing_a_"), _fake("_missing_b_", required=False))
    )
    assert [d.module for d in deps.missing()] == ["_missing_a_"]
    assert len(deps.missing(required_only=False)) == 2


def test_install_command_names_the_running_interpreter():
    command = deps.install_command([_fake()])
    assert sys.executable in command
    assert "-m pip install fakepkg" in command


def test_missing_message_includes_package_and_command():
    message = deps.missing_message([_fake()])
    assert "fakepkg" in message
    assert sys.executable in message


def test_report_lists_every_dependency():
    text = deps.report()
    for dependency in deps.DEPENDENCIES:
        assert dependency.package in text
    assert sys.executable in text


def test_report_says_ok_when_nothing_is_missing(monkeypatch):
    monkeypatch.setattr(deps, "DEPENDENCIES", (deps.Dependency("json", "json", "標準", True),))
    assert "そろっています" in deps.report()


def test_report_shows_install_command_when_missing(monkeypatch):
    monkeypatch.setattr(deps, "DEPENDENCIES", (_fake(),))
    text = deps.report()
    assert "そろっています" not in text
    assert "-m pip install fakepkg" in text
