@echo off
rem Open the graphical Time Capsule dashboard from the repository root.
setlocal
cd /d "%~dp0.."
set "PY=python"
where py >nul 2>nul && set "PY=py"
%PY% dashboard.py %*
endlocal
