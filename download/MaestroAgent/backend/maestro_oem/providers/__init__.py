"""
Signal normalizers — convert raw provider data into ExecutionSignal objects.

Each provider has a normalize() function that takes raw API data
and returns ExecutionSignal objects.

This is the ONLY way signals enter the OEM.
"""

from maestro_oem.providers.github import normalize_github
from maestro_oem.providers.jira import normalize_jira
from maestro_oem.providers.slack import normalize_slack
from maestro_oem.providers.confluence import normalize_confluence
from maestro_oem.providers.gmail import normalize_gmail

__all__ = [
    "normalize_github",
    "normalize_jira",
    "normalize_slack",
    "normalize_confluence",
    "normalize_gmail",
]
