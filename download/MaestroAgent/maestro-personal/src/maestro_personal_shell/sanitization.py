"""Output Sanitization Layer (P86 / FA31).

Every API response passes through `sanitize_output()` before serialization.
This module loads the regex patterns from `config/sanitization_patterns.yaml`
and applies them recursively to all string fields in the response.

Why this exists:
    Audit #2 (2026-07-27) found that the Prepare card rendered the literal
    string "[SEMANTIC INJECTION DETECTED AND REMOVED]" to the user. The
    guard string is internal defensive machinery — it should never be
    exposed. The same audit found UUID-labeled credentials, raw email
    headers, and Kotak/Zerodha client codes in responses.

    This module is the structural guarantee (P86) that no internal guard
    string, debug token, HTML entity, raw email header, UUID-labeled
    credential, or placeholder marker appears in user-facing responses.

Usage:
    from maestro_personal_shell.sanitization import sanitize_output
    cleaned = sanitize_output(response_dict)

    # Or as a FastAPI middleware (preferred — applies to every response):
    from maestro_personal_shell.sanitization import SanitizationMiddleware
    app.add_middleware(SanitizationMiddleware)

Governance citations:
    - P1: every pattern is tested by scripts/check_p86_output_sanitization.py
    - P6: every redaction is logged loudly (no silent swallowing)
    - P10: root cause documented — guard strings leaked because no output
      sanitization layer existed between the LLM safety filter and the
      HTTP response serializer
    - P86: this module IS the P86 enforcement
    - FA31: leaking internal guard strings is forbidden; this module
      prevents it structurally
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Singleton: load patterns once on first use, cache for the process lifetime.
_patterns_cache: list[dict[str, Any]] | None = None
_config_cache: dict[str, Any] | None = None

# The config file lives at <project_root>/config/sanitization_patterns.yaml.
# In dev (editable install) the root is two levels up from this file:
#   src/maestro_personal_shell/sanitization.py → ../.. = src/... but we
# actually need to walk up to the repo root that contains `config/`.
# Try several candidate locations in order; first match wins.
_CANDIDATE_CONFIG_PATHS = [
    # Editable install / dev: <repo>/maestro-personal/config/sanitization_patterns.yaml
    Path(__file__).resolve().parent.parent.parent / "config" / "sanitization_patterns.yaml",
    # Installed package: <repo>/config/sanitization_patterns.yaml (one level up from src/)
    Path(__file__).resolve().parent.parent / "config" / "sanitization_patterns.yaml",
    # Railway/production: relative to CWD
    Path.cwd() / "config" / "sanitization_patterns.yaml",
    Path.cwd() / "src" / "config" / "sanitization_patterns.yaml",
]
_CONFIG_PATH: Path | None = None
for _candidate in _CANDIDATE_CONFIG_PATHS:
    if _candidate.exists():
        _CONFIG_PATH = _candidate
        break


def _load_patterns() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load and compile sanitization patterns from the YAML config.

    Returns (compiled_patterns, config). Compiled patterns are dicts with
    keys: name, regex (compiled), replacement, scope.
    """
    global _patterns_cache, _config_cache
    if _patterns_cache is not None and _config_cache is not None:
        return _patterns_cache, _config_cache

    if not _CONFIG_PATH or not _CONFIG_PATH.exists():
        logger.error(
            "sanitization: config file not found in any candidate path — "
            "sanitization DISABLED. Searched: %s",
            [str(p) for p in _CANDIDATE_CONFIG_PATHS],
        )
        _patterns_cache = []
        _config_cache = {"enabled": False, "log_redactions": True}
        return _patterns_cache, _config_cache

    try:
        with _CONFIG_PATH.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("sanitization: failed to load %s: %s — sanitization DISABLED", _CONFIG_PATH, e)
        _patterns_cache = []
        _config_cache = {"enabled": False, "log_redactions": True}
        return _patterns_cache, _config_cache

    raw_patterns = doc.get("patterns", []) or []
    compiled: list[dict[str, Any]] = []
    for p in raw_patterns:
        name = p.get("name", "<unnamed>")
        pattern_str = p.get("pattern", "")
        if not pattern_str:
            continue
        try:
            # Use re.MULTILINE so ^ and $ match line starts (for header patterns)
            regex = re.compile(pattern_str, re.MULTILINE)
        except re.error as e:
            logger.error("sanitization: pattern %r failed to compile (%s) — skipping", name, e)
            continue
        compiled.append({
            "name": name,
            "regex": regex,
            "replacement": p.get("replacement", "[redacted]"),
            "scope": p.get("scope", "all"),
        })

    cfg = doc.get("config", {}) or {}
    _patterns_cache = compiled
    _config_cache = cfg
    logger.info("sanitization: loaded %d patterns from %s (enabled=%s)",
                len(compiled), _CONFIG_PATH, cfg.get("enabled", True))
    return compiled, cfg


