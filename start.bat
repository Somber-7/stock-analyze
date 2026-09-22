@echo off
setlocal
cd /d "%~dp0frontend"
call npm.cmd run electron
if errorlevel 1 pause
