@echo off
rem Creates hil\.runtime (git-ignored) with the pinned PlatformIO. Nothing is installed outside it.
setlocal
set PIO_VERSION=6.2.0
set HERE=%~dp0
if not exist "%HERE%.runtime\Scripts\python.exe" python -m venv "%HERE%.runtime" || exit /b 1
"%HERE%.runtime\Scripts\python.exe" -m pip install --quiet platformio==%PIO_VERSION% || exit /b 1
echo PlatformIO %PIO_VERSION% ready in %HERE%.runtime
