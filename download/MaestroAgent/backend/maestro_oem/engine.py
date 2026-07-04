"""OEMEngine — orchestrates the signal → model pipeline.

The engine is the entry point. You feed it signals, it updates the model.

    engine = OEMEngine()
    engine.ingest(signals)
    model = engine.get_model()
    summary = model.get_summary()

The engine is stateless between calls — all state lives in the model.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_oem.model import ExecutionModel, ModelDelta
from maestro_oem.signal import ExecutionSignal

logger = logging.getLogger(__name__)


class OEMEngine:
    """
    Orchestrates the OEM update pipeline.

    Usage:
        engine = OEMEngine()
        deltas = engine.ingest(signals)
        model = engine.get_model()
    """

    def __init__(self) -> None:
        self.model = ExecutionModel()
        self.deltas: list[ModelDelta] = []
        self._injection_filter = None

    def _get_injection_filter(self):
        """Lazily load the PromptInjectionFilter (P1 fix)."""
        if self._injection_filter is None:
            try:
                from maestro_oem.prompt_injection_defense import PromptInjectionFilter
                self._injection_filter = PromptInjectionFilter()
            except Exception as e:
                logger.warning("OEMEngine: PromptInjectionFilter unavailable: %s", e)
        return self._injection_filter

    def _check_injection(self, signal: ExecutionSignal) -> None:
        """P1 fix: Check a signal for prompt injection before ingesting.

        If injection is detected, the signal is MARKED (not dropped — P6
        fail-safe). The prompt_injection_risk field is added to the
        signal's metadata so downstream consumers can see the flag.
        """
        filt = self._get_injection_filter()
        if filt is None:
            return

        # Build a dict representation of the signal for the filter
        signal_dict = {
            "type": str(signal.type),
            "actor": signal.actor or "",
            "artifact": signal.artifact or "",
            "metadata": dict(signal.metadata) if signal.metadata else {},
            "timestamp": signal.timestamp.isoformat() if hasattr(signal.timestamp, "isoformat") else "",
        }

        result = filt.check_signal(signal_dict)
        if result.is_suspicious:
            # Mark the signal (P6: flag, don't drop)
            # Pydantic models may not allow direct metadata mutation,
            # so we use model_copy or direct setattr
            try:
                signal.metadata["prompt_injection_risk"] = result.to_dict()
            except Exception:
                # If metadata is frozen, try setattr
                try:
                    setattr(signal, "prompt_injection_risk", result.to_dict())
                except Exception:
                    pass
            logger.warning(
                "OEMEngine: prompt injection detected in signal %s — patterns: %s. "
                "Signal flagged (not dropped).",
                signal.signal_id,
                result.detected_patterns,
            )

    def ingest(self, signals: list[ExecutionSignal]) -> list[ModelDelta]:
        """
        Process a batch of signals and update the model.

        P1 fix: each signal is checked for prompt injection before
        processing. Flagged signals are marked, not dropped (P6).

        H-05 fix: each signal's authority_weight is set from the
        SourceAuthorityModel before processing. Authority is DERIVED
        from org chart data (P13), not caller-supplied. Authority
        modulates confidence, never silences the signal (P6).

        H-06 fix: free-text commitments are extracted from MESSAGE_SENT
        and EMAIL signals BEFORE processing. Extracted commitments are
        ADDITIONAL signals — the originals are never dropped (P6).
        Extracted commitments inherit authority_weight from their source
        (H-05 integration).

        Returns a list of ModelDeltas, one per signal (originals + extracted).
        """
        # H-05: Apply authority weights from the default SourceAuthorityModel.
        # This is a no-op if no org chart has been loaded (all weights stay 0.5).
        try:
            from maestro_oem.source_authority import get_default_model
            get_default_model().apply_to_signals(signals)
        except Exception as e:
            logger.warning("OEMEngine.ingest: failed to apply authority weights: %s", e)

        # H-06: Extract commitments from free text BEFORE processing.
        # Extracted signals are ADDITIONAL — originals are never dropped (P6).
        try:
            from maestro_oem.commitment_extractor import CommitmentExtractor
            extractor = CommitmentExtractor()
            extracted = extractor.extract(signals)
            if extracted:
                logger.info("CommitmentExtractor: extracted %d commitment(s) from %d signal(s)",
                            len(extracted), len(signals))
                signals = signals + extracted  # originals + extracted
        except Exception as e:
            logger.warning("OEMEngine.ingest: CommitmentExtractor failed: %s", e)

        deltas: list[ModelDelta] = []
        for signal in signals:
            self._check_injection(signal)
            delta = self.model.process_signal(signal)
            deltas.append(delta)
            self.deltas.append(delta)
        return deltas

    def ingest_one(self, signal: ExecutionSignal) -> ModelDelta:
        """Process a single signal.

        P1 fix: checks for prompt injection before processing.
        H-05 fix: applies authority weight before processing.
        """
        # H-05: Apply authority weight
        try:
            from maestro_oem.source_authority import get_default_model
            get_default_model().apply_to_signal(signal)
        except Exception as e:
            logger.warning("OEMEngine.ingest_one: failed to apply authority weight: %s", e)

        self._check_injection(signal)
        delta = self.model.process_signal(signal)
        self.deltas.append(delta)
        return delta

    def get_model(self) -> ExecutionModel:
        return self.model

    def get_summary(self) -> dict[str, Any]:
        return self.model.get_summary()

    def get_deltas(self) -> list[ModelDelta]:
        return self.deltas

    def reset(self) -> None:
        """Reset the engine and model to initial state."""
        self.model = ExecutionModel()
        self.deltas = []
