@echo off
REM #jww
REM #h1
REM #hc 内部仕上概要表を範囲選択してください
REM #1 仕上表を配置する用紙の左上を指示してください
REM #e
REM ------------------------------------------------------------
REM  Jw_cad 外部変形 : 内部仕上概要表 → 室別の縦組み仕上表
REM
REM  横長の内部仕上概要表を範囲選択すると、罫線から表を読み取って、
REM  1室ぶんずつ縦組みの仕上表（床・巾木・腰壁・壁・天井・備考）を
REM  A3用紙に縦一列で5枠ずつ並べて作図します。
REM  室が6室以上のときは、用紙をそのまま下へ足していきます。
REM
REM  うまくいかないときは、このフォルダにできる
REM  shiage_log.txt を見てください（自動で開きます）。
REM  読み取った表の格子と、室ごとの中身が全部載っています。
REM
REM  上の制御行の意味（この説明文には井桁記号を書かないこと。
REM  Jw_cad が制御文字列として読んでしまうため）
REM    jww … jww形式で座標ファイルを受け取る
REM    h1  … 範囲内の図形データを書き出す
REM    hc  … 範囲選択時に表示するメッセージ
REM    1   … 点を指示させる。指示点は hp1 として渡される
REM    e   … 制御文字列の終わり
REM
REM  元の概要表は削除されません（先頭に hd を出さないため）。
REM ------------------------------------------------------------
setlocal
set "DIR=%~dp0"
set "ERR=%DIR%shiage_error.txt"
set "LOG=%DIR%shiage_log.txt"

set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python が見つかりません。> "%ERR%"
  echo コマンドプロンプトで py --version が動くか確認してください。>> "%ERR%"
  notepad "%ERR%"
  goto :eof
)

"%PY%" "%DIR%shiage.py" 2> "%ERR%"
if errorlevel 1 goto :failed
goto :eof

:failed
echo. >> "%ERR%"
echo ---- 詳しい記録は shiage_log.txt を見てください ---- >> "%ERR%"
if exist "%LOG%" (notepad "%LOG%") else (notepad "%ERR%")
