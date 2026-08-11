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
REM  動作には Ruby が必要です。パスが通っていない場合は
REM  下の RUBY の行に ruby.exe の場所を書いてください。
REM
REM  上の制御行の意味（この説明文には井桁記号を書かないこと）
REM    jww … jww形式で座標ファイルを受け取る
REM    h0  … 範囲内の図形データを jwc_temp.txt に書き出す
REM    hc  … 範囲選択時に表示するメッセージ
REM    1   … 点を指示させる。指示点は hp1 として渡される
REM    e   … 制御文字列の終わり
REM ------------------------------------------------------------
setlocal

set "RUBY=ruby"

"%RUBY%" -v >nul 2>&1
if errorlevel 1 goto :noruby

"%RUBY%" "%~dp0jww_ceiling_plan.rb" "" "%~dp0天伏図ルール.txt"
goto :eof

:noruby
echo he Ruby が見つかりません。Ruby をインストールするか、天井伏図生成.bat の RUBY の行に ruby.exe の場所を書いてください。> jwc_temp.txt
goto :eof
