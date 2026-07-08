# Known Limitations

## Pilot Scope

### What Works
- Situation-centric intelligence across Ask, Briefing, Prepare, Whisper
- Learning loop (A→B→C→D) with falsification
- Governance operator surface (promote, suspend, falsify, override)
- Tenant isolation (org-scoped)
- ACL on derived intelligence (restricted evidence redacted)
- Prompt injection detection (12 attack patterns)
- Calibration honesty (sample-size display gate)
- Duplicate-work meta-situation detection

### What Is Partially Supported
- **Early-checkpoint detection:** 5/7 first checkpoints detect immediately. 2/7 require a second signal (non-high-salience first signals). Lowering the threshold further risks false-positive situations in multi-entity scenarios.
- **Naked-LLM comparison:** Harness executed in maestro-only mode (200/240 = 83.3%). Full LLM baseline requires an API key (OpenAI/Anthropic).
- **Calibration data:** Learning loop is mechanically closed but empirically thin (<10 real outcomes per pattern). Pilot must generate this data.

### What Is Not Supported in Pilot
- **Multi-tenant production:** Single-tenant only for pilot. Multi-tenant requires security pen-test + load testing.
- **Real-time meeting transcription:** Architecture exists but not validated with live audio.
- **PostgreSQL:** SQLite is pilot-acceptable. Postgres migration deferred until second customer.
- **SOC 2 Type II:** Not started. Required for enterprise contracts.
- **ChromaDB/vector embeddings:** Falls back to TF-IDF when `sentence-transformers` is not installed. Semantic search works but is less powerful.

## Degraded Modes

| Component | Failure Mode | Behavior |
|-----------|-------------|----------|
| LLM provider | API unavailable | Falls back to rule-based synthesis (deterministic, no entropy) |
| Database | SQLite locked | In-memory fallback, situations not persisted |
| Vector search | ChromaDB unavailable | TF-IDF fallback (less semantic, still functional) |
| Signal providers | Connector failure | Graceful degradation — existing signals remain, no new ingestion |

## Out of Scope for Pilot

- Browser extension (exists but not pilot-critical)
- Ambient intelligence engines (12 built, not behaviorally validated)
- PWA/offline mode (architecturally present, not tested)
- Multi-language support (deferred)
- Advanced analytics dashboard (exists, not executive-validated)
