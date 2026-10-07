@echo off
REM Double-click on a Windows laptop that only has Python installed.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-laptop.ps1"
pause
