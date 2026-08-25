@echo off
rem GUI 版を起動する
cd /d "%~dp0"
python -m s2pdf gui
if errorlevel 1 pause
