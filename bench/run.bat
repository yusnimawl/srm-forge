@echo off
rem Windows entry point of the SRM benchmark: checks the platform, fetches the pinned uv,
rem builds the private environment under .runtime\ and runs "python -m srmbench %*".
rem Exit codes: 2 unsupported platform, 3 setup failure, otherwise the exit code of srmbench.
setlocal EnableDelayedExpansion

set "BENCH=%~dp0"
set "RT=%BENCH%.runtime"
set "UV=%RT%\uv\uv.exe"
set "PY=%RT%\venv\Scripts\python.exe"
set "CURL=%SystemRoot%\System32\curl.exe"
set "TAR=%SystemRoot%\System32\tar.exe"

rem ---- 1. Platform gate ------------------------------------------------------------------
set "ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "ARCH=%PROCESSOR_ARCHITEW6432%"
if /i not "%ARCH%"=="AMD64" set "WHY=the CPU architecture is %ARCH%" & goto unsupported

set "BUILD="
for /f "tokens=3" %%B in ('reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v CurrentBuild 2^>nul ^| findstr /i CurrentBuild') do set "BUILD=%%B"
if not defined BUILD set "WHY=the Windows build number cannot be read" & goto unsupported
set "NONNUM="
for /f "delims=0123456789" %%N in ("!BUILD!") do set "NONNUM=%%N"
if defined NONNUM set "WHY=the Windows build number is not numeric (!BUILD!)" & goto unsupported
if !BUILD! LSS 17134 set "WHY=Windows build !BUILD! is older than 17134 (Windows 10 1803)" & goto unsupported

rem ---- 2. uv ----------------------------------------------------------------------------
set "UV_VER="
set "WIN_SHA="
for /f "usebackq tokens=1,* delims==" %%A in ("%BENCH%uv.version") do (
    if "%%A"=="version" set "UV_VER=%%B"
    if "%%A"=="windows_sha256" set "WIN_SHA=%%B"
)
if not defined UV_VER echo uv.version has no version line.& goto setup_failed
if not defined WIN_SHA echo uv.version has no windows_sha256 line.& goto setup_failed

if exist "%UV%" goto uv_ready
echo Downloading uv %UV_VER% ...
if not exist "%RT%" mkdir "%RT%"
if exist "%RT%\uv" rmdir /s /q "%RT%\uv"
mkdir "%RT%\uv"
"%CURL%" -fL --retry 3 -o "%RT%\uv.zip" "https://github.com/astral-sh/uv/releases/download/%UV_VER%/uv-x86_64-pc-windows-msvc.zip"
if errorlevel 1 echo Could not download uv from GitHub. Check the network connection.& goto setup_failed
call :hashfile "%RT%\uv.zip" GOT
if /i not "!GOT!"=="%WIN_SHA%" echo The downloaded uv archive failed its SHA-256 check ^(got !GOT!^).& del "%RT%\uv.zip" 2>nul & goto setup_failed
"%TAR%" -xf "%RT%\uv.zip" -C "%RT%\uv"
if errorlevel 1 echo Could not unpack the uv archive.& goto setup_failed
del "%RT%\uv.zip"
if not exist "%UV%" echo The uv archive did not contain uv.exe.& goto setup_failed
:uv_ready

rem ---- 3. Everything uv writes stays under .runtime ------------------------------------------
set "UV_CACHE_DIR=%RT%\cache"
set "UV_PYTHON_INSTALL_DIR=%RT%\python"
set "UV_PYTHON_PREFERENCE=only-managed"

rem ---- 4. Is the environment current? --------------------------------------------------------
call :hashfile "%BENCH%requirements.lock" H_LOCK
call :hashfile "%BENCH%..\pyproject.toml" H_PROJ
set "STAMP=!H_LOCK! !H_PROJ!"
set "OLD="
if not exist "%PY%" goto build_env
if not exist "%RT%\stamp" goto build_env
set /p OLD=<"%RT%\stamp"
if "!OLD!"=="!STAMP!" goto run

rem ---- 5. Python, venv, packages -------------------------------------------------------------
:build_env
if exist "%RT%\stamp" del "%RT%\stamp"
echo Setting up the benchmark environment in %RT% ...
"%UV%" venv "%RT%\venv" --python 3.12 --clear
if errorlevel 1 goto setup_failed
"%UV%" pip sync --python "%PY%" "%BENCH%requirements.lock"
if errorlevel 1 goto setup_failed
"%UV%" pip install --python "%PY%" --no-deps -e "%BENCH%.."
if errorlevel 1 goto setup_failed
>"%RT%\stamp" (echo !STAMP!)

rem ---- 6. Run ----------------------------------------------------------------------------
:run
rem A flag left by an interrupted earlier run must not be acted on.
if exist "%RT%\finish" del "%RT%\finish"
set "PYTHONPATH=%BENCH:~0,-1%"
"%PY%" -m srmbench %*
set "RC=%ERRORLEVEL%"

rem ---- 7. Finish: srmbench leaves the user's choice in .runtime\finish -------------------------
set "FIN="
if exist "%RT%\finish" set /p FIN=<"%RT%\finish"
if /i "!FIN!"=="delete" goto finish_delete
if /i "!FIN!"=="keep-full" goto finish_full
if exist "%RT%\finish" del "%RT%\finish"
if "%~1"=="" pause
exit /b %RC%

:finish_delete
cd /d "%BENCH%"
rmdir /s /q "%RT%"
if "%~1"=="" pause
exit /b %RC%

:finish_full
del "%RT%\finish"
"%UV%" pip install --python "%PY%" -e "%BENCH%..[web]"
if errorlevel 1 echo Installing the web extra failed; the benchmark environment is unchanged otherwise.
echo Web frontend: cd web, npm ci, npm run build (needs Node 22).
if "%~1"=="" pause
exit /b %RC%

:unsupported
echo This machine is not supported: %WHY%. Supported: Windows 10 1803+ or 11 on x64, Linux x86_64 with glibc 2.28+.
if "%~1"=="" pause
exit /b 2

:setup_failed
echo Setup failed. Delete %RT% and run this script again; if it keeps failing, see bench\README.md.
if "%~1"=="" pause
exit /b 3

rem Sets the variable named by %2 to the SHA-256 of the file %1 (lower case, no spaces).
:hashfile
set "%~2="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%~1" SHA256') do if not defined %~2 set "%~2=%%H"
set "%~2=!%~2: =!"
exit /b 0
