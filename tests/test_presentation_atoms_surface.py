"""Freezes the public surface against the API reference, so adding or removing an export is a conscious change."""

import re
import types
from pathlib import Path

import pytest

import pytypehint


_API_DOC = Path(__file__).resolve().parent.parent / "docs" / "vocabulary.md"


def _documented_public_api_names() -> list[str]:
    """The backticked names of the API reference's 'Public API' bullet list, in order."""
    text = _API_DOC.read_text(encoding="utf-8")

    section = re.search(r"^## Public API$\n(.*?)(?=\n^## |\Z)", text, re.M | re.S)
    assert section is not None, f"{_API_DOC.name} has no '## Public API' section"

    # The list block only: its bullets start with '- ' and wrap with a two-space
    # indent. This drops the surrounding prose, which backticks `pytypehint`
    # itself without exporting a name called that.
    bullets = [line for line in section.group(1).splitlines()
               if line.startswith("- ") or line.startswith("  ")]
    assert bullets, f"{_API_DOC.name}: 'Public API' section has no bullet list"

    return re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", "\n".join(bullets))


def test_documentation_public_api_list_is_parseable():
    """API reference: 'Everything public is exported from `pytypehint`' — the guard that keeps the parsing below honest."""
    names = _documented_public_api_names()

    assert len(names) > 20
    assert "struct_of" in names and "MISSING" in names


def test_all_exports_everything_the_documentation_documents():
    """API reference, 'Public API': every documented name must really be exported."""
    documented = set(_documented_public_api_names())

    missing = sorted(documented - set(pytypehint.__all__))
    assert not missing, (
        f"API reference documents {', '.join(missing)} but pytypehint.__all__ does not "
        f"export them")


def test_all_exports_nothing_the_documentation_omits():
    """Every public export must appear in the API reference."""
    documented = set(_documented_public_api_names())

    undocumented = sorted(set(pytypehint.__all__) - documented)
    assert not undocumented, (
        f"pytypehint.__all__ exports {', '.join(undocumented)} but the API reference's "
        f"'Public API' section does not document them")


def test_all_and_documentation_agree_exactly():
    """API reference, 'Public API': the two lists are one list written twice; this states it in one assertion."""
    assert set(pytypehint.__all__) == set(_documented_public_api_names())


def test_all_has_no_duplicates():
    """API reference, 'Public API': each name is listed once, so the export list must not repeat one either."""
    duplicates = sorted({n for n in pytypehint.__all__ if pytypehint.__all__.count(n) > 1})
    assert not duplicates, f"pytypehint.__all__ repeats: {', '.join(duplicates)}"

    documentation = _documented_public_api_names()
    repeated = sorted({n for n in documentation if documentation.count(n) > 1})
    assert not repeated, f"API reference's 'Public API' repeats: {', '.join(repeated)}"


@pytest.mark.parametrize("name", pytypehint.__all__)
def test_every_exported_name_resolves(name):
    """API reference: 'Everything public is exported from `pytypehint`' — an entry in __all__ that resolves to nothing breaks `import *`."""
    assert hasattr(pytypehint, name), f"pytypehint.__all__ lists {name!r} but the module has no such attribute"


def test_star_import_delivers_exactly_all():
    """API reference, 'Public API': __all__ is what `from pytypehint import *` hands over."""
    namespace: dict = {}
    exec("from pytypehint import *", namespace)

    delivered = {n for n in namespace if not n.startswith("__")}
    assert delivered == set(pytypehint.__all__)


def test_module_leaks_no_public_name_outside_all():
    """Public attributes must be explicitly exported."""
    leaked = sorted(
        name for name, value in vars(pytypehint).items()
        if not name.startswith("_")
        and name not in pytypehint.__all__
        # Submodules are an import artefact, not a documented export.
        and not isinstance(value, types.ModuleType))

    assert not leaked, (
        f"pytypehint exposes {', '.join(leaked)} outside __all__; either export "
        f"them in the API reference or make them private")
