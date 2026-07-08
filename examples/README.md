# pydblclick examples

## Unregistered usage
Only the scripts enhanced with a "import pydblclick" 1st line will benefit from the added features

## Registered usage

Prerequisite: `pip install pydblclick` then `pydblclick register` (see the main
[README](../README.md)). Once registered, **every** `.py`/`.pyw` file is wrapped on
double-click — nothing to add to the scripts themselves.

## Comparison table

Double-click each file and observe:
| File | Without pydblclick import line <br>(a) | With pydblclick import line <br>(b) | With pydblclick registered & associated<br>or "Open with pydblclick" selected <br>(a or b)
|---|---|---|---|
| `01_HelloWorld.py` | ❌ The console flashes away | ✅ The console stays visible <br>a menu is shown <br>a title is set | ✅ Same |
| `02_Unexpected_exception.py` | ❌ The console flashes away | ✅ The traceback is readable instead of flashing away; <br>`<i>` gives a post-mortem console <br>a title is set | ✅ Same |
| `03_Syntax_error.py` | ❌ The console flashes away | ❌ The console flashes away | ✅ Even a script that cannot compile <br>shows a readable error <br>a title is set |
| `04_Import_error.py` | ❌ The console flashes away | ✅ Missing module: read the error, <br>`<c>` opens a cmd to pip-install <br>`<r>` to restart after install <br>a title is set | ✅ Same |
| `10_WindowedHelloWorld.pyw` | ✅ Windowed execution | ✅ No impact | ✅ No impact |
| `11_HelloWorld.pyw_with_exception.pyw` | ❌ The window flashes away | ❌ The window flashes away | ✅ A console appears with the output and <br>traceback instead of dying silently |
| `12_cmd_calls_a_pydblclick_enhanced_script.bat` | ✅ No impact | ✅ No impact | ✅ No impact | ✅ No impact |
| `20a_NoPause_option.py` | - | ✅ no pause when all goes well... | ✅ Same |
| `20b_NoPause_option_but_exception.py` | - | ✅ An exception still forces the pause | ✅ Same |
| `21_PEP723_dependencies.py` | ❌ The console flashes away | ✅ Inline dependencies (PEP 723) <br>auto-installed via [uv](https://docs.astral.sh/uv/) if available | ✅ Same |
| `22_OptOut_directive.py` | - | ✅ pydblclick steps aside — the console flashes away <br>like plain Python (the pre-pydblclick world) | ✅ Same |