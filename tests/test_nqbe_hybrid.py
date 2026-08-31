import numpy as np
import pytest

from football_prediction_lab.nqbe_hybrid import (
    ContextualPsychologicalManipulationDetector,
    ExtremeScenarioSimulator,
    LivePsychoTacticalStressCalibrator,
    MarketNarrativeResonanceAnalyzer,
    MarketTopologyMapper,
    QuantumAmplitudeEstimationRiskEngine,
    QuantumBayesianNetwork,
    QuantumCombinatorialArbitrageSearch,
    QuantumKernelAnomalyDetector,
    TacticalParticleSimulator,
    TemporalContextEncoder,
)


def test_qkad_is_deterministic_and_flags_distant_vector() -> None:
    detector = QuantumKernelAnomalyDetector(threshold=0.2).fit([[1, 0], [0.9, 0.1]])
    result = detector.score([0, 1])
    assert result.backend == "classical_quantum_kernel_proxy"
    assert result.anomaly is True


def test_qbn_combines_probability_amplitudes() -> None:
    value = QuantumBayesianNetwork().combine({"bap": 0.6, "tps": 0.8}, {"bap": 2, "tps": 1})
    assert 0.0 < value < 1.0


def test_qcas_finds_a_valid_combination() -> None:
    found = QuantumCombinatorialArbitrageSearch().search(
        {"btts": {"yes": 2.2, "no": 2.2}, "result": {"home": 2.2, "away": 2.2}},
    )
    assert found
    assert found[0]["margin"] > 0


def test_extreme_scenario_simulator_is_bounded() -> None:
    value = ExtremeScenarioSimulator().expected_btts(1.2, 1.0)
    assert 0.0 < value < 1.0


def test_context_and_topology_outputs_are_auditable() -> None:
    vector = TemporalContextEncoder().encode([0.1, 0.5, -0.2])
    topology = MarketTopologyMapper().map({"a": [1, 2, 3], "b": [2, 4, 6], "c": [3, 2, 1]})
    assert vector.shape == (3,)
    assert topology["hub"] in {"a", "b", "c"}
    assert len(topology["edges"]) >= 1


def test_tactical_simulator_is_deterministic() -> None:
    simulator = TacticalParticleSimulator()
    first = simulator.simulate(1.3, 1.0, simulations=500, seed=11)
    second = simulator.simulate(1.3, 1.0, simulations=500, seed=11)
    assert first == second
    assert sum(
        first[key] for key in ("home_win_probability", "draw_probability", "away_win_probability")
    ) == pytest.approx(1.0)


def test_narrative_and_manipulation_detectors_are_screening_tools() -> None:
    narrative = MarketNarrativeResonanceAnalyzer().analyze(["strong form", "injury doubt"])
    manipulation = ContextualPsychologicalManipulationDetector().detect(
        [0.1, 0.9, 0.2], [0.2, 0.8, 0.3]
    )
    assert narrative["dominant_narrative"] == "neutral"
    assert manipulation["flagged"] is True
    assert manipulation["interpretation"] == "screening_signal_not_causal_proof"


def test_stress_and_risk_calibration() -> None:
    assert LivePsychoTacticalStressCalibrator().calibrate(0.4, 0.8) == pytest.approx(0.6)
    result = QuantumAmplitudeEstimationRiskEngine().estimate([-0.2, 0.1, 0.05, -0.1])
    assert result.var >= 0
    assert result.samples == 4
    assert np.isfinite(result.mean)
