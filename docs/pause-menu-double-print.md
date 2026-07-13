# Bug note: pause menu printed twice under PowerShell piped stdin

## Status

**Not a user-facing bug.** It reproduces only when stdin is driven through
PowerShell's `|` operator; a real double-click (interactive console) and normal
OS pipes are unaffected — the menu prints exactly once. Documented here because
it was observed during v0.4.0 testing and is worth understanding before someone
"fixes" it and breaks the (correct) single-print behavior.

## Symptom

Running a wrapped script and feeding a newline through PowerShell prints the
pause prompt twice:

```powershell
"`n" | python -m pydblclick examples\01b_HelloWorld_WITH_pydblclick_import.py
```
```
hello ...
Press <Enter> to Quit. (<c> for cmd console. <i> for interactive python. <r> to restart.)
Press <Enter> to Quit. (<c> for cmd console. <i> for interactive python. <r> to restart.)
```

Both the direct `-m pydblclick` path and the v0.4.0 `import pydblclick` bootstrap
relaunch show it identically (the bootstrap is a faithful relay — it does not add
the second print).

## Root cause

PowerShell **prepends a UTF-8 BOM** to the bytes it pipes to a native process:

```powershell
"`n" | python -c "import sys; print(repr(sys.stdin.buffer.read()))"
# b'\xef\xbb\xbf\n\r\n'
```

The pause menu loop in `pydblclick/_child.py::display_pause_prompt_and_menu()`
reads the choice with `input()` and dispatches on it:

```python
while True:
    ...
    wait = input("Press <Enter> to Quit. ...")
    ...
    if   wait.lower() == "c":  ...
    elif wait.lower() == "i":  ...
    elif wait.lower() == "r":  ...
    elif wait.lower() == "":   break      # <- Enter quits
    # (no else: unrecognized input silently re-loops)
```

Sequence with the BOM-prefixed stream:

1. `input()` reads the first line: the BOM `\xef\xbb\xbf` decodes to the char
   `"﻿"`, so `wait == "﻿"` — a **non-empty, unrecognized** choice.
2. It matches none of `c`/`i`/`r`/`""`, and there is no `else`, so the outer
   `while True` loops and prints the prompt a **second** time.
3. The next `input()` reads `""` (the `\n\r\n` remainder) → matches `""` → quit.

So the second print is the BOM being treated as a stray menu keystroke.

## Why it does not affect real usage

- A real double-click gives the child a genuine interactive console; the user
  presses Enter once → `input()` returns `""` → one print, quit.
- Normal OS pipes (Python `subprocess` with `input="\n"`, a batch redirect, etc.)
  carry no BOM.

Verified — the menu prints exactly once in every real scenario:

- `tests/test_import_fallback.py::test_import_inert_under_pydblclick` asserts
  `result.stdout.count("Press <Enter> to Quit.") == 1`.
- Subprocess probe with `input` of `"\n"`, `""` (immediate EOF) and `"\n\n"` all
  yield `menu printed 1x`.

Only PowerShell's `|` (which BOM-prefixes stdin) produces the double print.

## Fixed in Unreleased (post-0.5.1)

`display_pause_prompt_and_menu()` in `pydblclick/_child.py` now normalizes the
input right after a successful `input()` call. Depending on the child's stdin
encoding, the BOM's 3 bytes surface either as the single codepoint U+FEFF
(utf-8) or as 3 mis-decoded Latin-1 characters `"\xef\xbb\xbf"` (non-utf-8
codepages, e.g. the default `cp1252` locale used when stdin is a plain pipe
rather than a real console) -- both are stripped, so a BOM-prefixed line
normalizes to `""` and is treated as Enter instead of an unrecognized
keystroke. A genuinely unrecognized choice now also prints `"Unknown
option."` before re-looping, instead of silently reprinting the menu. The single-print behavior on a real double-click and on normal OS pipes
is unchanged (still asserted by
`tests/test_import_fallback.py::test_import_inert_under_pydblclick`); see
`tests/test_pydblclick.py::test_pause_menu_normalizes_bom_prefixed_choice` and
`tests/test_subprocess.py::test_pause_menu_single_print_with_bom_prefixed_stdin`
for the BOM case specifically.
