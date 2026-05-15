from __future__ import annotations

from app.models import DerivedMarketMetric, KalshiOrderbookSnapshot, OpportunityScore, SharpBookLimitsSnapshot
from app.services.metrics import clamp


def average_limit(limits: list[SharpBookLimitsSnapshot]) -> float:
    values = [limit.limit_amount for limit in limits if limit.limit_amount is not None]
    if not values:
        return 0
    return sum(values) / len(values)


def score_queue_positioning(
    metric: DerivedMarketMetric,
    orderbook: KalshiOrderbookSnapshot,
    limits: list[SharpBookLimitsSnapshot],
) -> float:
    limit_component = clamp(average_limit(limits) / 20)
    depth_component = clamp(100 - orderbook.total_depth / 20)
    spread_component = 100 if (metric.spread or 0) >= 2 else 35
    volume_component = clamp((metric.contracts_per_minute or 0) * 20)
    volatility_penalty = metric.volatility_score or 0
    return clamp(
        limit_component * 0.25
        + depth_component * 0.20
        + spread_component * 0.20
        + volume_component * 0.20
        + (100 - volatility_penalty) * 0.15
    )


def score_stale_opportunity(metric: DerivedMarketMetric, orderbook: KalshiOrderbookSnapshot) -> float:
    edge_component = clamp(abs(metric.edge_yes or 0) * 15)
    sharp_move_component = metric.sharp_move_score or 0
    depth_component = clamp(orderbook.total_depth / 30)
    lag_component = clamp((metric.kalshi_lag_seconds or 0) / 3)
    return clamp(edge_component * 0.35 + sharp_move_component * 0.30 + depth_component * 0.20 + lag_component * 0.15)


def score_market_making(metric: DerivedMarketMetric, orderbook: KalshiOrderbookSnapshot) -> float:
    spread_component = clamp(((metric.spread or 0) - 1) * 35)
    liquidity_component = metric.liquidity_score or 0
    volume_component = clamp((metric.contracts_per_minute or 0) * 25)
    stability_component = 100 - (metric.volatility_score or 0)
    return clamp(
        spread_component * 0.30
        + liquidity_component * 0.25
        + volume_component * 0.25
        + stability_component * 0.20
    )


def score_maker_stress(metric: DerivedMarketMetric, orderbook: KalshiOrderbookSnapshot) -> float:
    imbalance_component = clamp(abs(metric.orderbook_imbalance or 0) * 100)
    spread_component = clamp(((metric.spread or 0) - 1) * 30)
    sharp_move_component = metric.sharp_move_score or 0
    depth_disappearance_proxy = clamp(100 - orderbook.total_depth / 20)
    return clamp(
        imbalance_component * 0.25
        + spread_component * 0.25
        + sharp_move_component * 0.30
        + depth_disappearance_proxy * 0.20
    )


def build_opportunity_score(
    metric: DerivedMarketMetric,
    orderbook: KalshiOrderbookSnapshot,
    limits: list[SharpBookLimitsSnapshot],
) -> OpportunityScore:
    queue = score_queue_positioning(metric, orderbook, limits)
    stale = score_stale_opportunity(metric, orderbook)
    market_making = score_market_making(metric, orderbook)
    stress = score_maker_stress(metric, orderbook)
    return OpportunityScore(
        market_id=metric.market_id,
        timestamp=metric.timestamp,
        queue_positioning_score=queue,
        stale_opportunity_score=stale,
        market_making_score=market_making,
        maker_stress_score=stress,
        notes_json={
            "formula_version": "mvp_v1",
            "assumptions": [
                "Scores are interpretable heuristics, not trade recommendations.",
                "Kalshi lag is left null until sharp move event matching is implemented.",
            ],
        },
    )
