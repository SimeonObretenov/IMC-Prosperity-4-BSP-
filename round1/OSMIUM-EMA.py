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
        self.MAX_SKEW = 3       
        self.MARGIN = 2         
        
        # EMA Settings
        # alpha = 2 / (N + 1). An alpha of 0.05 roughly equals a 39-tick moving average.
        # This means it will slowly drag the fair value toward the current price without overreacting to noise.
        self.EMA_ALPHA = 0.05   
        self.DEFAULT_FAIR_VALUE = 10000 

    def run(self, state: TradingState):
        """
        Takes all buy and sell orders for all symbols as an input,
        and outputs a list of orders to be sent.
        """
        result = {}
        conversions = 0
        
        # --- 1. State Parsing (Load previous EMA) ---
        # We deserialize traderData to extract our saved state.
        trader_state = {}
        if state.traderData:
            try:
                trader_state = json.loads(state.traderData)
            except json.JSONDecodeError:
                trader_state = {}

        product = "ASH_COATED_OSMIUM"

        if product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            if len(order_depth.buy_orders) != 0 and len(order_depth.sell_orders) != 0:
                
                # --- 2. Order Book Extraction ---
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                
                best_bid_vol = order_depth.buy_orders[best_bid]
                best_ask_vol = abs(order_depth.sell_orders[best_ask])
                
                current_position = state.position.get(product, 0)
                mid_price = (best_bid + best_ask) / 2.0
                
                # --- 3. Dynamic Fair Value (EMA Calculation) ---
                # Fetch the last known EMA, or use 10,000 if it's the very first tick
                current_ema = trader_state.get("EMA_OSMIUM", self.DEFAULT_FAIR_VALUE)
                
                # Update the EMA with the new mid_price
                current_ema = (mid_price * self.EMA_ALPHA) + (current_ema * (1 - self.EMA_ALPHA))
                
                # Save it back to our state dictionary for the next timestamp
                trader_state["EMA_OSMIUM"] = current_ema
                
                # We round the EMA to the nearest integer to use as our base Fair Value
                dynamic_fair_value = int(round(current_ema))
                
                # --- 4. Dynamic Continuous Inventory Skew ---
                inventory_ratio = current_position / self.POSITION_LIMIT 
                raw_skew = inventory_ratio * self.MAX_SKEW
                
                if raw_skew > 0:
                    skew_amount = ceil(raw_skew)
                elif raw_skew < 0:
                    skew_amount = floor(raw_skew)
                else:
                    skew_amount = 0
                
                # --- 5. Base Market Making Quotes ---
                our_bid_price = dynamic_fair_value - self.MARGIN - skew_amount
                our_ask_price = dynamic_fair_value + self.MARGIN - skew_amount
                    
                # --- 6. Predictive Order Book Imbalance (Micro-Momentum) ---
                total_vol = best_bid_vol + best_ask_vol
                obi = best_bid_vol / total_vol if total_vol > 0 else 0.5
                
                # If the book is heavily skewed towards buyers, step up to buy momentum
                if obi >= 0.75:
                    our_bid_price += 1
                    our_ask_price += 1
                    
                # If the book is heavily skewed towards sellers, step down to sell momentum
                elif obi <= 0.25:
                    our_bid_price -= 1
                    our_ask_price -= 1

                # --- 7. Safety Bounding (Liquidity Taking) ---
                # Ensure we never quote worse than the best available market prices
                our_bid_price = min(our_bid_price, best_ask)
                our_ask_price = max(our_ask_price, best_bid)
                
                # Determine capacity
                max_buy_volume = self.POSITION_LIMIT - current_position
                max_sell_volume = -self.POSITION_LIMIT - current_position 
                
                # --- 8. Order Placement execution ---
                # Place Bids: Only buy if OBI > 0.20 (no massive sell wall incoming)
                if max_buy_volume > 0 and obi > 0.20:
                    orders.append(Order(product, our_bid_price, max_buy_volume))
                    
                # Place Asks: Only sell if OBI < 0.80 (no massive buy wall incoming)
                if max_sell_volume < 0 and obi < 0.80:
                    orders.append(Order(product, our_ask_price, max_sell_volume))
                    
                result[product] = orders
                
        # Serialize our state dictionary back into a string to pass to the next timestamp
        traderData = json.dumps(trader_state)
                
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData