@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
pushd "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" load_data.py %*
) else (
  python load_data.py %*
)
set "CATALOG_EXIT=%ERRORLEVEL%"
if "%~1"=="" pause
popd
exit /b %CATALOG_EXIT%
