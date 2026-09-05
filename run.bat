@echo off
rem Launch PZ Zone Viewer with whichever Python is available.
setlocal
where py >nul 2>&1 && (py -3 "%~dp0main.py" %* & exit /b)
python "%~dp0main.py" %*
