@echo off
rem ===================================================================
rem  PDF文字認識 － これ 1 本ですべての操作ができます。
rem
rem   ・PDF（またはフォルダ）をドラッグ＆ドロップ → そのまま変換
rem   ・ダブルクリック（準備がまだ）             → そのまま準備する
rem   ・ダブルクリック（準備ずみ）               → 変換するファイルを聞く
rem
rem  読み取り方は自動で決めます。横書き・縦書き・図面のどれでも、
rem  そのまま落としてください。
rem  調べる・入れ直すといった、ふだん使わない操作は m を打つと出ます。
rem ===================================================================
chcp 932 >nul
setlocal EnableExtensions
set "HERE=%~dp0"
title PDF文字認識

rem ---- ドラッグ＆ドロップされたファイルを組み直す ----
set "ARGS="
:collect
if "%~1"=="" goto have_args
set ARGS=%ARGS% "%~1"
shift
goto collect

:have_args

rem ---- Python を探す（py ランチャー優先） ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
set "PYTHONIOENCODING=cp932:replace"

if not defined PY (
  echo.
  echo   Python が見つかりません。
  echo.
  echo   https://www.python.org/downloads/windows/ から Python を入れてください。
  echo   インストール画面の「Add python.exe to PATH」に必ずチェックを入れます。
  echo   入れ終わったら、このバッチをダブルクリックしてください。
  echo   そのまま準備が始まります。
  echo.
  pause
  exit /b 2
)

rem ---- ファイルが落とされていれば、迷わずそのまま変換する ----
if defined ARGS goto convert

rem ---- 準備ができていなければ、メニューを出さずにそのまま準備する ----
rem 初回に開いていきなり番号を選ばせるのは、こちらの都合。やることが
rem 1 つしかない場面で選択肢を出さない。
%PY% "%HERE%pdf_ocr.py" --selftest --no-download --quiet >nul 2>nul
if errorlevel 1 (
  echo.
  echo   まだ準備ができていないので、これから準備します。
  echo   （初回だけです。次からは、この画面は出ません）
  echo.
  goto setup
)

rem ===================================================================
rem  準備ずみでダブルクリックされたとき
rem
rem  ここで番号の一覧を出すのは誤りだった。ふだんやることは「PDF を
rem  変換する」の 1 つしかないのに、[1]～[7] を並べて選ばせると、
rem  何を選べばよいのか・全部やるのかが分からなくなる。用があるのは
rem  1 つだけなので、聞くことも 1 つだけにする。
rem ===================================================================
:ready
cls
echo.
echo   ===============================================================
echo    PDF文字認識    準備はできています
echo   ===============================================================
echo.
echo    ふだんの使い方は 1 つだけです。
echo    変換したい PDF を、この PDF文字認識.bat のアイコンに
echo    ドラッグ＆ドロップしてください。それだけで変換されます。
echo.
echo    ですので、この画面はそのまま閉じてかまいません。
echo.
echo   ---------------------------------------------------------------
echo    この画面から変換することもできます。
echo    変換したい PDF を、下の枠にドラッグ＆ドロップして Enter。
echo.
echo      何も入れずに Enter …… 閉じる
echo      m と打って Enter …… その他の操作（調べる・入れ直す など）
echo   ---------------------------------------------------------------
echo.
set "DROP="
set /p "DROP=  ここへ: "
if not defined DROP exit /b 0
set DROP=%DROP:"=%
if not defined DROP exit /b 0
if /i "%DROP%"=="m" goto menu
set ARGS="%DROP%"
set "EXTRA="
set "FROMREADY=1"
goto convert

rem ===================================================================
rem  その他の操作（ready の画面で m を打ったとき）
rem ===================================================================
:menu
cls
echo.
echo   ===============================================================
echo    PDF文字認識
echo   ===============================================================
echo.
echo    ふだんの変換に、この画面は要りません。
echo    下のことをしたいときだけ使います。
echo.
echo    ---------------------------------------------------------------
echo     [1] 準備をやり直す（tesseract を入れ直したときなど）
echo     [2] PDF を変換する（ファイルの場所を入力）
echo     [3] 元から入っている文字を消してから変換し直す
echo     [4] PDF の中身を調べる（変換はしません）
echo     [5] 読み取りの調査ファイルを作る（不具合を調べてもらうとき）
echo     [6] 動作確認をする（同梱のサンプルで試す）
echo     [7] 使い方.txt を開く
echo     [8] 画面で操作する（GUI。読み取りエンジンを横書き・縦書き別に選べる）
echo     [0] 前の画面に戻る
echo    ---------------------------------------------------------------
echo.
echo    やりたいことの番号を 1 つだけ打って Enter を押します。
echo    （例  4  と打って Enter。順番に全部を実行するものではありません）
echo.
set "SEL="
set /p "SEL=  どれにしますか（番号を 1 つ）: "

