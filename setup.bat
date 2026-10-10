@echo off
rem setup.bat - Quick setup script for meal-planner on Windows CMD
echo Installing meal-planner and registering global 'meals' shortcut...

where uv >nul 2>&1
if %ERRORLEVEL% equ 0 (
    uv pip install -e .
) else (
    python -m pip install -e .
)

set "REPO_ROOT=%~dp0"
set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "PY_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
if not exist "%PY_EXE%" (
    for /f "delims=" %%I in ('where python') do set "PY_EXE=%%I" & goto :found_py
)
:found_py

set "LOCAL_BIN=%USERPROFILE%\.local\bin"
if not exist "%LOCAL_BIN%" mkdir "%LOCAL_BIN%"

(
echo @echo off
echo "%PY_EXE%" "%REPO_ROOT%\main.py" %%*
) > "%LOCAL_BIN%\meals.cmd"

echo.
echo [OK] Setup complete! Global 'meals' shortcut installed to %LOCAL_BIN%\meals.cmd
echo You can now open a freshly launched terminal from anywhere and run: meals
