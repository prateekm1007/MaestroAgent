"""MEDIUM-2 fix — Semantic cross-source deduplication.

MEDIUM-2 from external audit at f16cf66:
> The content hash dedup (_compute_content_hash) only deduplicates
> identical signal content — it does not detect semantic copies across
> sources.
> Suggested fix: Cross-source dedup using embedding similarity.

The existing dedup in model.py uses exact-match content_hash (SHA-256 of
type + actor + artifact + metadata). This catches:
  - Same CRM event imported twice (identical content → same hash)
  - Same Slack message re-ingested (identical content → same hash)

But it MISSES:
  - "Globex SSO commitment discussed" on Slack
  - "SSO delivery promise to Globex" in an email
  - "Globex SSO timeline confirmed" in a Jira comment
  These are semantically the same event but have different text, different
  actors, different providers → different content_hash → 3 LOs created
  instead of 1.

This module provides SemanticDeduplicator — uses embedding cosine similarity
to detect cross-source duplicates. Falls back gracefully when embeddings
are unavailable (returns "not a duplicate" — fail-safe, P6).

Usage in model.py:
    from maestro_oem.semantic_dedup import SemanticDeduplicator
    dedup = SemanticDeduplicator()
    if dedup.is_semantic_duplicate(signal, existing_lo):
        # Add evidence to existing LO instead of creating a new one
        existing_lo.add_evidence(...)
    else:
        # Create new LO
        self.learning_objects[lo.lo_id] = lo
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Similarity threshold for semantic dedup (0.0 to 1.0).
# 0.85 = "very similar" — high enough to avoid false positives,
# low enough to catch paraphrased versions of the same event.
SEMANTIC_DEDUP_THRESHOLD = 0.85


class SemanticDeduplicator:
    """Detect semantic duplicates across sources using embedding similarity.

    The deduplicator extracts a "semantic fingerprint" from each signal
    (the text describing the event) and compares it against the text of
    existing LearningObjects. If cosine similarity exceeds the threshold,
    the signals are considered semantic duplicates.

    Falls back to "not a duplicate" when embeddings are unavailable
    (sentence-transformers not installed). This is fail-safe (P6) —
    the system continues to work with exact-match dedup only.

    The deduplicator uses TF-IDF character n-gram fallback when
    sentence-transformers is not available, which is still more
    semantic than exact-match hashing.
    """

    def __init__(self, threshold: float = SEMANTIC_DEDUP_THRESHOLD) -> None:
        self.threshold = threshold
        self._embedder: Any = None
        self._embedder_ready = False
        self._tfidf_fallback: Any = None

    def _get_embedder(self) -> Any:
        """Lazily load the embedding model. Falls back to TF-IDF."""
        if self._embedder_ready:
            return self._embedder
        self._embedder_ready = True
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("SemanticDeduplicator: loaded sentence-transformers")
        except ImportError:
            logger.info(
                "SemanticDeduplicator: sentence-transformers unavailable, "
                "using TF-IDF fallback (less powerful but still semantic)"
            )
            self._embedder = None
            from maestro_oem.semantic_matcher import SemanticMatcher
            self._tfidf_fallback = SemanticMatcher()
        except Exception as e:
            logger.warning("SemanticDeduplicator: embedder load failed: %s", e)
            self._embedder = None
        return self._embedder

    def _extract_text(self, signal: Any) -> str:
        """Extract the semantic text from a signal for comparison."""
        parts = []
        if hasattr(signal, "artifact") and signal.artifact:
            parts.append(str(signal.artifact))
        if hasattr(signal, "metadata") and signal.metadata:
            for key in ("text", "body", "subject", "commitment", "description", "note"):
                val = signal.metadata.get(key, "")
                if val:
                    parts.append(str(val))
        return " ".join(parts).strip()

    def _extract_lo_text(self, lo: Any) -> str:
        """Extract the semantic text from a LearningObject for comparison."""
        parts = []
        if hasattr(lo, "title") and lo.title:
            parts.append(str(lo.title))
        if hasattr(lo, "description") and lo.description:
            parts.append(str(lo.description))
        return " ".join(parts).strip()

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not v1 or not v2:
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def _embed(self, text: str) -> list[float] | None:
        """Embed text using sentence-transformers or TF-IDF fallback."""
        if not text:
            return None
        embedder = self._get_embedder()
        if embedder is not None:
            try:
                vec = embedder.encode(text, normalize_embeddings=True)
                return vec.tolist() if hasattr(vec, "tolist") else list(vec)
            except Exception as e:
                logger.debug("SemanticDeduplicator: embed failed: %s", e)
                return None
        # TF-IDF fallback
        if self._tfidf_fallback is not None:
            try:
                vec = self._tfidf_fallback.embed(text, [text])
                return vec
            except Exception as e:
                logger.debug("SemanticDeduplicator: TF-IDF embed failed: %s", e)
        return None

    def is_semantic_duplicate(
        self,
        signal: Any,
        existing_lo: Any,
    ) -> bool:
        """Check if a signal is semantically a duplicate of an existing LO.

        Args:
            signal: The new ExecutionSignal to check.
            existing_lo: An existing LearningObject to compare against.

        Returns:
            True if the signal's text is semantically similar to the LO's
            text (cosine similarity >= threshold). False otherwise.
            Always returns False if embeddings are unavailable (fail-safe).
        """
        sig_text = self._extract_text(signal)
        lo_text = self._extract_lo_text(existing_lo)
        if not sig_text or not lo_text:
            return False

        sig_vec = self._embed(sig_text)
        lo_vec = self._embed(lo_text)
        if sig_vec is None or lo_vec is None:
            return False

        similarity = self._cosine_similarity(sig_vec, lo_vec)
        if similarity >= self.threshold:
            logger.info(
                "SemanticDeduplicator: duplicate detected (similarity=%.3f, threshold=%.2f) "
                "sig_text=%r lo_text=%r",
                similarity, self.threshold, sig_text[:60], lo_text[:60],
            )
            return True
        return False

    def find_semantic_duplicate(
        self,
        signal: Any,
        existing_los: list[Any],
    ) -> Any | None:
        """Find the first existing LO that is a semantic duplicate of the signal.

        Args:
            signal: The new ExecutionSignal to check.
            existing_los: List of existing LearningObjects to search.

        Returns:
            The first LO that is a semantic duplicate, or None if no match.
        """
        for lo in existing_los:
            if self.is_semantic_duplicate(signal, lo):
                return lo
        return None
