try: import pydblclick  # optional: pip install pydblclick -- or delete these 3 lines
except ImportError:
    import os, sys; ("PROMPT" in os.environ or sys.stdin is None) or input("Tip: 'pip install pydblclick' makes this script double-click friendly. (Enter to run anyway)")

# Keep these lines on the FIRST lines of the script.
# This is the recommended form for scripts you distribute to recipients whose
# machine you don't control -- unlike the plain "import pydblclick" one-liner
# (see 01b), a machine WITHOUT pydblclick installed does not just die on an
# ImportError whose console flashes away unread: it prints a readable tip and
# pauses (except under .pyw / a console, where there is nothing to pause on).
# - Without pydblclick pip-installed: reads the tip, then pauses so it can be read
# - With pydblclick pip-installed but NOT registered: the import re-launches this script through pydblclick features
# - With pydblclick pip-installed AND registered: the import line is inert, full pydblclick experience directly
print("hello world")
a = 1
# Thanks to pydblclick features, when double-clicked, this script ends with the pydblclick pause menu.
# Try <i> : the interactive console knows the variable 'a' which can be inspected for debugging.
