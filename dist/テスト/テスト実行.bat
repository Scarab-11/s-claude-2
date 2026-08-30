@echo off
REM ------------------------------------------------------------
REM  Jw_cad なしで動作を確認するためのテスト用バッチ。
REM  sample_jwc_temp.txt を jwc_temp.txt にコピーして
REM  jww_text_align.vbs を実行し、結果をメモ帳で開きます。
REM  （このファイルには jww の制御行が無いので、Jw_cad の
REM    外部変形メニューには表示されません）
REM ------------------------------------------------------------
setlocal
cd /d "%~dp0"
copy /y "sample_jwc_temp.txt" "jwc_temp.txt" >nul
cscript //nologo "..\jww_text_align.vbs"
if errorlevel 1 goto :err
echo.
echo 結果を jwc_temp.txt に出力しました。
notepad "jwc_temp.txt"
goto :eof
:err
echo エラーが発生しました。
pause
