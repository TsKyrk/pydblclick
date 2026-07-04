@echo off

REM Convert a python script into an exe
pip install pyinstaller
set exe_name=pydblclick
pyinstaller --onefile pydblclick_exe.py --name %exe_name%

REM Copy the exe into a folder known by the windows PATH (we use the python/Script folder)
for /f %%A in ('py -c "import sys, os; print(os.path.join(os.path.split(sys.executable)[0],'Scripts'))"') do set "exe_location=%%A"
echo The executable is being copied here: %exe_location%
explorer %exe_location%
copy /Y ".\dist\%exe_name%.exe" "%exe_location%"

REM pause only if double-clicked:
echo %cmdcmdline%|find /i """%~f0""">nul && pause