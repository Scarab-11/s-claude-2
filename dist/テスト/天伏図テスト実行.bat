@echo off
REM ------------------------------------------------------------
REM  Jw_cad なしで動作を確認するためのテスト用バッチ。
REM  sample_平面図.txt を jwc_temp.txt にコピーして
REM  jww_ceiling_plan.rb を実行し、結果をメモ帳で開きます。
REM  （このファイルには jww の制御行が無いので、Jw_cad の
REM    外部変形メニューには表示されません）
REM ------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "RUBY=ruby"

"%RUBY%" -v >nul 2>&1
if errorlevel 1 goto :noruby

copy /y "sample_平面図.txt" "jwc_temp.txt" >nul
"%RUBY%" "..\jww_ceiling_plan.rb" "jwc_temp.txt" "..\天伏図ルール.txt"
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

:noruby
echo Ruby が見つかりません。Ruby をインストールして PATH を通してください。
pause
