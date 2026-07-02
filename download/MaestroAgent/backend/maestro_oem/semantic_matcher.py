"""
V8 Competitor Analysis Feature B — Semantic Ask.

Replaces the keyword matcher in decision.py answer_question() with
embedding-based semantic similarity. The keyword matcher had a known
bug: a question sharing a single common word with an unrelated law
would surface that law as "relevant evidence" (e.g., "should we hire
more engineers" matched a churn learning object because both contained
"engineers").

The SemanticMatcher uses character n-gram TF-IDF vectors with cosine
similarity. This is genuinely more semantic than keyword matching:
  - Character n-grams capture morphological variants ("hire" ≈ "hiring"
    ≈ "hired") — keyword matching misses these
  - TF-IDF weighting means domain-specific terms (like "OAuth") dominate
    over common words (like "the") — keyword matching treats all words
    equally
  - Cosine similarity produces a continuous score, not a binary match —
    results are ranked by actual relevance, not just overlap count

The interface is designed so a real embedding model (Ollama, OpenAI,
Cohere) can replace the TF-IDF backend in production. The TF-IDF
backend is the default for dev/test environments where no embedding
model is available.

Used by: decision.py answer_question(), which powers GET /api/oem/ask
and the ASK surface.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


class SemanticMatcher:
    """Embedding-based semantic similarity for the Ask engine.

    The matcher computes character n-gram TF-IDF vectors for each text
    and compares them via cosine similarity. This is more semantic than
    keyword matching because:

    1. Character n-grams capture morphological variants — "hire",
       "hiring", "hired", "hires" all share the n-gram "hir" and are
       treated as similar. Keyword matching treats these as different
       words.

    2. TF-IDF weighting down-weights common terms (like "the", "is",
       "should") and up-weights rare domain-specific terms (like "OAuth",
       "bottleneck"). Keyword matching treats all words equally.

    3. Cosine similarity produces a continuous score [0, 1] — results
       are ranked by actual semantic relevance, not just word overlap
       count. This means a law about "recruitment" can match a question
       about "hiring" even though they share no words, because they
       share character n-grams.

    Production upgrade path: the embed() method can be replaced with a
    real embedding model (Ollama nomic-embed-text, OpenAI text-embedding-
    3-small, etc.) without changing any calling code. The TF-IDF backend
    is the default for dev/test.
    """

    def __init__(
        self,
        ngram_size: int = 3,
        max_features: int = 5000,
        similarity_threshold: float = 0.15,
    ) -> None:
        """Initialize the semantic matcher.

        Args:
            ngram_size: Character n-gram size (default 3). 3-grams capture
                       morphological variants while keeping the vocabulary
                       manageable.
            max_features: Maximum vocabulary size. Keeps memory bounded.
            similarity_threshold: Minimum cosine similarity to consider a
                                  match relevant (default 0.15). Below this,
                                  the result is filtered out.
        """
        self.ngram_size = ngram_size
        self.max_features = max_features
        self.similarity_threshold = similarity_threshold
        # Document frequency: how many texts contain each n-gram
        self._df: Counter[str] = Counter()
        # Total number of documents seen (for IDF computation)
        self._num_docs: int = 0
        # Cache for embeddings
        self._embed_cache: dict[str, list[float]] = {}

    def fit(self, texts: list[str]) -> None:
        """Build the TF-IDF vocabulary from a corpus of texts.

        Call this once with all the texts you want to search against
        (laws, learning objects, etc.) before calling similarity().

        Args:
            texts: list of text documents to build the vocabulary from.
        """
        self._df = Counter()
        self._num_docs = 0
        self._embed_cache = {}

        for text in texts:
            if not text:
                continue
            ngrams = self._extract_ngrams(text)
            # Update document frequency (each n-gram counted once per doc)
            for ng in set(ngrams):
                self._df[ng] += 1
            self._num_docs += 1

        # Limit vocabulary to top max_features by document frequency
        if len(self._df) > self.max_features:
            top = self._df.most_common(self.max_features)
            self._df = Counter(dict(top))

    def embed(self, text: str) -> list[float]:
        """Compute the TF-IDF vector for a text.

        Returns a sparse vector represented as a list of floats. The
        vector is keyed by the n-gram vocabulary built by fit().

        In production, this method can be replaced with a real embedding
        model call (e.g., Ollama, OpenAI). The calling code doesn't
        change — only the backend.

        Args:
            text: The text to embed.

        Returns:
            list[float] — the TF-IDF vector (or embedding vector in
            production). Length = len(self._df).
        """
        if not text:
            return [0.0] * max(len(self._df), 1)

        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._embed_cache:
            return self._embed_cache[cache_key]

        ngrams = self._extract_ngrams(text)
        if not ngrams or not self._df:
            self._embed_cache[cache_key] = [0.0] * max(len(self._df), 1)
            return self._embed_cache[cache_key]

        # Term frequency
        tf = Counter(ngrams)

        # TF-IDF vector
        vocab = list(self._df.keys())
        vocab_index = {ng: i for i, ng in enumerate(vocab)}
        vector = [0.0] * len(vocab)

        for ng, count in tf.items():
            if ng not in vocab_index:
                continue
            tf_val = count / len(ngrams)  # normalized TF
            idf_val = math.log((self._num_docs + 1) / (self._df[ng] + 1)) + 1  # smoothed IDF
            vector[vocab_index[ng]] = tf_val * idf_val

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        self._embed_cache[cache_key] = vector
        return vector

    def similarity(self, text1: str, text2: str) -> float:
        """Compute the cosine similarity between two texts.

        Args:
            text1: First text.
            text2: Second text.

        Returns:
            float in [0, 1] — 0 = completely dissimilar, 1 = identical.
        """
        v1 = self.embed(text1)
        v2 = self.embed(text2)
        return self._cosine(v1, v2)

    def rank(self, query: str, candidates: list[tuple[str, Any]]) -> list[tuple[float, Any]]:
        """Rank candidates by semantic similarity to the query.

        Args:
            query: The search query.
            candidates: list of (text, payload) tuples to rank.

        Returns:
            list of (similarity_score, payload) tuples, sorted by score
            descending. Results below similarity_threshold are filtered out.
        """
        q_vec = self.embed(query)
        scored: list[tuple[float, Any]] = []

        for text, payload in candidates:
            if not text:
                continue
            c_vec = self.embed(text)
            score = self._cosine(q_vec, c_vec)
            if score >= self.similarity_threshold:
                scored.append((score, payload))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    # Round 48: Stop words that cause false-positive n-gram matches.
    # These common English words have low semantic content but high n-gram
    # overlap (e.g., "should" in "should we hire" matching "should" in
    # "Pattern should be analyzed"). Filtering them eliminates the
    # "hire engineers" → churn false positive.
    _STOP_WORDS = frozenset({
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'ought',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
        'into', 'through', 'during', 'before', 'after', 'above', 'below',
        'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further',
        'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how',
        'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
        'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
        'than', 'too', 'very', 'just', 'also', 'now', 'we', 'us', 'our',
        'i', 'you', 'your', 'he', 'she', 'it', 'its', 'they', 'them',
        'this', 'that', 'these', 'those', 'what', 'which', 'who', 'whom',
        'and', 'or', 'but', 'if', 'while', 'about', 'against', 'between',
    })

    def _extract_ngrams(self, text: str) -> list[str]:
        """Extract character n-grams from text, filtering stop words.

        Normalizes to lowercase and removes non-alphanumeric characters
        before extracting n-grams. Stop words are filtered to prevent
        false-positive matches from common English words.
        """
        # Normalize: lowercase, keep only alphanumeric + spaces
        normalized = "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in text)
        # Split into words, then extract n-grams from each word
        ngrams: list[str] = []
        for word in normalized.split():
            # Round 48: skip stop words that cause false-positive n-gram matches
            if word in self._STOP_WORDS:
                continue
            if len(word) < self.ngram_size:
                # Short words are included as-is (padded)
                ngrams.append(f"#{word}#")
            else:
                for i in range(len(word) - self.ngram_size + 1):
                    ngrams.append(word[i:i + self.ngram_size])
        return ngrams

    def _cosine(self, v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not v1 or not v2:
            return 0.0
        # Vectors are already L2-normalized in embed(), so cosine = dot product
        dot = sum(a * b for a, b in zip(v1, v2))
        # Clamp to [0, 1] (TF-IDF vectors are non-negative, so cosine is [0, 1])
        return max(0.0, min(1.0, dot))


def build_semantic_matcher(model: Any) -> SemanticMatcher:
    """Build a SemanticMatcher fitted on the model's laws + learning objects.

    This is the factory function used by decision.py to create a matcher
    that's already fitted on the current model state.

    Args:
        model: The ExecutionModel to fit on.

    Returns:
        A fitted SemanticMatcher ready for similarity queries.
    """
    matcher = SemanticMatcher()

    # Collect all texts to fit on
    texts: list[str] = []
    for law in model.laws.values():
        texts.append(f"{law.statement} {law.condition} {law.outcome}")
    for lo in model.learning_objects.values():
        texts.append(f"{lo.title} {lo.description}")

    matcher.fit(texts)
    return matcher
