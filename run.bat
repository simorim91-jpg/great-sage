@echo off
title Great Sage - AI Assistant
cd /d "%~dp0"

rem --- use the installed python 3.12 ---
set "PY=C:\Users\simor\AppData\Local\Programs\Python\Python312\python.exe"
if exist "%PY%" goto :run
for /f "delims=" %%i in ('where python 2^>nul') do (set "PY=%%i" & goto :run)
echo Python not found. Please install Python 3.12.
pause
exit /b

:run
echo Starting Great Sage...
"%PY%" main.py
pause