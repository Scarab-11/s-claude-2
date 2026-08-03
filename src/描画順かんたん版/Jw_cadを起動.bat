@echo off
setlocal
rem ============================================================
rem  Jw_cad と [線の重なり順] ボタンを一緒に起動する
rem
rem  このバッチのショートカットをデスクトップに作り、ふだんの
rem  Jw_cad のアイコンの代わりにこれを使ってください。
rem  Jw_cad を起動するたびに、ボタンも一緒に出ます。
rem
rem  スタートアップに登録するより確実です。
rem ============================================================

set "PF86=%ProgramFiles(x86)%"
set "JW="

for %%P in (
 "C:\jww\jw_win.exe"
 "D:\jww\jw_win.exe"
 "E:\jww\jw_win.exe"
 "%SystemDrive%\jww\jw_win.exe"
 "%ProgramFiles%\jww\jw_win.exe"
 "%PF86%\jww\jw_win.exe"
) do if not defined JW if exist "%%~P" set "JW=%%~P"

if not defined JW goto NOJW

start "" "%JW%"
call "%~dp0ボタンを出す.bat"
exit /b

:NOJW
echo.
echo  jw_win.exe が見つかりませんでした。
echo.
echo  Jw_cad をふだんどおり起動してから、
echo  「ボタンを出す.bat」をダブルクリックしてください。
echo  ボタンだけ後から出しても、動きは同じです。
echo.
pause
exit /b
