@echo off
echo ============================================
echo  Zoho Creator MCP Agent - Setup
echo ============================================
echo.

:: Check Python 3.12
py -3.12 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python 3.12 is not installed.
    echo Install with: winget install Python.Python.3.12
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
py -3.12 -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/4] Installing Python dependencies...
pip install "mcp[cli]" playwright Pillow python-dotenv
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [4/4] Installing Playwright Chromium browser...
playwright install chromium
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Playwright browsers.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Setup Complete!
echo ============================================
echo.
echo Next steps:
echo   1. Configure Claude Desktop (see README.md)
echo   2. Restart Claude Desktop
echo   3. Start chatting!
echo.
pause
