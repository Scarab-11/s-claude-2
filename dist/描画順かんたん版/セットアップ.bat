@echo off
setlocal
rem ============================================================
rem  線の重なり順  セットアップ
rem
rem  このバッチをダブルクリックするだけで、
rem    ・必要なファイルを %USERPROFILE%\線の重なり順 へ入れる
rem    ・デスクトップに起動用ショートカットを作る
rem    ・Jw_cad とボタンを起動する
rem  まで終わります。
rem
rem  置き場所を %USERPROFILE% にするのは、
rem    ・必ず存在する
rem    ・必ず書き込みができる（jwc_temp.txt が作れる）
rem    ・OneDrive に移動されない（ドキュメントは移動される）
rem  ためです。
rem ============================================================

set "DEST=%USERPROFILE%\線の重なり順"
set "SRC=%~dp0"

echo.
echo  ============================================================
echo   線の重なり順  セットアップ
echo  ============================================================
echo.
echo   組み込み先
echo       %DEST%
echo.
echo   Enter キーを押すと始めます。やめるときはこの窓を閉じてください。
echo.
pause >nul

if not exist "%SRC%線の重なり順を直す.bat" goto NOSRC
if not exist "%SRC%jww_draw_order.vbs"     goto NOSRC

echo   ファイルを入れています ...

if not exist "%DEST%" mkdir "%DEST%"
if not exist "%DEST%" goto NOMKDIR

copy /y "%SRC%線の重なり順を直す.bat" "%DEST%\" >nul
copy /y "%SRC%jww_draw_order.vbs"     "%DEST%\" >nul
copy /y "%SRC%ボタンを出す.ahk"        "%DEST%\" >nul
copy /y "%SRC%ボタンを出す.bat"        "%DEST%\" >nul
copy /y "%SRC%Jw_cadを起動.bat"        "%DEST%\" >nul
copy /y "%SRC%お読みください.txt"      "%DEST%\" >nul

rem --- 本当に書き込めるか確かめる（ここが駄目だと外部変形が動かない）
echo test> "%DEST%\書き込み確認.tmp" 2>nul
if not exist "%DEST%\書き込み確認.tmp" goto NOWRITE
del "%DEST%\書き込み確認.tmp" >nul 2>&1

rem --- デスクトップにショートカットを作る ---------------------
echo   デスクトップにショートカットを作っています ...

set "VBS=%TEMP%\jwsc_mklnk.vbs"
>"%VBS%"  echo Set s = CreateObject("WScript.Shell")
>>"%VBS%" echo Set l = s.CreateShortcut(s.SpecialFolders("Desktop") ^& "\Jw_cad（線の重なり順つき）.lnk")
>>"%VBS%" echo l.TargetPath = "%DEST%\Jw_cadを起動.bat"
>>"%VBS%" echo l.WorkingDirectory = "%DEST%"
>>"%VBS%" echo l.Description = "Jw_cad と [線の重なり順] ボタンを一緒に起動します"
>>"%VBS%" echo l.Save
cscript //nologo "%VBS%" >nul 2>&1
del "%VBS%" >nul 2>&1

rem --- AutoHotkey があるか調べる ------------------------------
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

echo.
echo  ------------------------------------------------------------
echo   組み込みが終わりました。
echo  ------------------------------------------------------------
echo.
echo   デスクトップに
echo       Jw_cad（線の重なり順つき）
echo   というショートカットを作りました。
echo   これからは、これで Jw_cad を起動してください。
echo.
echo   ★ 最初の 1 回だけ、Jw_cad 側の操作が要ります。
echo.
echo     [線の重なり順] ボタンを押すと「ファイル選択」の窓が出ます。
echo     左の一覧を
echo         C: ^> Users ^> %USERNAME% ^> 線の重なり順
echo     とたどり、右に出る
echo         線の重なり順を直す.bat
echo     をダブルクリックしてください。
echo     Jw_cad がこの場所を覚えるので、次からはボタン 1 回だけです。
echo.
echo   Enter キーを押すと、Jw_cad とボタンを起動します。
echo.
pause >nul

start "" "%DEST%\Jw_cadを起動.bat"
exit /b


:NOSRC
echo.
echo  [できません] 必要なファイルが同じフォルダにありません。
echo.
echo   zip の中から直接このバッチを実行していませんか。
echo   いったん zip を右クリックして [すべて展開] してから、
echo   出てきたフォルダの中の セットアップ.bat を
echo   ダブルクリックしてください。
echo.
pause
exit /b


:NOMKDIR
echo.
echo  [できません] フォルダを作れませんでした。
echo       %DEST%
echo.
pause
exit /b


:NOWRITE
echo.
echo  [できません] 次の場所に書き込めません。
echo       %DEST%
echo.
echo   外部変形は動くときに jwc_temp.txt というファイルを
echo   ここに作るので、書き込めないと並べ替えができません。
echo.
pause
exit /b


:NOAHK
echo.
echo  ------------------------------------------------------------
echo   ファイルの組み込みは終わりました。あと 1 つだけ要ります。
echo  ------------------------------------------------------------
echo.
echo   AutoHotkey v2 が入っていません。ボタンを使うにはこれが要ります。
echo   無料です。
echo.
echo   Enter キーを押すと、配布ページをブラウザで開きます。
echo   入れ終わったら、もう一度 セットアップ.bat を
echo   ダブルクリックしてください。
echo.
pause >nul
start "" "https://www.autohotkey.com/"
echo.
echo   （ボタンを使わない方法もあります。お読みください.txt の
echo     「使い方 B」をご覧ください。追加ソフトは要りません。）
echo.
pause
exit /b
