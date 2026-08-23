@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    set PYCMD=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PYCMD=py
    ) else (
        echo Python が見つかりませんでした。
        echo https://www.python.org/downloads/ からインストールしてください。
        echo （インストール時に「Add python.exe to PATH」に必ずチェックを入れてください）
        pause
        exit /b 1
    )
)

echo サーバーを起動しています...
echo このウィンドウを閉じるとアプリは使えなくなります。閉じずにそのままにしておいてください。
echo.

start "" cmd /c "timeout /t 2 >nul && start http://localhost:8000"
%PYCMD% -m http.server 8000

echo.
echo サーバーが終了しました。
pause
