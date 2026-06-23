"""maestro_memory — multi-tier memory: short-term, semantic, graph, long-term.

Memory is what makes long runs tractable. Without tiered memory, every
agent drowns in its own transcript. With it:

- **Short-term**: bounded rolling window per agent. Summarized on overflow.
- **Semantic**: Chroma/PGVector. Embed every output, retrieve top-k by query.
- **Graph**: entity/agent relationships. "Who produced what, who consumed it."
- **Long-term**: SQLite. Promoted episodes with timestamps, tags, provenance.

The `MemoryManager` is the single entry point. Agents and loops call
`manager.write(...)` and `manager.recall(...)`. The manager routes the
write to the appropriate tiers and handles compaction, versioning, and
RBAC.
"""

from maestro_memory.manager import MemoryManager, MemoryEntry
from maestro_memory.short_term import ShortTermMemory
from maestro_memory.long_term import LongTermMemory
from maestro_memory.vector import VectorMemory, ChromaVectorMemory, InMemoryVectorMemory
from maestro_memory.graph import GraphMemory, NetworkXGraphMemory

__all__ = [
    "MemoryManager",
    "MemoryEntry",
    "ShortTermMemory",
    "LongTermMemory",
    "VectorMemory",
    "ChromaVectorMemory",
    "InMemoryVectorMemory",
    "GraphMemory",
    "NetworkXGraphMemory",
]
