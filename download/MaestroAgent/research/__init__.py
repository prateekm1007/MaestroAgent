"""Research package: methodology + findings.

Methodology (tools for doing science):
  - PreRegistration: write-once protocol with hash verification
  - ValidityRegion: bounded conditional claims
  - Model selection: AIC, BIC, MDL

Findings (scientific results):
  - TSS v1: Temporal Scale Separation (Supported)
  - Dual-Component v1: Behavioral + Representational interference (Predictive)
  - ASS construct: defines TSS's scope
"""

from research.methodology import PreRegistration, ValidityRegion, compute_model_selection_criteria, compare_models, is_complexity_justified
from research.findings import TSS_V1, DUAL_COMPONENT_V1, ALL_THEORIES, AdaptiveStateSystem
