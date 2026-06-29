"""
OEMEngine — orchestrates the signal → model pipeline.

The engine is the entry point. You feed it signals, it updates the model.

    engine = OEMEngine()
    engine.ingest(signals)
    model = engine.get_model()
    summary = model.get_summary()

The engine is stateless between calls — all state lives in the model.
"""

from __future__ import annotations

from typing import Any

from maestro_oem.model import ExecutionModel, ModelDelta
from maestro_oem.signal import ExecutionSignal


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

    def ingest(self, signals: list[ExecutionSignal]) -> list[ModelDelta]:
        """
        Process a batch of signals and update the model.

        Returns a list of ModelDeltas, one per signal.
        """
        deltas: list[ModelDelta] = []
        for signal in signals:
            delta = self.model.process_signal(signal)
            deltas.append(delta)
            self.deltas.append(delta)
        return deltas

    def ingest_one(self, signal: ExecutionSignal) -> ModelDelta:
        """Process a single signal."""
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
