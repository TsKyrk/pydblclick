"""Unit tests for pyexewrap._script_meta (opt-out directive, PEP 723 parsing)."""
from pyexewrap._script_meta import extract_pep723_toml, has_opt_out, parse_pep723


# ---------------------------------------------------------------------------
# Opt-out directive
# ---------------------------------------------------------------------------

def test_opt_out_detected():
    assert has_opt_out("# pyexewrap: off\nprint('hi')\n") is True


def test_opt_out_case_and_spacing_tolerant():
    assert has_opt_out("#PYEXEWRAP:  OFF\n") is True
    assert has_opt_out("  \n#  pyexewrap : off\n") is False  # space before ':' not allowed
    assert has_opt_out("# pyexewrap: off\r\nprint('crlf')\r\n") is True


def test_opt_out_absent():
    assert has_opt_out("print('no directive')\n") is False
    assert has_opt_out("s = '# pyexewrap: off'  # inside a string, same line\n") is False


# ---------------------------------------------------------------------------
# PEP 723 block extraction
# ---------------------------------------------------------------------------

PEP723_EXAMPLE = '''\
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests<3",
#   "rich",
# ]
# ///

import requests
'''


def test_extract_toml_from_spec_example():
    toml = extract_pep723_toml(PEP723_EXAMPLE)
    assert toml is not None
    assert 'requires-python = ">=3.11"' in toml
    assert '"requests<3"' in toml


def test_no_block_returns_none():
    assert extract_pep723_toml("print('plain script')\n") is None
    assert parse_pep723("print('plain script')\n") is None


def test_two_script_blocks_treated_as_none():
    text = PEP723_EXAMPLE + "\n" + PEP723_EXAMPLE
    assert extract_pep723_toml(text) is None


def test_other_block_types_ignored():
    text = "# /// test\n# dependencies = [\"x\"]\n# ///\n"
    assert extract_pep723_toml(text) is None


# ---------------------------------------------------------------------------
# PEP 723 parsing
# ---------------------------------------------------------------------------

def test_parse_dependencies_and_requires_python():
    meta = parse_pep723(PEP723_EXAMPLE)
    assert meta == {
        "dependencies": ["requests<3", "rich"],
        "requires-python": ">=3.11",
    }


def test_parse_block_without_dependencies():
    text = '# /// script\n# requires-python = ">=3.9"\n# ///\n'
    meta = parse_pep723(text)
    assert meta == {"dependencies": [], "requires-python": ">=3.9"}


def test_parse_empty_block_is_none():
    # The PEP 723 reference regex requires at least one content line between
    # the markers, so a zero-line block is not a valid metadata block.
    text = "# /// script\n# ///\n"
    assert parse_pep723(text) is None
