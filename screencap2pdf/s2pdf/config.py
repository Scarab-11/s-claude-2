"""キャプチャ設定（プロファイル）の保持と保存。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

from .imaging import ImageOptions


def config_dir() -> Path:
    """設定ファイルを置く場所。"""
    base = os.environ.get("S2PDF_HOME")
    if base:
        return Path(base)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "s2pdf"
    return Path.home() / ".config" / "s2pdf"


def profiles_path() -> Path:
    return config_dir() / "profiles.json"


def next_available_dir(path: Path) -> Path:
    """中身のある同名フォルダがあれば `_2`, `_3` … と番号を足した名前を返す。"""
    if not path.exists() or not any(path.iterdir()):
        return path
    number = 2
    while True:
        candidate = path.with_name(f"{path.name}_{number}")
        if not candidate.exists() or not any(candidate.iterdir()):
            return candidate
        number += 1


def next_available_path(path: Path) -> Path:
    """同名ファイルがあれば `_2`, `_3` … と番号を足した名前を返す。"""
    if not path.exists():
        return path
    number = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


@dataclass
class Region:
    """キャプチャする矩形（画面の実ピクセル座標）。"""

    left: int
    top: int
    width: int
    height: int

    def as_bbox(self) -> dict[str, int]:
        """mss に渡す形式。"""
        return {
            "left": int(self.left),
            "top": int(self.top),
            "width": int(self.width),
            "height": int(self.height),
        }

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.width, self.height)

    def relative_to(self, origin_left: int, origin_top: int) -> "Region":
        """原点をずらした座標系での矩形（画面座標 → ウィンドウ内座標）。"""
        return Region(self.left - origin_left, self.top - origin_top, self.width, self.height)

    def crop_box(self, image_width: int, image_height: int) -> tuple[int, int, int, int]:
        """画像からこの範囲を切り出すための箱。画像からはみ出す分は詰める。"""
        left = max(0, min(self.left, image_width))
        top = max(0, min(self.top, image_height))
        right = max(left, min(self.left + self.width, image_width))
        bottom = max(top, min(self.top + self.height, image_height))
        return (left, top, right, bottom)

    def intersects(self, other: "Region") -> bool:
        return not (
            self.left + self.width <= other.left
            or other.left + other.width <= self.left
            or self.top + self.height <= other.top
            or other.top + other.height <= self.top
        )

    def __str__(self) -> str:
        return f"({self.left}, {self.top}) {self.width}x{self.height}"

    @classmethod
    def from_any(cls, value: Any) -> "Region":
        if isinstance(value, Region):
            return value
        if isinstance(value, dict):
            return cls(
                int(value["left"]),
                int(value["top"]),
                int(value["width"]),
                int(value["height"]),
            )
        if isinstance(value, (list, tuple)) and len(value) == 4:
            return cls(*(int(v) for v in value))
        raise ValueError(f"領域として解釈できません: {value!r}")

    @classmethod
    def parse(cls, text: str) -> "Region":
        """'100,120,800,1200' 形式の文字列から作る。"""
        parts = [p.strip() for p in text.replace(" ", ",").split(",") if p.strip()]
        if len(parts) != 4:
            raise ValueError("領域は 左,上,幅,高さ の 4 つの数値で指定してください。")
        left, top, width, height = (int(p) for p in parts)
        if width <= 0 or height <= 0:
            raise ValueError("幅と高さは 1 以上にしてください。")
        return cls(left, top, width, height)


@dataclass
class Profile:
    """1 つのキャプチャ設定。"""

    name: str = "default"
    region: Optional[Region] = None
    window_title: Optional[str] = None
    # "screen" = 画面をそのまま撮る / "window" = ウィンドウの中身を直接撮る（裏で動かせる）
    capture_mode: str = "screen"
    key: str = "right"
    pages: int = 0  # 0 なら「同じページが続くまで」自動判定
    start_delay: float = 3.0  # 開始ボタンを押してから 1 枚目までの待ち
    settle_delay: float = 0.6  # ページ送り後、描画が落ち着くまでの待ち
    after_shot_delay: float = 0.1  # 撮影してからキーを送るまでの待ち
    output_dir: str = "capture"
    prefix: str = "page"
    image_format: str = "png"
    stop_on_duplicate: bool = True  # ページが変わらなくなったら終わりとみなす
    duplicate_threshold: float = 0.004
    verify_page_turn: bool = True  # キーを送ったあと、実際に変わったか確かめる
    change_timeout: float = 5.0  # 変わるのを待つ最大秒数
    trim: bool = False
    trim_tolerance: int = 10
    trim_padding: int = 0
    grayscale: bool = False
    max_width: Optional[int] = None
    pdf_dpi: int = 150
    jpeg_quality: Optional[int] = None

    def image_options(self) -> ImageOptions:
        return ImageOptions(
            trim=self.trim,
            trim_tolerance=self.trim_tolerance,
            trim_padding=self.trim_padding,
            grayscale=self.grayscale,
            max_width=self.max_width,
        )

    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser()

    def image_path(self, index: int) -> Path:
        """1 始まりのページ番号に対応する画像パス。"""
        return self.output_path() / f"{self.prefix}_{index:04d}.{self.image_format}"

    @property
    def uses_window_capture(self) -> bool:
        """ウィンドウを直接キャプチャする（他の作業と並行できる）モードか。"""
        return self.capture_mode == "window"

    def validate(self) -> None:
        from .winput import normalize_key

        if self.capture_mode not in ("screen", "window"):
            raise ValueError("キャプチャ方式は screen か window にしてください。")
        if self.uses_window_capture:
            if not (self.window_title or "").strip():
                raise ValueError(
                    "ウィンドウを直接キャプチャするモードでは、対象ウィンドウの指定が必要です。"
                )
        elif self.region is None:
            raise ValueError("キャプチャ範囲が未設定です。先に範囲を指定してください。")
        if self.region is not None and (self.region.width <= 0 or self.region.height <= 0):
            raise ValueError("キャプチャ範囲の幅と高さは 1 以上にしてください。")
        normalize_key(self.key)
        if self.pages < 0:
            raise ValueError("ページ数は 0 以上にしてください（0 = 自動判定）。")
        if self.image_format.lower() not in ("png", "jpg", "jpeg"):
            raise ValueError("画像形式は png か jpg にしてください。")
        if self.change_timeout < 0:
            raise ValueError("変化を待つ秒数は 0 以上にしてください。")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["region"] = asdict(self.region) if self.region else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        region = kwargs.get("region")
        kwargs["region"] = Region.from_any(region) if region else None
        return cls(**kwargs)


@dataclass
class ProfileStore:
    """プロファイルを JSON ファイルに保存する。"""

    path: Path = field(default_factory=profiles_path)

    def load_all(self) -> dict[str, Profile]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        result: dict[str, Profile] = {}
        for name, data in raw.items():
            try:
                profile = Profile.from_dict(data)
            except (TypeError, ValueError):
                continue
            profile.name = name
            result[name] = profile
        return result

    def load(self, name: str) -> Optional[Profile]:
        return self.load_all().get(name)

    def save(self, profile: Profile) -> Path:
        profiles = self.load_all()
        profiles[profile.name] = profile
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {name: p.to_dict() for name, p in profiles.items()}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.path

    def delete(self, name: str) -> bool:
        profiles = self.load_all()
        if name not in profiles:
            return False
        del profiles[name]
        payload = {n: p.to_dict() for n, p in profiles.items()}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
