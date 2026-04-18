@echo off
setlocal
chcp 65001 >nul
cd /d %~dp0

if exist ".venv\Scripts\python.exe" (
    echo Local virtual environment already exists.
    choice /c Y /n /m "Press any key to continue..."
    goto :eof
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        echo Virtual environment created successfully.
        choice /c Y /n /m "Press any key to continue..."
        goto :eof
    )
)

where python >nul 2>nul
if %errorlevel%==0 (
    python -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        echo Virtual environment created successfully.
        choice /c Y /n /m "Press any key to continue..."
        goto :eof
    )
)

echo Python not found for creating the virtual environment.
echo Please install Python 3.13 first.
choice /c Y /n /m "Press any key to continue..."
