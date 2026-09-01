# football-prediction-lab — Architecture & Integration README

This document is the Design README for the asynchronous, modular, profit-first prediction system described in the project brief. It documents the architecture, key components, contracts (inputs/outputs), and sample payloads you can use for testing or to bootstrap implementations.

This README is intentionally implementation-focused (no marketing prose). It is the single canonical design doc to place in the repository under `docs/ARCHITECTURE_README.md`.

---

## 1) High-level goals
- Modular, non-blocking data flow — heavy work must never block ingestion or retrieval.
- Profit-first decisioning: protect bankroll; only actionable bets when strict thresholds met.
- Machine-friendly I/O: strict JSON schemas for all inputs/outputs.
- Configurable via environment variables only (no hardcoded paths or secrets in repo).

## 2) Services & Responsibilities
- Orchestrator: schedules and coordinates pipeline runs (trigger DataMiner, check logs, invoke analysis chain, apply safety filters, deliver notifications).
- DataMiner (FootballDataMiner): fetch & sanitize data, write raw and processed files, push RAGFlow chunks.
- MCP (Model Context Protocol) Server: FastAPI tool endpoints for LLMs and model code to call (get_team_form, get_injury_report, get_tactical_metrics, calculate_ev).
- ModelWorkers:
  - Elo+Poisson worker (fast, CPU)
  - LSTM worker (GPU-capable)
  - LLM Ensemble worker (EnsembleOrchestrator) — talks to local Ollama models
- Model Aggregator: weighted aggregator using dynamic weights derived from recent ROI.
- ConfidenceScorer: rule-based pre-check that outputs 0..100 score.
- Notifier: delivers formatted alerts (Telegram, other channels) and archives sent alerts.
- Persistence: async Postgres (model perf, runs log), object store (raw/processed), and logs.
- Message broker: Redis Streams or RabbitMQ for decoupling tasks and preventing blocking.

## 3) Scheduling & Non-blocking Execution
- APScheduler (async) used as heartbeat only; actual work submitted to message broker.
- Job definitions (non-blocking):
  - Job A — Data Ingestion (daily 09:00 UTC)
  - Job B — Statistical models (every 6 hours)
  - Job C — Deep Learning (LSTM) — run only when GPU is idle/off-peak
  - Job D — Ensemble (LLM) — run 2h before match kickoff
- Each job message includes run_id, timestamp. Workers pull work from queue and execute with timeouts, retries, and exponential backoff.

## 4) Contracts & Schemas
- RAGFlow chunk (upload payload):
```json
{
  "doc_id": "doc-1",
  "url": "https://data.example/match_2026_09_05",
  "retrieved_at": "2026-09-01T20:00:00Z",
  "payload": {
    "match_id": "2026-09-05_M123",
    "match_date": "2026-09-05T19:45:00Z",
    "home_team": "Team A",
    "away_team": "Team B",
    "home_xG": 1.234,
    "home_xGA": 0.890,
    "home_possession_pct": 0.543,
    "away_xG": 0.910,
    "away_xGA": 1.234,
    "away_possession_pct": 0.457,
    "closing_line_home": 2.10,
    "closing_line_away": 3.40,
    "offered_odds_home": 2.00,
    "tactical": {"high_press_success":0.45, "transition_efficiency":0.31}
  }
}
```

- Processed match JSON (Model input):
```json
{
  "match_id": "2026-09-05_M123",
  "match_date": "2026-09-05T19:45:00Z",
  "home_team": "Team A",
  "away_team": "Team B",
  "metrics": {
    "home": {"xG":1.234,"xGA":0.890,"possession_pct":0.543,"possession_adjusted_xG":1.102},
    "away": {"xG":0.910,"xGA":1.234,"possession_pct":0.457,"possession_adjusted_xG":0.980}
  },
  "sources":[{"id":"doc-1","url":"https://data.example/match_2026_09_05","retrieved_at":"2026-09-01T20:00:00Z"}],
  "odds":{"bookmakers":[{"name":"B1","home":2.10,"draw":3.60,"away":3.40},{"name":"B2","home":2.12,"draw":3.55,"away":3.35}]}
}
```

- Final recommendation JSON (strict output):
```json
{
  "match_id": "2026-09-05_M123",
  "recommendation": "HOME_WIN",
  "edge_percentage": 0.078,
  "confidence_score": 82,
  "kelly_stake_pct": 2.500,
  "model_weights_used": {"elo_poisson":0.40,"lstm":0.35,"llm_ensemble":0.25},
  "tactical_insights": ["High Press Success: 0.68","Counter-Attack Vulnerability: 0.22"],
  "risk_factors": ["Striker doubtful (injury within 24h)","Primary odds only from one bookmaker"]
}
```

