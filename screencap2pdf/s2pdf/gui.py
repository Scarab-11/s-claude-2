"""GUI 版（Tkinter）。範囲をドラッグで選び、ボタンで実行する。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from . import __version__, deps, pdfbuild, winput
from .config import Profile, ProfileStore, Region
from .engine import CaptureError, Capturer
from .region import pick_region

PAD = {"padx": 6, "pady": 4}


class ProgressWindow(tk.Toplevel):
    """キャプチャ中だけ出す小さな進捗表示。撮影範囲を避けて配置する。"""

    def __init__(self, master: tk.Misc, region: Region, on_cancel) -> None:
        super().__init__(master)
        self.title("キャプチャ中")
        self.overrideredirect(False)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", on_cancel)

        self.status = tk.StringVar(value="準備中...")
        ttk.Label(self, textvariable=self.status, width=42).grid(
            row=0, column=0, columnspan=2, **PAD
        )
        self.bar = ttk.Progressbar(self, length=280, mode="indeterminate")
        self.bar.grid(row=1, column=0, columnspan=2, **PAD)
        self.bar.start(30)
        ttk.Label(self, text="Esc キーでも中止できます").grid(row=2, column=0, **PAD)
        ttk.Button(self, text="中止", command=on_cancel).grid(row=2, column=1, **PAD)

        self.update_idletasks()
        self._place_clear_of(region)

    def _place_clear_of(self, region: Region) -> None:
        """撮影範囲にかからない位置に置く。"""
        width = self.winfo_width() or 320
        height = self.winfo_height() or 120
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        margin = 12
        candidates = [
            (screen_w - width - margin, screen_h - height - 60),
            (margin, screen_h - height - 60),
            (screen_w - width - margin, margin),
            (margin, margin),
        ]
        for x, y in candidates:
            spot = Region(x, y, width, height)
            if not spot.intersects(region):
                self.geometry(f"+{x}+{y}")
                return
        self.geometry(f"+{candidates[0][0]}+{candidates[0][1]}")

    def set_total(self, total: int) -> None:
        if total > 0:
            self.bar.stop()
            self.bar.configure(mode="determinate", maximum=total, value=0)

    def set_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.bar.configure(value=done)
            self.status.set(f"{done} / {total} ページ")
        else:
            self.status.set(f"{done} ページ撮影済み（終端まで自動）")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"画面キャプチャ → PDF  v{__version__}")
        self.resizable(False, False)

        self.store = ProfileStore()
        self.profile = self.store.load("default") or Profile()

        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._stop_flag = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._progress_window: Optional[ProgressWindow] = None

        self._build_vars()
        self._build_widgets()
        self._load_profile_into_form(self.profile)
        self.after(100, self._drain_queue)
        self.after(200, self._warn_about_missing_dependencies)

    def _warn_about_missing_dependencies(self) -> None:
        """足りないライブラリは、撮り始める前に知らせる。"""
        lacking = deps.missing()
        if not lacking:
            return
        message = deps.missing_message(lacking)
        self.write_log("警告: " + message.replace("\n\n", " "))
        messagebox.showwarning("ライブラリが足りません", message)

    # ---- 画面構築 ---------------------------------------------------

    def _build_vars(self) -> None:
        self.var_region = tk.StringVar(value="未設定")
        self.var_window = tk.StringVar()
        self.var_key = tk.StringVar(value="right")
        self.var_pages = tk.StringVar(value="0")
        self.var_start_delay = tk.StringVar(value="3.0")
        self.var_settle_delay = tk.StringVar(value="0.6")
        self.var_outdir = tk.StringVar(value="capture")
        self.var_prefix = tk.StringVar(value="page")
        self.var_format = tk.StringVar(value="png")
        self.var_autostop = tk.BooleanVar(value=True)
        self.var_trim = tk.BooleanVar(value=False)
        self.var_gray = tk.BooleanVar(value=False)
        self.var_maxwidth = tk.StringVar(value="")
        self.var_pdf = tk.StringVar(value="output.pdf")
        self.var_dpi = tk.StringVar(value="150")
        self.var_jpeg = tk.StringVar(value="")
        self.var_autopdf = tk.BooleanVar(value=True)
        self.var_resume = tk.BooleanVar(value=False)
        self.var_start_index = tk.StringVar(value="1")
        self.var_retake_index = tk.StringVar(value="1")
        self._region: Optional[Region] = None

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self)
        outer.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # --- 1. キャプチャ範囲
        box = ttk.LabelFrame(outer, text="1. キャプチャ範囲")
        box.grid(row=0, column=0, sticky="ew", pady=4)
        ttk.Label(box, textvariable=self.var_region, width=34).grid(row=0, column=0, **PAD)
        ttk.Button(box, text="範囲を選ぶ", command=self.on_pick_region).grid(row=0, column=1, **PAD)
        ttk.Button(box, text="プレビュー", command=self.on_preview).grid(row=0, column=2, **PAD)

        # --- 2. ページ送り
        box = ttk.LabelFrame(outer, text="2. ページ送り")
        box.grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Label(box, text="対象ウィンドウ").grid(row=0, column=0, sticky="w", **PAD)
        self.combo_window = ttk.Combobox(box, textvariable=self.var_window, width=34)
        self.combo_window.grid(row=0, column=1, columnspan=2, sticky="w", **PAD)
        ttk.Button(box, text="一覧を更新", command=self.on_refresh_windows).grid(row=0, column=3, **PAD)

        ttk.Label(box, text="送るキー").grid(row=1, column=0, sticky="w", **PAD)
        ttk.Combobox(
            box,
            textvariable=self.var_key,
            values=["right", "left", "down", "up", "pagedown", "pageup", "space", "enter"],
            width=12,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", **PAD)

        ttk.Label(box, text="ページ数（0=自動）").grid(row=1, column=2, sticky="e", **PAD)
        ttk.Spinbox(box, from_=0, to=99999, textvariable=self.var_pages, width=8).grid(
            row=1, column=3, sticky="w", **PAD
        )

        ttk.Label(box, text="開始までの待ち(秒)").grid(row=2, column=0, sticky="w", **PAD)
        ttk.Spinbox(
            box, from_=0, to=60, increment=0.5, textvariable=self.var_start_delay, width=8
        ).grid(row=2, column=1, sticky="w", **PAD)
        ttk.Label(box, text="ページ送り後の待ち(秒)").grid(row=2, column=2, sticky="e", **PAD)
        ttk.Spinbox(
            box, from_=0, to=30, increment=0.1, textvariable=self.var_settle_delay, width=8
        ).grid(row=2, column=3, sticky="w", **PAD)

        ttk.Checkbutton(
            box, text="同じ画面が続いたら終端とみなして自動で止める", variable=self.var_autostop
        ).grid(row=3, column=0, columnspan=4, sticky="w", **PAD)

        # --- 3. 保存と加工
        box = ttk.LabelFrame(outer, text="3. 画像の保存と加工")
        box.grid(row=2, column=0, sticky="ew", pady=4)
        ttk.Label(box, text="保存先フォルダ").grid(row=0, column=0, sticky="w", **PAD)
        ttk.Entry(box, textvariable=self.var_outdir, width=34).grid(
            row=0, column=1, columnspan=2, sticky="w", **PAD
        )
        ttk.Button(box, text="参照", command=self.on_browse_outdir).grid(row=0, column=3, **PAD)

        ttk.Label(box, text="ファイル名の接頭辞").grid(row=1, column=0, sticky="w", **PAD)
        ttk.Entry(box, textvariable=self.var_prefix, width=12).grid(row=1, column=1, sticky="w", **PAD)
        ttk.Label(box, text="画像形式").grid(row=1, column=2, sticky="e", **PAD)
        ttk.Combobox(
            box, textvariable=self.var_format, values=["png", "jpg"], width=8, state="readonly"
        ).grid(row=1, column=3, sticky="w", **PAD)

        ttk.Checkbutton(box, text="余白を自動で切る", variable=self.var_trim).grid(
            row=2, column=0, sticky="w", **PAD
        )
        ttk.Checkbutton(box, text="グレースケール", variable=self.var_gray).grid(
            row=2, column=1, sticky="w", **PAD
        )
        ttk.Label(box, text="横幅を縮小(px)").grid(row=2, column=2, sticky="e", **PAD)
        ttk.Entry(box, textvariable=self.var_maxwidth, width=8).grid(row=2, column=3, sticky="w", **PAD)

        # --- 4. PDF
        box = ttk.LabelFrame(outer, text="4. PDF")
        box.grid(row=3, column=0, sticky="ew", pady=4)
        ttk.Label(box, text="出力ファイル").grid(row=0, column=0, sticky="w", **PAD)
        ttk.Entry(box, textvariable=self.var_pdf, width=34).grid(
            row=0, column=1, columnspan=2, sticky="w", **PAD
        )
        ttk.Button(box, text="参照", command=self.on_browse_pdf).grid(row=0, column=3, **PAD)
        ttk.Label(box, text="解像度(dpi)").grid(row=1, column=0, sticky="w", **PAD)
        ttk.Entry(box, textvariable=self.var_dpi, width=8).grid(row=1, column=1, sticky="w", **PAD)
        ttk.Label(box, text="JPEG品質(空=無劣化)").grid(row=1, column=2, sticky="e", **PAD)
        ttk.Entry(box, textvariable=self.var_jpeg, width=8).grid(row=1, column=3, sticky="w", **PAD)
        ttk.Checkbutton(box, text="撮影後に自動で PDF を作る", variable=self.var_autopdf).grid(
            row=2, column=0, columnspan=2, sticky="w", **PAD
        )
        ttk.Button(box, text="画像フォルダから PDF を作る", command=self.on_build_pdf).grid(
            row=2, column=2, columnspan=2, sticky="e", **PAD
        )

        # --- 5. 実行
        box = ttk.LabelFrame(outer, text="5. 実行")
        box.grid(row=4, column=0, sticky="ew", pady=4)
        ttk.Label(box, text="開始ページ").grid(row=0, column=0, sticky="w", **PAD)
        ttk.Spinbox(box, from_=1, to=99999, textvariable=self.var_start_index, width=8).grid(
            row=0, column=1, sticky="w", **PAD
        )
        ttk.Checkbutton(box, text="続きから（既存画像を飛ばす）", variable=self.var_resume).grid(
            row=0, column=2, columnspan=2, sticky="w", **PAD
        )
        self.btn_start = ttk.Button(box, text="開始", command=self.on_start)
        self.btn_start.grid(row=1, column=0, **PAD)
        self.btn_stop = ttk.Button(box, text="中止", command=self.on_stop, state="disabled")
        self.btn_stop.grid(row=1, column=1, **PAD)
        ttk.Label(box, text="このページを撮り直す").grid(row=1, column=2, sticky="e", **PAD)
        retake = ttk.Frame(box)
        retake.grid(row=1, column=3, sticky="w", **PAD)
        ttk.Spinbox(retake, from_=1, to=99999, textvariable=self.var_retake_index, width=6).pack(
            side="left"
        )
        ttk.Button(retake, text="撮る", command=self.on_retake, width=6).pack(side="left", padx=4)

        # --- ログ
        self.log = tk.Text(outer, height=9, width=72, state="disabled", wrap="none")
        self.log.grid(row=5, column=0, sticky="ew", pady=4)

        bottom = ttk.Frame(outer)
        bottom.grid(row=6, column=0, sticky="ew")
        ttk.Button(bottom, text="設定を保存", command=self.on_save_profile).pack(side="left", padx=4)
        ttk.Button(bottom, text="保存した設定を読み込む", command=self.on_load_profile).pack(
            side="left", padx=4
        )
        ttk.Button(bottom, text="画像フォルダを開く", command=self.on_open_outdir).pack(
            side="left", padx=4
        )

    # ---- ログ・キュー -----------------------------------------------

    def write_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                kind, payload = item[0], item[1:]
                if kind == "msg":
                    self.write_log(payload[0])
                elif kind == "progress":
                    if self._progress_window:
                        self._progress_window.set_progress(payload[0], payload[1])
                elif kind == "done":
                    self._on_worker_done(payload[0])
                elif kind == "error":
                    self._on_worker_error(payload[0])
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    # ---- フォーム <-> プロファイル -----------------------------------

    def _load_profile_into_form(self, profile: Profile) -> None:
        self._region = profile.region
        self.var_region.set(str(profile.region) if profile.region else "未設定")
        self.var_window.set(profile.window_title or "")
        self.var_key.set(profile.key)
        self.var_pages.set(str(profile.pages))
        self.var_start_delay.set(f"{profile.start_delay:g}")
        self.var_settle_delay.set(f"{profile.settle_delay:g}")
        self.var_outdir.set(profile.output_dir)
        self.var_prefix.set(profile.prefix)
        self.var_format.set(profile.image_format)
        self.var_autostop.set(profile.stop_on_duplicate)
        self.var_trim.set(profile.trim)
        self.var_gray.set(profile.grayscale)
        self.var_maxwidth.set(str(profile.max_width) if profile.max_width else "")
        self.var_dpi.set(str(profile.pdf_dpi))
        self.var_jpeg.set(str(profile.jpeg_quality) if profile.jpeg_quality else "")

    def _int_or_none(self, text: str, label: str) -> Optional[int]:
        text = text.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            raise ValueError(f"{label}は数値で入力してください。") from None

    def _build_profile(self) -> Profile:
        """入力欄からプロファイルを組み立てる（検証つき）。"""
        try:
            pages = int(self.var_pages.get() or 0)
            start_delay = float(self.var_start_delay.get() or 0)
            settle_delay = float(self.var_settle_delay.get() or 0)
            dpi = int(self.var_dpi.get() or 150)
        except ValueError:
            raise ValueError("ページ数・待ち時間・解像度は数値で入力してください。") from None

        profile = Profile(
            name="default",
            region=self._region,
            window_title=self.var_window.get().strip() or None,
            key=winput.normalize_key(self.var_key.get()),
            pages=pages,
            start_delay=start_delay,
            settle_delay=settle_delay,
            output_dir=self.var_outdir.get().strip() or "capture",
            prefix=self.var_prefix.get().strip() or "page",
            image_format=self.var_format.get(),
            stop_on_duplicate=self.var_autostop.get(),
            trim=self.var_trim.get(),
            grayscale=self.var_gray.get(),
            max_width=self._int_or_none(self.var_maxwidth.get(), "横幅"),
            pdf_dpi=dpi,
            jpeg_quality=self._int_or_none(self.var_jpeg.get(), "JPEG品質"),
        )
        profile.validate()
        return profile

    # ---- ボタンの処理 -----------------------------------------------

    def on_pick_region(self) -> None:
        self.withdraw()
        self.update()
        try:
            region = pick_region(master=self, initial=self._region)
        finally:
            self.deiconify()
            self.lift()
        if region is None:
            self.write_log("範囲の選択を中止しました。")
            return
        self._region = region
        self.var_region.set(str(region))
        self.write_log(f"範囲を設定しました: {region}")

    def on_preview(self) -> None:
        try:
            profile = self._build_profile()
        except ValueError as exc:
            messagebox.showerror("入力エラー", str(exc))
            return
        path = Path(profile.output_dir).expanduser() / "_preview.png"
        try:
            self.withdraw()
            self.update()
            Capturer(profile).save_preview(path)
        except (CaptureError, OSError) as exc:
            messagebox.showerror("エラー", str(exc))
            return
        finally:
            self.deiconify()
        self.write_log(f"プレビューを保存しました: {path}")
        self._show_image(path)

    def _show_image(self, path: Path) -> None:
        """プレビュー画像を別ウィンドウで表示する。"""
        try:
            from PIL import ImageTk, Image as PILImage
        except ImportError:  # pragma: no cover
            return
        window = tk.Toplevel(self)
        window.title(f"プレビュー - {path.name}")
        with PILImage.open(path) as img:
            img.load()
            preview = img.copy()
        preview.thumbnail((900, 900))
        photo = ImageTk.PhotoImage(preview)
        label = ttk.Label(window, image=photo)
        label.image = photo  # 参照を保持しないと消える
        label.pack()

    def on_refresh_windows(self) -> None:
        try:
            titles = [info.title for info in winput.list_windows()]
        except RuntimeError as exc:
            messagebox.showerror("エラー", str(exc))
            return
        self.combo_window["values"] = titles
        self.write_log(f"ウィンドウ {len(titles)} 件を取得しました。")

    def on_browse_outdir(self) -> None:
        path = filedialog.askdirectory(title="画像の保存先")
        if path:
            self.var_outdir.set(path)

    def on_browse_pdf(self) -> None:
        path = filedialog.asksaveasfilename(
            title="PDF の保存先", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")]
        )
        if path:
            self.var_pdf.set(path)

    def on_open_outdir(self) -> None:
        path = Path(self.var_outdir.get()).expanduser()
        if not path.exists():
            messagebox.showinfo("お知らせ", f"{path} はまだありません。")
            return
        import subprocess
        import sys

        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def on_save_profile(self) -> None:
        try:
            profile = self._build_profile()
        except ValueError as exc:
            messagebox.showerror("入力エラー", str(exc))
            return
        path = self.store.save(profile)
        self.write_log(f"設定を保存しました: {path}")

    def on_load_profile(self) -> None:
        profile = self.store.load("default")
        if profile is None:
            messagebox.showinfo("お知らせ", "保存された設定がありません。")
            return
        self._load_profile_into_form(profile)
        self.write_log("保存した設定を読み込みました。")

    def on_build_pdf(self) -> None:
        directory = Path(self.var_outdir.get()).expanduser()
        output = Path(self.var_pdf.get()).expanduser()
        try:
            dpi = int(self.var_dpi.get() or 150)
            quality = self._int_or_none(self.var_jpeg.get(), "JPEG品質")
            path, count = pdfbuild.build_pdf_from_directory(
                directory, output, dpi=dpi, jpeg_quality=quality
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("エラー", str(exc))
            return
        size = pdfbuild.format_size(path.stat().st_size)
        self.write_log(f"PDF を作成しました: {path}（{count} ページ / {size}）")
        messagebox.showinfo("完了", f"{path}\n{count} ページ / {size}")

    def on_retake(self) -> None:
        try:
            profile = self._build_profile()
            index = int(self.var_retake_index.get())
        except ValueError as exc:
            messagebox.showerror("入力エラー", str(exc))
            return
        self.write_log(
            f"{profile.start_delay:g} 秒後に {index} ページ目を撮り直します。対象を表示してください。"
        )
        self.withdraw()
        self.update()

        def finish() -> None:
            try:
                path = Capturer(profile).capture_page(index)
                self.write_log(f"{index} ページ目を撮り直しました: {path.name}")
            except (CaptureError, OSError) as exc:
                messagebox.showerror("エラー", str(exc))
            finally:
                self.deiconify()

        self.after(int(profile.start_delay * 1000) or 1, finish)

    # ---- 実行 -------------------------------------------------------

    def on_start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        try:
            profile = self._build_profile()
            start_index = int(self.var_start_index.get() or 1)
        except ValueError as exc:
            messagebox.showerror("入力エラー", str(exc))
            return

        self._stop_flag.clear()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.write_log("---- 開始 ----")

        assert profile.region is not None
        self._progress_window = ProgressWindow(self, profile.region, self.on_stop)
        self._progress_window.set_total(profile.pages)
        self.withdraw()  # 自分が写り込まないように隠す（進捗は小窓に出る）

        self._worker = threading.Thread(
            target=self._run_worker,
            args=(profile, start_index, self.var_resume.get()),
            daemon=True,
        )
        self._worker.start()

    def _run_worker(self, profile: Profile, start_index: int, resume: bool) -> None:
        try:
            capturer = Capturer(
                profile,
                on_message=lambda text: self._queue.put(("msg", text)),
                on_progress=lambda done, total: self._queue.put(("progress", done, total)),
                should_stop=self._stop_flag.is_set,
            )
            report = capturer.run(start_index=start_index, resume=resume)
            self._queue.put(("done", (profile, report)))
        except Exception as exc:  # スレッド内の例外を UI に運ぶ
            self._queue.put(("error", exc))

    def on_stop(self) -> None:
        self._stop_flag.set()
        self.write_log("中止を要求しました...")

    def _cleanup_after_run(self) -> None:
        if self._progress_window is not None:
            self._progress_window.destroy()
            self._progress_window = None
        self.deiconify()
        self.lift()
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _on_worker_done(self, payload) -> None:
        profile, report = payload
        self._cleanup_after_run()
        self.write_log(f"{report.reason} 保存したページ数: {report.page_count}")
        if report.removed:
            self.write_log(f"終端の重複 {len(report.removed)} 枚を削除しました。")

        if self.var_autopdf.get() and report.page_count:
            try:
                path, count = pdfbuild.build_pdf_from_directory(
                    profile.output_path(),
                    Path(self.var_pdf.get()).expanduser(),
                    dpi=profile.pdf_dpi,
                    jpeg_quality=profile.jpeg_quality,
                )
            except (ValueError, OSError) as exc:
                messagebox.showerror("PDF 作成エラー", str(exc))
                return
            size = pdfbuild.format_size(path.stat().st_size)
            self.write_log(f"PDF を作成しました: {path}（{count} ページ / {size}）")
            messagebox.showinfo("完了", f"{path}\n{count} ページ / {size}")
        else:
            messagebox.showinfo("完了", f"{report.reason}\n{report.page_count} ページ")

    def _on_worker_error(self, exc: Exception) -> None:
        self._cleanup_after_run()
        self.write_log(f"エラー: {exc}")
        messagebox.showerror("エラー", str(exc))


def main() -> int:
    winput.enable_dpi_awareness()
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
