"""
Dependency tracking — every law, LO, and pattern knows which signals created it.

Disconnect GitHub → engineering laws weaken. Slack remains.
Disconnect Slack → decision confidence weakens. Nothing else.

The DependencyGraph maps:
  Provider → Signal → Receipt → LearningObject → Pattern → Law → Recommendation

When a provider is disconnected:
  1. Find all signals from that provider
  2. Find all LOs that depend on those signals
  3. Find all patterns that depend on those LOs
  4. Find all laws that depend on those patterns
  5. Weaken confidence of affected laws (remove that provider's contribution)
  6. Recompute confidence

When a provider is reconnected:
  1. Re-ingest the signals from that provider
  2. LOs, patterns, laws rebuild their evidence
  3. Confidence recalibrates

Nothing else is affected. Disconnecting GitHub does not weaken Slack-derived laws.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from maestro_oem.confidence import ConfidenceCalculator
from maestro_oem.law import LawStatus
from maestro_oem.learning_object import LearningObject
from maestro_oem.signal import ExecutionSignal, SignalProvider


class DependencyImpact(BaseModel):
    """
    The impact of disconnecting (or reconnecting) a provider.

    Lists everything that was affected — for transparency and UI display.
    """
    provider: str
    action: str  # "disconnect" or "reconnect"
    affected_signals: int = 0
    affected_learning_objects: list[str] = Field(default_factory=list)  # LO IDs
    affected_patterns: list[str] = Field(default_factory=list)  # Pattern IDs
    affected_laws: list[str] = Field(default_factory=list)  # Law codes
    confidence_before: dict[str, float] = Field(default_factory=dict)  # law_code → before
    confidence_after: dict[str, float] = Field(default_factory=dict)  # law_code → after
    laws_stressed: list[str] = Field(default_factory=list)
    laws_invalidated: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "action": self.action,
            "affected_signals": self.affected_signals,
            "affected_learning_objects": len(self.affected_learning_objects),
            "affected_patterns": len(self.affected_patterns),
            "affected_laws": len(self.affected_laws),
            "confidence_changes": {
                law: {
                    "before": round(self.confidence_before.get(law, 0), 4),
                    "after": round(self.confidence_after.get(law, 0), 4),
                    "delta": round(self.confidence_after.get(law, 0) - self.confidence_before.get(law, 0), 4),
                }
                for law in self.affected_laws
            },
            "laws_stressed": self.laws_stressed,
            "laws_invalidated": self.laws_invalidated,
            "timestamp": self.timestamp.isoformat(),
        }


class DependencyGraph:
    """
    Tracks which providers, signals, LOs, patterns, and laws depend on each other.

    Built from the ExecutionModel's state. Used to compute the blast radius
    of disconnecting or reconnecting a provider.
    """

    def __init__(self) -> None:
        # provider → set of signal_ids
        self.provider_signals: dict[str, set[str]] = defaultdict(set)
        # signal_id → set of LO_ids
        self.signal_los: dict[str, set[str]] = defaultdict(set)
        # lo_id → set of pattern_ids
        self.lo_patterns: dict[str, set[str]] = defaultdict(set)
        # pattern_id → set of law_codes
        self.pattern_laws: dict[str, set[str]] = defaultdict(set)
        # law_code → set of provider_names (which providers contributed evidence)
        self.law_providers: dict[str, set[str]] = defaultdict(set)

    def build_from_model(self, model: Any) -> None:
        """Build the dependency graph from an ExecutionModel."""
        # We need access to the model's internal structures
        # Import here to avoid circular imports
        from maestro_oem.model import ExecutionModel

        # 1. Map signals → providers
        # We don't store signals directly in the model, but we can infer
        # provider from LOs (each LO has a providers set)
        # and from receipts (each receipt has signal_provider)

        # 2. Map LOs → their signal_ids, and signals → their providers (via receipts)
        for lo_id, lo in model.learning_objects.items():
            lo_id_str = str(lo_id)
            for signal_id in lo.signal_ids:
                sid_str = str(signal_id)
                self.signal_los[sid_str].add(lo_id_str)
                # Find the provider for this signal via receipts
                for chain in model.receipt_chains.values():
                    for receipt in chain.receipts:
                        if str(receipt.signal_id) == sid_str:
                            self.provider_signals[receipt.signal_provider].add(sid_str)

        # 3. Map patterns → LOs
        for pattern in model.pattern_detector.patterns:
            pid_str = str(pattern.pattern_id)
            for lo_id in pattern.learning_object_ids:
                self.lo_patterns[str(lo_id)].add(pid_str)

        # 4. Map laws → patterns, and laws → providers
        for law_code, law in model.laws.items():
            for pattern_id in law.pattern_ids:
                self.pattern_laws[str(pattern_id)].add(law_code)
            self.law_providers[law_code] = set(law.providers)

    def get_provider_dependencies(self, provider: str) -> dict[str, set]:
        """
        Get everything that depends on a specific provider.

        Returns:
        - signals: all signal_ids from this provider
        - learning_objects: all LO_ids that depend on those signals
        - patterns: all pattern_ids that depend on those LOs
        - laws: all law_codes that depend on those patterns
        """
        signals = self.provider_signals.get(provider, set()).copy()
        los: set[str] = set()
        for sid in signals:
            los.update(self.signal_los.get(sid, set()))

        patterns: set[str] = set()
        for lo_id in los:
            patterns.update(self.lo_patterns.get(lo_id, set()))

        laws: set[str] = set()
        for pid in patterns:
            laws.update(self.pattern_laws.get(pid, set()))

        # Also include laws that directly list this provider
        for law_code, providers in self.law_providers.items():
            if provider in providers:
                laws.add(law_code)

        return {
            "signals": signals,
            "learning_objects": los,
            "patterns": patterns,
            "laws": laws,
        }

    def get_law_dependencies(self, law_code: str) -> dict[str, set]:
        """
        Get everything a law depends on.

        Returns:
        - patterns: pattern_ids that feed this law
        - learning_objects: LO_ids that feed those patterns
        - signals: signal_ids that produced those LOs
        - providers: which providers contributed
        """
        patterns: set[str] = set()
        for pid, laws in self.pattern_laws.items():
            if law_code in laws:
                patterns.add(pid)

        los: set[str] = set()
        for lo_id, pids in self.lo_patterns.items():
            if pids & patterns:
                los.add(lo_id)

        signals: set[str] = set()
        for sid, lo_ids in self.signal_los.items():
            if lo_ids & los:
                signals.add(sid)

        providers: set[str] = set()
        for prov, sids in self.provider_signals.items():
            if sids & signals:
                providers.add(prov)

        # Also check law_providers directly (for laws with explicit provider links)
        providers.update(self.law_providers.get(law_code, set()))

        return {
            "patterns": patterns,
            "learning_objects": los,
            "signals": signals,
            "providers": providers,
        }

    def get_blast_radius(self, provider: str) -> dict[str, int]:
        """
        Get the blast radius of disconnecting a provider.

        Returns counts of affected entities.
        """
        deps = self.get_provider_dependencies(provider)
        return {
            "signals": len(deps["signals"]),
            "learning_objects": len(deps["learning_objects"]),
            "patterns": len(deps["patterns"]),
            "laws": len(deps["laws"]),
        }


class DependencyManager:
    """
    Manages provider disconnection and reconnection.

    When a provider is disconnected:
    1. Identify all LOs that have evidence from that provider
    2. Remove that provider's evidence from those LOs (reduce evidence_count)
    3. Remove that provider from LO's providers set
    4. Recompute LO confidence
    5. Find laws linked to those LOs
    6. Remove that provider from law's providers set
    7. Recompute law confidence
    8. If law confidence drops below threshold → stress/invalidate

    When reconnected:
    1. Re-ingest all signals from that provider
    2. LOs, patterns, laws rebuild their evidence
    3. Confidence recalibrates

    Nothing else is affected. Disconnecting GitHub does not weaken Slack-derived laws.
    """

    def __init__(self, model: Any) -> None:
        self.model = model
        self.graph = DependencyGraph()
        self.graph.build_from_model(model)
        self.calc = ConfidenceCalculator()

    def disconnect_provider(self, provider: str) -> DependencyImpact:
        """
        Disconnect a provider and weaken all dependent laws/LOs.

        Returns a DependencyImpact describing what was affected.
        """
        impact = DependencyImpact(provider=provider, action="disconnect")
        deps = self.graph.get_provider_dependencies(provider)

        impact.affected_signals = len(deps["signals"])
        impact.affected_learning_objects = list(deps["learning_objects"])
        impact.affected_patterns = list(deps["patterns"])
        impact.affected_laws = list(deps["laws"])

        # Record confidence before
        for law_code in deps["laws"]:
            law = self.model.laws.get(law_code)
            if law:
                impact.confidence_before[law_code] = law.confidence

        # 1. Weaken LOs that have evidence from this provider
        affected_lo_ids: set[str] = set()
        for lo_id_str in deps["learning_objects"]:
            lo_id = UUID(lo_id_str)
            lo = self.model.learning_objects.get(lo_id)
            if not lo:
                continue

            # Remove this provider from the LO's providers
            if provider in lo.providers:
                lo.providers.discard(provider)
                # Reduce evidence count by the number of signals from this provider
                # that contributed to this LO
                provider_signals_in_lo = 0
                for sid in lo.signal_ids:
                    sid_str = str(sid)
                    if sid_str in deps["signals"]:
                        provider_signals_in_lo += 1

                if provider_signals_in_lo > 0:
                    lo.evidence_count = max(0, lo.evidence_count - provider_signals_in_lo)
                    lo.contradiction_count = lo.contradiction_count  # Keep contradictions

                affected_lo_ids.add(lo_id_str)

        # 2. Weaken laws that depend on those LOs
        for law_code in deps["laws"]:
            law = self.model.laws.get(law_code)
            if not law:
                continue

            # Remove this provider from the law's providers
            if provider in law.providers:
                law.providers.discard(provider)

                # Reduce evidence count
                # Count how many of the law's signal_ids came from this provider
                provider_signals_in_law = 0
                for sid in law.signal_ids:
                    if str(sid) in deps["signals"]:
                        provider_signals_in_law += 1

                if provider_signals_in_law > 0:
                    law.evidence_count = max(0, law.evidence_count - provider_signals_in_law)

                    # Add counter-examples for the removed evidence
                    # (the law lost supporting evidence — this weakens it)
                    # We DON'T add counter_examples (that would mean the law was WRONG)
                    # Instead, we reduce validated_runtimes proportionally
                    reduction = min(provider_signals_in_law, law.validated_runtimes)
                    law.validated_runtimes = max(0, law.validated_runtimes - reduction)

                # Recompute confidence
                law.confidence = self.calc.compute_law_confidence(
                    validated_runtimes=law.validated_runtimes,
                    failed_runtimes=law.failed_runtimes,
                    evidence_count=law.evidence_count,
                    providers=law.providers,
                    last_validated=law.last_validated,
                )

                # Check if law should be stressed
                if law.validated_runtimes > 0 or law.failed_runtimes > 0:
                    ratio = law.failed_runtimes / max(1, law.validated_runtimes + law.failed_runtimes)
                    if ratio > 0.3 and law.status == LawStatus.VALIDATED:
                        law.status = LawStatus.STRESSED
                        impact.laws_stressed.append(law_code)
                    if ratio > 0.5:
                        law.status = LawStatus.INVALIDATED
                        impact.laws_invalidated.append(law_code)

                impact.confidence_after[law_code] = law.confidence

        # 3. Remove the provider from connected_providers
        self.model.connected_providers.discard(provider)

        # 4. Recompute all LO confidence
        for lo_id_str in affected_lo_ids:
            lo_id = UUID(lo_id_str)
            lo = self.model.learning_objects.get(lo_id)
            if lo:
                lo.confidence = self.calc.compute_lo_confidence(
                    evidence_count=lo.evidence_count,
                    contradiction_count=lo.contradiction_count,
                    providers=lo.providers,
                    first_seen=lo.first_seen,
                    last_seen=lo.last_seen,
                )

        return impact

    def reconnect_provider(
        self,
        provider: str,
        signals: list[ExecutionSignal],
    ) -> DependencyImpact:
        """
        Reconnect a provider by re-ingesting its signals.

        LOs, patterns, and laws rebuild their evidence naturally
        through the normal signal processing pipeline.

        Returns a DependencyImpact describing what was affected.
        """
        impact = DependencyImpact(provider=provider, action="reconnect")

        # Record confidence before
        for law_code, law in self.model.laws.items():
            if provider in self.graph.law_providers.get(law_code, set()):
                impact.confidence_before[law_code] = law.confidence
                impact.affected_laws.append(law_code)

        # Re-ingest the signals
        # The model's process_signal will handle everything:
        # - Create new LOs or add evidence to existing ones
        # - Update patterns
        # - Update laws
        # - Recompute confidence
        from maestro_oem.engine import OEMEngine

        engine = OEMEngine()
        engine.model = self.model  # Use the existing model

        for signal in signals:
            if signal.provider.value == provider:
                engine.ingest_one(signal)
                impact.affected_signals += 1

        # Record confidence after
        for law_code in impact.affected_laws:
            law = self.model.laws.get(law_code)
            if law:
                impact.confidence_after[law_code] = law.confidence

        # Re-add to connected_providers
        self.model.connected_providers.add(provider)

        # Rebuild the dependency graph
        self.graph = DependencyGraph()
        self.graph.build_from_model(self.model)

        return impact

    def get_dependency_report(self) -> dict[str, Any]:
        """
        Get a full dependency report showing which providers feed which laws.

        For each law:
        - Which providers contribute evidence
        - How many signals from each provider
        - What happens if a provider is disconnected
        """
        report: dict[str, Any] = {}

        for law_code, law in self.model.laws.items():
            deps = self.graph.get_law_dependencies(law_code)
            blast = {}
            for provider in deps["providers"]:
                blast[provider] = self.graph.get_blast_radius(provider)
            report[law_code] = {
                "statement": law.statement,
                "confidence": round(law.confidence, 4),
                "status": law.status.value,
                "providers": sorted(deps["providers"]),
                "signal_count": len(deps["signals"]),
                "lo_count": len(deps["learning_objects"]),
                "pattern_count": len(deps["patterns"]),
                "blast_radius": blast,
            }

        return report
