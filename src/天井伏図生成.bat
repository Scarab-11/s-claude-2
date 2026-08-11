@echo off
REM #jww
REM #h0
REM #hc 平面図を範囲選択してください（文字を含む）
REM #1 天井伏図を作図する位置（左下）を指示してください
REM #e
REM ------------------------------------------------------------
REM  Jw_cad 外部変形 : 天井伏図生成
REM
REM  範囲選択した平面図から、天井伏図のたたき台を作ります。
REM  室名の文字を見つけて天井仕上記号を書き、仕上表を付けます。
REM  元の平面図は消えません。指示した点を左下として作図します。
REM
REM  どの室にどの記号を書くか、どのレイヤを落とすかは
REM  天伏図ルール.txt で指定します。
REM
REM  動作には Python 3.8 以上が必要です。
REM  py ランチャーと python の両方が見つからない場合は、下の
REM  PYTHON の行に python.exe の場所を直接書いてください。
REM    例  set "PYTHON=C:\Python311\python.exe"
REM
REM  上の制御行の意味（この説明文には井桁記号を書かないこと）
REM    jww … jww形式で座標ファイルを受け取る
REM    h0  … 範囲内の図形データを jwc_temp.txt に書き出す
REM    hc  … 範囲選択時に表示するメッセージ
REM    1   … 点を指示させる。指示点は hp1 として渡される
REM    e   … 制御文字列の終わり
REM ------------------------------------------------------------
setlocal

set "PYTHON="

REM py ランチャーを先に試す。python.org のインストーラが入れるもので、
REM 「PATH に追加」にチェックを入れていなくても使えます。
if not defined PYTHON (
    py -3 -V >nul 2>&1 && set "PYTHON=py -3"
)
if not defined PYTHON (
    python -V >nul 2>&1 && set "PYTHON=python"
)
if not defined PYTHON goto :nopython

%PYTHON% "%~dp0jww_ceiling_plan.py" "" "%~dp0天伏図ルール.txt"
goto :eof

:nopython
echo he Python が見つかりません。Python をインストールするか、天井伏図生成.bat の PYTHON の行に python.exe の場所を書いてください。> jwc_temp.txt
goto :eof
