@echo off
rem Install Wine and DOSBox-X for Time Capsule from the repository root.
setlocal
cd /d "%~dp0.."
set "PY=python"
where py >nul 2>nul && set "PY=py"
%PY% scripts\setup.py %*
endlocal
