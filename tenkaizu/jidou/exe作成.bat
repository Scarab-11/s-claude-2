@echo off
REM ------------------------------------------------------------
REM  tenkaizu.exe を作ります
REM
REM  このバッチを走らせるPCにだけ Python と PyInstaller が要ります。
REM  出来上がった「配布用」フォルダを相手に渡せば、
REM  相手のPCには Python は要りません。
REM
REM  使い方 : このバッチをダブルクリックするだけ
REM           exe作成.bat onedir  と打つと、1ファイルではなく
REM           フォルダ一式で作ります（ウイルス対策ソフトの誤検知が減ります）
REM ------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python が見つかりません。
  echo python.org からインストールしてください。
  echo インストール時に「Add python.exe to PATH」にチェックを入れること。
  pause
  exit /b 1
)
echo 使う Python :
"%PY%" --version

echo.
echo ---- PyInstaller を用意します ----
"%PY%" -m pip install --upgrade --disable-pip-version-check pyinstaller
if errorlevel 1 (
  echo PyInstaller を入れられませんでした。ネットにつながっているか確認してください。
  pause
  exit /b 1
)

set "MODE=--onefile"
if /i "%~1"=="onedir" set "MODE=--onedir"

echo.
echo ---- exe を作ります  %MODE% ----
"%PY%" -m PyInstaller %MODE% --console --clean --noconfirm --noupx --name tenkaizu --workpath "%~dp0_build" --distpath "%~dp0_dist" --specpath "%~dp0_build" "%~dp0tenkaizu.py"
if errorlevel 1 (
  echo ビルドに失敗しました。
  pause
  exit /b 1
)

echo.
echo ---- 配布用フォルダを作ります ----
set "OUT=%~dp0配布用"
if exist "%OUT%" rd /s /q "%OUT%"
mkdir "%OUT%"
if /i "%MODE%"=="--onefile" (
  copy /y "%~dp0_dist\tenkaizu.exe" "%OUT%\" >nul
) else (
  xcopy /e /i /y "%~dp0_dist\tenkaizu" "%OUT%" >nul
)
copy /y "%~dp0展開図_自動作図.bat" "%OUT%\" >nul
copy /y "%~dp0tenkaizu_setting.txt" "%OUT%\" >nul

rd /s /q "%~dp0_build" 2>nul
rd /s /q "%~dp0_dist" 2>nul

echo.
echo ============================================================
echo  完成しました。
echo.
echo  「配布用」フォルダの中身を、相手のPCの
echo  Jw_cad 外部変形フォルダ（例 C:\jww\外変\）にコピーしてください。
echo  相手のPCに Python は要りません。
echo.
echo  設定を変えるときは、同じフォルダの tenkaizu_setting.txt を
echo  メモ帳で書き換えます（exe を作り直す必要はありません）。
echo ============================================================
echo.
pause
