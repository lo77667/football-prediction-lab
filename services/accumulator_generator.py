# ruff: noqa: E501

import asyncio
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import combinations
from typing import Any

# File: services/accumulator_generator.py
# Smart Accumulator Generator for football-prediction-lab
# - Strict filters
# - Safe / Value / System generators
# - Async correlation checks
# - Deterministic (no random combinations)
# - Logs generated accas to acca_history.json

ACCA_HISTORY_PATH = "acca_history.json"

# Safety thresholds (as requested)
MIN_EDGE_PER_LEG = 0.08  # 8%
MIN_CONFIDENCE = 0.75  # 75%
MAX_ACCA_SIZE = 4

# Kelly sizing modifiers
QUARTER_KELLY_CAP = 0.02  # 2% (quarter-kelly limit)
HALF_KELLY_CAP = 0.01  # 1% (half-kelly cap for value acca)

# System defaults
SYSTEM_DEFAULTS = {
    "2/4": {"legs": 4, "min_hits": 2},
    "3/5": {"legs": 5, "min_hits": 3},
    "4/6": {"legs": 6, "min_hits": 4},
}


# Data model for a leg
@dataclass
class Leg:
    match_id: str
    match: str
    pick: str
    odds: float
    edge: float  # fraction, e.g., 0.09 for 9%
    confidence: float  # fraction 0..1
    market: str
    reasoning: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# Utility functions
