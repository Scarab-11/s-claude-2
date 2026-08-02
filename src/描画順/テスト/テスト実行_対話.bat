@echo off
REM ------------------------------------------------------------
REM  Jw_cad なしで動作を確認するためのテスト用バッチ（対話式）。
REM  sample_jwc_temp.txt を jwc_temp.txt にコピーして
REM  jww_draw_order.vbs を引数なしで実行します。
REM  並べ方・番号の種類・番号を実際に入力して試せます。
REM ------------------------------------------------------------
setlocal
cd /d "%~dp0"
copy /y "sample_jwc_temp.txt" "jwc_temp.txt" >nul
cscript //nologo "..\jww_draw_order.vbs"
if errorlevel 1 goto :err
echo.
echo 結果を jwc_temp.txt に出力しました。
notepad "jwc_temp.txt"
goto :eof
:err
echo エラーが発生しました。
pause
