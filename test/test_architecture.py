"""The dependency direction in docs/structure.md, as a test.

It reads the imports with ast, so nothing is imported or run. A package may
import only from a package of a lower rank; a new import that points upwards
(or sideways, between two packages of the same rank) fails here instead of
growing into a cycle.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Lower rank = lower layer. accounts and projects share a rank on purpose: they
# know nothing of each other.
RANK = {"core": 0, "accounts": 1, "projects": 1, "facts": 2, "integrations": 3, "tools": 4, "subscriber": 4}


def _imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            # `from src.facts import categories` names a module, not just a package.
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _package_of(module: str) -> str | None:
    """'src.facts.facts' -> 'facts', 'src.subscriber' -> 'subscriber'."""
    parts = module.split(".")
    return parts[1] if parts[0] == "src" and len(parts) > 1 else None


def _src_files():
    for path in sorted((ROOT / "src").rglob("*.py")):
        if path.name != "__init__.py":
            yield path, _package_of(".".join(path.relative_to(ROOT).with_suffix("").parts))


def test_every_src_package_has_a_rank():
    """Every package under src/ is listed in RANK."""
    # A new package must be placed in RANK (and in docs/structure.md) on purpose.
    packages = {package for _, package in _src_files()}
    assert packages <= set(RANK), f"unranked packages: {sorted(packages - set(RANK))}"


def test_src_imports_only_downwards():
    """No src/ package imports from a package of equal or higher rank."""
    upwards = []
    for path, package in _src_files():
        for module in _imported_modules(path):
            other = _package_of(module)
            if other and other != package and RANK[other] >= RANK[package]:
                upwards.append(f"{path.relative_to(ROOT)} ({package}) imports {module} ({other})")
    assert not upwards, "imports that point up or sideways:\n" + "\n".join(sorted(set(upwards)))


@pytest.mark.parametrize("above", ["api", "agent", "eval"])
def test_src_never_imports_the_layers_that_use_it(above):
    """No file under src/ imports from api, agent, or eval — those layers
    consume src, not the other way around."""
    offenders = []
    for path, _ in _src_files():
        for module in _imported_modules(path):
            if module == above or module.startswith(f"{above}."):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")
    assert not offenders, "\n".join(sorted(set(offenders)))


def test_routers_do_not_import_each_other():
    """No file under api/routers/ imports another router module or api.main."""
    # Each router stands on its own; what two of them share belongs in src/ or api/deps.py.
    offenders = []
    for path in sorted((ROOT / "api" / "routers").glob("*.py")):
        for module in _imported_modules(path):
            if module.startswith("api.routers.") or module == "api.main":
                offenders.append(f"{path.name} imports {module}")
    assert not offenders, "\n".join(offenders)
