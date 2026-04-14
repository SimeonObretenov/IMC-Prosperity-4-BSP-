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
        # --- Hyperparameters ---
        self.POSITION_LIMIT = 80
        self.MAX_SKEW = 3       # The maximum number of ticks we will shift our price when inventory is 100% full
        self.FAIR_VALUE = 10000 # Hardcoded fair value for ASH_COATED_OSMIUM
        self.MARGIN = 2         # Desired profit margin per trade around fair value

    def run(self, state: TradingState):
        """
        Takes all buy and sell orders for all symbols as an input,
        and outputs a list of orders to be sent.
        """
        result = {}
        conversions = 0
        traderData = state.traderData if state.traderData else ""

        product = "ASH_COATED_OSMIUM"

        if product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            # Ensure the order book isn't empty before calculating
            if len(order_depth.buy_orders) != 0 and len(order_depth.sell_orders) != 0:
                
                # --- 1. Order Book Extraction ---
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                
                best_bid_vol = order_depth.buy_orders[best_bid]
                best_ask_vol = abs(order_depth.sell_orders[best_ask])
                
                current_position = state.position.get(product, 0)
                
                # --- 2. Dynamic Continuous Inventory Skew ---
                inventory_ratio = current_position / self.POSITION_LIMIT 
                raw_skew = inventory_ratio * self.MAX_SKEW
                
                # Use ceil/floor to ensure we start skewing immediately, even with small positions
                if raw_skew > 0:
                    skew_amount = ceil(raw_skew)
                elif raw_skew < 0:
                    skew_amount = floor(raw_skew)
                else:
                    skew_amount = 0
                
                # --- 3. Fair Value Pricing ---
                # Instead of matching the order book, quote relative to $10,000
                our_bid_price = self.FAIR_VALUE - self.MARGIN - skew_amount
                our_ask_price = self.FAIR_VALUE + self.MARGIN - skew_amount
                
                # Safety check: Prevent quoting higher than the best ask (or lower than best bid)
                # This automatically turns our orders into Market Taker orders if the market is mispriced.
                our_bid_price = min(our_bid_price, best_ask)
                our_ask_price = max(our_ask_price, best_bid)
                    
                # --- 4. Order Book Imbalance (Adverse Selection Protection) ---
                total_vol = best_bid_vol + best_ask_vol
                obi = best_bid_vol / total_vol if total_vol > 0 else 0.5
                
                # Determine capacity
                max_buy_volume = self.POSITION_LIMIT - current_position
                max_sell_volume = -self.POSITION_LIMIT - current_position 
                
                # --- 5. Order Placement execution ---
                
                # Place Bids: Only buy if OBI > 0.20 (no massive sell wall incoming)
                if max_buy_volume > 0 and obi > 0.20:
                    orders.append(Order(product, our_bid_price, max_buy_volume))
                    
                # Place Asks: Only sell if OBI < 0.80 (no massive buy wall incoming)
                if max_sell_volume < 0 and obi < 0.80:
                    orders.append(Order(product, our_ask_price, max_sell_volume))
                    
                result[product] = orders
                
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData
