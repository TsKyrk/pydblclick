"""Reads execution directives and PEP 723 inline metadata from a script's source.

Two kinds of information are extracted by the parent supervisor before it
decides how to launch the script:

- The pyexewrap opt-out directive: a `# pyexewrap: off` comment line anywhere
  in the script makes pyexewrap step aside and run it with plain Python
  (no wrapping, no pause). This is the per-script granularity that the legacy
  shebang used to provide, but application-level: no launcher can take it away.

- The PEP 723 inline script metadata block (`# /// script` ... `# ///`):
  when present, the script is executed through `uv run` so its dependencies
  are resolved automatically in an ephemeral environment.
  Reference: https://peps.python.org/pep-0723/
"""
import re

# Reference regex from the PEP 723 specification
PEP723_BLOCK_RE = re.compile(
    r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
)

OPT_OUT_RE = re.compile(r"(?mi)^#\s*pyexewrap:\s*off\s*$")


def read_script_text(path):
    """Best-effort read of the script source; never raises."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def has_opt_out(text):
    """True if the script asks pyexewrap to step aside (`# pyexewrap: off`)."""
    return bool(OPT_OUT_RE.search(text))


def extract_pep723_toml(text):
    """Return the TOML content of the `script` metadata block, or None.

    Per the PEP, more than one `script` block is an error: in that case we
    behave as if there was none (the script is then run without uv and will
    surface its own errors).
    """
    matches = [m for m in PEP723_BLOCK_RE.finditer(text) if m.group("type") == "script"]
    if len(matches) != 1:
        return None
    content = matches[0].group("content")
    return "".join(
        line[2:] if line.startswith("# ") else line[1:]
        for line in content.splitlines(keepends=True)
    )


def _parse_toml(toml_text):
    """Parse the metadata TOML. Falls back to a minimal parser before 3.11."""
    try:
        import tomllib
    except ImportError:
        return _naive_toml_parse(toml_text)
    try:
        return tomllib.loads(toml_text)
    except Exception:
        return None


def _naive_toml_parse(toml_text):
    """Minimal fallback for Python < 3.11 (no tomllib).

    Handles the two PEP 723 keys in their common form:
        requires-python = ">=3.9"
        dependencies = ["requests", 'rich>=13']
    TOML quoted strings in these positions are also valid Python literals,
    so ast.literal_eval is enough.
    """
    import ast
    result = {}
    text = re.sub(r"(?m)^\s*#.*$", "", toml_text)  # strip comment-only lines
    m = re.search(r"(?ms)^requires-python\s*=\s*(\"[^\"]*\"|'[^']*')\s*$", text)
    if m:
        result["requires-python"] = ast.literal_eval(m.group(1))
    m = re.search(r"(?ms)^dependencies\s*=\s*(\[.*?\])", text)
    if m:
        try:
            result["dependencies"] = list(ast.literal_eval(m.group(1)))
        except (ValueError, SyntaxError):
            pass
    return result


def parse_pep723(text):
    """Return {'dependencies': [...], 'requires-python': str|None} or None.

    None means "no usable PEP 723 block": the script should be run normally.
    """
    toml_text = extract_pep723_toml(text)
    if toml_text is None:
        return None
    data = _parse_toml(toml_text)
    if data is None:
        return None
    return {
        "dependencies": list(data.get("dependencies", [])),
        "requires-python": data.get("requires-python"),
    }
