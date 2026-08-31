"""Auditable research implementations for the remaining NQBE layers.

The algorithms here are deliberately explicit about their status: quantum
components are classical simulators/proxies, narrative inputs are caller-owned
structured records, and tactical simulations are scenario tools. Nothing in
this module connects to bookmakers, places wagers, or claims production-grade
accuracy without a dataset-specific validation study.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import exp

import numpy as np


@dataclass(frozen=True)
class QuantumAnomalyResult:
    score: float
    anomaly: bool
    kernel_width: float
    backend: str = "classical_quantum_kernel_proxy"


class QuantumKernelAnomalyDetector:
    """RBF kernel proxy for the QKAD interface.

    The feature map is deterministic and uses normalized vectors. The result is
    intentionally labelled as a proxy until a Qiskit/Cirq backend is supplied.
    """

    def __init__(self, kernel_width: float = 1.0, threshold: float = 0.7) -> None:
        if kernel_width <= 0 or threshold < 0:
            raise ValueError("kernel_width must be positive and threshold non-negative")
        self.kernel_width = float(kernel_width)
        self.threshold = float(threshold)
        self._reference: np.ndarray | None = None

    def fit(self, vectors: Sequence[Sequence[float]]) -> QuantumKernelAnomalyDetector:
        matrix = self._matrix(vectors)
        self._reference = matrix.mean(axis=0)
        return self

    def score(self, vector: Sequence[float]) -> QuantumAnomalyResult:
        if self._reference is None:
            raise RuntimeError("QKAD must be fitted before scoring")
        point = self._matrix([vector])[0]
        distance = float(np.linalg.norm(point - self._reference))
        kernel = exp(-(distance**2) / (2.0 * self.kernel_width**2))
        anomaly_score = 1.0 - kernel
        return QuantumAnomalyResult(
            anomaly_score, anomaly_score >= self.threshold, self.kernel_width
        )

    @staticmethod
    def _matrix(vectors: Sequence[Sequence[float]]) -> np.ndarray:
        matrix = np.asarray(vectors, dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] == 0 or not np.isfinite(matrix).all():
            raise ValueError("vectors must be a non-empty finite 2D array")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.maximum(norms, 1e-12)


class QuantumBayesianNetwork:
    """Small amplitude-style probability combiner used as a QBN proxy."""

    def combine(
        self, probabilities: Mapping[str, float], weights: Mapping[str, float] | None = None
    ) -> float:
        if not probabilities:
            raise ValueError("at least one probability is required")
        values = np.asarray(list(probabilities.values()), dtype=float)
        if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
            raise ValueError("probabilities must be in [0, 1]")
        if weights is None:
            weights_array = np.ones(len(values))
        else:
            if set(weights) != set(probabilities):
                raise ValueError("weights must match probability keys")
            weights_array = np.asarray([weights[key] for key in probabilities], dtype=float)
            if (weights_array < 0).any() or weights_array.sum() == 0:
                raise ValueError("weights must be non-negative and non-zero")
        amplitudes = np.sqrt(values)
        combined = float(np.square(np.average(amplitudes, weights=weights_array)))
        return min(1.0, max(0.0, combined))


class QuantumCombinatorialArbitrageSearch:
    """Enumerate market combinations; a deterministic QCAS search proxy."""

    def search(
        self, markets: Mapping[str, Mapping[str, float]], max_combinations: int = 10000
    ) -> list[dict[str, object]]:
        if not markets or max_combinations < 1:
            raise ValueError("markets must be non-empty and max_combinations positive")
        selections = []
        for market, odds in markets.items():
            if not odds:
                raise ValueError(f"market {market!r} has no selections")
            selections.append([(market, name, float(value)) for name, value in odds.items()])
        results: list[dict[str, object]] = []
        for combination in self._product(selections, max_combinations):
            implied = sum(1.0 / item[2] for item in combination)
            if implied < 1.0:
                results.append(
                    {"legs": combination, "implied_probability": implied, "margin": 1.0 - implied}
                )
        return results

    @staticmethod
    def _product(groups: Sequence[Sequence[tuple[str, str, float]]], limit: int):
        count = 0
        for item in groups[0]:
            yield from QuantumCombinatorialArbitrageSearch._product_tail(
                groups, 1, [item], limit, count
            )
            count += 1
            if count >= limit:
                return

    @staticmethod
    def _product_tail(groups, index, current, limit, count):
        if index == len(groups):
            yield tuple(current)
            return
        if count >= limit:
            return
        for item in groups[index]:
            yield from QuantumCombinatorialArbitrageSearch._product_tail(
                groups, index + 1, current + [item], limit, count
            )


@dataclass(frozen=True)
class ExtremeScenario:
    name: str
    probability: float
    home_goal_rate_multiplier: float
    away_goal_rate_multiplier: float


class ExtremeScenarioSimulator:
    """Finite-state scenario simulator for defensive collapse and attacking pressure."""

    def __init__(self, scenarios: Sequence[ExtremeScenario] | None = None) -> None:
        self.scenarios = tuple(
            scenarios
            or (
                ExtremeScenario("baseline", 0.70, 1.0, 1.0),
                ExtremeScenario("home_defensive_collapse", 0.15, 1.0, 1.35),
                ExtremeScenario("away_defensive_collapse", 0.15, 1.35, 1.0),
            )
        )
        total = sum(item.probability for item in self.scenarios)
        if not self.scenarios or abs(total - 1.0) > 1e-9:
            raise ValueError("scenario probabilities must sum to 1")

    def expected_btts(self, home_rate: float, away_rate: float) -> float:
        if home_rate <= 0 or away_rate <= 0:
            raise ValueError("goal rates must be positive")
        result = 0.0
        for scenario in self.scenarios:
            home = home_rate * scenario.home_goal_rate_multiplier
            away = away_rate * scenario.away_goal_rate_multiplier
            result += scenario.probability * (1.0 - exp(-home) - exp(-away) + exp(-(home + away)))
        return min(1.0, max(0.0, result))


class TemporalContextEncoder:
    """Compute a normalized momentum vector from ordered event deltas."""

    def encode(self, events: Sequence[float], decay: float = 0.8) -> np.ndarray:
        if not events or not 0.0 < decay <= 1.0:
            raise ValueError("events must be non-empty and decay must be in (0, 1]")
        values = np.asarray(events, dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("events must be finite")
        weights = decay ** np.arange(len(values) - 1, -1, -1)
        weighted = float(np.dot(values, weights) / weights.sum())
        return np.asarray([weighted, float(values[-1]), float(values.mean())], dtype=float)


class MarketTopologyMapper:
    """Build correlation topology and identify the highest-degree market hub."""

    def map(
        self, series: Mapping[str, Sequence[float]], threshold: float = 0.5
    ) -> dict[str, object]:
        if len(series) < 2 or not 0.0 <= threshold <= 1.0:
            raise ValueError("at least two series and a threshold in [0, 1] are required")
        names = list(series)
        matrix = np.asarray([series[name] for name in names], dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] < 2 or not np.isfinite(matrix).all():
            raise ValueError("series must have equal finite lengths of at least two")
        correlation = np.nan_to_num(np.corrcoef(matrix), nan=0.0)
        edges = [
            (names[i], names[j], float(abs(correlation[i, j])))
            for i in range(len(names))
            for j in range(i + 1, len(names))
            if abs(correlation[i, j]) >= threshold
        ]
        degrees = {
            name: sum(1 for left, right, _ in edges if name in {left, right}) for name in names
        }
        hub = max(degrees, key=degrees.get)
        return {"nodes": names, "edges": edges, "degrees": degrees, "hub": hub}


class TacticalParticleSimulator:
    """Deterministic Monte Carlo-like match simulator for research scenarios."""

    def simulate(
        self, home_rate: float, away_rate: float, simulations: int = 10000, seed: int = 7
    ) -> dict[str, float]:
        if home_rate <= 0 or away_rate <= 0 or simulations < 1:
            raise ValueError("rates must be positive and simulations must be positive")
        rng = np.random.default_rng(seed)
        home_goals = rng.poisson(home_rate, simulations)
        away_goals = rng.poisson(away_rate, simulations)
        return {
            "home_win_probability": float(np.mean(home_goals > away_goals)),
            "draw_probability": float(np.mean(home_goals == away_goals)),
            "away_win_probability": float(np.mean(home_goals < away_goals)),
            "btts_probability": float(np.mean((home_goals > 0) & (away_goals > 0))),
            "simulations": float(simulations),
        }


class MarketNarrativeResonanceAnalyzer:
    """Transparent keyword-based narrative baseline; no hidden social-data access."""

    POSITIVE = frozenset({"form", "return", "strong", "win", "boost", "fit"})
    NEGATIVE = frozenset({"injury", "suspend", "crisis", "loss", "doubt", "weak"})

    def analyze(self, texts: Iterable[str]) -> dict[str, object]:
        tokens = [token.lower().strip(".,!?;:()[]") for text in texts for token in text.split()]
        positive = sum(token in self.POSITIVE for token in tokens)
        negative = sum(token in self.NEGATIVE for token in tokens)
        total = positive + negative
        score = 0.0 if total == 0 else (positive - negative) / total
        dominant = "positive" if score > 0 else "negative" if score < 0 else "neutral"
        return {
            "dominant_narrative": dominant,
            "resonance": float(score),
            "positive_hits": positive,
            "negative_hits": negative,
            "evidence_count": len(tokens),
        }


class ContextualPsychologicalManipulationDetector:
    """Flag unusual co-movement between information and market-flow scores."""

    def detect(
        self,
        information_scores: Sequence[float],
        flow_scores: Sequence[float],
        threshold: float = 0.8,
    ) -> dict[str, object]:
        info = np.asarray(information_scores, dtype=float)
        flow = np.asarray(flow_scores, dtype=float)
        if (
            len(info) != len(flow)
            or len(info) < 2
            or not np.isfinite(info).all()
            or not np.isfinite(flow).all()
        ):
            raise ValueError("score sequences must have equal finite lengths of at least two")
        correlation = float(np.corrcoef(info, flow)[0, 1]) if np.std(info) and np.std(flow) else 0.0
        return {
            "correlation": correlation,
            "flagged": abs(correlation) >= threshold,
            "threshold": threshold,
            "interpretation": "screening_signal_not_causal_proof",
        }


class LivePsychoTacticalStressCalibrator:
    """Normalize optional observable stress proxies into a bounded score."""

    def calibrate(
        self, body_language: float | None = None, voice_stress: float | None = None
    ) -> float:
        values = [float(value) for value in (body_language, voice_stress) if value is not None]
        if not values:
            return 0.0
        if any(not np.isfinite(value) for value in values):
            raise ValueError("stress inputs must be finite")
        return float(np.clip(np.mean(values), 0.0, 1.0))


@dataclass(frozen=True)
class RiskEstimate:
    var: float
    mean: float
    percentile: float
    samples: int


class QuantumAmplitudeEstimationRiskEngine:
    """Deterministic classical VaR proxy with QAE-compatible output semantics."""

    def estimate(self, returns: Sequence[float], confidence: float = 0.95) -> RiskEstimate:
        values = np.asarray(returns, dtype=float)
        if len(values) < 2 or not np.isfinite(values).all() or not 0.0 < confidence < 1.0:
            raise ValueError(
                "returns must contain two finite values and confidence must be in (0, 1)"
            )
        percentile = float(np.quantile(values, 1.0 - confidence))
        return RiskEstimate(
            var=max(0.0, -percentile),
            mean=float(values.mean()),
            percentile=percentile,
            samples=len(values),
        )


def _safe_probability(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))
