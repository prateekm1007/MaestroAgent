"""Plugin loader — discovers filesystem plugins.

A filesystem plugin is a `.py` file in `backend/plugins/` that defines
a `register(registry: PluginRegistry) -> None` function. The loader
imports each file and calls its `register` function.

This is the simplest possible plugin model — drop a `.py` file in a
directory and it loads. v0.2 will add a manifest format and signature
verification for untrusted plugins.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from maestro_plugins.registry import PluginEntry, PluginRegistry

logger = logging.getLogger(__name__)


def discover_plugins() -> list[PluginEntry]:
    """Discover plugins from the backend/plugins/ directory."""
    plugins_dir = Path(__file__).parent.parent / "plugins"
    if not plugins_dir.exists():
        return []
    entries: list[PluginEntry] = []
    for p in plugins_dir.glob("*.py"):
        if p.name.startswith("_"):
            continue
        try:
            entries.extend(_load_plugin_file(p))
        except Exception as exc:
            logger.warning("Failed to load plugin %s: %s", p, exc)
    return entries


def load_plugin(name: str) -> Any:
    """Load a plugin by name from the plugins directory."""
    plugins_dir = Path(__file__).parent.parent / "plugins"
    path = plugins_dir / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"Plugin {name} not found at {path}")
    spec = importlib.util.spec_from_file_location(f"maestro_plugin_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_plugin_file(path: Path) -> list[PluginEntry]:
    """Load a single plugin file and return its entries."""
    spec = importlib.util.spec_from_file_location(
        f"maestro_plugin_{path.stem}", path
    )
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # If the plugin defines a `PLUGIN_ENTRIES` list, use it.
    if hasattr(module, "PLUGIN_ENTRIES"):
        return list(module.PLUGIN_ENTRIES)

    # Otherwise, if it defines `register`, call it with a temp registry.
    if hasattr(module, "register"):
        temp = PluginRegistry()
        # Remove builtins from the temp so we don't double-register.
        temp._entries.clear()
        module.register(temp)
        return list(temp._entries.values())

    return []
