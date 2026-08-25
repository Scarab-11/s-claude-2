@echo off
rem コマンドライン版。例: s2pdf.bat run --pages 120 --pdf book.pdf
cd /d "%~dp0"
python -m s2pdf %*
