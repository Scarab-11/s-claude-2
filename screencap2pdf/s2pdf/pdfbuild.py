"""連番画像を 1 つの PDF にまとめる。"""

from __future__ import annotations

import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional, Sequence

from PIL import Image

# (終わったページ数, 全ページ数)
ProgressHook = Callable[[int, int], None]

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
_NUMBER_RE = re.compile(r"(\d+)")


def natural_key(path: Path) -> tuple:
    """page_2.png が page_10.png より前に来るように並べるためのキー。"""
    parts = _NUMBER_RE.split(path.name)
    return tuple((1, int(p), "") if p.isdigit() else (0, 0, p.lower()) for p in parts)


def collect_images(directory: Path) -> list[Path]:
    """フォルダ内の画像を連番順に集める。

    `_` で始まる名前（プレビューなどの作業用ファイル）は PDF に入れない。
    """
    if not directory.exists():
        return []
    files = [
        p
        for p in directory.iterdir()
        if p.is_file()
        and p.suffix.lower() in IMAGE_SUFFIXES
        and not p.name.startswith("_")
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


class PdfBuildError(RuntimeError):
    """PDF を作れなかったときに投げる。理由をそのまま利用者に見せる。"""


def build_pdf(
    images: Sequence[Path],
    output: Path,
    dpi: int = 150,
    jpeg_quality: Optional[int] = None,
    on_progress: Optional[ProgressHook] = None,
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
            return _write_pdf(converted, output, dpi, on_progress)
    return _write_pdf(images, output, dpi, on_progress)


def _write_pdf(
    images: Sequence[Path],
    output: Path,
    dpi: int,
    on_progress: Optional[ProgressHook] = None,
) -> Path:
    """まず img2pdf、駄目なら Pillow で書き出す。

    img2pdf は失敗する理由がいくつもある（未導入、対応していない画像形式など）ので、
    どんな失敗でも Pillow 側に回して、そちらも駄目なら理由をまとめて伝える。
    """
    try:
        return _write_with_img2pdf(images, output, dpi, on_progress)
    except Exception as img2pdf_error:  # noqa: BLE001 - 理由は下で伝える
        try:
            return _write_with_pillow(images, output, dpi, on_progress)
        except Exception as pillow_error:  # noqa: BLE001
            raise PdfBuildError(
                f"PDF を作成できませんでした（{len(images)} ページ）。\n"
                f"img2pdf: {img2pdf_error}\n"
                f"Pillow: {pillow_error}"
            ) from pillow_error


def _write_with_img2pdf(
    images: Sequence[Path],
    output: Path,
    dpi: int,
    on_progress: Optional[ProgressHook] = None,
) -> Path:
    """再エンコードなしでそのまま埋め込む（画質劣化なし）。

    ページ数が多いと PDF 全体をメモリに載せられないので、ファイルに直接書かせる。
    """
    import img2pdf

    layout = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
    if on_progress:
        on_progress(0, len(images))
    with open(output, "wb") as fh:
        img2pdf.convert(
            [str(p) for p in images], layout_fun=layout, outputstream=fh
        )
    if on_progress:
        on_progress(len(images), len(images))
    return output


def _load_page(path: Path) -> Image.Image:
    """1 枚だけ読み込んで、ファイルを閉じた状態の画像を返す。"""
    with Image.open(path) as src:
        src.load()
        if src.mode not in ("RGB", "L"):
            return src.convert("RGB")
        return src.copy()


# Pillow で書き出すときに一度に扱うページ数。
# 大きすぎるとメモリを食い、小さすぎると追記のたびに PDF を読み直すので遅くなる。
PILLOW_CHUNK_SIZE = 25


def _write_with_pillow(
    images: Sequence[Path],
    output: Path,
    dpi: int,
    on_progress: Optional[ProgressHook] = None,
) -> Path:
    """img2pdf が使えない環境向け。

    Pillow の ``save_all`` は渡したページを全部同時にメモリへ載せるため、
    数百ページを一度に渡すとメモリ不足で失敗する。少しずつ追記していく。
    """
    total = len(images)
    done = 0
    for start in range(0, total, PILLOW_CHUNK_SIZE):
        chunk = images[start : start + PILLOW_CHUNK_SIZE]
        pages = [_load_page(path) for path in chunk]
        try:
            pages[0].save(
                output,
                "PDF",
                resolution=float(dpi),
                save_all=True,
                append_images=pages[1:],
                append=start > 0,
            )
        finally:
            for page in pages:
                page.close()
        done += len(chunk)
        if on_progress:
            on_progress(done, total)
    return output


def build_pdf_from_directory(
    directory: Path,
    output: Path,
    dpi: int = 150,
    jpeg_quality: Optional[int] = None,
    on_progress: Optional[ProgressHook] = None,
) -> tuple[Path, int]:
    """フォルダ内の連番画像から PDF を作る。(出力パス, ページ数) を返す。"""
    images = collect_images(directory)
    if not images:
        raise ValueError(f"{directory} に画像が見つかりません。")
    build_pdf(
        images, output, dpi=dpi, jpeg_quality=jpeg_quality, on_progress=on_progress
    )
    return output, len(images)


def format_size(num_bytes: int) -> str:
    """人が読めるファイルサイズ表記。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
