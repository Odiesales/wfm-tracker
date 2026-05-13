@echo off
echo ============================================
echo   WFM Transaction Tracker
echo ============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Checking dependencies...
pip install -r requirements.txt -q

echo.
echo Starting WFM Transaction Tracker...
echo Open your browser at: http://localhost:8501
echo (Press Ctrl+C to stop the app)
echo.

REM Run on all network interfaces so team can access via your IP
streamlit run app.py --server.address 0.0.0.0 --server.port 8501

pause