rem 画面の [1] をそのまま写して「[1]」と打つ人がいる。全角で打つ人もいる。
rem 弾いて黙って画面を描き直すと、何が悪いのか分からないまま同じ画面が
rem 出続けることになるので、直せるものはこちらで直してから見比べる。
set "SEL=%SEL:[=%"
set "SEL=%SEL:]=%"
set "SEL=%SEL: =%"
set "SEL=%SEL:０=0%"
set "SEL=%SEL:１=1%"
set "SEL=%SEL:２=2%"
set "SEL=%SEL:３=3%"
set "SEL=%SEL:４=4%"
set "SEL=%SEL:５=5%"
set "SEL=%SEL:６=6%"
set "SEL=%SEL:７=7%"

if "%SEL%"=="1" goto setup
if "%SEL%"=="2" goto ask_convert
if "%SEL%"=="3" goto ask_retext
if "%SEL%"=="4" goto ask_check
if "%SEL%"=="5" goto ask_dump
if "%SEL%"=="6" goto selftest
if "%SEL%"=="7" goto readme
if "%SEL%"=="8" goto gui
if "%SEL%"=="0" goto ready

rem 入れられた文字はそのまま画面に出さない。& や > が混ざっていると、
rem echo の行がそこで切れて別の命令として動いてしまうため。
echo.
echo   その入力では選べません。
echo   0 から 8 の数字を 1 つだけ打って Enter を押してください。
echo   （かっこや記号は要りません。複数の番号もまとめて打てません）
echo.
pause
goto menu

rem ---- ファイルの場所を聞く（枠にドラッグしても入ります） ----
:ask_convert
call :ask_path "変換する PDF" || goto menu
set "EXTRA="
goto convert

:ask_retext
call :ask_path "文字を入れ直す PDF" || goto menu
set "EXTRA=--retext"
goto convert

:ask_check
call :ask_path "調べる PDF" || goto menu
echo.
%PY% "%HERE%pdf_ocr.py" --check %ARGS%
goto after

:ask_dump
echo.
echo   読み取りの中身を 元の名前_調査.txt に書き出します。
echo   ページ数が多いと大きくなるので、問題のあるページだけを
echo   抜き出した PDF を落とすのがおすすめです。
call :ask_path "調べる PDF" || goto menu
echo.
%PY% "%HERE%pdf_ocr.py" --dumpocr %ARGS%
goto after

:ask_path
echo.
echo   %~1 を、この枠にドラッグ＆ドロップして Enter を押してください。
echo   （何も入れずに Enter でメニューに戻ります）
echo.
set "DROP="
set /p "DROP=  ここへ: "
if not defined DROP exit /b 1
rem エクスプローラからドラッグすると引用符が付き、手で打つと付かない。
rem いったん外してから付け直して、どちらでも通るようにする。
set DROP=%DROP:"=%
if not defined DROP exit /b 1
set ARGS="%DROP%"
exit /b 0

rem ===================================================================
rem  各処理
rem ===================================================================
:setup
cls
echo.
echo   準備をします
echo   ============
echo.
echo   [1/3] 必要な部品を入れます（少し時間がかかります）
%PY% -m pip install --upgrade pip
rem tkinterdnd2 は画面（GUI）のドラッグ＆ドロップ用。onnxruntime 以下 4 つは
rem PP-OCRv5（mobile は同梱、server は選んだときに確認して取得）を動かす
rem ためのもの。いつもの読み取り（tesseract）だけなら使わないが、あとから
rem 画面で選べるように、ここでまとめて用意しておく。
%PY% -m pip install --upgrade pypdfium2 pypdf reportlab pillow tkinterdnd2 ^
    onnxruntime opencv-python-headless pyclipper shapely
