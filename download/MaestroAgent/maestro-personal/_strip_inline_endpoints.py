"""Surgical script to strip inline @app endpoints from api.py.

Each block starts at an @app.post/@app.get/@app.delete line and ends at the
next @app.* decorator OR a section separator comment (`# ---`).

We EXCLUDE:
- @app.middleware
- @app.exception_handler
- @app.add_api_websocket_route (handled separately — keep WS handler)

We ALSO delete router-specific Pydantic model classes that have been moved
to the router files. These are identified by name.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


API_PATH = Path(__file__).resolve().parent / "src" / "maestro_personal_shell" / "api.py"


# Pydantic model classes that have been moved to routers and should be
# DELETED from api.py. The shared models (LoginRequest, LoginResponse,
# SignalCreate, SignalResponse, AskRequest, AskResponse, CommitmentResponse,
# CommitmentsMasterpieceResponse, SituationResponse, WhatChangedResponse,
# WhatChangedMasterpieceResponse, PrepareResponse) STAY in api.py because
# they're shared / imported by other modules.
MODELS_TO_DELETE = {
    "WhisperResponse",
    "GmailSyncRequest", "GmailSyncResponse",
    "CalendarSyncRequest", "CalendarSyncResponse",
    "DeviceRegisterRequest", "DeviceRegisterResponse",
    "PushDeliverResponse",
    "TranscriptChunkRequest",
    "PostCallSummaryRequest",
    "FollowUpEmailRequest",
    "PreCallIntelRequest",
    "PostCallSummaryUIRequest",
    "PlaybookUpsertRequest", "PlaybookMatchRequest", "PlaybookOutcomeRequest",
    "ShadowStartRequest", "ShadowNoteRequest", "ShadowFeedbackRequest",
    "ConnectorConnectRequest", "ConnectorDraftRequest",
    "ConnectorAutoDraftRequest", "DraftResolutionRequest",
    "TalkRatioRequest", "NegotiationRequest",
    "PredictionRequest", "OutcomeRequest",
    "CommitmentSimulationRequest",
    "SlackIngestRequest", "TranscriptIngestRequest",
    "BriefingResponse", "TheMomentResponse",
}


def find_block_end(lines: list[str], start: int) -> int:
    """Find the end of a @app.* block. Returns the index of the last line
    of the block (exclusive end = last+1)."""
    # The block extends until we hit:
    # - Another @app.* decorator
    # - A section comment line (`# ---` at start, after blank lines)
    # - A top-level `def ` or `class ` (not inside the function)
    # - EOF
    # The decorator at `start` is immediately followed by `async def` or
    # `def` (the function signature). We skip that line and start looking
    # for the end AFTER it.
    i = start + 1
    # Skip past the function signature line(s) — there may be multi-line
    # signatures with continuations.
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            # Check if this is a multi-line signature (no colon at end)
            if not stripped.rstrip().endswith(":"):
                i += 1
                continue
            i += 1  # move past the signature line
            break
        elif stripped.startswith("@"):  # additional decorators
            i += 1
            continue
        else:
            i += 1
            break
    # Now i points to the first line of the function body. Keep going
    # until we find a top-level def/class/decorator or section comment.
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        # Next decorator → end
        if stripped.startswith("@app."):
            return i
        # Section separator → end
        if stripped.startswith("# ---") and i > start + 1:
            return i
        # Top-level def/class (column 0) → end
        if (stripped.startswith("def ") or stripped.startswith("class ")
                or stripped.startswith("async def ")) and not line.startswith(" ") and not line.startswith("\t"):
            return i
        i += 1
    return i


def main():
    src = API_PATH.read_text()
    lines = src.split("\n")

    # Find all @app.* decorator lines (excluding middleware/exception_handler)
    blocks_to_delete = []  # list of (start, end) tuples (end exclusive)
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("@app."):
            kind = stripped.split("(", 1)[0].split(".", 1)[1].split()[0]
            if kind in ("middleware", "exception_handler"):
                i += 1
                continue
            # Found an endpoint decorator
            start = i
            end = find_block_end(lines, i)
            blocks_to_delete.append((start, end))
            i = end
        else:
            i += 1

    # Find Pydantic model classes to delete (top-level `class X(BaseModel):`)
    model_blocks = []  # list of (start, end) tuples
    i = 0
    while i < len(lines):
        line = lines[i]
        if not (line.startswith(" ") or line.startswith("\t")):
            m = re.match(r"^class (\w+)\(BaseModel\):", line)
            if m and m.group(1) in MODELS_TO_DELETE:
                start = i
                end = find_block_end(lines, i)
                model_blocks.append((start, end))
                i = end
                continue
        i += 1

    # Also delete the _login_decorator line + comment that's now unused
    # (the routers handle rate limiting)
    extra_lines_to_delete = set()
    for i, line in enumerate(lines):
        # Delete the _login_decorator = ... line
        if line.startswith("_login_decorator = "):
            extra_lines_to_delete.add(i)
        # Delete the # 1. POST /api/auth/login — bearer token auth comment
        if line.startswith("# 1. POST /api/auth/login"):
            extra_lines_to_delete.add(i)
        if line.startswith("# Phase 1: stricter rate limit"):
            extra_lines_to_delete.add(i)

    # Combine all blocks to delete
    all_blocks = blocks_to_delete + model_blocks
    # Convert to set of line indices
    lines_to_delete = set()
    for start, end in all_blocks:
        for j in range(start, end):
            lines_to_delete.add(j)
    lines_to_delete.update(extra_lines_to_delete)

    # Build the new file
    new_lines = [line for i, line in enumerate(lines) if i not in lines_to_delete]

    # Clean up: collapse 3+ consecutive blank lines into 2
    cleaned = []
    blank_count = 0
    for line in new_lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append(line)
        else:
            blank_count = 0
            cleaned.append(line)

    # Write back
    API_PATH.write_text("\n".join(cleaned))

    print(f"Deleted {len(lines_to_delete)} lines from {API_PATH.name}")
    print(f"  - {len(blocks_to_delete)} @app endpoint blocks")
    print(f"  - {len(model_blocks)} model classes")
    print(f"  - {len(extra_lines_to_delete)} extra lines")
    print(f"Original: {len(lines)} lines, New: {len(cleaned)} lines")


if __name__ == "__main__":
    main()
