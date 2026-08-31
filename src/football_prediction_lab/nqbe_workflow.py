"""End-to-end, research-only NQBE workflow orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from .nqbe import (
    BayesianAdaptivePoisson,
    LiveFlowAnalyzer,
    SmartArbitrageDetector,
)
from .nqbe_hybrid import (
    ContextualPsychologicalManipulationDetector,
    ExtremeScenarioSimulator,
    LivePsychoTacticalStressCalibrator,
    MarketNarrativeResonanceAnalyzer,
    QuantumAmplitudeEstimationRiskEngine,
    QuantumBayesianNetwork,
    QuantumKernelAnomalyDetector,
    TacticalParticleSimulator,
    TemporalContextEncoder,
)


@dataclass(frozen=True)
class NQBEInput:
    """All point-in-time features required by the research workflow."""

    match_id: str
    captured_at: datetime
    kickoff_at: datetime
    odds_history: Sequence[float]
    home_rate: float
    away_rate: float
    narrative_texts: Sequence[str] = ()
    event_deltas: Sequence[float] = ()
    market_series: Mapping[str, Sequence[float]] | None = None
    information_scores: Sequence[float] = ()
    flow_scores: Sequence[float] = ()
    stress_body: float | None = None
    stress_voice: float | None = None
    historical_returns: Sequence[float] = ()


@dataclass(frozen=True)
class NQBEResult:
    """Serializable research output with explicit non-commercial status."""

    match_id: str
    captured_at: datetime
    status: str
    btts_probability: float
    scenario_btts_probability: float
    tactical_btts_probability: float
    market_flow_action: str
    market_flow_confidence: float
    arbitrage: dict[str, object] | None
    context_vector: tuple[float, ...] | None
    narrative: dict[str, object]
    manipulation: dict[str, object] | None
    stress: float
    quantum_anomaly: dict[str, object] | None
    risk: dict[str, object] | None
    research_only: bool = True


class NQBEResearchWorkflow:
    """Compose all available NQBE layers without placing or recommending a bet."""

    def __init__(self) -> None:
        self.flow = LiveFlowAnalyzer()
        self.arbitrage = SmartArbitrageDetector()
        self.poisson = BayesianAdaptivePoisson()
        self.scenarios = ExtremeScenarioSimulator()
        self.qbn = QuantumBayesianNetwork()
        self.qkad = QuantumKernelAnomalyDetector()
        self.narrative = MarketNarrativeResonanceAnalyzer()
        self.manipulation = ContextualPsychologicalManipulationDetector()
        self.stress = LivePsychoTacticalStressCalibrator()
        self.risk = QuantumAmplitudeEstimationRiskEngine()

    def run(self, payload: NQBEInput) -> NQBEResult:
        self._validate_time(payload)
        if payload.home_rate <= 0 or payload.away_rate <= 0:
            raise ValueError("goal rates must be positive")

        flow_signals = self.flow.analyze(payload.odds_history)
        last_flow = flow_signals[-1] if flow_signals else None
        arbitrage = None
        if len(payload.odds_history) >= 2:
            latest = payload.odds_history[-1]
            arbitrage_result = self.arbitrage.scan({"yes": latest, "no": latest})
            arbitrage = {
                "eligible": arbitrage_result.eligible,
                "implied_probability": arbitrage_result.implied_probability,
                "margin": arbitrage_result.margin,
            }

        btts = self.poisson.predict_btts()
        scenario_btts = self.scenarios.expected_btts(payload.home_rate, payload.away_rate)
        tactical = TacticalParticleSimulator().simulate(
            payload.home_rate,
            payload.away_rate,
            simulations=10000,
            seed=self._seed(payload.match_id),
        )
        combined = self.qbn.combine(
            {"bap": btts, "scenario": scenario_btts, "tactical": tactical["btts_probability"]}
        )

        context = None
        if payload.event_deltas:
            context = tuple(
                float(item) for item in TemporalContextEncoder().encode(payload.event_deltas)
            )
        narrative = self.narrative.analyze(payload.narrative_texts)
        manipulation = None
        if payload.information_scores and payload.flow_scores:
            manipulation = self.manipulation.detect(payload.information_scores, payload.flow_scores)
        stress = self.stress.calibrate(payload.stress_body, payload.stress_voice)

        anomaly = None
        if payload.market_series and len(payload.market_series) >= 2:
            rows = list(payload.market_series.values())
            self.qkad.fit(rows[:-1] if len(rows) > 2 else rows)
            anomaly_result = self.qkad.score(rows[-1])
            anomaly = {
                "score": anomaly_result.score,
                "anomaly": anomaly_result.anomaly,
                "backend": anomaly_result.backend,
            }

        risk = None
        if payload.historical_returns:
            risk_result = self.risk.estimate(payload.historical_returns)
            risk = {
                "var": risk_result.var,
                "mean": risk_result.mean,
                "percentile": risk_result.percentile,
                "samples": risk_result.samples,
            }
        return NQBEResult(
            match_id=payload.match_id,
            captured_at=payload.captured_at,
            status="research_only",
            btts_probability=combined,
            scenario_btts_probability=scenario_btts,
            tactical_btts_probability=float(tactical["btts_probability"]),
            market_flow_action=last_flow.action if last_flow else "hold",
            market_flow_confidence=last_flow.confidence if last_flow else 0.0,
            arbitrage=arbitrage,
            context_vector=context,
            narrative=narrative,
            manipulation=manipulation,
            stress=stress,
            quantum_anomaly=anomaly,
            risk=risk,
        )

    @staticmethod
    def _validate_time(payload: NQBEInput) -> None:
        if not payload.match_id:
            raise ValueError("match_id is required")
        if payload.captured_at >= payload.kickoff_at:
            raise ValueError("captured_at must be strictly before kickoff_at")

    @staticmethod
    def _seed(match_id: str) -> int:
        return sum((index + 1) * ord(char) for index, char in enumerate(match_id)) % (2**32)


__all__ = ["NQBEInput", "NQBEResult", "NQBEResearchWorkflow"]
