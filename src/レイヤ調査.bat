@echo off
REM #jww
REM #h2
REM #hc 平面図を範囲選択してください（文字を含む）
REM #e
REM ------------------------------------------------------------
REM  Jw_cad 外部変形 : レイヤ調査
REM
REM  範囲選択したデータが、どのレイヤに何本入っているかを調べて
REM  メモ帳に表示します。図面には何も書きません。
REM
REM  天伏図ルール.txt の KEEP / WALL_FROM / SYMBOL_LAYER に書く
REM  レイヤ番号は、これで調べてください。
REM
REM  線の長さを見ると区別がつきます。
REM    長い線ばかり      壁の中心線か基準線
REM    短い線がたくさん  建具・柱・家具
REM    文字だけ          部屋名
REM ------------------------------------------------------------
setlocal

set "PYTHON="
if not defined PYTHON (
    py -3 -V >nul 2>&1 && set "PYTHON=py -3"
)
if not defined PYTHON (
    python -V >nul 2>&1 && set "PYTHON=python"
)
if not defined PYTHON goto :nopython

%PYTHON% "%~dp0jww_ceiling_plan.py" "" "%~dp0天伏図ルール.txt" --layers
start "" notepad "%~dp0jww_ceiling_plan.log"
goto :eof

:nopython
echo he Python が見つかりません。Python をインストールするか、天井伏図生成.bat の PYTHON の行に python.exe の場所を書いてください。> jwc_temp.txt
goto :eof
