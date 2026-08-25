"""必要なライブラリが入っているかを調べる。

Windows には複数の Python が入っていることが多く、
「pip install したのに動かない」の大半は別の Python に入れてしまった場合なので、
案内には必ず実行中の Python 自身のパスを含める。
"""

from __future__ import annotations

import importlib.util
import sys
from typing import NamedTuple


class Dependency(NamedTuple):
    module: str  # import するときの名前
    package: str  # pip で入れるときの名前
    purpose: str
    required: bool

    @property
    def installed(self) -> bool:
        return importlib.util.find_spec(self.module) is not None


DEPENDENCIES = (
    Dependency("PIL", "Pillow", "画像の読み書きと加工", True),
    Dependency("mss", "mss", "画面キャプチャ", True),
    Dependency("img2pdf", "img2pdf", "無劣化での PDF 結合（無い場合は Pillow で代替）", False),
)


def missing(required_only: bool = True) -> list[Dependency]:
    """入っていないライブラリの一覧。"""
    return [
        dep
        for dep in DEPENDENCIES
        if not dep.installed and (dep.required or not required_only)
    ]


def install_command(dependencies) -> str:
    """そのまま貼り付けて実行できる pip コマンド。"""
    packages = " ".join(dep.package for dep in dependencies)
    return f'"{sys.executable}" -m pip install {packages}'


def missing_message(dependencies) -> str:
    """利用者に見せるメッセージ。"""
    names = "、".join(dep.package for dep in dependencies)
    return (
        f"{names} が入っていません。\n\n"
        "次のコマンドをコマンドプロンプトに貼り付けて実行してください:\n"
        f"{install_command(dependencies)}"
    )


def report() -> str:
    """`s2pdf doctor` の出力。"""
    lines = [
        f"Python: {sys.version.split()[0]}",
        f"実行ファイル: {sys.executable}",
        "",
        "ライブラリ:",
    ]
    for dep in DEPENDENCIES:
        mark = "OK  " if dep.installed else ("なし" if dep.required else "任意")
        lines.append(f"  [{mark}] {dep.package:<10} {dep.purpose}")

    not_installed = missing(required_only=False)
    lines.append("")
    if not missing(required_only=True):
        lines.append("必要なライブラリはそろっています。")
    if not_installed:
        lines.append("入れるには:")
        lines.append(f"  {install_command(not_installed)}")
    return "\n".join(lines)
