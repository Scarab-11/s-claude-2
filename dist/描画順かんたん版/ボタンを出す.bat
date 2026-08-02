@echo off
setlocal
rem ============================================================
rem  線の重なり順 ボタンを出す
rem
rem  ボタンを出す.ahk をダブルクリックすると Jw_cad が開いて
rem  しまう場合は、このバッチをダブルクリックしてください。
rem  AutoHotkey を探して、直接そこから起動します。
rem ============================================================

set "PF86=%ProgramFiles(x86)%"
set "AHK="

for %%P in (
 "%ProgramFiles%\AutoHotkey\v2\AutoHotkey64.exe"
 "%ProgramFiles%\AutoHotkey\v2\AutoHotkey32.exe"
 "%PF86%\AutoHotkey\v2\AutoHotkey64.exe"
 "%PF86%\AutoHotkey\v2\AutoHotkey32.exe"
 "%LOCALAPPDATA%\Programs\AutoHotkey\v2\AutoHotkey64.exe"
 "%LOCALAPPDATA%\Programs\AutoHotkey\v2\AutoHotkey32.exe"
 "%ProgramFiles%\AutoHotkey\AutoHotkey.exe"
 "%PF86%\AutoHotkey\AutoHotkey.exe"
) do if not defined AHK if exist "%%~P" set "AHK=%%~P"

if not defined AHK goto NOAHK
if not exist "%~dp0ボタンを出す.ahk" goto NOFILE

start "" "%AHK%" "%~dp0ボタンを出す.ahk"
exit /b

:NOAHK
echo.
echo  AutoHotkey が見つかりませんでした。
echo.
echo  ボタンを使うには AutoHotkey v2 が必要です。
echo      https://www.autohotkey.com/
echo  からダウンロードして入れてください（無料）。
echo.
echo  入れたくない場合は、ボタンなしでも使えます。
echo  お読みください.txt の「使い方 B」をご覧ください。
echo.
pause
exit /b

:NOFILE
echo.
echo  ボタンを出す.ahk が同じフォルダにありません。
echo.
pause
exit /b
