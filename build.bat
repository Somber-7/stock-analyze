@echo off
setlocal
cd /d "%~dp0"
if not defined STOCK_PYTHON set "STOCK_PYTHON=%USERPROFILE%\miniconda3\envs\stock-analyze\python.exe"
if not exist "%STOCK_PYTHON%" (
  echo Set STOCK_PYTHON to your Python executable.
  exit /b 1
)
pushd frontend
call npm.cmd run build
if errorlevel 1 exit /b 1
popd
"%STOCK_PYTHON%" -m PyInstaller --noconfirm --onefile --name backend --distpath . --workpath build_tmp --specpath build_tmp --add-data "%CD%\frontend\dist;dist" --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.lifespan.on run.py
if errorlevel 1 exit /b 1
pushd frontend
call npm.cmd run electron:build
if errorlevel 1 exit /b 1
popd
echo Done. See dist-electron-namuh. Credentials are not bundled.