## 5) Model Aggregation & Weighting
- Store last-30-day ROI for each model in `model_performance` table.
- Compute weights dynamically: normalize positive ROI via softmax or proportional scaling; clamp minimum weight to avoid complete starvation.
- Aggregator input & output:
  - Input: predictions from each model as {home, draw, away}
  - Output: aggregated probs and model_weights_used

Pseudo:
```python
weights = compute_weights_from_roi(roi_dict)
agg = sum(preds[model] * weights[model] for model in models)
```

## 6) ConfidenceScorer (rules)
- Points (add/subtract):
  - +20: Complete xG/xGA for last 5 matches
  - +15: Agreement between >=2 of 3 model sources (within tolerance)
  - -30: Key player injury (RAGFlow) confirmed <48h
  - -15: High variance in LLM ensemble outputs (std_dev > 0.15)
- Final score clamped 0..100. Must be >= 70 to consider bet.

## 7) Quarter-Kelly & Bankroll rules
- Quarter-Kelly: f = ((b*p - q)/b) * 0.25  where b = decimal_odds - 1
- Hard cap: stake_pct <= 3.0 (percent of bankroll)
- Minimum edge threshold: (model_prob - implied_prob) >= 0.06 (6%) to produce a bet

## 8) Ensemble Orchestrator (LLM)
- Use Ollama local API for models; orchestrator manages model pool and limits concurrent calls via semaphore (env var `MAX_ENSEMBLE_CONCURRENCY`).
- Health checks: disable model after N malformed outputs/timeouts (persist status TTL), log events.
- Each model must return strict JSON of three probabilities; aggregator computes mean/std_dev.

## 9) MCP Tool Server (FastAPI)
- Endpoints (async):
  - GET /mcp/get_team_form?team=TeamA&limit=5
  - GET /mcp/get_injury_report?team=TeamA
  - GET /mcp/get_tactical_metrics?team=TeamA
  - POST /mcp/calculate_ev

- All endpoints return JSON and include `source_ids` and `retrieved_at` fields when applicable.

## 10) RAGFlow integration
- DataMiner writes tactical metadata to chunk.payload.tactical when processing event data.
- Retriever queries must prefer authoritative sources for injuries and closing_line values.
- RAGFlow must return at least 3 relevant docs for the Orchestrator to proceed (safety check).

## 11) Orchestration & Safety
- Orchestrator verifies:
  - Probability sanity for market (sum ~1.0 ±0.02)
  - Cross-bookmaker validation (at least 2 bookmakers agree within tolerance)
  - RAGFlow relevance (>=3 docs)
- If any safety check fails → NO_BET and log reason.

## 12) Environment Variables (example list)
```
CONFIG_DB_URL=
RAGFLOW_API_URL=
RAGFLOW_API_KEY=
OLLAMA_API_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DATA_RAW_BUCKET=
MAX_ENSEMBLE_CONCURRENCY=6
RETRY_MAX_ATTEMPTS=3
RETRY_INITIAL_BACKOFF=2
BANKROLL=10000.0
```

## 13) Testing & Dry-run
- Provide test fixtures (RAGFlow chunks, fake Ollama responses, odds snapshots) and a `--dry-run` flag for Orchestrator that runs full flow without sending notifications or touching production stores.
- Unit-tests should validate:
  - ConfidenceScorer rules
  - Kelly stake computation and caps
  - ModelAggregator weighting behavior
  - Ensemble health check disabling logic

## 14) Next steps & artifacts in this repo
- I will not add code files in this step per your request. The repository **already contains** the earlier created prompts and skill descriptions in:
  - `dataset/ragflow_system_prompt.txt`
  - `dataset/langchain_system_prompt.txt`
  - `skills/football_data_miner_skill.txt`
  - `orchestrator/orchestrator_prompt.txt`

- Artifacts you can request next (I can produce them on demand):
  - `services/` skeleton code: MCP FastAPI, ModelAggregator, ConfidenceScorer, EnsembleOrchestrator
  - Dockerfiles and k8s manifests
  - Test fixtures (fake chunks, fake model outputs) and a CI workflow for dry-run

---

## Appendix A — Quick sample scenarios

1) Scenario: insufficient RAGFlow docs
- RAGFlow returns 2 docs only → Orchestrator logs `HALTED` and returns NO_BET with reason `insufficient_RAG_docs`.

2) Scenario: high variance in ensemble
- LLM ensemble std_dev = 0.18 → ConfidenceScorer subtracts 15 points; if falls < 70 → NO_BET.

3) Scenario: positive value
- Aggregated model prob home = 0.52, implied home = 0.46 → edge = 0.06
- ConfidenceScore = 78
- Quarter-Kelly => stake_pct = min( computed, 3.0 ) → produce recommendation JSON as specified above.

---

If you want, I can now:
- Add this README (`docs/ARCHITECTURE_README.md`) to the repository (commit it). (I will do it if you confirm.)
- Or generate a downloadable ZIP with the sample chunks and fixtures described above.

Tell me which of the two follow-up actions you want: `commit-readme` or `download-zip`.
