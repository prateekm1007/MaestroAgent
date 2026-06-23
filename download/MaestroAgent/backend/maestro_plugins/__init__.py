"""maestro_plugins — plugin discovery, loading, and registry.

Plugins extend MaestroAgent with new agents, tools, loops, verifiers,
and memory backends. A plugin is a Python package that declares an
entry point group `maestro.plugins` with one or more of these kinds:

- `agent` — registers a new agent factory.
- `tool` — registers a new tool callable.
- `loop` — registers a new loop factory.
- `verifier` — registers a new verifier.
- `memory_backend` — registers a new memory backend.

For v0.1, plugins run in-process. The sandboxed out-of-process mode is
deferred to v0.2.
"""

from maestro_plugins.registry import PluginRegistry, PluginEntry
from maestro_plugins.loader import load_plugin, discover_plugins

__all__ = ["PluginRegistry", "PluginEntry", "load_plugin", "discover_plugins"]
