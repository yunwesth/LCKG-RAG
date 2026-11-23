"""Fails if a module imports across a forbidden boundary (masterplan: everything modular).

Allowed dependency direction:  common  <-  kg_tools  <-  orchestrator ;  common <- ingest ;
evals and scripts are leaf consumers. Modules talk through `common.protocols`, not each other.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# package -> project packages it may import (besides itself)
ALLOWED = {
    "common": set(),
    "kg_tools": {"common"},
    "ingest": {"common"},
    "orchestrator": {"common", "kg_tools"},
    "evals": {"common"},
    "scripts": {"common", "kg_tools", "ingest", "orchestrator", "evals"},
}


def imported_top_level(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_no_forbidden_imports():
    violations = []
    for pkg, allowed in ALLOWED.items():
        for f in (ROOT / pkg).rglob("*.py"):
            bad = (imported_top_level(f) & set(ALLOWED)) - allowed - {pkg}
            if bad:
                violations.append(f"{f.relative_to(ROOT)} imports {sorted(bad)}")
    assert not violations, "\n".join(violations)


def test_only_ingest_may_use_admin_credentials():
    offenders = [
        str(f.relative_to(ROOT))
        for pkg in ("kg_tools", "orchestrator", "evals")
        for f in (ROOT / pkg).rglob("*.py")
        if "admin_password" in f.read_text() or "admin_user" in f.read_text()
    ]
    assert not offenders, f"admin credentials used outside ingest: {offenders}"
