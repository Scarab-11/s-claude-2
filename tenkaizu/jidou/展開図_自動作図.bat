@echo off
REM #jww
REM #h1
REM #hc 平面図全体を範囲選択してください
REM #1 展開図を配置する位置（左上）を指示してください
REM #e
REM ------------------------------------------------------------
REM  Jw_cad 外部変形 : 平面図から展開図を自動作図する
REM
REM  壁芯の一点鎖線から室を検出し、各室の A～D 面を作図します。
REM  室名と天井高（ch=2500 の形）が両方ある室だけが対象です。
REM
REM  うまくいかないときは、このフォルダにできる
REM  tenkaizu_log.txt を見てください（自動で開きます）。
REM
REM  上の制御行の意味（この説明文には井桁記号を書かないこと。
REM  Jw_cad が制御文字列として読んでしまうため）
REM    jww … jww形式で座標ファイルを受け取る
REM    h1  … 範囲内の図形データを書き出す
REM    hc  … 範囲選択時に表示するメッセージ
REM    1   … 点を指示させる。指示点は hp1 として渡される
REM    e   … 制御文字列の終わり
REM
REM  平面図は削除されません（先頭に hd を出さないため）。
REM ------------------------------------------------------------
setlocal
set "DIR=%~dp0"
set "ERR=%DIR%tenkaizu_error.txt"
set "LOG=%DIR%tenkaizu_log.txt"

REM ---- exe があればそれを使う（配布先に Python は不要）----
if exist "%DIR%tenkaizu.exe" (
  "%DIR%tenkaizu.exe" 2> "%ERR%"
  if errorlevel 1 goto :failed
  goto :eof
)

REM ---- exe が無ければ Python でスクリプトを実行する ----
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python が見つかりません。> "%ERR%"
  echo コマンドプロンプトで py --version が動くか確認してください。>> "%ERR%"
  echo.>> "%ERR%"
  echo Python を入れずに使うには、exe作成.bat で作った>> "%ERR%"
  echo tenkaizu.exe をこのフォルダに置いてください。>> "%ERR%"
  notepad "%ERR%"
  goto :eof
)

"%PY%" "%DIR%tenkaizu.py" 2> "%ERR%"
if errorlevel 1 goto :failed
goto :eof

:failed
echo. >> "%ERR%"
echo ---- 詳しい記録は tenkaizu_log.txt を見てください ---- >> "%ERR%"
if exist "%LOG%" (notepad "%LOG%") else (notepad "%ERR%")
