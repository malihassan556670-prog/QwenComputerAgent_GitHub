@echo off
cd /d "%~dp0"
title Qwen Computer Agent
"%~dp0venv\Scripts\python.exe" "%~dp0controller.py"
pause
