"""
Patched API entry point that fixes the commitment classifier.

This module imports the original api module and applies the classifier patch
before the FastAPI app starts. This allows us to fix the classifier without
modifying the original 249KB api.py file.
"""

# Import and apply the classifier patch FIRST
import maestro_personal_shell.commitment_classifier_patch_v2  # noqa: F401

# Now import the original api module (which will use the patched classifier)
from maestro_personal_shell.api import app  # noqa: F401

# Re-export everything from the original api
from maestro_personal_shell.api import *  # noqa: F401, F403
