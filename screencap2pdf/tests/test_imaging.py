from PIL import Image

from s2pdf import imaging


def _page_with_margin(margin: int = 20, size: int = 100) -> Image.Image:
    """白い余白の中に黒い四角がある画像。"""
    img = Image.new("RGB", (size, size), (255, 255, 255))
    inner = Image.new("RGB", (size - margin * 2, size - margin * 2), (0, 0, 0))
    img.paste(inner, (margin, margin))
    return img


def test_auto_trim_removes_uniform_margin():
    img = _page_with_margin(margin=20, size=100)
    trimmed = imaging.auto_trim(img)
    assert trimmed.size == (60, 60)


def test_auto_trim_keeps_padding():
    img = _page_with_margin(margin=20, size=100)
    trimmed = imaging.auto_trim(img, padding=5)
    assert trimmed.size == (70, 70)


def test_auto_trim_returns_original_when_blank():
    blank = Image.new("RGB", (50, 50), (240, 240, 240))
    assert imaging.auto_trim(blank).size == (50, 50)


def test_auto_trim_ignores_noise_below_tolerance():
    img = Image.new("RGB", (60, 60), (255, 255, 255))
    img.putpixel((3, 3), (250, 250, 250))  # 差 5 は許容差 10 以内
    assert imaging.auto_trim(img, tolerance=10).size == (60, 60)


def test_apply_options_resizes_and_grayscales():
    img = _page_with_margin(margin=10, size=200)
    options = imaging.ImageOptions(trim=True, grayscale=True, max_width=90)
    result = imaging.apply_options(img, options)
    assert result.width == 90
    assert result.height == 90  # 180x180 を 90 幅に縮小
    assert result.mode == "L"


def test_apply_options_drops_alpha():
    img = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
    result = imaging.apply_options(img, imaging.ImageOptions())
    assert result.mode == "RGB"


def test_fingerprint_detects_same_and_different_pages():
    page_a = _page_with_margin(margin=20)
    page_b = _page_with_margin(margin=20)
    page_c = _page_with_margin(margin=5)

    fp_a = imaging.fingerprint(page_a)
    fp_b = imaging.fingerprint(page_b)
    fp_c = imaging.fingerprint(page_c)

    assert imaging.looks_same(fp_a, fp_b)
    assert not imaging.looks_same(fp_a, fp_c)
    assert imaging.difference(fp_a, fp_b) == 0.0
    assert imaging.difference(fp_a, fp_c) > 0.0


def test_difference_of_mismatched_fingerprints():
    assert imaging.difference(b"", b"") == 1.0
    assert imaging.difference(b"abc", b"ab") == 1.0
