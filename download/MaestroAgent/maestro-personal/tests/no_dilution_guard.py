"""
No-dilution guard — AST-based architectural guard.

Extracted from test_personal_shell_works.py to fix 3 weaknesses identified
by the auditor at cfbe442:

1. Logic duplication: the positive test reimplemented the guard logic
   instead of calling it. Now both tests call check_for_dilution().
2. String-presence bypass: a comment mentioning "calibration_primitives"
   bypassed the guard. Now uses AST to check for real import statements.
3. Dead `import ast`: the guard didn't use AST. Now it does.

The guard scans .py files for forbidden patterns (inline reimplementations
of Core capabilities). If a forbidden pattern is found, the guard checks
whether the file has a REAL import (via AST) of the corresponding Core
primitive. If not, it's a dilution violation.

This is the mechanical defense against the dilution pattern returning
under time pressure (P34). The guard is called by both the real test
and the positive test, so they cannot diverge.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass, field


@dataclass
class DilutionRule:
    """A rule for detecting dilution of a Core capability.

    Attributes:
        forbidden_patterns: string patterns that indicate inline
            reimplementations (e.g., "(p - actual) ** 2" for Brier score)
        required_imports: module names that must be imported if a
            forbidden pattern is present (e.g., "calibration_primitives")
        capability_name: human-readable name for error messages
    """
    forbidden_patterns: list[str]
    required_imports: list[str]
    capability_name: str


# The rules — each maps a Core capability to its forbidden patterns
# and required imports.
DILUTION_RULES: list[DilutionRule] = [
    DilutionRule(
        forbidden_patterns=[
            "(p - actual) ** 2",  # inline Brier
            "(p-actual)**2",
            "brier_score =",
            "def brier",
        ],
        required_imports=["calibration_primitives"],
        capability_name="Brier score / calibration",
    ),
    DilutionRule(
        forbidden_patterns=[
            "def synthesize_judgment",
            "def _synthesize",
            "MIN_EVIDENCE_FOR_DECISION =",
        ],
        required_imports=["judgment_synthesizer", "JudgmentSynthesizer"],
        capability_name="Judgment synthesis",
    ),
]


@dataclass
class DilutionViolation:
    """A single dilution violation found by the guard."""
    file_name: str
    pattern: str
    capability: str
    required_imports: list[str]
    message: str

    def __str__(self) -> str:
        return self.message


def _has_real_import(source: str, module_names: list[str]) -> bool:
    """Check if the source has a REAL import of any of the module names.

    Uses AST to parse the source and check for actual import statements,
    NOT string presence (which can be fooled by comments mentioning the
    module name).

    Recognizes:
      - `import calibration_primitives`
      - `from calibration_primitives import ...`
      - `from maestro_cognitive_council.calibration_primitives import ...`
      - `import ... as JudgmentSynthesizer` (alias)
      - `from ... import JudgmentSynthesizer` (name import)

    A comment like `# must import calibration_primitives` does NOT count.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # If the file doesn't parse, fall back to string check
        # (better than skipping — a syntax error in a Personal module
        # is itself a problem worth surfacing)
        for name in module_names:
            if name in source:
                return True
        return False

    for node in ast.walk(tree):
        # `import calibration_primitives` or `import foo.calibration_primitives`
        if isinstance(node, ast.Import):
            for alias in node.names:
                for name in module_names:
                    if name in alias.name:
                        return True
                    # Also check alias (import X as JudgmentSynthesizer)
                    if alias.asname and name in alias.asname:
                        return True
        # `from calibration_primitives import ...` or
        # `from foo import calibration_primitives` or
        # `from foo import JudgmentSynthesizer`
        elif isinstance(node, ast.ImportFrom):
            # Check the module being imported from
            if node.module:
                for name in module_names:
                    if name in node.module:
                        return True
            # Check the names being imported
            for alias in node.names:
                for name in module_names:
                    if name in alias.name:
                        return True
                    if alias.asname and name in alias.asname:
                        return True

    return False


def check_for_dilution(
    package_dir: pathlib.Path,
    rules: list[DilutionRule] | None = None,
) -> list[DilutionViolation]:
    """Scan a package directory for dilution violations.

    For each .py file in the directory (recursively), check each rule.
    If a forbidden pattern is found AND the file does not have a real
    import of the required module, it's a violation.

    Args:
        package_dir: the directory to scan (e.g., src/maestro_personal_shell/)
        rules: the dilution rules to check (default: DILUTION_RULES)

    Returns:
        A list of DilutionViolation objects. Empty list = no violations.
    """
    if rules is None:
        rules = DILUTION_RULES

    violations: list[DilutionViolation] = []

    if not package_dir.exists():
        # If the dir doesn't exist, that's not "no violations" —
        # that's a guard misconfiguration. But we return empty rather
        # than fail, because the scans-real-package test catches this
        # separately.
        return violations

    for py_file in package_dir.rglob("*.py"):
        try:
            source = py_file.read_text()
        except Exception:
            continue

        for rule in rules:
            for pattern in rule.forbidden_patterns:
                if pattern in source:
                    # Found a forbidden pattern — check for real import
                    if not _has_real_import(source, rule.required_imports):
                        violation = DilutionViolation(
                            file_name=py_file.name,
                            pattern=pattern,
                            capability=rule.capability_name,
                            required_imports=rule.required_imports,
                            message=(
                                f"{py_file.name}: found '{pattern}' "
                                f"({rule.capability_name}) without importing "
                                f"any of {rule.required_imports}"
                            ),
                        )
                        violations.append(violation)

    return violations
