"""
Smoke test for the Personal shell.

Per build directions Day 1 (P1 — execute, don't read): write the test
BEFORE writing the shell. Run it. It will fail (shell doesn't exist yet).
Then write shell.py to make it pass.

This is the Day 1 gate: if this test passes, the thesis is testable —
the existing Core can detect situations from personal signals via a
thin shell, without extraction, without Rust, without HTTP.
"""

import sys
import pathlib

# Add src to path so we can import maestro_personal without pip install
# during development
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest


class TestPersonalShellSmoke:
    """Day 1 gate: thin Personal shell calling existing Core must detect
    situations from personal signals (not enterprise signals)."""

    def test_personal_shell_detects_situation_from_personal_signals(self):
        """A thin Personal shell calling existing Core must detect situations
        from personal signals."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal

        state = PersonalOemState(signals=[
            PersonalSignal(
                entity="Alex",
                text="I will send the proposal by Friday",
                signal_type="commitment_made",
            ),
            PersonalSignal(
                entity="Alex",
                text="Following up on the proposal — did you get a chance to review?",
                signal_type="reported_statement",
            ),
            PersonalSignal(
                entity="Alex",
                text="Meeting moved to Tuesday",
                signal_type="calendar_change",
            ),
        ])
        shell = PersonalShell(oem_state=state)
        situations = shell.detect_situations()
        assert len(situations) >= 1, (
            f"Expected ≥1 situation from 3 personal signals, got {len(situations)}. "
            "The Core must detect situations from personal signals via the thin shell."
        )
        # The situation should be about Alex
        entities = [getattr(s, "entity", "") for s in situations]
        assert any("alex" in e.lower() for e in entities if e), (
            f"Expected a situation about Alex, got entities: {entities}"
        )

    def test_personal_shell_empty_state_returns_empty(self):
        """An empty personal state yields no situations — fail closed."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState

        state = PersonalOemState(signals=[])
        shell = PersonalShell(oem_state=state)
        situations = shell.detect_situations()
        assert situations == [], (
            f"Empty state should yield no situations, got {len(situations)}"
        )

    def test_personal_shell_does_not_import_enterprise_oem_state(self):
        """The shell must NOT import the enterprise oem_state singleton.

        Per auditor's verified finding: council.py:57 imports enterprise
        oem_state which loads the enterprise demo seed. The Personal shell
        must use PersonalOemState, not the enterprise singleton.
        """
        import maestro_personal_shell.shell as shell_module
        source = open(shell_module.__file__).read()
        assert "from maestro_api.oem_state import" not in source, (
            "Personal shell must not import enterprise oem_state singleton"
        )
        assert "maestro_api.oem_state" not in source, (
            "Personal shell must not reference enterprise oem_state"
        )


