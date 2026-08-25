"""連番画像を 1 つの PDF にまとめる。"""

from __future__ import annotations

import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

from PIL import Image

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
_NUMBER_RE = re.compile(r"(\d+)")


def natural_key(path: Path) -> tuple:
    """page_2.png が page_10.png より前に来るように並べるためのキー。"""
    parts = _NUMBER_RE.split(path.name)
    return tuple((1, int(p), "") if p.isdigit() else (0, 0, p.lower()) for p in parts)


def collect_images(directory: Path) -> list[Path]:
    """フォルダ内の画像を連番順に集める。"""
    files = [
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files, key=natural_key)


def iter_pdf_inputs(paths: Iterable[Path]) -> list[Path]:
    """ファイル・フォルダ混在の入力を画像パスの列に展開する。"""
    result: list[Path] = []
    for path in paths:
        if path.is_dir():
            result.extend(collect_images(path))
        elif path.suffix.lower() in IMAGE_SUFFIXES:
            result.append(path)
    return result


@contextmanager
def _jpeg_copies(images: Sequence[Path], quality: int) -> Iterator[list[Path]]:
    """JPEG に再圧縮した一時ファイルを作る（PDF を小さくしたいとき用）。"""
    with tempfile.TemporaryDirectory(prefix="s2pdf-") as tmpdir:
        tmp = Path(tmpdir)
        converted: list[Path] = []
        for index, path in enumerate(images):
            with Image.open(path) as img:
                img.load()
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                dest = tmp / f"{index:06d}.jpg"
                img.save(dest, "JPEG", quality=int(quality), optimize=True)
            converted.append(dest)
        yield converted


def build_pdf(
    images: Sequence[Path],
    output: Path,
    dpi: int = 150,
    jpeg_quality: Optional[int] = None,
) -> Path:
    """画像を PDF にまとめる。

    ``jpeg_quality`` を指定すると JPEG に再圧縮してからまとめるのでファイルが小さくなる。
    指定しない場合は元の画質のまま埋め込む。
    """
    if not images:
        raise ValueError("PDF にする画像が 1 枚もありません。")
    missing = [p for p in images if not p.exists()]
    if missing:
        raise FileNotFoundError(f"画像が見つかりません: {missing[0]}")

    output.parent.mkdir(parents=True, exist_ok=True)

    if jpeg_quality is not None:
        with _jpeg_copies(images, jpeg_quality) as converted:
            return _write_pdf(converted, output, dpi)
    return _write_pdf(images, output, dpi)


def _write_pdf(images: Sequence[Path], output: Path, dpi: int) -> Path:
    try:
        return _write_with_img2pdf(images, output, dpi)
    except ImportError:
        return _write_with_pillow(images, output, dpi)


def _write_with_img2pdf(images: Sequence[Path], output: Path, dpi: int) -> Path:
    """img2pdf があれば再エンコードなしでそのまま埋め込む（画質劣化なし）。"""
    import img2pdf

    layout = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
    with open(output, "wb") as fh:
        fh.write(img2pdf.convert([str(p) for p in images], layout_fun=layout))
    return output


def _write_with_pillow(images: Sequence[Path], output: Path, dpi: int) -> Path:
    """img2pdf が入っていない環境向けのフォールバック。"""
    pages: list[Image.Image] = []
    try:
        for path in images:
            img = Image.open(path)
            img.load()
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            pages.append(img)
        first, rest = pages[0], pages[1:]
        first.save(
            output,
            "PDF",
            save_all=True,
            append_images=rest,
            resolution=float(dpi),
        )
    finally:
        for img in pages:
            img.close()
    return output


def build_pdf_from_directory(
    directory: Path,
    output: Path,
    dpi: int = 150,
    jpeg_quality: Optional[int] = None,
) -> tuple[Path, int]:
    """フォルダ内の連番画像から PDF を作る。(出力パス, ページ数) を返す。"""
    images = collect_images(directory)
    if not images:
        raise ValueError(f"{directory} に画像が見つかりません。")
    build_pdf(images, output, dpi=dpi, jpeg_quality=jpeg_quality)
    return output, len(images)


def format_size(num_bytes: int) -> str:
    """人が読めるファイルサイズ表記。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
