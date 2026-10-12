@echo off
rem Launch the Time Capsule CLI from the repository root.
setlocal
cd /d "%~dp0.."
set "PY=python"
where py >nul 2>nul && set "PY=py"
%PY% launcher.py %*
endlocal
