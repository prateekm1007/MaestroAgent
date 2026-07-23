"""Email-parser framework — extract commitments from platform notification emails.

T2 sources (Amazon, LinkedIn, Instagram, Facebook) don't have consumer read APIs.
But they send notification emails that contain commitments. This framework parses
those emails and re-tags the source to the platform of origin.

This is the "quiet moat multiplier": 4 "connectors" for the price of one parser
layer, zero new OAuth, huge coverage. The commitment from an Amazon "delivery by
Tuesday" email gets source:"amazon" even though the bytes came through Gmail.
"""
from __future__ import annotations

import re
import logging
from typing import Callable

from maestro_personal_shell.connector_framework import Signal

logger = logging.getLogger(__name__)

# Parser registry: (pattern, parser_fn)
# Each pattern matches against the email's From header or body text.
# If matched, the parser_fn extracts structured commitment data and
# returns a new Signal with the source overridden to the platform.
_PARSERS: list[tuple[re.Pattern, Callable]] = []


def register_parser(pattern: str, flags: int = re.IGNORECASE):
    """Decorator: register an email parser for a sender/content pattern.

    Usage:
        @register_parser(r"(ship|delivery|order).*amazon")
        def parse_amazon(sig: Signal) -> list[Signal]:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        compiled = re.compile(pattern, flags)
        _PARSERS.append((compiled, fn))
        return fn
    return decorator


def parse_email_signal(signal: Signal) -> list[Signal]:
    """Run all matching parsers on an email-derived signal.

    If no parser matches, returns the original signal unchanged.
    If a parser matches, returns the parser's enriched signals with
    the source overridden to the platform of origin.
    """
    from_header = signal.metadata.get("from", "")
    text = signal.text

    for pattern, fn in _PARSERS:
        if pattern.search(from_header) or pattern.search(text):
            try:
                result = fn(signal)
                if result:
                    return result
            except Exception as e:
                logger.warning("Email parser %s failed: %s", fn.__name__, e)

    return [signal]


# Import all parsers to register them
try:
    from maestro_personal_shell.connector_framework.parsers import amazon  # noqa: F401
except ImportError:
    pass
try:
    from maestro_personal_shell.connector_framework.parsers import linkedin_mail  # noqa: F401
except ImportError:
    pass
try:
    from maestro_personal_shell.connector_framework.parsers import instagram_mail  # noqa: F401
except ImportError:
    pass
try:
    from maestro_personal_shell.connector_framework.parsers import facebook_mail  # noqa: F401
except ImportError:
    pass
