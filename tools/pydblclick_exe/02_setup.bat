@echo off

:: https://stackoverflow.com/questions/1894967/how-to-request-administrator-access-inside-a-batch-file
:: BatchGotAdmin
:-------------------------------------
REM  --> Check for permissions
    IF "%PROCESSOR_ARCHITECTURE%" EQU "amd64" (
>nul 2>&1 "%SYSTEMROOT%\SysWOW64\cacls.exe" "%SYSTEMROOT%\SysWOW64\config\system"
) ELSE (
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
)

REM --> If error flag set, we do not have admin.
if '%errorlevel%' NEQ '0' (
    echo Requesting administrative privileges...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    set params= %*
    echo UAC.ShellExecute "cmd.exe", "/c ""%~s0"" %params:"=""%", "", "runas", 1 >> "%temp%\getadmin.vbs"

    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    pushd "%CD%"
    CD /D "%~dp0"
:--------------------------------------   

:Get the exe location set previously
for /f %%A in ('py -c "import sys, os; print(os.path.join(os.path.split(sys.executable)[0],'Scripts'))"') do set "exe_location=%%A"
echo %exe_location%

:Check if the exe is already associated with py files
echo ftype | findstr -i Python.File
ftype | findstr -i Python.File | findstr /I /L %exe_location%
if '%errorlevel%' NEQ '0' (
    echo Not found. Association can be made. Resuming...
) else (
    echo Found. Already setup. Canceling...
    goto :pause
)

:Show and backup initial file association settings
echo === Initial settings ===
ftype | findstr -i python
assoc | findstr -i python

echo === Initial settings ===   >  Backup_Full.txt
ftype | findstr -i python       >> Backup_Full.txt
assoc | findstr -i python       >> Backup_Full.txt

ftype | findstr -i Python.File  >  Backup_One.txt

:Define the new file association (.py are bind to Python.File,  Python.File is bind to <cmd "%%1" %%*>
ftype Python.File="%exe_location%\pydblclick.exe" ^"%%L^" %%*

:pause
REM pause only if double-clicked:
echo %cmdcmdline%|find /i """%~f0""">nul && pause