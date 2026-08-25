"""キー名の正規化と、ウィンドウ一覧の絞り込み条件。"""

import pytest

from s2pdf import winput


def _listable(**overrides):
    """一覧に出る条件を満たす引数一式。個別に上書きして使う。"""
    kwargs = {
        "visible": True,
        "tool_window": False,
        "cloaked": False,
        "own_process": False,
        "width": 800,
        "height": 600,
    }
    kwargs.update(overrides)
    return kwargs


def test_ordinary_window_is_listed():
    assert winput.should_list_window("メモ帳", **_listable())


@pytest.mark.parametrize(
    "overrides",
    [
        {"visible": False},  # 見えていない
        {"tool_window": True},  # ツールウィンドウ
        {"cloaked": True},  # DWM に隠されている
        {"own_process": True},  # 自分自身
        {"width": 20},  # 小さすぎる
        {"height": 20},
    ],
)
def test_uninteresting_windows_are_skipped(overrides):
    assert not winput.should_list_window("メモ帳", **_listable(**overrides))


@pytest.mark.parametrize("title", ["", "   ", "Program Manager", "Default IME"])
def test_system_windows_are_skipped(title):
    assert not winput.should_list_window(title, **_listable())


def test_normalize_key_accepts_arrows_and_aliases():
    assert winput.normalize_key("→") == "right"
    assert winput.normalize_key("PgDn") == "pagedown"
    assert winput.normalize_key(" RIGHT ") == "right"
    assert winput.normalize_key("return") == "enter"


def test_normalize_key_rejects_unknown():
    with pytest.raises(ValueError):
        winput.normalize_key("ページ送り")


def test_key_names_include_the_common_ones():
    names = winput.key_names()
    for key in ("right", "left", "pagedown", "space", "enter"):
        assert key in names


def test_windows_only_functions_refuse_elsewhere():
    if winput.IS_WINDOWS:  # pragma: no cover - Windows では別の経路
        pytest.skip("Windows では実際に動く")
    with pytest.raises(RuntimeError, match="Windows"):
        winput.list_windows()
    with pytest.raises(RuntimeError, match="Windows"):
        winput.send_key("right")


def test_escape_check_is_safe_on_other_platforms():
    if winput.IS_WINDOWS:  # pragma: no cover
        pytest.skip("Windows では実際に動く")
    assert winput.is_escape_pressed() is False
