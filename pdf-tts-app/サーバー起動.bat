@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Each check is on its own line and branches with goto: %errorlevel%
rem inside a parenthesised if-block is expanded when the block is parsed
rem rather than when it runs, and "if cond cmd && cmd2" is ambiguous.
set "PYCMD="
where python >nul 2>nul && set "PYCMD=python"
if defined PYCMD goto :found_python
where py >nul 2>nul && set "PYCMD=py"
if defined PYCMD goto :found_python
goto :no_python

:found_python
echo ============================================================
echo  このウィンドウは閉じないでください。
echo  閉じるとサーバーが止まり、アプリが開けなくなります。
echo  終わるときに、このウィンドウを閉じてください。
echo ============================================================
echo.
echo サーバーを起動しています...

set "EDGE="
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "EDGE=1"
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "EDGE=1"
if defined EDGE goto :open_edge

echo 既定のブラウザで開きます。
start "" cmd /c "timeout /t 2 >nul && start http://localhost:8000"
goto :serve

:open_edge
echo Microsoft Edge で開きます（高音質な音声が使えます）。
start "" cmd /c "timeout /t 2 >nul && start microsoft-edge:http://localhost:8000"

:serve
echo.
%PYCMD% -m http.server 8000

echo.
echo サーバーが終了しました。
pause
exit /b 0

:no_python
echo Python が見つかりませんでした。
echo https://www.python.org/downloads/ からインストールしてください。
echo （インストール時に「Add python.exe to PATH」に必ずチェックを入れてください）
pause
exit /b 1
