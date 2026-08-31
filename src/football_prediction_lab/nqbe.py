"""Research-only MVP components for the NQBE design document.

The module deliberately contains no bookmaker integrations, order execution, or
real-money wagering code. It provides deterministic, auditable primitives for
historical/backtest workflows:

* ``NeuralNoiseFilter``: dependency-free robust temporal denoising proxy.
* ``LiveFlowAnalyzer``: exponentially weighted price-return anomaly detector.
* ``BayesianAdaptivePoisson``: Gamma-Poisson goal-rate model with BTTS output.
* ``SmartArbitrageDetector``: binary/multi-outcome implied-probability scanner.
* ``half_kelly_fraction``: capped research sizing diagnostic.

These components are signals for evaluation, not financial advice or guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log
from statistics import median
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class FlowSignal:
    """A point-in-time market-flow signal."""

    action: str
    z_score: float
    return_value: float
    baseline_mean: float
    baseline_std: float
    confidence: float


class NeuralNoiseFilter:
    """Deterministic robust temporal denoiser used as an NNF MVP proxy.

    A production CNN requires a trained model and a frozen training artifact.
    Until that artifact exists, this implementation uses a rolling median followed
    by an EMA, which is transparent and safe for reproducible backtests.
    """

    def __init__(self, window: int = 5, smoothing: float = 0.35) -> None:
        if window < 1 or window % 2 == 0:
            raise ValueError("window must be a positive odd integer")
        if not 0.0 < smoothing <= 1.0:
            raise ValueError("smoothing must be in (0, 1]")
        self.window = window
        self.smoothing = smoothing

    def transform(self, values: Iterable[float]) -> list[float]:
        series = [self._finite(value) for value in values]
        if not series:
            return []
        robust: list[float] = []
        radius = self.window // 2
        for index in range(len(series)):
            start = max(0, index - radius)
            stop = min(len(series), index + radius + 1)
            robust.append(median(series[start:stop]))
        output = [robust[0]]
        for value in robust[1:]:
            output.append(self.smoothing * value + (1.0 - self.smoothing) * output[-1])
        return output

    @staticmethod
    def _finite(value: float) -> float:
        result = float(value)
        if not isfinite(result):
            raise ValueError("noise-filter input must be finite")
        return result


class LiveFlowAnalyzer:
    """Detect unusual decimal-odds movements using exponentially weighted returns."""

    def __init__(self, decay: float = 0.2, z_threshold: float = 2.0) -> None:
        if not 0.0 < decay <= 1.0:
            raise ValueError("decay must be in (0, 1]")
        if z_threshold <= 0:
            raise ValueError("z_threshold must be positive")
        self.decay = decay
        self.z_threshold = z_threshold

    def analyze(self, odds: Sequence[float]) -> list[FlowSignal]:
        if len(odds) < 2:
            return []
        prices = [self._validate_odds(item) for item in odds]
        returns = [log(prices[index - 1] / prices[index]) for index in range(1, len(prices))]
        mean = returns[0]
        variance = 0.0
        signals: list[FlowSignal] = []
        for value in returns:
            variance = (1.0 - self.decay) * variance + self.decay * (value - mean) ** 2
            std = max(variance**0.5, 1e-9)
            z_score = (value - mean) / std
            action = "buy" if z_score >= self.z_threshold else "sell" if z_score <= -self.z_threshold else "hold"
            confidence = min(1.0, abs(z_score) / (self.z_threshold * 2.0))
            signals.append(FlowSignal(action, z_score, value, mean, std, confidence))
            mean = (1.0 - self.decay) * mean + self.decay * value
        return signals

    @staticmethod
    def _validate_odds(value: float) -> float:
        result = float(value)
        if not isfinite(result) or result <= 1.0:
            raise ValueError("decimal odds must be finite and greater than 1.0")
        return result


@dataclass(frozen=True)
class PoissonPosterior:
    alpha: float
    beta: float

    @property
    def rate(self) -> float:
        return self.alpha / self.beta


class BayesianAdaptivePoisson:
    """Independent Gamma-Poisson posterior for home and away goal rates."""

    def __init__(self, alpha_home: float = 1.4, beta_home: float = 1.0,
                 alpha_away: float = 1.1, beta_away: float = 1.0) -> None:
        for value in (alpha_home, beta_home, alpha_away, beta_away):
            if value <= 0 or not isfinite(value):
                raise ValueError("Poisson prior parameters must be finite and positive")
        self._home = PoissonPosterior(alpha_home, beta_home)
        self._away = PoissonPosterior(alpha_away, beta_away)

    @property
    def home_rate(self) -> float:
        return self._home.rate

    @property
    def away_rate(self) -> float:
        return self._away.rate

    def update(self, goals_home: int, goals_away: int, minutes_played: float = 90.0) -> None:
        if goals_home < 0 or goals_away < 0 or minutes_played <= 0:
            raise ValueError("goals must be non-negative and minutes_played positive")
        exposure = minutes_played / 90.0
        self._home = PoissonPosterior(self._home.alpha + goals_home, self._home.beta + exposure)
        self._away = PoissonPosterior(self._away.alpha + goals_away, self._away.beta + exposure)

    def predict_btts(self) -> float:
        probability = 1.0 - exp(-self.home_rate) - exp(-self.away_rate) + exp(-(self.home_rate + self.away_rate))
        return min(1.0, max(0.0, probability))


@dataclass(frozen=True)
class ArbitrageOpportunity:
    selections: Mapping[str, float]
    implied_probability: float
    margin: float
    eligible: bool


class SmartArbitrageDetector:
    """Find mathematical arbitrage candidates from a complete odds snapshot."""

    def __init__(self, max_implied_probability: float = 1.0) -> None:
        if max_implied_probability <= 0:
            raise ValueError("max_implied_probability must be positive")
        self.max_implied_probability = max_implied_probability

    def scan(self, odds: Mapping[str, float]) -> ArbitrageOpportunity:
        if len(odds) < 2:
            raise ValueError("at least two mutually exclusive selections are required")
        clean = {str(key): float(value) for key, value in odds.items()}
        if any(not isfinite(value) or value <= 1.0 for value in clean.values()):
            raise ValueError("all decimal odds must be finite and greater than 1.0")
        implied = sum(1.0 / value for value in clean.values())
        return ArbitrageOpportunity(clean, implied, 1.0 - implied, implied < self.max_implied_probability)


def half_kelly_fraction(probability: float, decimal_odds: float, cap: float = 0.05) -> float:
    """Return a capped half-Kelly diagnostic fraction for research simulations."""
    probability = float(probability)
    decimal_odds = float(decimal_odds)
    cap = float(cap)
    if not 0.0 <= probability <= 1.0 or decimal_odds <= 1.0 or cap <= 0.0:
        raise ValueError("probability, odds, and cap are outside the valid range")
    net_odds = decimal_odds - 1.0
    full_kelly = (probability * decimal_odds - 1.0) / net_odds
    return min(cap, max(0.0, 0.5 * full_kelly))
