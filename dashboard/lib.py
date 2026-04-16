"""
Library functions for Prosperity 4 Dashboard
Handles loading and processing CSV data files.
"""
import pandas as pd
import numpy as np
import os
from pathlib import Path


def get_data_dir():
    """Get the data directory path."""
    return Path(__file__).parent.parent / "data"


def list_rounds():
    """List available rounds in the data directory."""
    data_dir = get_data_dir()
    if not data_dir.exists():
        return []
    return sorted([d.name for d in data_dir.iterdir() if d.is_dir()])


def list_days(round_name):
    """List available days for a given round."""
    round_dir = get_data_dir() / round_name
    if not round_dir.exists():
        return []

    days = set()
    for f in round_dir.glob("prices_*.csv"):
        # Extract day from filename like prices_round_1_day_0.csv
        parts = f.stem.split("_")
        if "day" in parts:
            day_idx = parts.index("day")
            if day_idx + 1 < len(parts):
                days.add(int(parts[day_idx + 1]))
    return sorted(days)


def list_products(round_name, day):
    """List available products for a given round and day."""
    prices_df = load_prices(round_name, day)
    if prices_df is None or prices_df.empty:
        return []
    return sorted(prices_df["product"].unique().tolist())


def load_prices(round_name, day):
    """Load prices CSV for a given round and day."""
    # Try different filename patterns
    patterns = [
        f"prices_round_{round_name.replace('round', '')}_day_{day}.csv",
        f"prices_{round_name}_day_{day}.csv",
    ]

    data_dir = get_data_dir() / round_name

    for pattern in patterns:
        filepath = data_dir / pattern
        if filepath.exists():
            df = pd.read_csv(filepath, sep=";")
            return df

    # Try to find any prices file matching the day
    for f in data_dir.glob(f"prices*day*{day}*.csv"):
        df = pd.read_csv(f, sep=";")
        return df

    return None


def load_trades(round_name, day):
    """Load trades CSV for a given round and day."""
    patterns = [
        f"trades_round_{round_name.replace('round', '')}_day_{day}.csv",
        f"trades_{round_name}_day_{day}.csv",
    ]

    data_dir = get_data_dir() / round_name

    for pattern in patterns:
        filepath = data_dir / pattern
        if filepath.exists():
            df = pd.read_csv(filepath, sep=";")
            return df

    # Try to find any trades file matching the day
    for f in data_dir.glob(f"trades*day*{day}*.csv"):
        df = pd.read_csv(f, sep=";")
        return df

    return None


def get_product_data(round_name, day, product):
    """Get combined price and trade data for a specific product."""
    prices_df = load_prices(round_name, day)
    trades_df = load_trades(round_name, day)

    if prices_df is None:
        return None, None

    # Filter by product
    product_prices = prices_df[prices_df["product"] == product].copy()
    product_prices = product_prices.sort_values("timestamp").reset_index(drop=True)

    product_trades = None
    if trades_df is not None:
        # Handle different column names for symbol/product
        symbol_col = "symbol" if "symbol" in trades_df.columns else "product"
        product_trades = trades_df[trades_df[symbol_col] == product].copy()
        product_trades = product_trades.sort_values("timestamp").reset_index(drop=True)

    return product_prices, product_trades


def calculate_fair(prices_df):
    """Calculate fair price based on mid-price or weighted mid."""
    if "mid_price" in prices_df.columns:
        return prices_df["mid_price"]

    # Calculate from bid/ask if mid_price not available
    bid = prices_df["bid_price_1"].fillna(0)
    ask = prices_df["ask_price_1"].fillna(0)

    # Handle cases where only one side exists
    fair = np.where(
        (bid > 0) & (ask > 0),
        (bid + ask) / 2,
        np.where(bid > 0, bid, ask)
    )
    return fair


def get_orderbook_at_timestamp(prices_df, timestamp):
    """Extract orderbook state at a specific timestamp."""
    row = prices_df[prices_df["timestamp"] == timestamp]
    if row.empty:
        # Find closest timestamp
        idx = (prices_df["timestamp"] - timestamp).abs().idxmin()
        row = prices_df.loc[[idx]]

    row = row.iloc[0]

    orderbook = {
        "bids": [],
        "asks": []
    }

    # Extract bid levels
    for i in range(1, 4):
        price_col = f"bid_price_{i}"
        vol_col = f"bid_volume_{i}"
        if price_col in row.index and pd.notna(row[price_col]):
            orderbook["bids"].append({
                "price": row[price_col],
                "volume": row.get(vol_col, 0) if pd.notna(row.get(vol_col)) else 0
            })

    # Extract ask levels
    for i in range(1, 4):
        price_col = f"ask_price_{i}"
        vol_col = f"ask_volume_{i}"
        if price_col in row.index and pd.notna(row[price_col]):
            orderbook["asks"].append({
                "price": row[price_col],
                "volume": row.get(vol_col, 0) if pd.notna(row.get(vol_col)) else 0
            })

    return orderbook


def compute_stats(prices_df, trades_df):
    """Compute trading statistics."""
    stats = {}

    # Price statistics
    if "mid_price" in prices_df.columns:
        mid_prices = prices_df["mid_price"].dropna()
        stats["min_price"] = mid_prices.min()
        stats["max_price"] = mid_prices.max()
        stats["mean_price"] = mid_prices.mean()
        stats["price_std"] = mid_prices.std()

    # Spread statistics
    if "bid_price_1" in prices_df.columns and "ask_price_1" in prices_df.columns:
        spreads = prices_df["ask_price_1"] - prices_df["bid_price_1"]
        spreads = spreads.dropna()
        if len(spreads) > 0:
            stats["avg_spread"] = spreads.mean()
            stats["min_spread"] = spreads.min()
            stats["max_spread"] = spreads.max()

    # Trade statistics
    if trades_df is not None and not trades_df.empty:
        stats["total_trades"] = len(trades_df)
        stats["total_volume"] = trades_df["quantity"].sum()
        stats["avg_trade_size"] = trades_df["quantity"].mean()
        stats["total_value"] = (trades_df["price"] * trades_df["quantity"]).sum()

    # PnL if available
    if "profit_and_loss" in prices_df.columns:
        pnl = prices_df["profit_and_loss"].dropna()
        if len(pnl) > 0:
            stats["final_pnl"] = pnl.iloc[-1]
            stats["max_pnl"] = pnl.max()
            stats["min_pnl"] = pnl.min()

    return stats