def _sanitize_string(s: str) -> str:
    """Apply all patterns to a single string. Returns the cleaned string.

    Patterns with scope="all" apply to every string. Patterns with
    scope="string_fields_only" also apply here (they're a subset of "all"
    in practice — the distinction matters in _walk where binary fields
    might exist, but for JSON responses everything is a string eventually).
    """
    patterns, cfg = _load_patterns()
    if not cfg.get("enabled", True) or not patterns:
        return s

    log_redactions = cfg.get("log_redactions", True)
    log_pattern_name = cfg.get("log_pattern_name", True)
    cleaned = s
    for p in patterns:
        # Skip empty replacements applied to non-matching strings (perf).
        if p["regex"].search(cleaned) is None:
            continue
        if log_redactions:
            if log_pattern_name:
                logger.warning(
                    "sanitization: PATTERN %s fired — replacing match with %r",
                    p["name"], p["replacement"][:40],
                )
            else:
                logger.warning("sanitization: redaction fired")
        cleaned = p["regex"].sub(p["replacement"], cleaned)
    return cleaned


def _walk(obj: Any, depth: int = 0) -> Any:
    """Recursively walk a JSON-serializable structure and sanitize all strings.

    Defensive: caps recursion at max_depth to prevent stack overflow on
    pathological inputs.
    """
    _, cfg = _load_patterns()
    max_depth = cfg.get("max_depth", 20)
    if depth > max_depth:
        logger.warning("sanitization: max_depth %d exceeded — returning object as-is", max_depth)
        return obj

    if isinstance(obj, str):
        return _sanitize_string(obj)
    if isinstance(obj, dict):
        return {k: _walk(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, depth + 1) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_walk(v, depth + 1) for v in obj)
    # int, float, bool, None, bytes — leave alone.
    return obj


def sanitize_output(obj: Any) -> Any:
    """Sanitize all string fields in a JSON-serializable response.

    This is the public entry point. Walks dicts/lists recursively and
    applies every pattern in config/sanitization_patterns.yaml to every
    string field. Non-string fields are passed through unchanged.

    Returns a NEW structure (does not mutate the input).
    """
    return _walk(obj)


# ---------------------------------------------------------------------------
# FastAPI middleware
# ---------------------------------------------------------------------------


class SanitizationMiddleware:
    """FastAPI/Starlette middleware that sanitizes every JSON response body.

    Add to the app with:
        from maestro_personal_shell.sanitization import SanitizationMiddleware
        app.add_middleware(SanitizationMiddleware)

    The middleware intercepts responses with content-type: application/json,
    parses the body, runs `sanitize_output()`, and re-serializes. Non-JSON
    responses (HTML, plain text, binary) are passed through unchanged.

    Per P85 (read-endpoint reliability), this middleware NEVER raises —
    if sanitization fails for any reason, the original response is returned
    and a loud log is emitted. Sanitization is a defense-in-depth layer;
    it must not become a new source of 500s.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        # Buffer the response so we can sanitize the body before sending.
        # We re-emit headers + status unchanged; only the body is modified.
        status_code = None
        headers = []
        body_chunks: list[bytes] = []

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                nonlocal status_code, headers
                status_code = message.get("status", 200)
                headers = list(message.get("headers", []))
                # Don't forward yet — wait for body.
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))
                # If more body is coming (streaming), we'd need to handle
                # that separately. For JSON API responses, this is a single
                # message — assume so until proven otherwise.
            else:
                await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # The underlying app raised; let the error bubble up to
            # FastAPI's default error handler. Sanitization doesn't interfere.
            raise

        body = b"".join(body_chunks)

        # Check content-type — only sanitize JSON.
        content_type = ""
        for k, v in headers:
            if k.lower() == b"content-type":
                content_type = v.decode("latin-1", errors="replace").lower()
                break

        if "application/json" in content_type and body:
            try:
                parsed = json.loads(body)
                cleaned = sanitize_output(parsed)
                new_body = json.dumps(cleaned, ensure_ascii=False, default=str).encode("utf-8")
                # Update content-length if it was set.
                headers = [
                    (k, v) for k, v in headers
                    if k.lower() != b"content-length"
                ]
                headers.append((b"content-length", str(len(new_body)).encode("ascii")))
                body = new_body
            except json.JSONDecodeError:
                # Body isn't valid JSON even though content-type said so.
                # Log and pass through unchanged.
                logger.warning(
                    "sanitization: response had content-type=application/json "
                    "but body failed to parse as JSON — passing through unchanged"
                )
            except Exception as e:
                # P85: never raise from sanitization. Log loudly and pass through.
                logger.error(
                    "sanitization: failed to sanitize response (P85 — passing through unchanged): %s",
                    e, exc_info=True,
                )

        # Emit the (possibly sanitized) response.
        await send({
            "type": "http.response.start",
            "status": status_code or 200,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": body})
