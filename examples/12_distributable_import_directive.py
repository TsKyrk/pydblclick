import pydblclick  # optional: pip install pydblclick -- or delete this line

# One line is enough to make this script distribution-friendly:
# - double-clicked WITH pydblclick registered: line is inert, full experience
# - pydblclick pip-installed but NOT registered: the import activates a
#   minimal fallback (readable errors + pause + hint about 'register')
# - run from a console: inert, plain-Python behavior
# - machine without pydblclick: ImportError -- the recipient reads the
#   comment and chooses: install pydblclick, or delete the line
print("hello from a distributable one-filer")
