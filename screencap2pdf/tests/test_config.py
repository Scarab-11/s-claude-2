import pytest

from s2pdf.config import (
    Profile,
    ProfileStore,
    Region,
    next_available_dir,
    next_available_path,
)


def test_next_available_dir_uses_the_name_when_free(tmp_path):
    assert next_available_dir(tmp_path / "capture") == tmp_path / "capture"


def test_next_available_dir_reuses_an_empty_folder(tmp_path):
    (tmp_path / "capture").mkdir()
    assert next_available_dir(tmp_path / "capture") == tmp_path / "capture"


def test_next_available_dir_counts_up_past_used_folders(tmp_path):
    for name in ("capture", "capture_2"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "page_0001.png").write_bytes(b"x")
    assert next_available_dir(tmp_path / "capture") == tmp_path / "capture_3"


def test_next_available_path_counts_up(tmp_path):
    assert next_available_path(tmp_path / "book.pdf") == tmp_path / "book.pdf"
    (tmp_path / "book.pdf").write_bytes(b"x")
    assert next_available_path(tmp_path / "book.pdf") == tmp_path / "book_2.pdf"
    (tmp_path / "book_2.pdf").write_bytes(b"x")
    assert next_available_path(tmp_path / "book.pdf") == tmp_path / "book_3.pdf"


def test_region_parse_accepts_commas_and_spaces():
    assert Region.parse("10,20,300,400").as_tuple() == (10, 20, 300, 400)
    assert Region.parse("10 20 300 400").as_tuple() == (10, 20, 300, 400)


@pytest.mark.parametrize("text", ["1,2,3", "1,2,3,4,5", "10,20,0,400"])
def test_region_parse_rejects_bad_input(text):
    with pytest.raises(ValueError):
        Region.parse(text)


def test_region_as_bbox_for_mss():
    assert Region(1, 2, 3, 4).as_bbox() == {"left": 1, "top": 2, "width": 3, "height": 4}


def test_region_relative_to_shifts_the_origin():
    assert Region(150, 90, 200, 300).relative_to(100, 50).as_tuple() == (50, 40, 200, 300)


def test_crop_box_stays_inside_the_image():
    assert Region(10, 20, 30, 40).crop_box(200, 200) == (10, 20, 40, 60)
    assert Region(180, 180, 100, 100).crop_box(200, 200) == (180, 180, 200, 200)
    assert Region(-20, -20, 50, 50).crop_box(200, 200) == (0, 0, 30, 30)
    assert Region(500, 500, 10, 10).crop_box(200, 200) == (200, 200, 200, 200)


def test_uses_window_capture_flag():
    assert Profile(capture_mode="window").uses_window_capture
    assert not Profile().uses_window_capture


def test_validate_rejects_unknown_capture_mode():
    with pytest.raises(ValueError, match="キャプチャ方式"):
        Profile(capture_mode="なんとか", region=Region(0, 0, 10, 10)).validate()


def test_region_intersects():
    base = Region(100, 100, 200, 200)
    assert base.intersects(Region(250, 250, 100, 100))
    assert not base.intersects(Region(300, 100, 50, 50))  # 右隣で接している
    assert not base.intersects(Region(0, 0, 50, 50))


def test_region_from_any_accepts_dict_list_and_region():
    assert Region.from_any({"left": 1, "top": 2, "width": 3, "height": 4}).as_tuple() == (1, 2, 3, 4)
    assert Region.from_any([1, 2, 3, 4]).as_tuple() == (1, 2, 3, 4)
    region = Region(1, 2, 3, 4)
    assert Region.from_any(region) is region


def test_profile_image_path_is_zero_padded(tmp_path):
    profile = Profile(output_dir=str(tmp_path), prefix="p", image_format="png")
    assert profile.image_path(7).name == "p_0007.png"


def test_profile_validate_requires_region():
    with pytest.raises(ValueError, match="キャプチャ範囲"):
        Profile().validate()


def test_profile_validate_rejects_unknown_key():
    profile = Profile(region=Region(0, 0, 10, 10), key="ページ送り")
    with pytest.raises(ValueError):
        profile.validate()


def test_profile_validate_rejects_bad_format():
    profile = Profile(region=Region(0, 0, 10, 10), image_format="gif")
    with pytest.raises(ValueError):
        profile.validate()


def test_profile_round_trip_through_dict():
    original = Profile(
        name="book",
        region=Region(5, 6, 700, 900),
        key="pagedown",
        pages=42,
        trim=True,
        max_width=1200,
    )
    restored = Profile.from_dict(original.to_dict())
    assert restored == original


def test_profile_from_dict_ignores_unknown_keys():
    profile = Profile.from_dict({"name": "x", "region": None, "未知の項目": 1})
    assert profile.name == "x"


def test_store_saves_and_loads(tmp_path):
    store = ProfileStore(path=tmp_path / "profiles.json")
    store.save(Profile(name="a", region=Region(1, 2, 3, 4), pages=10))
    store.save(Profile(name="b", region=Region(5, 6, 7, 8)))

    loaded = store.load("a")
    assert loaded is not None
    assert loaded.pages == 10
    assert loaded.region.as_tuple() == (1, 2, 3, 4)
    assert set(store.load_all()) == {"a", "b"}


def test_store_delete(tmp_path):
    store = ProfileStore(path=tmp_path / "profiles.json")
    store.save(Profile(name="a"))
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert store.load("a") is None


def test_store_survives_broken_file(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{ broken", encoding="utf-8")
    assert ProfileStore(path=path).load_all() == {}


def test_image_options_description():
    profile = Profile(trim=True, grayscale=True, max_width=800)
    text = profile.image_options().describe()
    assert "余白除去" in text and "グレースケール" in text and "800" in text
