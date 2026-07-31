#!/usr/bin/env python3
"""Deep audit: find unwired modules in the MaestroAgent codebase.

A module is "wired" if it is imported (directly or transitively) by one
of the production entry points:
  - maestro-personal/src/maestro_personal_shell/api.py (the FastAPI app)
  - maestro-personal/src/maestro_personal_shell/shell.py (the shell)
  - backend/maestro_oem/engine.py (the OEM engine)

A module is "unwired" if it exists on disk but is NOT imported by any
production entry point — only by tests, or by nothing at all.

This is a P11/P43 audit: "built-but-not-wired is not done."

Output: a table of all modules, classified as:
  - WIRED (imported by a production entry point, directly or transitively)
  - TEST-ONLY (imported only by test files)
  - ORPHAN (not imported by anything)
"""
import ast
import os
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path("/home/z/my-project/MaestroAgent/download/MaestroAgent")
BACKEND_OEM = ROOT / "backend" / "maestro_oem"
PERSONAL_SHELL = ROOT / "maestro-personal" / "src" / "maestro_personal_shell"

# Production entry points
ENTRY_POINTS = [
    PERSONAL_SHELL / "api.py",
    PERSONAL_SHELL / "shell.py",
    BACKEND_OEM / "engine.py",
]

def get_module_name(file_path: Path) -> str:
    """Get the module name (e.g., 'maestro_oem.delivery_decision')."""
    try:
        rel = file_path.relative_to(ROOT)
        parts = list(rel.parts[:-1]) + [rel.stem]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)
    except ValueError:
        return file_path.stem

def extract_imports(file_path: Path) -> set[str]:
    """Extract all imported module names from a Python file."""
    if not file_path.exists():
        return set()
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
                # Also add the full path for relative imports
                if node.level and node.level > 0:
                    # Relative import — resolve against the file's package
                    pkg_parts = file_path.relative_to(ROOT).parts[:-1]
                    base = ".".join(pkg_parts[:len(pkg_parts) - node.level + 1]) if len(pkg_parts) >= node.level else ""
                    if base:
                        full = f"{base}.{node.module}" if node.module else base
                        imports.add(full)
    return imports

def find_all_python_files(root: Path) -> list[Path]:
    """Find all .py files, excluding tests."""
    files = []
    for p in root.rglob("*.py"):
        parts = p.parts
        if "test" in p.name.lower() or "tests" in parts or "__pycache__" in parts:
            continue
        files.append(p)
    return files

def build_import_graph(root: Path) -> dict[Path, set[Path]]:
    """Build a graph: file -> set of files it imports."""
    all_files = find_all_python_files(root)
    # Map module names to file paths
    name_to_path = {}
    for f in all_files:
        # Register both the full module name and the short name
        full_name = get_module_name(f)
        short_name = f.stem
        name_to_path[full_name] = f
        name_to_path[short_name] = f
        # Also register maestro_oem.X and maestro_personal_shell.X forms
        if "maestro_oem" in full_name:
            name_to_path[full_name.split(".")[-1]] = f
        if "maestro_personal_shell" in full_name:
            name_to_path[full_name.split(".")[-1]] = f

    graph = {}
    for f in all_files:
        imports = extract_imports(f)
        resolved = set()
        for imp in imports:
            # Try exact match
            if imp in name_to_path:
                resolved.add(name_to_path[imp])
            else:
                # Try suffix match (e.g., "maestro_oem.delivery_decision" matches)
                for name, path in name_to_path.items():
                    if imp.endswith(name) or name.endswith(imp):
                        if path != f:  # don't self-reference
                            resolved.add(path)
                            break
        graph[f] = resolved
    return graph

def transitive_closure(graph: dict[Path, set[Path]], start: Path) -> set[Path]:
    """Compute the transitive closure of imports from start."""
    visited = set()
    queue = [start]
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited

def main():
    print("=" * 78)
    print("DEEP AUDIT: Unwired Modules (P11/P43)")
    print("=" * 78)

    # Build import graph for both source trees
    oem_graph = build_import_graph(BACKEND_OEM)
    personal_graph = build_import_graph(PERSONAL_SHELL)

    # Merge the graphs
    all_graph = {**oem_graph, **personal_graph}

    # Compute transitive closure from each entry point
    wired = set()
    for ep in ENTRY_POINTS:
        if ep.exists():
            closure = transitive_closure(all_graph, ep)
            wired |= closure
            print(f"\nEntry point: {ep.relative_to(ROOT)}")
            print(f"  Transitive closure: {len(closure)} files")

    # Find all modules that are NOT in the wired set
    all_modules = set(all_graph.keys())
    unwired = all_modules - wired

    # For each unwired module, check if it's imported by any test file
    test_files = []
    for root in [BACKEND_OEM, PERSONAL_SHELL]:
        for p in root.rglob("test*.py"):
            test_files.append(p)
        for p in root.rglob("*test*.py"):
            if p not in test_files:
                test_files.append(p)

    test_imported = set()
    for tf in test_files:
        imports = extract_imports(tf)
        for imp in imports:
            for name, path in {**{get_module_name(f): f for f in all_modules},
                              **{f.stem: f for f in all_modules}}.items():
                if imp.endswith(name) or name.endswith(imp):
                    test_imported.add(path)

    # Classify
    orphans = unwired - test_imported
    test_only = unwired & test_imported

    print(f"\n{'=' * 78}")
    print(f"SUMMARY")
    print(f"{'=' * 78}")
    print(f"Total modules (excl. tests): {len(all_modules)}")
    print(f"Wired (in transitive closure of entry points): {len(wired)}")
    print(f"Test-only (imported by tests, not by production): {len(test_only)}")
    print(f"Orphans (not imported by anything): {len(orphans)}")

    print(f"\n{'=' * 78}")
    print(f"ORPHAN MODULES (not imported by anything — strongest candidates")
    print(f"for P11 'built-but-not-wired' findings)")
    print(f"{'=' * 78}")
    for f in sorted(orphans, key=lambda x: x.name):
        try:
            rel = f.relative_to(ROOT)
            size = f.stat().st_size
            print(f"  {rel} ({size} bytes)")
        except ValueError:
            print(f"  {f}")

    print(f"\n{'=' * 78}")
    print(f"TEST-ONLY MODULES (imported by tests but not by production)")
    print(f"{'=' * 78}")
    for f in sorted(test_only, key=lambda x: x.name):
        try:
            rel = f.relative_to(ROOT)
            size = f.stat().st_size
            print(f"  {rel} ({size} bytes)")
        except ValueError:
            print(f"  {f}")

if __name__ == "__main__":
    main()
