# -*- coding: utf-8 -*-
"""PDF文字認識 － 画面で操作する版。

横書き・縦書きそれぞれの読み取りエンジン（tesseract / PP-OCRv5 mobile /
PP-OCRv5 server）を選べる。使い方は「起動口として追加」の分そのままで、
ふだんの PDF文字認識.bat（ドラッグ＆ドロップ・番号メニュー）は変えていない。
"""
import csv
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pdf_ocr                                                # noqa: E402

DND_ERROR = None
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError as exc:
    HAS_DND = False
    DND_ERROR = "tkinterdnd2 が無い（%s）" % exc

ENGINES = [
    ("tesseract（既定・精度重視）", "tesseract"),
    ("tesseract（速度重視・小さい言語データ）", "tesseract_fast"),
    ("PP-OCRv5 mobile（軽い・同梱ずみ）", "ppocr_mobile"),
    ("PP-OCRv5 server（重いが精度重視・初回に確認して取得）", "ppocr_server"),
]
LABEL_OF = {key: label for label, key in ENGINES}
KEY_OF = {label: key for label, key in ENGINES}


def settings_path():
    base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            or os.path.expanduser("~"))
    return os.path.join(base, "pdf_ocr", "gui_settings.json")


def load_gui_settings():
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_gui_settings(data):
    path = settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def conversion_log_path():
    return os.path.join(os.path.dirname(settings_path()), "変換ログ.csv")


LOG_HEADER = ["日時", "ファイル名", "結果", "横書きの読み取り", "縦書きの読み取り",
             "ページ数", "文字列数", "秒", "備考"]


