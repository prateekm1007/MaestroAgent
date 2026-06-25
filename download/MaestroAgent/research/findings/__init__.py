"""Research findings: versioned theories and constructs.

Each theory is an immutable snapshot. Future revisions are new files
(theory_v2.py), not overwrites. This preserves the scientific record.

Current findings:
  - TSS v1 (Supported): same-scale ASSs interfere
  - Dual-Component v1 (Predictive): behavioral + representational interference
  - ASS construct: defines what TSS applies to
"""

from research.findings.TSS.theory_v1 import TSS_V1, AdaptiveStateSystem, VersionedTheory, VersionedPrediction, EvidenceLevel
from research.findings.DualComponent.theory_v1 import DUAL_COMPONENT_V1

ALL_THEORIES = [TSS_V1, DUAL_COMPONENT_V1]
