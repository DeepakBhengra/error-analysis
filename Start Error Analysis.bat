@echo off
title Error Analysis — Order Replay
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-prod.ps1"
if errorlevel 1 (
  echo.
  echo Failed to start. See messages above.
  pause
)
