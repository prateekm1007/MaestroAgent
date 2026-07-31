"""Ops swarm package — autonomous operations for Maestro.

Phase 1 (this package):
  - governance/          : constitution files (ANTI_ENTROPY, FORBIDDEN_ACTIONS, etc.)
  - governance_enforcer  : 3-layer enforcement (deterministic + LLM critic + outcome verify)
  - case_memory          : FTS5-backed incident knowledge base, seeded from audit
  - ops_council          : ticket loop (diagnose → repair → verify → report)

Phase 2 (future):
  - Specialize into Coordinator/Diagnostician/Repair/Verifier/Reporter agents
  - Add maestro_memory vector+graph legs to case memory
  - Runbook promotion (verified fixes crystallize into deterministic scripts)
  - MCP server exposing governance + case memory to all agents
"""
