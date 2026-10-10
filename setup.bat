@echo off
rem setup.bat - Quick setup script for meal-planner on Windows CMD
echo Installing meal-planner and registering the 'meals' shortcut...

where uv >nul 2>&1
if %ERRORLEVEL% equ 0 (
    uv pip install -e .
) else (
    python -m pip install -e .
)

if %ERRORLEVEL% equ 0 (
    echo.
    echo [OK] Installation successful! You can now type 'meals' directly from anywhere in this environment.
) else (
    echo.
    echo [!] Installation encountered an issue. You can still run 'meals.bat' in this directory.
)