def _load_acca_history() -> list[dict[str, Any]]:
    if not os.path.exists(ACCA_HISTORY_PATH):
        return []
    try:
        with open(ACCA_HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _append_acca_history(entry: dict[str, Any]) -> None:
    arr = _load_acca_history()
    arr.insert(0, entry)
    # keep reasonable history size
    arr = arr[:1000]
    with open(ACCA_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False, indent=2)


# Correlation check (async) - conservative heuristics
async def check_correlation(a: Leg, b: Leg, top_teams: list[str] | None = None) -> bool:
    """
    Return True if matches are sufficiently uncorrelated (i.e., safe to combine).
    Conservative rules implemented:
    - If legs are on the same exact match_id -> correlated (False)
    - If same match (same match_id) but different markets -> usually correlated; disallow combining unless markets are orthogonal (we disallow Team Win + Over2.5 in same match)  # noqa: E501
    - If top_teams provided and both matches involve any team in top_teams and are in same league -> treat as correlated and disallow  # noqa: E501

    Note: This function is intentionally conservative and async-friendly (uses asyncio.sleep 0 to yield control).  # noqa: E501
    """
    await asyncio.sleep(0)  # yield control for asyncio

    # same match => correlated
    if a.match_id == b.match_id:
        return False

    # Simple text heuristic: if pick strings mention the same team name -> correlated
    a_teams = (
        set([t.strip().lower() for t in a.match.split("vs")]) if "vs" in a.match.lower() else set()
    )
    b_teams = (
        set([t.strip().lower() for t in b.match.split("vs")]) if "vs" in b.match.lower() else set()
    )
    if a_teams & b_teams:
        # share a team across legs -> correlated
        return False

    # Disallow combining contradictory markets within same match scenario handled above.
    # If both matches are from same league and involve top teams -> correlated
    # We don't have league metadata reliably here; caller may provide top_teams list to make this stricter.  # noqa: E501
    if top_teams:
        top_lower = {t.lower() for t in top_teams}
        a_in_top = any(team in top_lower for team in a_teams)
        b_in_top = any(team in top_lower for team in b_teams)
        if a_in_top and b_in_top:
            return False

    # default: treated as uncorrelated
    return True


# Deterministic selection helpers
def _eligible_legs_from_candidates(candidates: list[dict[str, Any]]) -> list[Leg]:
    """
    Convert raw candidate dicts (from scanner) into Leg objects and apply per-leg strict filters.
    Each candidate dict must contain: match_id, match, selection/pick, odds, edge_pct (percentage or fraction), our_prob/confidence  # noqa: E501
    Returns list of Legs that satisfy MIN_EDGE_PER_LEG and MIN_CONFIDENCE.
    """
    legs: list[Leg] = []
    for c in candidates:
        try:
            edge = float(c.get("edge_pct", 0.0))
            # edge may be percentage (e.g., 9.1) or fraction (0.091) -> normalize
            if edge > 1.5:
                edge_frac = edge / 100.0
            else:
                edge_frac = edge
            if edge_frac < MIN_EDGE_PER_LEG:
                continue
            conf = float(c.get("confidence") or c.get("our_prob") or c.get("confidence_pct") or 0.0)
            # confidence might be percent or fraction
            if conf > 1.5:
                conf_frac = conf / 100.0
            else:
                conf_frac = conf
            if conf_frac < MIN_CONFIDENCE:
                continue
            match_id = str(c.get("match_id") or c.get("id") or "")
            match = str(c.get("match") or c.get("teams") or "")
            pick = str(c.get("selection") or c.get("pick") or "")
            odds = float(c.get("odds") or c.get("price") or 0.0)
            market = str(c.get("market") or "")
            reasoning = str(c.get("reasoning") or "")
            leg = Leg(
                match_id=match_id,
                match=match,
                pick=pick,
                odds=odds,
                edge=edge_frac,
                confidence=conf_frac,
                market=market,
                reasoning=reasoning,
            )
            legs.append(leg)
        except Exception:
            continue
    # sort deterministic: highest edge first, then highest confidence
    legs.sort(key=lambda L: (L.edge, L.confidence), reverse=True)
    return legs


# Accumulator combinatorics and scoring
def _combine_odds(legs: list[Leg]) -> float:
    prod = 1.0
    for leg in legs:
        prod *= leg.odds
    return prod


def _combined_edge(legs: list[Leg]) -> float:
    """
    Combined true probability approx: assume independence -> product of true probs? Not correct for 1X2.  # noqa: E501
    Simpler: convert each leg's implied true prob = implied from edge+implied? Here we only have edge and implied prob unknown.  # noqa: E501
    We approximate combined edge pct by summing individual edges on log-odds scale conservatively.
    For simplicity and conservatism, compute combined_edge_pct = sum(edges) * 100 (edges are fractional)  # noqa: E501
    """
    return sum(leg.edge for leg in legs) * 100.0


# Kelly stake calculators
def _quarter_kelly_stake(bankroll: float, suggested_kelly_frac: float) -> float:
    # quarter-kelly capped at QUARTER_KELLY_CAP
    return round(min(suggested_kelly_frac / 4.0, QUARTER_KELLY_CAP) * 100.0, 3)


def _half_kelly_stake(bankroll: float, suggested_kelly_frac: float) -> float:
    return round(min(suggested_kelly_frac / 2.0, HALF_KELLY_CAP) * 100.0, 3)


def _estimate_kelly_fraction_from_edges(legs: list[Leg]) -> float:
    """
    Rough estimate for combined Kelly fraction: use average edge weighted by odds.
    This is heuristic: full Kelly for multi-leg requires full true prob and b.
    We'll compute avg_edge = mean(edge_i) and conservative kelly = avg_edge / 2
    """
    if not legs:
        return 0.0
    avg_edge = sum(leg.edge for leg in legs) / len(legs)
    # cap at 0.5
    return max(0.0, min(0.5, avg_edge / 2.0))


# Generator modes
async def generate_safe_accumulator(
    candidates: list[dict[str, Any]], bankroll: float
) -> dict[str, Any] | None:
    """
    Safe Accumulator: 2-3 legs, markets: Double Chance or Over 1.5 only, combined odds 2.0-3.0, quarter-kelly up to 2%.  # noqa: E501
    Deterministic: pick top legs matching market constraints and passing correlation checks.
    """
    legs = _eligible_legs_from_candidates(candidates)
    if not legs:
        return None

    # filter allowed markets
    allowed_markets = {
        "double_chance",
        "1X2_double_chance",
        "over_1.5",
        "over 1.5",
        "over_1.5_goals",
    }
    filtered = [
        leg
        for leg in legs
        if leg.market.lower() in allowed_markets
        or "double" in leg.market.lower()
        or "1.5" in leg.market.lower()
    ]
    if not filtered:
        return None

    # try combinations of size 2, then 3
    for size in (2, 3):
        if size > MAX_ACCA_SIZE:
            continue
        for combo in combinations(filtered, size):
            # correlation checks pairwise
            ok = True
            for a, b in combinations(combo, 2):
                if not await check_correlation(a, b):
                    ok = False
                    break
                # don't combine Team Win with Over 2.5 on same match - handled by check_correlation if same match  # noqa: E501
            if not ok:
                continue
            total_odds = _combine_odds(combo)
            if not (2.0 <= total_odds <= 3.0):
                continue
            combined_edge = _combined_edge(list(combo))
            kelly_frac = _estimate_kelly_fraction_from_edges(list(combo))
            stake_pct = _quarter_kelly_stake(bankroll, kelly_frac)
            acca = {
                "type": f"SAFE_ACCA_{size}_FOLD",
                "total_odds": round(total_odds, 3),
                "combined_edge_pct": round(combined_edge, 3),
                "legs": [leg.to_json() for leg in combo],
                "stake_recommendation": f"{stake_pct}% of Bankroll",
                "risk_warning": "Low-medium variance; quarter-Kelly applied. Do not exceed recommended stake.",  # noqa: E501
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }
            _append_acca_history({"mode": "safe", "acca": acca})
            return acca
    return None


async def generate_value_accumulator(
    candidates: list[dict[str, Any]], bankroll: float
) -> dict[str, Any] | None:
    """
    Value Accumulator: 3-4 legs, markets: 1X2, Asian Handicap, Over 2.5. Target combined edge > 15%.
    Deterministic: choose top legs by edge, ensure pairwise uncorrelated.
    """
    legs = _eligible_legs_from_candidates(candidates)
    if not legs:
        return None
    allowed_markets = {
        "1x2",
        "1x2_home",
        "1x2_away",
        "asian_handicap",
        "asian",
        "over_2.5",
        "over 2.5",
        "over_2.5_goals",
    }
    filtered = [
        leg
        for leg in legs
        if any(k in leg.market.lower() for k in ["1x2", "asian", "over 2.5", "2.5"])
        or leg.market.lower() in allowed_markets
    ]
    if not filtered:
        return None
    # try sizes 4 then 3 (prefer larger if edges permit) while respecting MAX_ACCA_SIZE
    for size in (4, 3):
        if size > MAX_ACCA_SIZE:
            continue
        # deterministic combos: choose top `size` by edge then test correlation; if fail, try next viable combo by sliding window  # noqa: E501
        top_candidates = filtered
        # iterate combinations in order of highest total edge sum
        combos = list(combinations(top_candidates, size))
        # sort combos by sum(edge) desc
        combos.sort(key=lambda c: sum(x.edge for x in c), reverse=True)
        for combo in combos:
            ok = True
            for a, b in combinations(combo, 2):
                if not await check_correlation(a, b):
                    ok = False
                    break
            if not ok:
                continue
            total_odds = _combine_odds(combo)
            combined_edge = _combined_edge(list(combo))
            if combined_edge <= 15.0:
                continue
            kelly_frac = _estimate_kelly_fraction_from_edges(list(combo))
            stake_pct = _half_kelly_stake(bankroll, kelly_frac)
            acca = {
                "type": f"VALUE_ACCA_{size}_FOLD",
                "total_odds": round(total_odds, 3),
                "combined_edge_pct": round(combined_edge, 3),
                "legs": [leg.to_json() for leg in combo],
                "stake_recommendation": f"{stake_pct}% of Bankroll",
                "risk_warning": "High variance. Half-Kelly (capped) applied. Do not exceed 1% stake.",  # noqa: E501
                "generated_at": datetime.utcnow().isoformat() + "Z",
            }
            _append_acca_history({"mode": "value", "acca": acca})
            return acca
    return None


def _compute_system_outcomes(legs: list[Leg], system_k: int) -> dict[str, Any]:
    """
    Compute stake/return table for system bets. For simplicity, assume we place 1 unit on each combination required by the system.  # noqa: E501
    Example: For 2/4, combinations are all 2-combinations of the 4 legs; stake = number_of_combinations * unit_bet  # noqa: E501
    We'll compute potential returns for different numbers of winning legs.
    """
    n = len(legs)
    combos = list(combinations(legs, system_k))
    num_combos = len(combos)
    # unit stake per combo = 1 (we'll scale to bankroll later)
    unit = 1.0
    total_stake_units = num_combos * unit
    # For each possible number of winners w from 0..n compute best-case payout given which combos win  # noqa: E501
    # We evaluate all subsets of winning legs (2^n) up to combinatorial limits; for n<=6 this is manageable  # noqa: E501
    from itertools import chain
    from itertools import combinations as icomb

    def all_subsets(iterable):
        s = list(iterable)
        return chain.from_iterable(icomb(s, r) for r in range(len(s) + 1))

    # map leg to index
    {i: legs[i] for i in range(n)}
    # For each subset of winning legs, compute payout
    payouts_by_wins = {w: [] for w in range(n + 1)}
    for r in all_subsets(range(n)):
        wins = set(r)
        # which combos are fully covered by wins? a combo pays out if all its legs are in wins
        payout = 0.0
        for combo in combos:
            # indices of combo legs
            combo_indices = [legs.index(c) for c in combo]
            if set(combo_indices).issubset(wins) and len(combo_indices) == system_k:
                # payout for this combo = product(odds) * unit
                payout += math.prod([c.odds for c in combo]) * unit
        payouts_by_wins[len(wins)].append(payout)
    # compute summary: for each w, min/max payout
    summary = {}
    for w, lst in payouts_by_wins.items():
        if not lst:
            summary[w] = {"min": 0.0, "max": 0.0, "avg": 0.0}
        else:
            summary[w] = {"min": min(lst), "max": max(lst), "avg": sum(lst) / len(lst)}
    return {
        "num_combos": num_combos,
        "unit_per_combo": unit,
        "total_stake_units": total_stake_units,
        "payouts": summary,
    }


async def generate_system_bets(
    candidates: list[dict[str, Any]], bankroll: float, system_key: str = "2/4"
) -> dict[str, Any] | None:
    """
    Generate system bets for specified system (e.g., 2/4, 3/5, 4/6). Must use legs with edge>=8% and confidence>=75%.  # noqa: E501
    Logic: pick top N legs (N = system legs), compute all required combinations, compute stake vs potential returns.  # noqa: E501
    Ensure breakeven if 1 leg loses: i.e., worst-case return when N-1 legs win should be >= total stake.  # noqa: E501
    If not achievable with unit stake 1, return the system with a warning.
    """
    if system_key not in SYSTEM_DEFAULTS:
        return None
    legs_needed = SYSTEM_DEFAULTS[system_key]["legs"]
    legs = _eligible_legs_from_candidates(candidates)
    if len(legs) < legs_needed:
        return None
    # take top `legs_needed` legs deterministically
    selected = legs[:legs_needed]
    # correlation safety: all pairwise must be uncorrelated
    for a, b in combinations(selected, 2):
        if not await check_correlation(a, b):
            # try to find next candidate to replace b
            replaced = False
            for alt in legs[legs_needed:]:
                if alt not in selected:
                    # attempt replacement
                    tmp = [x for x in selected if x != b] + [alt]
                    ok = True
                    for x, y in combinations(tmp, 2):
                        if not await check_correlation(x, y):
                            ok = False
                            break
                    if ok:
                        selected = tmp
                        replaced = True
                        break
            if not replaced:
                return None
    # compute system outcomes
    k = SYSTEM_DEFAULTS[system_key]["min_hits"]
    outcomes = _compute_system_outcomes(selected, k)
    total_stake_units = outcomes["total_stake_units"]
    # choose unit stake so that total stake relative to bankroll not excessive; aim for <= 1% of bankroll  # noqa: E501
    max_unit = (bankroll * 0.01) / total_stake_units if total_stake_units > 0 else 0.0
    unit_stake = round(max_unit, 4)
    scaled_total_stake = unit_stake * total_stake_units

    # compute payouts scaled
    scaled_payouts = {}
    for w, stats in outcomes["payouts"].items():
        scaled_payouts[w] = {k: round(v * unit_stake, 3) for k, v in stats.items()}
    # compute worst-case when N-1 wins
    worst_case_wins = legs_needed - 1
    worst_min = scaled_payouts.get(worst_case_wins, {}).get("min", 0.0)
    breakeven = worst_min >= scaled_total_stake

    system = {
        "type": f"SYSTEM_{system_key}",
        "legs": [leg.to_json() for leg in selected],
        "unit_stake_per_combo": unit_stake,
        "total_stake": round(scaled_total_stake, 3),
        "payouts": scaled_payouts,
        "breakeven_if_{0}_wins": breakeven,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    _append_acca_history({"mode": "system", "system_key": system_key, "system": system})
    return system


# Integration helpers for Telegram bot
async def generate_optimal_acca_for_day(
    candidates: list[dict[str, Any]], bankroll: float
) -> dict[str, Any]:
    """
    Try safe then value accumulators deterministically; return best available (value preferred if bigger combined edge)  # noqa: E501
    """
    safe = await generate_safe_accumulator(candidates, bankroll)
    value = await generate_value_accumulator(candidates, bankroll)

    # choose which to return by combined_edge_pct primarily
    def score(x):
        if not x:
            return -1
        return x.get("combined_edge_pct", 0.0)

    chosen = value if score(value) > score(safe) else safe
    if not chosen:
        return {"message": "No safe accumulators today. Stick to singles."}
    return chosen


# Example small test harness (not run on import)
if __name__ == "__main__":
    # demo candidates (would normally come from profit_engine.scan_and_score)
    demo = [
        {
            "match_id": "M1",
            "match": "Arsenal vs Chelsea",
            "selection": "Over 2.5",
            "odds": 1.85,
            "edge_pct": 9.1,
            "confidence": 0.8,
            "market": "over_2.5",
            "reasoning": "xG and news",
        },
        {
            "match_id": "M2",
            "match": "Bayern vs Dortmund",
            "selection": "BTTS Yes",
            "odds": 1.70,
            "edge_pct": 8.5,
            "confidence": 0.82,
            "market": "btts",
            "reasoning": "both strong",
        },
        {
            "match_id": "M3",
            "match": "Inter vs Milan",
            "selection": "Inter Win",
            "odds": 2.10,
            "edge_pct": 10.2,
            "confidence": 0.79,
            "market": "1x2",
            "reasoning": "home advantage",
        },
        {
            "match_id": "M4",
            "match": "PSG vs Lyon",
            "selection": "Over 1.5",
            "odds": 1.45,
            "edge_pct": 8.2,
            "confidence": 0.85,
            "market": "over_1.5",
            "reasoning": "attack",
        },
        {
            "match_id": "M5",
            "match": "Ajax vs PSV",
            "selection": "Ajax Win",
            "odds": 2.05,
            "edge_pct": 9.0,
            "confidence": 0.78,
            "market": "1x2",
            "reasoning": "form",
        },
    ]

    async def run_demo():
        acca = await generate_optimal_acca_for_day(demo, bankroll=1000)
        print(json.dumps(acca, indent=2))
        system = await generate_system_bets(demo, bankroll=1000, system_key="2/4")
        print(json.dumps(system, indent=2))

    asyncio.run(run_demo())
