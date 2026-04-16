import json
import math
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
        # --- ASH_COATED_OSMIUM Hyperparameters ---
        self.POSITION_LIMIT_OSMIUM = 80
        self.MAX_SKEW = 5       
        self.MARGIN = 1        
        self.FAIR_VALUE = 10000 

        # --- INTARIAN_PEPPER_ROOT Hyperparameters ---
        self.POSITION_LIMIT_PEPPER = 80 

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        
        trader_state = {}
        if state.traderData:
            try:
                trader_state = json.loads(state.traderData)
            except json.JSONDecodeError:
                trader_state = {}

        # =========================================================
        # 1. ASH_COATED_OSMIUM STRATEGY
        # =========================================================
        product_osmium = "ASH_COATED_OSMIUM"

        if product_osmium in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product_osmium]
            orders: List[Order] = []
            
            if len(order_depth.buy_orders) != 0 and len(order_depth.sell_orders) != 0:
                
                # --- Order Book Extraction ---
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                
                best_bid_vol = order_depth.buy_orders[best_bid]
                best_ask_vol = abs(order_depth.sell_orders[best_ask])
                
                current_position = state.position.get(product_osmium, 0)
                
                # --- Dynamic Continuous Inventory Skew (Quadratic Deadband) ---
                inventory_ratio = current_position / self.POSITION_LIMIT_OSMIUM 
                raw_skew = math.copysign((abs(inventory_ratio) ** 2) * self.MAX_SKEW, inventory_ratio)
                
                skew_amount = round(raw_skew)
                
                # --- Base Pricing (Titanium Guardrails) ---
                raw_base_bid = self.FAIR_VALUE - self.MARGIN - skew_amount
                raw_base_ask = self.FAIR_VALUE + self.MARGIN - skew_amount
                
                base_bid = min(self.FAIR_VALUE, raw_base_bid)
                base_ask = max(self.FAIR_VALUE, raw_base_ask)
                    
                # --- Predictive Order Book Imbalance (Micro-Momentum) ---
                total_vol = best_bid_vol + best_ask_vol
                obi = best_bid_vol / total_vol if total_vol > 0 else 0.5
                
                if obi >= 0.85:
                    base_bid += 1
                    base_ask += 1
                elif obi <= 0.15:
                    base_bid -= 1
                    base_ask -= 1

                buy_volume_left = self.POSITION_LIMIT_OSMIUM - current_position
                sell_volume_left = self.POSITION_LIMIT_OSMIUM + current_position 
                
                # --- Market Taking (Surgical Gap Exploitation) ---
                for ask_price, ask_vol_raw in sorted(order_depth.sell_orders.items()):
                    ask_vol = abs(ask_vol_raw)
                    if ask_price <= base_bid and buy_volume_left > 0:
                        vol_to_take = min(buy_volume_left, ask_vol)
                        orders.append(Order(product_osmium, ask_price, vol_to_take))
                        buy_volume_left -= vol_to_take
                
                for bid_price, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
                    if bid_price >= base_ask and sell_volume_left > 0:
                        vol_to_take = min(sell_volume_left, bid_vol)
                        orders.append(Order(product_osmium, bid_price, -vol_to_take))
                        sell_volume_left -= vol_to_take

                # --- Market Making (Passive Pennying) ---
                proposed_bid = best_bid + 1
                proposed_ask = best_ask - 1

                our_bid_price = min(base_bid, proposed_bid)
                our_ask_price = max(base_ask, proposed_ask)
                
                if our_bid_price >= our_ask_price:
                    our_bid_price = base_bid
                    our_ask_price = base_ask
                
                # --- Post Remaining Capacity passively ---
                if buy_volume_left > 0:
                    orders.append(Order(product_osmium, our_bid_price, buy_volume_left))
                    
                if sell_volume_left > 0:
                    orders.append(Order(product_osmium, our_ask_price, -sell_volume_left))
                    
                result[product_osmium] = orders

        # =========================================================
        # 2. INTARIAN_PEPPER_ROOT STRATEGY
        # =========================================================
        product_pepper = "INTARIAN_PEPPER_ROOT"

        if product_pepper in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product_pepper]
            orders: List[Order] = []
            
            if len(order_depth.sell_orders) != 0:
                
                # --- Order Book Extraction ---
                best_ask = min(order_depth.sell_orders.keys())
                current_position = state.position.get(product_pepper, 0)
                
                # --- Buy and Hold Execution ---
                max_buy_volume = self.POSITION_LIMIT_PEPPER - current_position
                
                if max_buy_volume > 0:
                    orders.append(Order(product_pepper, best_ask, max_buy_volume))
                    
                result[product_pepper] = orders
                
        # =========================================================
        # CLEANUP & LOGGING
        # =========================================================
        traderData = json.dumps(trader_state)
        logger.flush(state, result, conversions, traderData)
        
        return result, conversions, traderData