def append_conversion_log(row):
    """1 ファイルの変換結果を 1 行、CSV に追記する（無ければ見出し付きで
    作る）。Excel でそのまま開けるよう utf-8-sig で書く。画面を閉じても
    消えないよう、設定ファイルと同じ場所に置く。
    """
    path = conversion_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        is_new = not os.path.isfile(path)
        with open(path, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(LOG_HEADER)
            writer.writerow(row)
    except OSError:
        pass


class App(object):
    def __init__(self, root):
        self.root = root
        self.root.title("PDF文字認識")
        self.root.geometry("640x520")
        self.queue = queue.Queue()
        self.cancel_flag = threading.Event()
        self.busy = False
        self.last_dst_dir = None

        saved = load_gui_settings()
        self.engine1_var = tk.StringVar(
            value=LABEL_OF.get(saved.get("engine1"), LABEL_OF["tesseract"]))
        self.engine2_var = tk.StringVar(
            value=LABEL_OF.get(saved.get("engine2"), LABEL_OF["tesseract"]))
        self.open_after_var = tk.BooleanVar(value=saved.get("open_after", True))

        self._build_ui()
        self._log("変換ログ（ファイルごとの所要秒数）: %s" % conversion_log_path())
        self._poll_queue()

    # ------------------------------------------------------------------
    # 画面
    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="横書きの読み取り:").grid(row=0, column=0, sticky="w")
        self.combo1 = ttk.Combobox(top, textvariable=self.engine1_var,
                                   values=[label for label, _ in ENGINES],
                                   state="readonly", width=42)
        self.combo1.grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(top, text="縦書きの読み取り:").grid(row=1, column=0, sticky="w",
                                                pady=(4, 0))
        self.combo2 = ttk.Combobox(top, textvariable=self.engine2_var,
                                   values=[label for label, _ in ENGINES],
                                   state="readonly", width=42)
        self.combo2.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(4, 0))

        self.drop_area = tk.Label(self.root, relief="groove", bg="#f4f4f4",
                                  height=6, justify="center")
        self.drop_area.pack(fill="x", **pad)
        self.dnd_ok = False
        reason = DND_ERROR
        if HAS_DND:
            if getattr(self.root, "TkdndVersion", None) is None:
                # main() で TkinterDnD.Tk() が失敗し、素の tk.Tk() に
                # 切り替わっている（tkdnd 拡張がこの機械の Tcl に読み込め
                # なかった）。drop_target_register() を試すまでもない。
                # 実際の失敗理由は main() が DND_ERROR に残している。
                if reason is None:
                    reason = "tkdnd 拡張が読み込めなかった（TkinterDnD.Tk() 失敗）"
            else:
                try:
                    self.drop_area.drop_target_register(DND_FILES)
                    self.drop_area.dnd_bind("<<Drop>>", self._on_drop)
                    self.dnd_ok = True
                except Exception as exc:                    # noqa: BLE001
                    # tkinterdnd2 は入っているが、この機械では tkdnd 拡張が
                    # 登録できなかった。ボタンでの選択に静かに切り替える。
                    # tkinterdnd2 の版によって TclError のことも
                    # RuntimeError のこともあるため、広く受ける。
                    reason = "drop_target_register() 失敗（%s: %s）" % (
                        type(exc).__name__, exc)
        self.drop_area.configure(
            text=("ここに PDF をドラッグ＆ドロップ\n（複数・フォルダも可）"
                 if self.dnd_ok else
                 "この画面へのドラッグ＆ドロップは使えません。\n"
                 "下の「PDF を選ぶ…」ボタンを使ってください。\n"
                 "（原因: %s）" % reason))

        buttons = ttk.Frame(self.root)
        buttons.pack(fill="x", padx=10)
        self.choose_button = ttk.Button(buttons, text="PDF を選ぶ…",
                                        command=self._choose_files)
        self.choose_button.pack(side="left")
        self.cancel_button = ttk.Button(buttons, text="キャンセル",
                                        command=self._on_cancel,
                                        state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))
        ttk.Checkbutton(buttons, text="完了後に保存先フォルダを開く",
                        variable=self.open_after_var).pack(side="left", padx=(16, 0))

        status = ttk.Frame(self.root)
        status.pack(fill="x", **pad)
        self.status_var = tk.StringVar(value="待機中")
        ttk.Label(status, textvariable=self.status_var).pack(anchor="w")
        self.progress = ttk.Progressbar(status, mode="determinate")
        self.progress.pack(fill="x", pady=(4, 0))

        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log = scrolledtext.ScrolledText(log_frame, height=12, state="disabled")
        self.log.pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------------
    # 開始
    # ------------------------------------------------------------------
    def _on_drop(self, event):
        paths = list(self.root.tk.splitlist(event.data))
        self._start(paths)

    def _choose_files(self):
        paths = filedialog.askopenfilenames(
            title="変換する PDF を選ぶ",
            filetypes=[("PDF", "*.pdf"), ("すべて", "*.*")])
        if paths:
            self._start(list(paths))

    def _start(self, paths):
        if self.busy:
            messagebox.showinfo("PDF文字認識", "変換が終わってから、次を始めてください。")
            return
        if not paths:
            return
        self.busy = True
        self.cancel_flag.clear()
        self.choose_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.combo1.configure(state="disabled")
        self.combo2.configure(state="disabled")
        self.progress.configure(value=0, maximum=100)
        self.status_var.set("準備しています …")
        engine1 = KEY_OF[self.engine1_var.get()]
        engine2 = KEY_OF[self.engine2_var.get()]
        save_gui_settings({"engine1": engine1, "engine2": engine2,
                           "open_after": bool(self.open_after_var.get())})
        thread = threading.Thread(target=self._worker,
                                  args=(paths, engine1, engine2), daemon=True)
        thread.start()

    def _on_cancel(self):
        self.cancel_flag.set()
        self.status_var.set("キャンセルしています …（今のページまでで打ち切ります）")

    def _on_close(self):
        if self.busy and not messagebox.askyesno(
                "PDF文字認識", "変換中です。終了しますか？"):
            return
        self.cancel_flag.set()
        self.root.destroy()

    # ------------------------------------------------------------------
    # 変換（別スレッド）
    # ------------------------------------------------------------------
    def _worker(self, paths, engine1, engine2):
        try:
            info = pdf_ocr.prepare_conversion(quiet=True)
        except RuntimeError as exc:
            self.queue.put(("error", str(exc)))
            self.queue.put(("done",))
            return

        settings = info["settings"]
        settings["ENGINE1"] = engine1
        settings["ENGINE2"] = engine2
        settings["_PPOCR_CONFIRM"] = self._confirm_from_worker
        settings["_PPOCR_PROGRESS"] = (
            lambda name, done, total:
                self.queue.put(("dl", name, done, total)))

        targets = pdf_ocr.collect_inputs(paths, settings["SUFFIX"])
        if not targets:
            self.queue.put(("error", "変換できる PDF がありません"
                                     "（フォルダの中に .pdf がない、"
                                     "または全部すでに変換済みです）。"))
            self.queue.put(("done",))
            return

        last_dst = None
        shown_fallback = set()
        for file_index, path in enumerate(targets, 1):
            if self.cancel_flag.is_set():
                break
            dst = pdf_ocr.output_path(path, settings, True)
            self.queue.put(("file", file_index, len(targets),
                            os.path.basename(path)))

            def on_progress(current, total, message):
                self.queue.put(("page", current, total, message))

            started_at = time.time()
            when = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                pages, words = pdf_ocr.ocr_pdf(
                    path, dst, settings, info["exe"], info["font_name"],
                    True, quiet=True, retext=False, on_progress=on_progress,
                    cancel=self.cancel_flag.is_set)
            except Exception as exc:                        # noqa: BLE001
                elapsed = time.time() - started_at
                self.queue.put(("filefail", os.path.basename(path),
                                str(exc), elapsed))
                # 実際に使ったエンジンを記録する（PP-OCRv5 が用意できず
                # tesseract に切り替わっていた場合は、選んだ方ではなく
                # settings 側が切り替わった後の値になっている）。
                append_conversion_log([
                    when, os.path.basename(path), "失敗",
                    LABEL_OF.get(settings.get("ENGINE1", engine1), engine1),
                    LABEL_OF.get(settings.get("ENGINE2", engine2), engine2),
                    "", "", "%.1f" % elapsed, str(exc)])
                continue
            finally:
                # 選んだ PP-OCRv5 が用意できず、tesseract に静かに切り替わ
                # った場合、その旨を知らせる（黙って別の結果が出ると、
                # 選んだつもりのエンジンで読んだと誤解されるため）。
                for message in settings.get("_ENGINE_FALLBACK") or []:
                    if message not in shown_fallback:
                        shown_fallback.add(message)
                        shown = (message
                                .replace("ENGINE1:", "横書きの読み取り:")
                                .replace("ENGINE2:", "縦書きの読み取り:"))
                        self.queue.put(("fallback", shown))
            elapsed = time.time() - started_at
            last_dst = dst
            self.queue.put(("filedone", os.path.basename(path),
                            os.path.basename(dst), pages, words, elapsed))
            append_conversion_log([
                when, os.path.basename(path), "成功",
                LABEL_OF.get(settings.get("ENGINE1", engine1), engine1),
                LABEL_OF.get(settings.get("ENGINE2", engine2), engine2),
                pages, words, "%.1f" % elapsed, ""])

        self.queue.put(("alldone", last_dst,
                        bool(self.cancel_flag.is_set())))

    def _confirm_from_worker(self):
        """PP-OCRv5 server を取ってよいか、画面側で確認する（別スレッドから
        呼ばれるので、キューで画面側に頼み、返事が来るまで待つ）。
        """
        done = threading.Event()
        box = {}
        self.queue.put(("confirm", done, box))
        done.wait()
        return box.get("ok", False)

    # ------------------------------------------------------------------
    # 画面の更新（メインスレッド、100ms ごと）
    # ------------------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                self._handle(item)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle(self, item):
        kind = item[0]
        if kind == "confirm":
            _, done, box = item
            box["ok"] = messagebox.askyesno(
                "PP-OCRv5 server の模型",
                "PP-OCRv5 server の模型（165MB）が手元にありません。\n"
                "いま取得しますか？（初回だけです）\n\n"
                "「いいえ」を選ぶと、この変換は tesseract で読みます。")
            done.set()
        elif kind == "dl":
            _, name, done_bytes, total_bytes = item
            if total_bytes:
                self.progress.configure(mode="determinate", maximum=total_bytes,
                                        value=done_bytes)
                self.status_var.set("%s を取得中 … %.1f / %.1f MB"
                                    % (name, done_bytes / 1048576.0,
                                       total_bytes / 1048576.0))
        elif kind == "file":
            _, index, count, name = item
            self.status_var.set("[%d/%d] %s を変換中 …" % (index, count, name))
            self._log("\n%s" % name)
            self.progress.configure(mode="determinate", maximum=100, value=0)
        elif kind == "page":
            _, current, total, message = item
            self.progress.configure(maximum=max(total, 1), value=current)
            self.status_var.set("%d/%d ページ … %s" % (current, total, message))
            self._log("  %d/%d ページ … %s" % (current, total, message))
        elif kind == "filedone":
            _, src_name, dst_name, pages, words, elapsed = item
            self._log("  → %s（%d ページ・%d 個の文字列・%.1f 秒）"
                      % (dst_name, pages, words, elapsed))
        elif kind == "filefail":
            _, name, message, elapsed = item
            self._log("  %s: 失敗しました（%s・%.1f 秒）"
                      % (name, message, elapsed))
        elif kind == "fallback":
            self._log("  ※ %s" % item[1])
        elif kind == "error":
            messagebox.showerror("PDF文字認識", item[1])
            self._log("エラー: %s" % item[1])
        elif kind == "alldone":
            _, last_dst, cancelled = item
            self.status_var.set("キャンセルしました" if cancelled else "完了しました")
            self._log("キャンセルしました" if cancelled else "すべて完了しました")
            if last_dst and self.open_after_var.get() and hasattr(os, "startfile"):
                try:
                    os.startfile(os.path.dirname(last_dst))            # noqa
                except OSError:
                    pass
            self._reset_busy()

    def _reset_busy(self):
        self.busy = False
        self.choose_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.combo1.configure(state="readonly")
        self.combo2.configure(state="readonly")


def main():
    global DND_ERROR
    root = None
    if HAS_DND:
        try:
            root = TkinterDnD.Tk()
        except Exception as exc:                            # noqa: BLE001
            # tkdnd 拡張が読み込めなかったときの例外は、入っている
            # tkinterdnd2 の版によって TclError のことも RuntimeError の
            # こともある（tkdnd を読めないと自ら RuntimeError に包んで
            # 投げ直す版がある）。ここで取りこぼすと画面すら開かずに
            # 落ちてしまうため、広く受けてボタンでの選択に切り替える。
            root = None
            DND_ERROR = "TkinterDnD.Tk() 失敗（%s: %s）" % (
                type(exc).__name__, exc)
    if root is None:
        root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
