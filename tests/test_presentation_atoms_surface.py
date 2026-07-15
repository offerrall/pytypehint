"""Freezes the public surface against the README, so adding or removing an export is a conscious change."""

import re
import types
from pathlib import Path

import pytest

import pytypehint


_README = Path(__file__).resolve().parent.parent / "README.md"


def _readme_public_api_names() -> list[str]:
    """The backticked names of the README's 'Public API' bullet list, in order."""
    text = _README.read_text(encoding="utf-8")

    section = re.search(r"^## Public API$\n(.*?)(?=\n^## |\Z)", text, re.M | re.S)
    assert section is not None, f"{_README.name} has no '## Public API' section"

    # The list block only: its bullets start with '- ' and wrap with a two-space
    # indent. This drops the surrounding prose, which backticks `pytypehint`
    # itself without exporting a name called that.
    bullets = [line for line in section.group(1).splitlines()
               if line.startswith("- ") or line.startswith("  ")]
    assert bullets, f"{_README.name}: 'Public API' section has no bullet list"

    return re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", "\n".join(bullets))


def test_readme_public_api_list_is_parseable():
    """README: 'Everything public is exported from `pytypehint`' — the guard that keeps the parsing below honest."""
    names = _readme_public_api_names()

    assert len(names) > 20
    assert "struct_of" in names and "MISSING" in names


def test_all_exports_everything_the_readme_documents():
    """README, 'Public API': every documented name must really be exported."""
    documented = set(_readme_public_api_names())

    missing = sorted(documented - set(pytypehint.__all__))
    assert not missing, (
        f"README documents {', '.join(missing)} but pytypehint.__all__ does not "
        f"export them")


def test_all_exports_nothing_the_readme_omits():
    """README, 'Status': 'This README is the specification' — an export it never mentions is undocumented surface."""
    documented = set(_readme_public_api_names())

    undocumented = sorted(set(pytypehint.__all__) - documented)
    assert not undocumented, (
        f"pytypehint.__all__ exports {', '.join(undocumented)} but the README's "
        f"'Public API' section does not document them")


def test_all_and_readme_agree_exactly():
    """README, 'Public API': the two lists are one list written twice; this states it in one assertion."""
    assert set(pytypehint.__all__) == set(_readme_public_api_names())


def test_all_has_no_duplicates():
    """README, 'Public API': each name is listed once, so the export list must not repeat one either."""
    duplicates = sorted({n for n in pytypehint.__all__ if pytypehint.__all__.count(n) > 1})
    assert not duplicates, f"pytypehint.__all__ repeats: {', '.join(duplicates)}"

    readme = _readme_public_api_names()
    repeated = sorted({n for n in readme if readme.count(n) > 1})
    assert not repeated, f"README's 'Public API' repeats: {', '.join(repeated)}"


@pytest.mark.parametrize("name", pytypehint.__all__)
def test_every_exported_name_resolves(name):
    """README: 'Everything public is exported from `pytypehint`' — an entry in __all__ that resolves to nothing breaks `import *`."""
    assert hasattr(pytypehint, name), f"pytypehint.__all__ lists {name!r} but the module has no such attribute"


def test_star_import_delivers_exactly_all():
    """README, 'Public API': __all__ is what `from pytypehint import *` hands over."""
    namespace: dict = {}
    exec("from pytypehint import *", namespace)

    delivered = {n for n in namespace if not n.startswith("__")}
    assert delivered == set(pytypehint.__all__)


def test_module_leaks_no_public_name_outside_all():
    """README, 'Status': 'This README is the specification' — a public attribute outside __all__ is surface nobody agreed to."""
    leaked = sorted(
        name for name, value in vars(pytypehint).items()
        if not name.startswith("_")
        and name not in pytypehint.__all__
        # Submodules are an import artefact, not a documented export.
        and not isinstance(value, types.ModuleType))

    assert not leaked, (
        f"pytypehint exposes {', '.join(leaked)} outside __all__; either export "
        f"them in the README or make them private")