if errorlevel 1 (
  echo.
  echo   部品を入れられませんでした。
  echo   社内ネットワークのプロキシ等で pip がつながらない場合があります。
  goto after
)
echo.
echo   [2/3] 日本語（縦書きを含む）の言語データを用意します
%PY% "%HERE%pdf_ocr.py" --install-langs
if errorlevel 2 (
  echo.
  echo   言語データが足りません。上の案内を見て手当てしてください。
  echo   （OCR 本体の tesseract が入っていない場合は、先にそちらを入れます。
  echo     入れ方は 使い方.txt の「1. 準備」をご覧ください）
  goto after
)
echo.
echo   [3/3] OCR 本体（tesseract）を確認します
%PY% "%HERE%pdf_ocr.py" --selftest
if errorlevel 1 (
  echo.
  echo   tesseract を入れたあと、もう一度このバッチをダブルクリック
  echo   してください。
  echo   入れ方は 使い方.txt の「1. 準備」をご覧ください。
  goto after
)
echo.
echo   準備ができました。
echo.
echo   これで終わりです。あとは、このバッチに PDF ファイルを
echo   ドラッグ＆ドロップするだけで変換できます。
echo.
echo   （上の「画面のドラッグ＆ドロップ」「PP-OCRv5」が「入っていません」
echo     の場合、GUI ではその部分だけ使えません（tesseract での変換は
echo     そのまま使えます）。入れ直すには、次をコマンドプロンプトで
echo     実行してください。
echo       %PY% -m pip install --upgrade tkinterdnd2 onnxruntime opencv-python-headless pyclipper shapely
goto after

:selftest
cls
echo.
echo   同梱のサンプル（画像だけの PDF）を変換して、文字が取り出せるかを
echo   確かめます。手元の PDF には触りません。
echo.
%PY% "%HERE%pdf_ocr.py" --overwrite --dumptext "%HERE%サンプル.pdf"
if errorlevel 1 goto after
echo.
echo   サンプル_OCR.pdf を開きます。Ctrl+F で「舗装」を検索してみてください。
start "" "%HERE%サンプル_OCR.pdf"
goto after

:readme
start "" notepad.exe "%HERE%使い方.txt"
goto menu

:gui
echo.
echo   画面を開いています …
rem コンソールが裏に残らないよう pythonw（コンソール無し版）があれば
rem そちらを使う。ただし [1] 準備 で部品を入れたのと同じ Python から
rem 辿ること。ここだけ別に「where pythonw」で探すと、別の Python
rem （たとえば Anaconda 等、他にも入っている場合）が先に見つかり、
rem 「準備で入れたはずの部品が無い」「ドラッグ＆ドロップが使えない」
rem ということが起こる。
set "PYW="
if "%PY%"=="py -3" (
  where pyw >nul 2>nul && set "PYW=pyw -3"
) else (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PYW if exist "%%~dpPpythonw.exe" set "PYW=%%~dpPpythonw.exe"
  )
)
if defined PYW (
  start "" /wait %PYW% "%HERE%PDF文字認識_GUI.pyw"
) else (
  start "" /wait %PY% "%HERE%PDF文字認識_GUI.pyw"
)
goto menu

:convert
rem --overwrite を必ず付ける。付けないと 2 回目以降が 元の名前_OCR_2.pdf、
rem _OCR_3.pdf … と別名で増えていき、利用者が最初に開いた 元の名前_OCR.pdf は
rem いつまでも古いままになる。「何度やり直しても結果が変わらない」の原因。
echo.
%PY% "%HERE%pdf_ocr.py" --overwrite %EXTRA% %ARGS%
set "RC=%ERRORLEVEL%"
if "%RC%"=="2" (
  echo.
  echo   準備が足りていません。このバッチをダブルクリックしてください。
  echo   足りないものがあれば、そのまま準備します。
)
goto after

:after
echo.
rem 呼ばれ方によって戻り先が違う。ドラッグ＆ドロップで起動したときは
rem ここで終わり、画面から操作したときは元の画面へ戻す。
if defined SEL goto back_menu
if defined FROMREADY goto back_ready
pause
exit /b 0

:back_menu
pause
set "SEL="
set "ARGS="
set "EXTRA="
goto menu

:back_ready
pause
set "ARGS="
set "EXTRA="
set "FROMREADY="
goto ready
