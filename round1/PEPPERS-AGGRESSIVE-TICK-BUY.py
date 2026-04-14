from itertools import product
import json
from math import ceil, floor
from typing import Any, List

try:
    from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
except ImportError:
    from prosperity3bt.datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )

        # We truncate state.traderData, trader_data, and self.logs to the same max. length to fit the log limit
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing.symbol, listing.product, listing.denomination])

        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]

        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )

        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice,
                observation.sunlightIndex,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])

        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        lo, hi = 0, min(len(value), max_length)
        out = ""

        while lo <= hi:
            mid = (lo + hi) // 2

            candidate = value[:mid]
            if len(candidate) < len(value):
                candidate += "..."

            encoded_candidate = json.dumps(candidate)

            if len(encoded_candidate) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1

        return out


logger = Logger()

class Trader:
    def __init__(self):
        self.POSITION_LIMIT = 80
        self.WINDOW_SIZE = 6 # Using the reactive window found in grid search

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        
        trader_state = {}
        if state.traderData:
            try:
                trader_state = json.loads(state.traderData)
            except json.JSONDecodeError:
                trader_state = {}

        product = "INTARIAN_PEPPER_ROOT"
        
        if product not in trader_state:
            trader_state[product] = {"history": [], "last_mid": None}

        if product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            if len(order_depth.buy_orders) > 0 and len(order_depth.sell_orders) > 0:
                # 1. Get Current Market Prices
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                current_mid = (best_bid + best_ask) / 2.0
                
                # 2. Update Moving Average History
                history: List[float] = trader_state[product]["history"]
                history.append(current_mid)
                if len(history) > self.WINDOW_SIZE:
                    history.pop(0) 
                
                # Calculate "Fair Price" (SMA)
                fair_price = sum(history) / len(history)
                
                # 3. Detect "Flattening"
                last_mid = trader_state[product]["last_mid"]
                is_flattened = (last_mid is not None and current_mid == last_mid)
                
                # 4. Save State for Next Tick
                trader_state[product]["history"] = history
                trader_state[product]["last_mid"] = current_mid
                
                # 5. Determine Target Position
                current_pos = state.position.get(product, 0)
                target_pos = current_pos # Default to no change

                if is_flattened:
                    # Logic: Revert to 0 when flat
                    target_pos = 0
                elif current_mid < fair_price:
                    # Logic: Price dropped fast -> Go All-In Long
                    target_pos = self.POSITION_LIMIT
                elif current_mid > fair_price:
                    # Logic: Price jumped fast -> Go All-In Short
                    target_pos = -self.POSITION_LIMIT

                # 6. Execute Orders (Aggressive Taker Orders)
                order_quantity = target_pos - current_pos

                if order_quantity > 0:
                    # Buying: Place bid at best_ask to guarantee immediate fill
                    orders.append(Order(product, best_ask, order_quantity))
                elif order_quantity < 0:
                    # Selling: Place ask at best_bid to guarantee immediate fill
                    orders.append(Order(product, best_bid, abs(order_quantity)))

                result[product] = orders
                
        traderData = json.dumps(trader_state)
        logger.flush(state, result, conversions, traderData)
        
        return result, conversions, traderData