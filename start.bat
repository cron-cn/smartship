@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM start.bat - Unified starter script
REM Usage: start.bat [run|debug|rebuild]
set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%

set MODE=%1
if "%MODE%"=="" set MODE=run

set VENV_DIR=%ROOT%\.venv
set PYTHON_EXE=%VENV_DIR%\Scripts\python.exe
set LOGFILE=%ROOT%\run_app.log

REM Find system python command
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  set "SYS_PY=py -3"
) else (
  where python >nul 2>&1
  if %ERRORLEVEL%==0 (
    set "SYS_PY=python"
  ) else (
    echo Python not found. Please install Python 3 and retry.
    pause
    exit /b 1
  )
)

REM Rebuild venv on demand
if /i "%MODE%"=="rebuild" (
  echo Rebuilding virtual environment at %VENV_DIR%...
  if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
  %SYS_PY% -m venv "%VENV_DIR%"
  if %ERRORLEVEL% neq 0 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
  "%PYTHON_EXE%" -m pip install -r "%ROOT%\hub\requirements.txt"
  echo Rebuild complete.
  pause
  exit /b 0
)

:ensure_venv
if not exist "%PYTHON_EXE%" (
  echo Virtual environment not found. Creating %VENV_DIR% ...
  %SYS_PY% -m venv "%VENV_DIR%"
  if %ERRORLEVEL% neq 0 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
)

REM Health check: ensure venv python is runnable; recreate if broken
"%PYTHON_EXE%" -c "import sys;print('ok')" >nul 2>&1
if %ERRORLEVEL% neq 0 (
  echo Detected broken virtual environment; recreating %VENV_DIR% ...
  rmdir /s /q "%VENV_DIR%"
  %SYS_PY% -m venv "%VENV_DIR%"
  if %ERRORLEVEL% neq 0 (
    echo Failed to recreate virtual environment.
    pause
    exit /b 1
  )
)

call "%VENV_DIR%\Scripts\activate.bat"

REM Install requirements (quiet)
echo Installing/ensuring required Python packages...
"%PYTHON_EXE%" -m pip install -r "%ROOT%\hub\requirements.txt"

if /i "%MODE%"=="debug" (
  echo Debug mode: launching and logging to %LOGFILE%
  echo Starting %DATE% %TIME% > "%LOGFILE%"
  "%PYTHON_EXE%" "%ROOT%\run_app.py" >> "%LOGFILE%" 2>&1
  set "RV=%ERRORLEVEL%"
  echo Application exited with code %RV%
  echo ----- Last 50 lines of log -----
  powershell -Command "Get-Content -Path '%LOGFILE%' -Tail 50 -Encoding UTF8"
  echo ---------------------------------
  echo Log saved to %LOGFILE%
  pause
  exit /b %RV%
)

REM Normal run: foreground (no redirection)
echo Starting application (foreground)...
"%PYTHON_EXE%" "%ROOT%\run_app.py"
set "RV=%ERRORLEVEL%"
echo Application exited with code %RV%
pause
exit /b %RV%
