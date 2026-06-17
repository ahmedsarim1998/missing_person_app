@echo off
echo Starting locAIte (PRODUCTION mode via Waitress)...

:: Loads backend\.env if present. Serves API + frontend on http://HOST:PORT.
:: First boot prints a generated admin password to the console if ADMIN_PASSWORD
:: is not set in backend\.env -- copy it and change it via reset_admin.py.
set APP_ENV=production
cd backend
python wsgi.py

pause
