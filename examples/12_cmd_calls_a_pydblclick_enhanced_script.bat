@echo off
rem A CLI/batch caller: pydblclick detects the console context -> no pause,
rem the script's exit code is propagated to the caller.
python -m pydblclick "%~dp001b_HelloWorld_WITH_pydblclick_import.py"
echo exit code: %ERRORLEVEL%
pause
