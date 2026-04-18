@echo off
setlocal
chcp 65001 >nul
cd /d %~dp0

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "tools\race_simulation.py"
    goto :eof
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "tools\race_simulation.py"
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "tools\race_simulation.py"
    goto :eof
)

echo Python environment not found.
echo Install Python 3.13 or run Create Environment.bat.
choice /c Y /n /m "Press any key to continue..."
