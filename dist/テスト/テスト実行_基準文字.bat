@echo off
REM ------------------------------------------------------------
REM  基準文字を指示した場合（hp1 あり）の動作確認用。
REM  sample_基準文字.txt には hp1 105 191 が入っているので、
REM  その点に一番近い「かきく」が基準文字になります。
REM ------------------------------------------------------------
setlocal
cd /d "%~dp0"
copy /y "sample_基準文字.txt" "jwc_temp.txt" >nul
cscript //nologo "..\jww_text_align.vbs"
if errorlevel 1 goto :err
echo.
echo 結果を jwc_temp.txt に出力しました。
notepad "jwc_temp.txt"
goto :eof
:err
echo エラーが発生しました。
pause
