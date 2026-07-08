import pydblclick  # optional: pip install pydblclick -- or delete this line
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "cowsay",
# ]
# ///
"""PEP 723 demo: this one-file script declares its own dependencies.

Double-clicked on a machine with pydblclick + uv, it runs with 'cowsay'
resolved automatically in an ephemeral environment -- the user never
touches pip or venvs. The same file also runs with 'uv run' on any OS.
"""
import cowsay

cowsay.cow("My dependencies installed themselves!")
