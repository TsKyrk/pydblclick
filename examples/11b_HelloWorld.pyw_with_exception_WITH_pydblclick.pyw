import pydblclick  # optional: pip install pydblclick -- or delete this line
print("some output before the crash")

from tkinter import *

root = Tk()
a = Label(root, text="Hello World")
a.pack()
print(1 / 0)  # without pydblclick, a crashing .pyw dies silently:
              # here a console appears with the output and the traceback
root.mainloop()
