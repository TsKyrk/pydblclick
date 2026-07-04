Initial bug:
when pydblclick is used and an exception occurs in exec("source") the traceback is in an altered form compared with a normal execution of the source with python.exe
This altered form is less convenient to debug the script.

Solution:
I've used exec(compile(mycode,myfile,"exec"), globals(), globals()) 
and I have removed the first item from the traceback stack