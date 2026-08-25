import re
from pathlib import Path

import pytest
from PIL import Image

from s2pdf import pdfbuild


def _write_pages(directory, count, size=(80, 100), suffix="png"):
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(1, count + 1):
        path = directory / f"page_{i:04d}.{suffix}"
        shade = min(255, 40 * i)
        Image.new("RGB", size, (shade, shade, shade)).save(path)
        paths.append(path)
    return paths


def test_natural_key_orders_numbers_numerically(tmp_path):
    for name in ("page_10.png", "page_2.png", "page_1.png"):
        Image.new("RGB", (4, 4)).save(tmp_path / name)
    names = [p.name for p in pdfbuild.collect_images(tmp_path)]
    assert names == ["page_1.png", "page_2.png", "page_10.png"]


def test_collect_images_skips_non_images(tmp_path):
    _write_pages(tmp_path, 2)
    (tmp_path / "memo.txt").write_text("not an image")
    assert len(pdfbuild.collect_images(tmp_path)) == 2


def test_collect_images_skips_working_files(tmp_path):
    _write_pages(tmp_path, 2)
    Image.new("RGB", (4, 4)).save(tmp_path / "_preview.png")
    assert [p.name for p in pdfbuild.collect_images(tmp_path)] == [
        "page_0001.png",
        "page_0002.png",
    ]


def test_collect_images_handles_missing_directory(tmp_path):
    assert pdfbuild.collect_images(tmp_path / "まだ無い") == []


def test_build_pdf_creates_file(tmp_path):
    images = _write_pages(tmp_path / "capture", 3)
    output = tmp_path / "out" / "book.pdf"
    pdfbuild.build_pdf(images, output)
    assert output.exists()
    assert output.read_bytes().startswith(b"%PDF")


def test_jpeg_quality_embeds_jpeg_streams(tmp_path):
    """品質を指定したときだけ JPEG(DCTDecode) で埋め込まれる。"""
    directory = tmp_path / "capture"
    _write_pages(directory, 2, size=(200, 260))

    lossless = tmp_path / "lossless.pdf"
    compressed = tmp_path / "compressed.pdf"
    pdfbuild.build_pdf_from_directory(directory, lossless)
    pdfbuild.build_pdf_from_directory(directory, compressed, jpeg_quality=40)

    assert b"DCTDecode" not in lossless.read_bytes()
    assert b"DCTDecode" in compressed.read_bytes()


def test_build_pdf_from_directory_returns_page_count(tmp_path):
    _write_pages(tmp_path / "capture", 5)
    output, count = pdfbuild.build_pdf_from_directory(tmp_path / "capture", tmp_path / "o.pdf")
    assert count == 5
    assert output.exists()


def _page_count(pdf: Path) -> int:
    """PDF のページ数を数える（外部ライブラリを足さずに済ませる）。"""
    from PIL import Image as PILImage  # noqa: F401  (Pillow は必須依存)

    text = pdf.read_bytes()
    # 追記された PDF には古い世代の /Count も残るので、最後のものを見る
    counts = re.findall(rb"/Count\s+(\d+)", text)
    return int(counts[-1]) if counts else 0


def test_pillow_fallback_writes_every_page(tmp_path):
    images = _write_pages(tmp_path / "capture", 60)  # 追記が複数回起きる枚数
    output = tmp_path / "fallback.pdf"
    pdfbuild._write_with_pillow(images, output, dpi=150)

    assert output.read_bytes().startswith(b"%PDF")
    assert _page_count(output) == 60


def test_pillow_fallback_reports_progress(tmp_path):
    images = _write_pages(tmp_path / "capture", 30)
    seen: list[tuple[int, int]] = []
    pdfbuild._write_with_pillow(
        images, tmp_path / "out.pdf", dpi=150, on_progress=lambda d, t: seen.append((d, t))
    )

    assert seen[-1] == (30, 30)
    assert all(total == 30 for _done, total in seen)


def test_img2pdf_path_writes_every_page(tmp_path):
    images = _write_pages(tmp_path / "capture", 40)
    output = tmp_path / "direct.pdf"
    pdfbuild._write_with_img2pdf(images, output, dpi=150)

    assert _page_count(output) == 40


def test_falls_back_to_pillow_when_img2pdf_fails(tmp_path, monkeypatch):
    """img2pdf が未導入でも、対応外の画像でも、Pillow 側で作り切る。"""
    images = _write_pages(tmp_path / "capture", 3)

    def broken(*_args, **_kwargs):
        raise RuntimeError("img2pdf が使えない状況")

    monkeypatch.setattr(pdfbuild, "_write_with_img2pdf", broken)
    output = pdfbuild._write_pdf(images, tmp_path / "out.pdf", dpi=150)

    assert output.exists()
    assert _page_count(output) == 3


def test_build_error_explains_both_failures(tmp_path, monkeypatch):
    images = _write_pages(tmp_path / "capture", 2)

    def broken_img2pdf(*_args, **_kwargs):
        raise RuntimeError("img2pdf 側の理由")

    def broken_pillow(*_args, **_kwargs):
        raise MemoryError("メモリが足りません")

    monkeypatch.setattr(pdfbuild, "_write_with_img2pdf", broken_img2pdf)
    monkeypatch.setattr(pdfbuild, "_write_with_pillow", broken_pillow)

    with pytest.raises(pdfbuild.PdfBuildError) as error:
        pdfbuild._write_pdf(images, tmp_path / "out.pdf", dpi=150)

    message = str(error.value)
    assert "img2pdf 側の理由" in message
    assert "メモリが足りません" in message
    assert "2 ページ" in message


def test_build_pdf_rejects_empty_input(tmp_path):
    with pytest.raises(ValueError):
        pdfbuild.build_pdf([], tmp_path / "x.pdf")


def test_build_pdf_reports_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        pdfbuild.build_pdf([tmp_path / "nope.png"], tmp_path / "x.pdf")


def test_iter_pdf_inputs_mixes_files_and_directories(tmp_path):
    directory = tmp_path / "capture"
    _write_pages(directory, 2)
    single = tmp_path / "extra.png"
    Image.new("RGB", (4, 4)).save(single)
    result = pdfbuild.iter_pdf_inputs([directory, single])
    assert [p.name for p in result] == ["page_0001.png", "page_0002.png", "extra.png"]


@pytest.mark.parametrize(
    "value,expected",
    [(512, "512 B"), (2048, "2.0 KB"), (5 * 1024 * 1024, "5.0 MB")],
)
def test_format_size(value, expected):
    assert pdfbuild.format_size(value) == expected
