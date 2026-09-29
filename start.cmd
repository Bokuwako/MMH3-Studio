@echo off
rem install.cmd writes studio_env.cmd (STUDIO_PY, MMH3_COMFY). Without it, assume the
rem ComfyUI portable folder sits next to this Studio folder.
if exist "%~dp0studio_env.cmd" call "%~dp0studio_env.cmd"
if not defined STUDIO_PY set "STUDIO_PY=%~dp0..\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\python_embeded\python.exe"
if not exist "%STUDIO_PY%" set "STUDIO_PY=python"
start "" "http://127.0.0.1:8791"
"%STUDIO_PY%" "%~dp0server.py" %*
pause
