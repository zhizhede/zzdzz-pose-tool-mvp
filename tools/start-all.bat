@echo off
setlocal
rem ============================================================
rem  zzdzz-pose-tool prerequisite launcher (one-click)
rem  1) ComfyUI   http://127.0.0.1:8188  generation engine
rem  2) pose-tool http://127.0.0.1:7860  pose editor / library
rem  Running services are skipped; safe to run repeatedly.
rem  Usage: double-click, or run in terminal: tools\start-all.bat
rem ============================================================

set "COMFYUI_DIR=E:\Program\zzdzz-ai\ComfyUI"
set "COMFYUI_PY=E:\Program\zzdzz-ai\ComfyUI-env\Scripts\python.exe"
set "COMFYUI_LOG=E:\Program\zzdzz-ai\comfyui.log"
set "ROOT=%~dp0.."
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%COMFYUI_PY%" (
    echo [ERROR] ComfyUI python not found: %COMFYUI_PY%
    echo         Install it first, see docs/generation-manual.md
    pause
    exit /b 1
)
if not exist "%VENV_PY%" (
    echo [ERROR] Project venv not found: %VENV_PY%
    pause
    exit /b 1
)

echo [1/2] Checking ComfyUI ...
curl -s -o nul --connect-timeout 2 http://127.0.0.1:8188/system_stats
if %errorlevel%==0 (
    echo        already running, skip.
) else (
    echo        starting, log: %COMFYUI_LOG%
    start "ComfyUI" /min /d "%COMFYUI_DIR%" cmd /c ""%COMFYUI_PY%" main.py --lowvram --port 8188 >>"%COMFYUI_LOG%" 2>&1"
)

echo [2/2] Checking pose-tool webapp ...
curl -s -o nul --connect-timeout 2 http://127.0.0.1:7860/api/poses
if %errorlevel%==0 (
    echo        already running, skip.
) else (
    echo        starting ...
    start "pose-tool" /min /d "%ROOT%" cmd /c ""%VENV_PY%" -m uvicorn pose_tool.webapp:create_app --factory --port 7860"
)

echo Waiting for services (up to 120s) ...
set /a TRIES=0
:wait_loop
set /a TRIES+=1
set "OK8188="
set "OK7860="
curl -s -o nul --connect-timeout 2 http://127.0.0.1:8188/system_stats && set "OK8188=1"
curl -s -o nul --connect-timeout 2 http://127.0.0.1:7860/api/poses && set "OK7860=1"
if defined OK8188 if defined OK7860 goto ready
if %TRIES% GEQ 40 goto timeout
timeout /t 3 /nobreak >nul
goto wait_loop

:ready
echo.
echo ================================================
echo  ALL READY
echo    pose editor : http://127.0.0.1:7860
echo    ComfyUI     : http://127.0.0.1:8188
echo  Next: pick a pose -^> download skeleton PNG
echo        -^> generate, see docs/generation-manual.md
echo ================================================
pause
exit /b 0

:timeout
echo.
if not defined OK8188 echo [FAILED] ComfyUI not ready, check log: %COMFYUI_LOG%
if not defined OK7860 echo [FAILED] pose-tool not ready, check venv and port 7860
pause
exit /b 1
