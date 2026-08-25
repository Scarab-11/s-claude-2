"""コマンドライン版の入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__, pdfbuild, winput
from .config import Profile, ProfileStore, Region
from .engine import CaptureError, Capturer

EPILOG = """\
使用例:
  s2pdf pick                       範囲をドラッグで選んで既定プロファイルに保存
  s2pdf preview                    いま選んでいる範囲を 1 枚だけ撮って確認
  s2pdf run --pages 120 --key right   120 ページ撮る
  s2pdf run --pdf book.pdf         撮り終えたらそのまま PDF にする
  s2pdf shot --index 37            37 ページ目だけ撮り直す
  s2pdf build capture -o out.pdf   既にある画像フォルダから PDF を作る
"""


def _add_profile_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        default="default",
        metavar="名前",
        help="使う設定プロファイル名（既定: default）",
    )


def _add_capture_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--region", metavar="左,上,幅,高さ", help="キャプチャ範囲を数値で指定")
    parser.add_argument("--window", metavar="タイトル", help="ページ送りキーを送るウィンドウ（部分一致）")
    parser.add_argument("--key", metavar="キー", help="ページ送りに使うキー（例: right, pagedown, space）")
    parser.add_argument("--pages", type=int, metavar="N", help="撮るページ数（0 で終端の自動判定）")
    parser.add_argument("--out-dir", metavar="フォルダ", help="画像の保存先")
    parser.add_argument("--prefix", metavar="接頭辞", help="画像ファイル名の接頭辞")
    parser.add_argument("--format", dest="image_format", choices=["png", "jpg"], help="画像形式")
    parser.add_argument("--start-delay", type=float, metavar="秒", help="開始してから 1 枚目までの待ち時間")
    parser.add_argument("--settle-delay", type=float, metavar="秒", help="ページ送り後の待ち時間")
    parser.add_argument("--trim", action="store_true", default=None, help="周囲の均一な余白を自動で切る")
    parser.add_argument("--no-trim", dest="trim", action="store_false", help="余白除去をしない")
    parser.add_argument("--grayscale", action="store_true", default=None, help="グレースケールにする")
    parser.add_argument("--max-width", type=int, metavar="px", help="この横幅まで縮小する")
    parser.add_argument(
        "--no-auto-stop",
        dest="stop_on_duplicate",
        action="store_false",
        default=None,
        help="同じ画面が続いても止めない",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s2pdf",
        description="画面の指定範囲を連続キャプチャして PDF にまとめます。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"s2pdf {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pick = sub.add_parser("pick", help="ドラッグでキャプチャ範囲を選ぶ")
    _add_profile_arg(p_pick)

    p_preview = sub.add_parser("preview", help="範囲を 1 枚だけ撮って確認する")
    _add_profile_arg(p_preview)
    _add_capture_args(p_preview)
    p_preview.add_argument("-o", "--output", default="preview.png", help="保存先（既定: preview.png）")

    p_run = sub.add_parser("run", help="連続キャプチャを実行する")
    _add_profile_arg(p_run)
    _add_capture_args(p_run)
    p_run.add_argument("--start", type=int, default=1, metavar="N", help="何ページ目から始めるか")
    p_run.add_argument("--resume", action="store_true", help="既にある画像の続きから撮る")
    p_run.add_argument("--pdf", metavar="ファイル", help="撮り終えたら PDF にまとめる")
    p_run.add_argument("--save", action="store_true", help="今回の指定をプロファイルに保存する")

    p_shot = sub.add_parser("shot", help="1 枚だけ撮る（失敗ページの撮り直し）")
    _add_profile_arg(p_shot)
    _add_capture_args(p_shot)
    p_shot.add_argument("--index", type=int, required=True, metavar="N", help="上書きするページ番号")

    p_build = sub.add_parser("build", help="画像フォルダから PDF を作る")
    p_build.add_argument("inputs", nargs="+", type=Path, help="画像フォルダ、または画像ファイル")
    p_build.add_argument("-o", "--output", type=Path, required=True, help="出力する PDF")
    p_build.add_argument("--dpi", type=int, default=150, help="PDF に埋め込む解像度（既定: 150）")
    p_build.add_argument(
        "--jpeg-quality",
        type=int,
        metavar="1-100",
        help="JPEG で再圧縮してファイルを小さくする（指定しなければ無劣化）",
    )

    p_windows = sub.add_parser("windows", help="開いているウィンドウの一覧を表示する")
    p_windows.add_argument("--filter", metavar="文字列", help="タイトルの部分一致で絞る")

    p_profiles = sub.add_parser("profiles", help="保存済みプロファイルを見る・消す")
    p_profiles.add_argument("--delete", metavar="名前", help="指定した名前のプロファイルを削除する")

    sub.add_parser("gui", help="GUI 版を起動する")
    sub.add_parser("doctor", help="必要なライブラリが入っているか調べる")

    return parser


def _load_profile(store: ProfileStore, name: str) -> Profile:
    profile = store.load(name)
    if profile is None:
        profile = Profile(name=name)
    return profile


def _apply_overrides(profile: Profile, args: argparse.Namespace) -> Profile:
    """コマンドラインで指定された項目だけ上書きする。"""
    if getattr(args, "region", None):
        profile.region = Region.parse(args.region)
    for attr, field_name in (
        ("window", "window_title"),
        ("key", "key"),
        ("pages", "pages"),
        ("out_dir", "output_dir"),
        ("prefix", "prefix"),
        ("image_format", "image_format"),
        ("start_delay", "start_delay"),
        ("settle_delay", "settle_delay"),
        ("trim", "trim"),
        ("grayscale", "grayscale"),
        ("max_width", "max_width"),
        ("stop_on_duplicate", "stop_on_duplicate"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            setattr(profile, field_name, value)
    if profile.key:
        profile.key = winput.normalize_key(profile.key)
    return profile


def _echo(text: str) -> None:
    print(text, flush=True)


def _progress(done: int, total: int) -> None:
    if total:
        _echo(f"  -- {done}/{total} ページ")


def cmd_pick(args: argparse.Namespace, store: ProfileStore) -> int:
    from .region import pick_region

    profile = _load_profile(store, args.profile)
    region = pick_region(initial=profile.region)
    if region is None:
        _echo("範囲の選択を中止しました。")
        return 1
    profile.region = region
    store.save(profile)
    _echo(f"範囲を保存しました: {region}  → プロファイル '{profile.name}'")
    return 0


def cmd_preview(args: argparse.Namespace, store: ProfileStore) -> int:
    profile = _apply_overrides(_load_profile(store, args.profile), args)
    capturer = Capturer(profile, on_message=_echo)
    path = capturer.save_preview(Path(args.output))
    _echo(f"プレビューを保存しました: {path}")
    return 0


def cmd_run(args: argparse.Namespace, store: ProfileStore) -> int:
    profile = _apply_overrides(_load_profile(store, args.profile), args)
    if args.save:
        store.save(profile)
        _echo(f"設定をプロファイル '{profile.name}' に保存しました。")

    capturer = Capturer(profile, on_message=_echo, on_progress=_progress)
    _echo(f"範囲: {profile.region}  キー: {profile.key}  保存先: {profile.output_path()}")
    _echo("途中で止めたいときは Esc を押してください。")
    try:
        report = capturer.run(start_index=args.start, resume=args.resume)
    except KeyboardInterrupt:
        _echo("中断しました。")
        return 130

    _echo(f"{report.reason} 保存したページ数: {report.page_count}")
    if report.removed:
        _echo(f"終端の重複 {len(report.removed)} 枚を削除しました。")

    if args.pdf and report.page_count:
        output, count = pdfbuild.build_pdf_from_directory(
            profile.output_path(),
            Path(args.pdf),
            dpi=profile.pdf_dpi,
            jpeg_quality=profile.jpeg_quality,
        )
        size = pdfbuild.format_size(output.stat().st_size)
        _echo(f"PDF を作成しました: {output}（{count} ページ / {size}）")
    return 0


def cmd_shot(args: argparse.Namespace, store: ProfileStore) -> int:
    profile = _apply_overrides(_load_profile(store, args.profile), args)
    capturer = Capturer(profile, on_message=_echo)
    if profile.start_delay > 0:
        _echo(f"{profile.start_delay:.0f} 秒後に撮ります。対象を表示してください。")
        import time

        time.sleep(profile.start_delay)
    path = capturer.capture_page(args.index)
    _echo(f"{args.index} ページ目を保存しました: {path}")
    return 0


def cmd_build(args: argparse.Namespace, _store: ProfileStore) -> int:
    images = pdfbuild.iter_pdf_inputs(args.inputs)
    if not images:
        _echo("画像が見つかりませんでした。")
        return 1
    output = pdfbuild.build_pdf(
        images, args.output, dpi=args.dpi, jpeg_quality=args.jpeg_quality
    )
    size = pdfbuild.format_size(output.stat().st_size)
    _echo(f"PDF を作成しました: {output}（{len(images)} ページ / {size}）")
    return 0


def cmd_windows(args: argparse.Namespace, _store: ProfileStore) -> int:
    needle = (args.filter or "").lower()
    for info in winput.list_windows():
        if needle and needle not in info.title.lower():
            continue
        _echo(f"{info.hwnd:>10}  {info.title}")
    return 0


def cmd_profiles(args: argparse.Namespace, store: ProfileStore) -> int:
    if args.delete:
        if store.delete(args.delete):
            _echo(f"プロファイル '{args.delete}' を削除しました。")
            return 0
        _echo(f"プロファイル '{args.delete}' は見つかりませんでした。")
        return 1

    profiles = store.load_all()
    if not profiles:
        _echo(f"保存されたプロファイルはありません。（{store.path}）")
        return 0
    _echo(f"設定ファイル: {store.path}")
    for name, profile in sorted(profiles.items()):
        region = profile.region or "未設定"
        _echo(
            f"  {name}: 範囲={region} キー={profile.key} ページ数="
            f"{profile.pages or '自動'} 保存先={profile.output_dir}"
        )
    return 0


def cmd_gui(_args: argparse.Namespace, _store: ProfileStore) -> int:
    from .gui import main as gui_main

    return gui_main()


def cmd_doctor(_args: argparse.Namespace, _store: ProfileStore) -> int:
    from . import deps

    _echo(deps.report())
    return 1 if deps.missing() else 0


COMMANDS = {
    "gui": cmd_gui,
    "doctor": cmd_doctor,
    "pick": cmd_pick,
    "preview": cmd_preview,
    "run": cmd_run,
    "shot": cmd_shot,
    "build": cmd_build,
    "windows": cmd_windows,
    "profiles": cmd_profiles,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    winput.enable_dpi_awareness()
    args = build_parser().parse_args(argv)
    store = ProfileStore()
    try:
        return COMMANDS[args.command](args, store)
    except (CaptureError, ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
