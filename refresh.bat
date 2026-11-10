@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=python"
if exist "D:/Programs/Python/Python38/python.exe" set "PY=D:/Programs/Python/Python38/python.exe"

if not exist "data\logs" mkdir "data\logs"
echo.>> "data\logs\fetch.log"
echo [%date% %time%] refresh start>> "data\logs\fetch.log"
"%PY%" -X utf8 scripts\fetch.py %*>> "data\logs\fetch.log" 2>&1
echo [%date% %time%] done exit=%errorlevel%>> "data\logs\fetch.log"
