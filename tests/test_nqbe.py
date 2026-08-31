import pytest

from football_prediction_lab.nqbe import (
    BayesianAdaptivePoisson,
    LiveFlowAnalyzer,
    NeuralNoiseFilter,
    SmartArbitrageDetector,
    half_kelly_fraction,
)


def test_noise_filter_is_robust_to_single_spike() -> None:
    filtered = NeuralNoiseFilter(window=3, smoothing=1.0).transform([1.0, 1.0, 20.0, 1.0, 1.0])
    assert filtered == [1.0] * 5


def test_noise_filter_rejects_invalid_configuration_and_values() -> None:
    with pytest.raises(ValueError):
        NeuralNoiseFilter(window=2)
    with pytest.raises(ValueError):
        NeuralNoiseFilter().transform([1.0, float("nan")])


def test_live_flow_analyzer_returns_a_signal_for_each_price_move() -> None:
    signals = LiveFlowAnalyzer(decay=0.5, z_threshold=0.8).analyze([2.0, 1.9, 1.8, 1.2])
    assert len(signals) == 3
    assert all(signal.action in {"buy", "sell", "hold"} for signal in signals)
    assert signals[-1].action == "buy"
    assert 0.0 <= signals[-1].confidence <= 1.0


def test_live_flow_analyzer_validates_decimal_odds() -> None:
    with pytest.raises(ValueError):
        LiveFlowAnalyzer().analyze([2.0, 1.0])


def test_bayesian_poisson_updates_both_rates_and_predicts_btts() -> None:
    model = BayesianAdaptivePoisson()
    before = (model.home_rate, model.away_rate)
    model.update(goals_home=2, goals_away=1)
    assert model.home_rate > before[0]
    assert model.away_rate != before[1]
    assert 0.0 < model.predict_btts() < 1.0


def test_arbitrage_detector_identifies_sub_one_implied_sum() -> None:
    opportunity = SmartArbitrageDetector().scan({"home": 2.2, "draw": 4.0, "away": 4.5})
    assert opportunity.eligible is True
    assert opportunity.margin > 0


def test_arbitrage_detector_rejects_incomplete_or_invalid_snapshot() -> None:
    with pytest.raises(ValueError):
        SmartArbitrageDetector().scan({"home": 2.0})
    with pytest.raises(ValueError):
        SmartArbitrageDetector().scan({"home": 2.0, "away": 1.0})


def test_half_kelly_is_non_negative_and_capped() -> None:
    assert half_kelly_fraction(0.6, 2.0, cap=0.05) == 0.05
    assert half_kelly_fraction(0.4, 2.0) == 0.0
    with pytest.raises(ValueError):
        half_kelly_fraction(1.1, 2.0)
