@echo off
REM ------------------------------------------------------------
REM  Jw_cad なしで動作を確認するためのテスト用バッチ。
REM  sample_jwc_temp.txt を jwc_temp.txt にコピーして
REM  jww_draw_order.vbs を「線色番号順（大きい番号が上）」で
REM  実行し、結果をメモ帳で開きます。
REM  （このファイルには jww の制御行が無いので、Jw_cad の
REM    外部変形メニューには表示されません）
REM
REM  結果の jwc_temp.txt は、上から下へ
REM    線色1 → 線色2 → 線色3 → 線色4 → 線色5 → 線色8
REM  の順に並んでいれば正常です（後にあるものほど上に描画）。
REM  分類できない sc 行が sl 行の直前に残っていることも
REM  あわせて確認してください。
REM ------------------------------------------------------------
setlocal
cd /d "%~dp0"
copy /y "sample_jwc_temp.txt" "jwc_temp.txt" >nul
cscript //nologo "..\jww_draw_order.vbs" /m:1 /k:1 /q
if errorlevel 1 goto :err
echo.
echo 結果を jwc_temp.txt に出力しました。
notepad "jwc_temp.txt"
goto :eof
:err
echo エラーが発生しました。
pause
