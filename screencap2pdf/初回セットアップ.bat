@echo off
rem 必要なライブラリをインストールする（初回だけ実行）
chcp 65001 > nul
cd /d "%~dp0"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo セットアップが終わりました。キャプチャPDF_GUI.bat を実行してください。
pause
