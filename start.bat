@echo off
chcp 65001 >nul
title TraidMe -- XAU/USD Gold Trading Assistant

echo.
echo  ==========================================
echo   TraidMe -- XAU/USD Gold Trading Assistant
echo  ==========================================
echo.

:: Chemin Python 3.14 detecte sur cette machine
set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python314\python.exe

if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe
)
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
)
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe
)

if not exist "%PYTHON_EXE%" (
    echo [ERREUR] Python introuvable.
    echo Telecharger : https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  Python : %PYTHON_EXE%
echo.

echo  [1/2] Installation des dependances...
"%PYTHON_EXE%" -m pip install -r backend\requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo [ERREUR] Installation echouee.
    pause
    exit /b 1
)
echo  [1/2] OK

echo  [2/2] Demarrage du serveur sur http://localhost:8000 ...
echo.
echo  Appuyez sur Ctrl+C pour arreter.
echo.

start "" /B cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

"%PYTHON_EXE%" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

pause