class TestPersonalShellSurfaces:
    """Day 2-3: the 4 surfaces are thin Core wrappers."""

    def test_commitments_surface_finds_commitment_to_alex(self):
        """The Commitments surface calls classify_transcript_chunk +
        should_treat_as_commitment from audit_safety."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal
        from maestro_personal_shell.surfaces.commitments import CommitmentsSurface

        state = PersonalOemState(signals=[
            PersonalSignal(
                entity="Alex",
                text="I will send the proposal by Friday",
                signal_type="commitment_made",
            ),
        ])
        shell = PersonalShell(oem_state=state)
        surface = CommitmentsSurface(shell=shell)
        commitments = surface.get_active_commitments()
        assert len(commitments) >= 1, (
            f"Expected ≥1 commitment, got {len(commitments)}"
        )

    def test_ask_surface_answers_what_did_i_promise_alex(self):
        """The Ask surface calls SituationAwareAskBridge.ask()."""
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal
        from maestro_personal_shell.surfaces.ask import AskSurface

        state = PersonalOemState(signals=[
            PersonalSignal(
                entity="Alex",
                text="I will send the proposal by Friday",
                signal_type="commitment_made",
            ),
        ])
        shell = PersonalShell(oem_state=state)
        surface = AskSurface(shell=shell)
        result = surface.ask("What did I promise Alex?")
        assert result is not None, "Ask must return a result"
        assert hasattr(result, "answer") or hasattr(result, "synthesized_answer"), (
            "Ask result must have an answer field"
        )


class TestNoDilution:
    """Day 4: the architectural guard. Personal modules must not reimplement
    Core capabilities — they must import them."""

    def test_no_personal_module_implements_brier_score(self):
        """No maestro_personal/*.py may implement Brier score inline —
        must import from calibration_primitives."""
        import ast
        import pathlib

        personal_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "maestro_personal_shell"
        forbidden_patterns = [
            "(p - actual) ** 2",  # inline Brier
            "(p-actual)**2",
            "brier_score =",
            "def brier",
        ]

        violations = []
        for py_file in personal_dir.rglob("*.py"):
            try:
                source = py_file.read_text()
                for pattern in forbidden_patterns:
                    if pattern in source:
                        # Check if it imports the Core primitive
                        if "calibration_primitives" not in source:
                            violations.append(f"{py_file.name}: found '{pattern}' without importing calibration_primitives")
            except Exception:
                continue

        assert not violations, (
            "Dilution violations found:\n" + "\n".join(violations) +
            "\n\nPersonal modules must import Core primitives, not reimplement them."
        )

    def test_no_personal_module_implements_judgment_synthesis(self):
        """No maestro_personal/*.py may implement judgment synthesis inline —
        must import from judgment_synthesizer."""
        import pathlib

        personal_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "maestro_personal_shell"
        forbidden_patterns = [
            "def synthesize_judgment",
            "def _synthesize",
            "MIN_EVIDENCE_FOR_DECISION =",
        ]

        violations = []
        for py_file in personal_dir.rglob("*.py"):
            try:
                source = py_file.read_text()
                for pattern in forbidden_patterns:
                    if pattern in source:
                        if "judgment_synthesizer" not in source and "JudgmentSynthesizer" not in source:
                            violations.append(f"{py_file.name}: found '{pattern}' without importing judgment_synthesizer")
            except Exception:
                continue

        assert not violations, (
            "Dilution violations found:\n" + "\n".join(violations)
        )

    def test_no_dilution_guard_actually_catches_violations(self):
        """P27 positive test: prove the guard catches dilution, not just
        passes vacuously. Inject a fake diluted file in a temp dir and
        verify the guard logic flags it.

        This test exists because the prior version of the no-dilution
        guard checked a non-existent path (src/maestro_personal/ instead
        of src/maestro_personal_shell/) and passed trivially. This test
        ensures the guard actually scans real files.
        """
        import pathlib
        import tempfile

        # The forbidden patterns the guard checks for
        forbidden_patterns = [
            "(p - actual) ** 2",
            "brier_score =",
            "def brier",
        ]

        # Create a temp dir with a fake diluted module
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_pkg = pathlib.Path(tmpdir) / "src" / "maestro_personal_shell"
            fake_pkg.mkdir(parents=True)
            fake_file = fake_pkg / "fake_diluted.py"
            fake_file.write_text(
                "# Fake diluted module — implements Brier inline\n"
                "# Does NOT import the Core primitive (this is the dilution pattern).\n"
                "def brier_score(p, actual):\n"
                "    return (p - actual) ** 2\n"
            )

            # Run the same logic the guard uses
            violations = []
            for py_file in fake_pkg.rglob("*.py"):
                try:
                    source = py_file.read_text()
                    for pattern in forbidden_patterns:
                        if pattern in source:
                            if "calibration_primitives" not in source:
                                violations.append(f"{py_file.name}: found '{pattern}' without importing calibration_primitives")
                except Exception:
                    continue

            # The guard MUST flag the fake diluted file
            assert len(violations) >= 1, (
                "P27 positive test: the no-dilution guard must catch a fake "
                "diluted module. If this fails, the guard is theater — it "
                "passes without actually scanning files."
            )
            assert "fake_diluted" in violations[0], (
                f"Guard must flag fake_diluted.py, got: {violations}"
            )

    def test_no_dilution_guard_scans_real_package(self):
        """P27 positive test: prove the guard scans the real package
        (maestro_personal_shell, 10 files), not an empty/non-existent dir.
        """
        import pathlib

        personal_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "maestro_personal_shell"

        # The real package must exist and have files
        assert personal_dir.exists(), (
            f"Real package dir must exist: {personal_dir}"
        )

        file_count = len(list(personal_dir.rglob("*.py")))
        assert file_count >= 8, (
            f"Guard must scan ≥8 real .py files in maestro_personal_shell/, "
            f"got {file_count}. If 0, the guard is scanning the wrong path "
            f"(the prior bug: src/maestro_personal/ which doesn't exist)."
        )

