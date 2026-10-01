"""List modules and public functions/classes in src/, api/, agent/, eval/
and test/ that have no docstring — run via
`python -m src.tools.docstring_audit`. Exits non-zero if anything is
missing, so it can gate the documentation pass the same way a test does.

Private helpers (a leading underscore) are skipped: the acceptance
criterion is "every public module and function", not every internal
detail — a private helper's purpose should already be clear from where
it's called and its name, or a "why" comment where it isn't (see
CLAUDE.md's comment guidance), not a docstring.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCAN_DIRS = ["src", "api", "agent", "eval", "test"]


def _is_private(name: str) -> bool:
    # Dunders (e.g. __init__) are still public API from a docstring's point
    # of view when they carry real behavior, but __init__ without a
    # docstring is the common case and usually redundant with the class's
    # own — so only a single leading underscore counts as private here.
    return name.startswith("_") and not name.startswith("__")


def _public_defs(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not _is_private(node.name):
                yield node


def _find_python_files():
    for scan_dir in SCAN_DIRS:
        for path in (ROOT / scan_dir).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def audit() -> list[str]:
    """Return one message per missing docstring, module path first."""
    missing = []
    for path in sorted(_find_python_files()):
        rel = path.relative_to(ROOT)
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))

        if ast.get_docstring(tree) is None:
            missing.append(f"{rel}: module has no docstring")

        for node in _public_defs(tree):
            if ast.get_docstring(node) is None:
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                missing.append(f"{rel}:{node.lineno}: {kind} '{node.name}' has no docstring")

    return missing


def main() -> int:
    """Run the audit and print each missing docstring. Exits 0 if none are
    missing, 1 otherwise, so it can be used as a CI/pre-commit gate."""
    missing = audit()
    if not missing:
        print("No missing docstrings.")
        return 0

    print(f"{len(missing)} missing docstring(s):")
    for line in missing:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
