"""このフォルダをブラウザから開けるようにする簡易サーバー。

`python -m http.server` はキャッシュに関する指示を何も返さないため、
ブラウザが独自の判断で古いファイルを使い続けることがあります。
git pull で更新したのに画面が変わらない、という状態はこれが原因です。

アプリ本体（index.html / app.js / style.css）は毎回読み直させ、
容量が大きく中身が変わらない vendor/ だけキャッシュを許可します。
"""
import http.server
import os
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path.startswith("/vendor/"):
            self.send_header("Cache-Control", "public, max-age=604800")
        else:
            self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()


class Server(socketserver.TCPServer):
    # Without this, restarting the server right after stopping it fails
    # with "Address already in use" for a minute or so.
    allow_reuse_address = True


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:
        with Server(("", PORT), NoCacheHandler) as httpd:
            print(f"サーバーを起動しました: http://localhost:{PORT}")
            print("このウィンドウを閉じるとサーバーが止まります。")
            print("-" * 60)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n終了しました。")
    except OSError as err:
        print(f"サーバーを起動できませんでした: {err}")
        print(f"別のウィンドウで既に起動している場合は、そのまま http://localhost:{PORT} を開いてください。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
