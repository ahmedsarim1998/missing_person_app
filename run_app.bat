@echo off
echo Starting locAIte (development mode)...

:: Single Flask server serves both the API and the new_front_end site.
:: For PRODUCTION use run_prod.bat (Waitress) instead.
set APP_ENV=development
start "locAIte Server" cmd /k "cd backend && python app.py"

:: Optional: live Facebook scan loop (configure FB_GROUP / FB_COOKIES first).
:: start "FB Scanner" cmd /k "cd backend && python fb_scan_runner.py --interval 600"

echo Application launched!
echo Open the site at: http://localhost:5000
pause
