@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "%~dp0web_app.py" (
  echo [ERROR] web_app.py 없음
  pause
  exit /b 1
)

taskkill /F /IM streamlit.exe >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8502 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1

python "%~dp0web_app.py"
