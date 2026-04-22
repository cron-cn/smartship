@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM One-click start: activate .venv and run the desktop app (run_app.py)
set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%

echo Working directory: %ROOT%

set VENV_DIR=%ROOT%\.venv
set PYTHON_EXE=%VENV_DIR%\Scripts\python.exe

REM Ensure Python exists on the system
where py >nul 2>&1
if %ERRORLEVEL%==0 (
	set "SYS_PY=py -3"
) else (
	where python >nul 2>&1
	if %ERRORLEVEL%==0 (
		set "SYS_PY=python"
	) else (
		echo Python not found. Please install Python 3.11+ and re-run this script.
		pause
		exit /b 1
	)
)

REM Create venv if missing
if not exist "%PYTHON_EXE%" (
	echo Virtual environment not found. Creating %VENV_DIR% ...
	%SYS_PY% -m venv "%VENV_DIR%"
	if %ERRORLEVEL% neq 0 (
		echo Failed to create virtual environment.
		pause
		exit /b 1
	)
)

REM Health check: if python exists but is broken, remove and recreate venv
if exist "%PYTHON_EXE%" (
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
)

REM Activate venv and run the app
if exist "%PYTHON_EXE%" (
	echo Activating virtual environment...
	call "%VENV_DIR%\Scripts\activate.bat"
	echo Running desktop app (run_app.py)...
	"%PYTHON_EXE%" "%ROOT%\run_app.py"
	set "RV=%ERRORLEVEL%"
	echo Application exited with code %RV%
	pause
	exit /b %RV%
) else (
	echo Virtual environment python not found at %PYTHON_EXE%
	pause
	exit /b 1
)

endlocal
