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
    Core capabilities — they must import them.

    The guard logic lives in no_dilution_guard.py (shared module). Both
    the real tests and the positive test call check_for_dilution() — no
    duplication. This fixes the prior weakness where the positive test
    reimplemented the guard logic (auditor P27 finding at cfbe442).
    """

    def test_no_personal_module_implements_brier_score(self):
        """No maestro_personal_shell/*.py may implement Brier score inline —
        must import from calibration_primitives.

        Uses AST-based import checking (not string presence) so a comment
        mentioning 'calibration_primitives' does not bypass the guard.
        """
        import pathlib
        from no_dilution_guard import check_for_dilution, DilutionRule

        personal_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "maestro_personal_shell"

        # Use only the Brier rule for this test
        brier_rule = DilutionRule(
            forbidden_patterns=[
                "(p - actual) ** 2",
                "(p-actual)**2",
                "brier_score =",
                "def brier",
            ],
            required_imports=["calibration_primitives"],
            capability_name="Brier score / calibration",
        )

        violations = check_for_dilution(personal_dir, rules=[brier_rule])

        assert not violations, (
            "Dilution violations found:\n" + "\n".join(str(v) for v in violations) +
            "\n\nPersonal modules must import Core primitives, not reimplement them."
        )

    def test_no_personal_module_implements_judgment_synthesis(self):
        """No maestro_personal_shell/*.py may implement judgment synthesis
        inline — must import from judgment_synthesizer."""
        import pathlib
        from no_dilution_guard import check_for_dilution, DilutionRule

        personal_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "maestro_personal_shell"

        judgment_rule = DilutionRule(
            forbidden_patterns=[
                "def synthesize_judgment",
                "def _synthesize",
                "MIN_EVIDENCE_FOR_DECISION =",
            ],
            required_imports=["judgment_synthesizer", "JudgmentSynthesizer"],
            capability_name="Judgment synthesis",
        )

        violations = check_for_dilution(personal_dir, rules=[judgment_rule])

        assert not violations, (
            "Dilution violations found:\n" + "\n".join(str(v) for v in violations)
        )

    def test_no_dilution_guard_actually_catches_violations(self):
        """P27 positive test: prove the guard catches dilution, not just
        passes vacuously. Inject a fake diluted file in a temp dir and
        verify the GUARD (not a copy of its logic) flags it.

        This test calls check_for_dilution() directly — the same function
        the real tests use. If the guard is modified, this test exercises
        the modified guard, not a stale copy. This fixes the prior weakness
        where the positive test reimplemented the guard logic.
        """
        import pathlib
        import tempfile
        from no_dilution_guard import check_for_dilution, DilutionRule

        brier_rule = DilutionRule(
            forbidden_patterns=[
                "(p - actual) ** 2",
                "brier_score =",
                "def brier",
            ],
            required_imports=["calibration_primitives"],
            capability_name="Brier score / calibration",
        )

        # Create a temp dir with a fake diluted module (NO import statement)
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

            # Call the ACTUAL guard function — not a copy of its logic
            violations = check_for_dilution(fake_pkg, rules=[brier_rule])

            # The guard MUST flag the fake diluted file
            assert len(violations) >= 1, (
                "P27 positive test: the no-dilution guard must catch a fake "
                "diluted module. If this fails, the guard is theater — it "
                "passes without actually scanning files."
            )
            assert "fake_diluted" in violations[0].file_name, (
                f"Guard must flag fake_diluted.py, got: {violations}"
            )

    def test_no_dilution_guard_ast_catches_comment_bypass(self):
        """P32 positive test: prove the AST-based import check cannot be
        bypassed by mentioning the module name in a comment.

        Prior guard used string presence: a comment like
        '# must import calibration_primitives' bypassed the guard.
        The new AST-based check parses the source and looks for real
        import statements — comments don't count.
        """
        import pathlib
        import tempfile
        from no_dilution_guard import check_for_dilution, DilutionRule

        brier_rule = DilutionRule(
            forbidden_patterns=["def brier"],
            required_imports=["calibration_primitives"],
            capability_name="Brier score / calibration",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_pkg = pathlib.Path(tmpdir) / "fake_pkg"
            fake_pkg.mkdir()
            fake_file = fake_pkg / "comment_bypass.py"
            # The file mentions calibration_primitives in a COMMENT but
            # does not actually import it. The guard MUST flag this.
            fake_file.write_text(
                "# This module mentions calibration_primitives in a comment\n"
                "# but does NOT actually import it.\n"
                "def brier_score(p, actual):\n"
                "    return (p - actual) ** 2\n"
            )

            violations = check_for_dilution(fake_pkg, rules=[brier_rule])

            assert len(violations) >= 1, (
                "P32 test: AST-based guard must flag a file that mentions "
                "calibration_primitives in a comment but does not actually "
                "import it. If this fails, the guard is still using string "
                "presence (the prior weakness)."
            )

    def test_no_dilution_guard_passes_when_real_import_exists(self):
        """P32 positive test: prove the AST-based check correctly recognizes
        real import statements. A file with a forbidden pattern BUT a real
        import of the Core primitive should NOT be flagged.
        """
        import pathlib
        import tempfile
        from no_dilution_guard import check_for_dilution, DilutionRule

        brier_rule = DilutionRule(
            forbidden_patterns=["def brier"],
            required_imports=["calibration_primitives"],
            capability_name="Brier score / calibration",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_pkg = pathlib.Path(tmpdir) / "fake_pkg"
            fake_pkg.mkdir()
            fake_file = fake_pkg / "real_import.py"
            # This file has the forbidden pattern BUT also a real import.
            # The guard should NOT flag this — the import satisfies the rule.
            fake_file.write_text(
                "from maestro_cognitive_council.calibration_primitives import compute_brier\n"
                "\n"
                "def brier_wrapper(p, actual):\n"
                "    # Uses the imported Core primitive — not dilution\n"
                "    return compute_brier(p, actual)\n"
            )

            violations = check_for_dilution(fake_pkg, rules=[brier_rule])

            assert len(violations) == 0, (
                "P32 test: guard must NOT flag a file that has a real import "
                "of the Core primitive, even if it contains a forbidden pattern "
                "like 'def brier'. If this fails, the AST check is too strict. "
                f"Violations: {violations}"
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

