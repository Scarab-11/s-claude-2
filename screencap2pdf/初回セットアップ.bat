@echo off
rem 必要なライブラリをインストールする（初回だけ実行）
chcp 65001 > nul
cd /d "%~dp0"

echo 使う Python を確認します...
python -c "import sys; print(sys.executable)" || goto :nopython
echo.

echo ライブラリをインストールします...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.

echo ---- 確認 ----
python -m s2pdf doctor
echo.
echo 上に「必要なライブラリはそろっています」と出ていれば準備完了です。
echo キャプチャPDF_GUI.bat を実行してください。
pause
exit /b

:nopython
echo.
echo Python が見つかりませんでした。
echo https://www.python.org/ からインストールし、
echo インストール画面の「Add python.exe to PATH」にチェックを入れてください。
pause
exit /b 1
