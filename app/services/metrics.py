from __future__ import annotations

from datetime import datetime, timezone

from app.models import DerivedMarketMetric, KalshiOrderbookSnapshot, Market, SharpBookOddsSnapshot


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def calculate_spread(best_yes_bid: int | None, best_yes_ask: int | None) -> int | None:
    if best_yes_bid is None or best_yes_ask is None:
        return None
    return max(0, best_yes_ask - best_yes_bid)


def calculate_orderbook_imbalance(snapshot: KalshiOrderbookSnapshot) -> float | None:
    yes_depth = snapshot.yes_bid_depth + snapshot.yes_ask_depth
    no_depth = snapshot.no_bid_depth + snapshot.no_ask_depth
    total = yes_depth + no_depth
    if total == 0:
        return None
    return (yes_depth - no_depth) / total


def consensus_fair_probability(sharp_odds: list[SharpBookOddsSnapshot]) -> float | None:
    latest_by_book_side: dict[tuple[str, str], SharpBookOddsSnapshot] = {}
    for odds in sharp_odds:
        latest_by_book_side[(odds.sportsbook, odds.side)] = odds

    probabilities = [
        odds.devigged_probability if odds.devigged_probability is not None else odds.implied_probability
        for odds in latest_by_book_side.values()
        if odds.side.lower() in {"yes", "home", "over", "selection"}
    ]
    if not probabilities:
        probabilities = [
            odds.devigged_probability if odds.devigged_probability is not None else odds.implied_probability
            for odds in latest_by_book_side.values()
        ]
    if not probabilities:
        return None
    return sum(probabilities) / len(probabilities)


def liquidity_score(total_depth: int, spread: int | None) -> float:
    depth_component = clamp(total_depth / 50)
    spread_component = 100 if spread is None else clamp(100 - (spread - 1) * 20)
    return (depth_component * 0.65) + (spread_component * 0.35)


def volatility_score(orderbooks: list[KalshiOrderbookSnapshot]) -> float:
    prices = [ob.best_yes_bid for ob in orderbooks if ob.best_yes_bid is not None]
    if len(prices) < 2:
        return 0
    mean = sum(prices) / len(prices)
    variance = sum((price - mean) ** 2 for price in prices) / (len(prices) - 1)
    return clamp((variance**0.5) * 20)


def contracts_per_minute(orderbooks: list[KalshiOrderbookSnapshot]) -> float | None:
    with_volume = [ob for ob in orderbooks if ob.volume is not None]
    if len(with_volume) < 2:
        return None
    first = with_volume[0]
    last = with_volume[-1]
    minutes = (last.timestamp - first.timestamp).total_seconds() / 60
    if minutes <= 0 or first.volume is None or last.volume is None:
        return None
    return max(0, (last.volume - first.volume) / minutes)


def sharp_move_score(sharp_odds: list[SharpBookOddsSnapshot]) -> float:
    by_book_side: dict[tuple[str, str], list[SharpBookOddsSnapshot]] = {}
    for odds in sharp_odds:
        by_book_side.setdefault((odds.sportsbook, odds.side), []).append(odds)

    max_move = 0.0
    for series in by_book_side.values():
        ordered = sorted(series, key=lambda item: item.timestamp)
        if len(ordered) < 2:
            continue
        first = ordered[0].devigged_probability or ordered[0].implied_probability
        last = ordered[-1].devigged_probability or ordered[-1].implied_probability
        max_move = max(max_move, abs(last - first))
    return clamp(max_move * 1000)


def build_metric(
    market: Market,
    latest_orderbook: KalshiOrderbookSnapshot,
    recent_orderbooks: list[KalshiOrderbookSnapshot],
    recent_sharp_odds: list[SharpBookOddsSnapshot],
    timestamp: datetime | None = None,
) -> DerivedMarketMetric:
    now = timestamp or datetime.now(timezone.utc)
    fair_probability = consensus_fair_probability(recent_sharp_odds)
    fair_price = round(fair_probability * 100) if fair_probability is not None else None
    yes_mid = None
    if latest_orderbook.best_yes_bid is not None and latest_orderbook.best_yes_ask is not None:
        yes_mid = (latest_orderbook.best_yes_bid + latest_orderbook.best_yes_ask) / 2

    edge_yes = fair_price - yes_mid if fair_price is not None and yes_mid is not None else None
    edge_no = -edge_yes if edge_yes is not None else None
    cpm = contracts_per_minute(recent_orderbooks)
    minutes_to_event = None
    if market.event_start_time:
        event_start_time = market.event_start_time
        if event_start_time.tzinfo is None:
            event_start_time = event_start_time.replace(tzinfo=timezone.utc)
        minutes_to_event = (event_start_time - now).total_seconds() / 60

    return DerivedMarketMetric(
        market_id=market.id,
        timestamp=now,
        consensus_fair_probability=fair_probability,
        consensus_fair_price=fair_price,
        edge_yes=edge_yes,
        edge_no=edge_no,
        spread=latest_orderbook.spread,
        volatility_score=volatility_score(recent_orderbooks),
        sharp_move_score=sharp_move_score(recent_sharp_odds),
        liquidity_score=liquidity_score(latest_orderbook.total_depth, latest_orderbook.spread),
        contracts_per_minute=cpm,
        time_to_event_minutes=minutes_to_event,
        orderbook_imbalance=calculate_orderbook_imbalance(latest_orderbook),
        liquidity_stability=None,
        kalshi_lag_seconds=None,
    )
