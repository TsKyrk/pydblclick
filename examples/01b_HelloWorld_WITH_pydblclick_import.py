import pydblclick  # optional: pip install pydblclick -- or delete this line

# Keep the import line on the FIRST line of the script
# This one line is enough to activate the pydblclick features without dealing with python file associations.
# The behavior is this :
# - Without pydblclick pip-installed: ImportError -- the user reads the comment and chooses to pip-install pydblclick, or to delete the import line
# - With pydblclick pip-installed but NOT registered: the import re-launches this script through pydblclick features
# - With pydblclick pip-installed AND registered: the import line is inert, full pydblclick experience directly
print("hello world")
a = 1
# Thanks to pydblclick features, when double-clicked, this script ends with the pydblclick pause menu.
# Try <i> : the interactive console knows the variable 'a' which can be inspected for debugging.
