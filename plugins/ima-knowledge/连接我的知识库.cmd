@echo off
chcp 65001 >nul
uv run --locked --script "%~dp0server.py" --connect
if errorlevel 1 pause
