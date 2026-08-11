@echo off
REM ------------------------------------------------------------
REM  Jw_cad なしで動作を確認するためのテスト用バッチ。
REM  sample_平面図.txt を jwc_temp.txt にコピーして
REM  jww_ceiling_plan.py を実行し、結果をメモ帳で開きます。
REM  （このファイルには jww の制御行が無いので、Jw_cad の
REM    外部変形メニューには表示されません）
REM ------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PYTHON="
if not defined PYTHON (
    py -3 -V >nul 2>&1 && set "PYTHON=py -3"
)
if not defined PYTHON (
    python -V >nul 2>&1 && set "PYTHON=python"
)
if not defined PYTHON goto :nopython

copy /y "sample_平面図.txt" "jwc_temp.txt" >nul
%PYTHON% "..\jww_ceiling_plan.py" "jwc_temp.txt" "..\天伏図ルール.txt"
if errorlevel 1 goto :err

echo.
echo 結果を jwc_temp.txt に出力しました。
notepad "jwc_temp.txt"
goto :eof

:err
echo エラーが発生しました。jwc_temp.txt の内容を確認してください。
notepad "jwc_temp.txt"
pause
goto :eof

:nopython
echo Python が見つかりません。Python をインストールしてください。
pause
