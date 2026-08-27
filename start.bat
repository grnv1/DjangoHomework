@echo off
setlocal
cd /d "%~dp0"

rem --- Locate a Python that has Django installed ---
set "PY=python"
python -c "import django" >nul 2>&1
if not errorlevel 1 goto :have_py

rem Fallback: common conda env paths for the "django" environment
for %%E in (
    "C:\ProgramData\anaconda3\envs\django\python.exe"
    "%USERPROFILE%\anaconda3\envs\django\python.exe"
    "%USERPROFILE%\anaconda3\envs\django\python.exe"
    "%LOCALAPPDATA%\anaconda3\envs\django\python.exe"
    "%LOCALAPPDATA%\miniconda3\envs\django\python.exe"
) do (
    if exist %%E (
        set "PY=%%~E"
        goto :have_py
    )
)

echo.
echo Python with Django not found.
echo Please install Django (pip install django) or activate the correct environment.
pause
exit /b 1

:have_py
echo Using Python: %PY%
echo.

echo [1/3] Running migrate...
"%PY%" manage.py migrate
if errorlevel 1 goto :error

"%PY%" manage.py shell -c "from django.contrib.auth.models import User; raise SystemExit(0 if User.objects.exists() else 1)" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Seeding demo data...
    "%PY%" manage.py seed
    if errorlevel 1 goto :error
) else (
    echo [2/3] Data already exists, skip seed
)

echo [3/3] Starting server: http://127.0.0.1:8000
echo Keep this window open. Press Ctrl+C to stop.
echo.
"%PY%" manage.py runserver %*
echo.
echo Server stopped.
pause
exit /b 0

:error
echo.
echo Startup failed. See error above.
pause
exit /b 1
