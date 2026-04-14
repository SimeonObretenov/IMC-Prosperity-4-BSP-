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
        self.MARGIN = 1         
        self.FAIR_VALUE = 10000 # Hardcoded fair value for maximum Round 1 profit

    def run(self, state: TradingState):
        """
        Takes all buy and sell orders for all symbols as an input,
        and outputs a list of orders to be sent.
        """
        result = {}
        conversions = 0
        
        # Parse traderData safely (useful for storing state for future assets)
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
                
                if raw_skew > 0:
                    skew_amount = ceil(raw_skew)
                elif raw_skew < 0:
                    skew_amount = floor(raw_skew)
                else:
                    skew_amount = 0
                
                # --- 3. Base Pricing ---
                base_bid = self.FAIR_VALUE - self.MARGIN - skew_amount
                base_ask = self.FAIR_VALUE + self.MARGIN - skew_amount
                    
                # --- 4. Predictive Order Book Imbalance (Micro-Momentum) ---
                total_vol = best_bid_vol + best_ask_vol
                obi = best_bid_vol / total_vol if total_vol > 0 else 0.5
                
                if obi >= 0.75:
                    base_bid += 1
                    base_ask += 1
                elif obi <= 0.25:
                    base_bid -= 1
                    base_ask -= 1

                # --- 5. Market Making vs. Market Taking (Gap Exploitation) ---
                
                # Undervalued: Market asks are cheaper than what we are willing to pay.
                # We send a bid at our base_bid. The engine will "walk the book" and eat all 
                # asks cheaper than base_bid, granting us instant, highly profitable fills.
                if best_ask < base_bid:
                    our_bid_price = base_bid
                    our_ask_price = base_ask
                    
                # Overvalued: Market bids are higher than what we are willing to sell for.
                # We send an ask at our base_ask. The engine will eat all bids higher than base_ask.
                elif best_bid > base_ask:
                    our_ask_price = base_ask
                    our_bid_price = base_bid
                    
                # Normal Market Making: The market is calm, no gaps to exploit.
                else:
                    # We want to "penny" the competition to guarantee we are at the front 
                    # of the queue, BUT we strictly cap it at our base_bid/base_ask so we 
                    # never overpay beyond our Fair Value limits.
                    our_bid_price = min(base_bid, best_bid + 1)
                    our_ask_price = max(base_ask, best_ask - 1)
                    
                    # Safety catch: If pennying causes our prices to cross the spread and 
                    # we don't want to accidentally send a market order during calm times.
                    if our_bid_price >= our_ask_price:
                        our_bid_price = base_bid
                        our_ask_price = base_ask
                
                # --- 6. Order Placement Execution ---
                # Determine capacity
                max_buy_volume = self.POSITION_LIMIT - current_position
                max_sell_volume = -self.POSITION_LIMIT - current_position 
                
                # We remove the rigid OBI block (obi > 0.20) here because we want to ensure 
                # we ALWAYS execute Gap Exploitations. The OBI shift in step 4 is enough protection.
                if max_buy_volume > 0:
                    orders.append(Order(product, our_bid_price, max_buy_volume))
                    
                if max_sell_volume < 0:
                    orders.append(Order(product, our_ask_price, max_sell_volume))
                    
                result[product] = orders
                
        # Serialize our state dictionary back into a string
        traderData = json.dumps(trader_state)
                
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData
