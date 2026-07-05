# pydblclick examples

Prerequisite: `pip install pydblclick` then `pydblclick register` (see the main
[README](../README.md)). Once registered, **every** `.py`/`.pyw` file is wrapped on
double-click — nothing to add to the scripts themselves.

Double-click each file and observe:

| File | What it demonstrates |
|---|---|
| `01_HelloWorld.py` | Output stays visible: pause prompt + menu (`<c>` cmd, `<i>` Python console with the script's variables, `<r>` restart) |
| `02_Unexpected_exception.py` | The traceback is readable instead of flashing away; `<i>` gives a post-mortem console |
| `03_Syntax_error.py` | Even a script that cannot compile shows a readable error |
| `04_Import_error.py` | Missing module: read the error, `<c>` opens a cmd to pip install |
| `05_NoPause_option.py` | `pydblclick_customizations['must_pause_in_console'] = False`: no pause when all goes well... |
| `06_NoPause_option_but_exception.py` | ...but an exception still forces the pause |
| `07_PEP723_dependencies.py` | Inline dependencies (PEP 723) auto-installed via [uv](https://docs.astral.sh/uv/) |
| `08_OptOut_directive.py` | `# pydblclick: off`: pydblclick steps aside — the console flashes away like plain Python (the pre-pydblclick world) |
| `09_WindowedHelloWorld.pyw` | Windowed script: no console at all |
| `10_WindowedHelloWorld_with_exception.pyw` | Windowed script that crashes: a console appears with the output and traceback instead of dying silently |
| `11_cmd_calls_a_script.bat` | A batch/CLI caller: no pause (it would break automation), exit code propagated |

Bonus trick — custom icons: create a Windows shortcut to a script (ALT+drag & drop)
and set a custom icon in its properties. Double-clicking the shortcut runs the script
through pydblclick with your icon.
