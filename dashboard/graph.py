"""
Graph functions for Prosperity 4 Dashboard
Creates Plotly visualizations for price, orderbook, and PnL data.
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from dash import dash_table


def price_graph(prices_df, trades_df=None, product=""):
    """Create a price chart with bid/ask levels and trades."""
    fig = go.Figure()

    timestamps = prices_df["timestamp"]

    # Plot bid levels (green)
    for i in range(1, 4):
        bid_col = f"bid_price_{i}"
        if bid_col in prices_df.columns:
            bid_prices = prices_df[bid_col]
            opacity = 1.0 - (i - 1) * 0.25
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=bid_prices,
                mode="lines",
                name=f"Bid {i}",
                line=dict(color=f"rgba(0, 200, 83, {opacity})", width=1),
                hovertemplate=f"Bid {i}: %{{y:.2f}}<extra></extra>"
            ))

    # Plot ask levels (red)
    for i in range(1, 4):
        ask_col = f"ask_price_{i}"
        if ask_col in prices_df.columns:
            ask_prices = prices_df[ask_col]
            opacity = 1.0 - (i - 1) * 0.25
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=ask_prices,
                mode="lines",
                name=f"Ask {i}",
                line=dict(color=f"rgba(255, 82, 82, {opacity})", width=1),
                hovertemplate=f"Ask {i}: %{{y:.2f}}<extra></extra>"
            ))

    # Plot mid price
    if "mid_price" in prices_df.columns:
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=prices_df["mid_price"],
            mode="lines",
            name="Mid Price",
            line=dict(color="blue", width=2),
            hovertemplate="Mid: %{y:.2f}<extra></extra>"
        ))

    # Plot trades as markers
    if trades_df is not None and not trades_df.empty:
        # Determine if trades are buys or sells based on price relative to mid
        fig.add_trace(go.Scatter(
            x=trades_df["timestamp"],
            y=trades_df["price"],
            mode="markers",
            name="Trades",
            marker=dict(
                color="purple",
                size=trades_df["quantity"] / trades_df["quantity"].max() * 15 + 5,
                opacity=0.7,
                symbol="diamond"
            ),
            hovertemplate="Trade: %{y:.2f}<br>Qty: %{customdata}<extra></extra>",
            customdata=trades_df["quantity"]
        ))

    fig.update_layout(
        title=f"{product} Price Chart",
        xaxis_title="Timestamp",
        yaxis_title="Price",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=50, r=50, t=80, b=50),
        height=500
    )

    return fig


def add_vertical_line(fig, timestamp):
    """Add a vertical line at the specified timestamp."""
    fig.add_vline(
        x=timestamp,
        line_dash="dash",
        line_color="gray",
        line_width=1
    )
    return fig


def pnl_graph(prices_df, product=""):
    """Create a PnL chart if profit_and_loss column exists."""
    fig = go.Figure()

    if "profit_and_loss" not in prices_df.columns:
        fig.add_annotation(
            text="No PnL data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=20)
        )
        return fig

    timestamps = prices_df["timestamp"]
    pnl = prices_df["profit_and_loss"]

    # Color based on positive/negative
    colors = ["green" if p >= 0 else "red" for p in pnl]

    fig.add_trace(go.Scatter(
        x=timestamps,
        y=pnl,
        mode="lines",
        name="PnL",
        line=dict(color="blue", width=2),
        fill="tozeroy",
        fillcolor="rgba(0, 100, 255, 0.1)",
        hovertemplate="PnL: %{y:.2f}<extra></extra>"
    ))

    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

    fig.update_layout(
        title=f"{product} Profit & Loss",
        xaxis_title="Timestamp",
        yaxis_title="PnL",
        hovermode="x unified",
        margin=dict(l=50, r=50, t=80, b=50),
        height=300
    )

    return fig


def orderbook_table(orderbook):
    """Create a visual orderbook display."""
    # Prepare data for display
    rows = []

    # Add asks (in reverse order so highest ask is at top)
    for ask in reversed(orderbook.get("asks", [])):
        rows.append({
            "bid_vol": "",
            "bid_price": "",
            "ask_price": f"{ask['price']:.2f}",
            "ask_vol": int(ask["volume"]) if ask["volume"] else ""
        })

    # Add spread row
    if orderbook.get("bids") and orderbook.get("asks"):
        spread = orderbook["asks"][0]["price"] - orderbook["bids"][0]["price"]
        rows.append({
            "bid_vol": "",
            "bid_price": f"Spread: {spread:.2f}",
            "ask_price": "",
            "ask_vol": ""
        })

    # Add bids
    for bid in orderbook.get("bids", []):
        rows.append({
            "bid_vol": int(bid["volume"]) if bid["volume"] else "",
            "bid_price": f"{bid['price']:.2f}",
            "ask_price": "",
            "ask_vol": ""
        })

    columns = [
        {"name": "Bid Vol", "id": "bid_vol"},
        {"name": "Bid", "id": "bid_price"},
        {"name": "Ask", "id": "ask_price"},
        {"name": "Ask Vol", "id": "ask_vol"},
    ]

    return dash_table.DataTable(
        data=rows,
        columns=columns,
        style_table={"width": "300px"},
        style_cell={
            "textAlign": "center",
            "padding": "5px",
            "fontSize": "14px"
        },
        style_data_conditional=[
            {
                "if": {"column_id": "bid_price"},
                "backgroundColor": "rgba(0, 200, 83, 0.2)",
                "color": "green",
                "fontWeight": "bold"
            },
            {
                "if": {"column_id": "bid_vol"},
                "backgroundColor": "rgba(0, 200, 83, 0.1)"
            },
            {
                "if": {"column_id": "ask_price"},
                "backgroundColor": "rgba(255, 82, 82, 0.2)",
                "color": "red",
                "fontWeight": "bold"
            },
            {
                "if": {"column_id": "ask_vol"},
                "backgroundColor": "rgba(255, 82, 82, 0.1)"
            },
        ],
        style_header={
            "backgroundColor": "#f8f9fa",
            "fontWeight": "bold"
        }
    )


def stats_table(stats):
    """Create a statistics display table."""
    rows = []

    stat_labels = {
        "min_price": "Min Price",
        "max_price": "Max Price",
        "mean_price": "Mean Price",
        "price_std": "Price Std Dev",
        "avg_spread": "Avg Spread",
        "min_spread": "Min Spread",
        "max_spread": "Max Spread",
        "total_trades": "Total Trades",
        "total_volume": "Total Volume",
        "avg_trade_size": "Avg Trade Size",
        "total_value": "Total Value",
        "final_pnl": "Final PnL",
        "max_pnl": "Max PnL",
        "min_pnl": "Min PnL"
    }

    for key, label in stat_labels.items():
        if key in stats:
            value = stats[key]
            if isinstance(value, float):
                value = f"{value:,.2f}"
            else:
                value = f"{value:,}"
            rows.append({"stat": label, "value": value})

    return dash_table.DataTable(
        data=rows,
        columns=[
            {"name": "Statistic", "id": "stat"},
            {"name": "Value", "id": "value"}
        ],
        style_table={"width": "300px"},
        style_cell={
            "textAlign": "left",
            "padding": "8px",
            "fontSize": "14px"
        },
        style_header={
            "backgroundColor": "#f8f9fa",
            "fontWeight": "bold"
        },
        style_data_conditional=[
            {
                "if": {"filter_query": '{stat} contains "PnL"'},
                "fontWeight": "bold"
            }
        ]
    )


def compare_graph(prices_df1, prices_df2, compare_type, product, label1="Dataset 1", label2="Dataset 2"):
    """Create comparison graphs between two datasets."""
    fig = go.Figure()

    if compare_type == "price":
        if "mid_price" in prices_df1.columns:
            fig.add_trace(go.Scatter(
                x=prices_df1["timestamp"],
                y=prices_df1["mid_price"],
                mode="lines",
                name=label1,
                line=dict(color="blue")
            ))
        if "mid_price" in prices_df2.columns:
            fig.add_trace(go.Scatter(
                x=prices_df2["timestamp"],
                y=prices_df2["mid_price"],
                mode="lines",
                name=label2,
                line=dict(color="red")
            ))

    elif compare_type == "pnl":
        if "profit_and_loss" in prices_df1.columns:
            fig.add_trace(go.Scatter(
                x=prices_df1["timestamp"],
                y=prices_df1["profit_and_loss"],
                mode="lines",
                name=label1,
                line=dict(color="blue"),
                fill="tozeroy"
            ))
        if "profit_and_loss" in prices_df2.columns:
            fig.add_trace(go.Scatter(
                x=prices_df2["timestamp"],
                y=prices_df2["profit_and_loss"],
                mode="lines",
                name=label2,
                line=dict(color="red"),
                fill="tozeroy"
            ))

    elif compare_type == "spread":
        spread1 = prices_df1["ask_price_1"] - prices_df1["bid_price_1"]
        spread2 = prices_df2["ask_price_1"] - prices_df2["bid_price_1"]

        fig.add_trace(go.Scatter(
            x=prices_df1["timestamp"],
            y=spread1,
            mode="lines",
            name=label1,
            line=dict(color="blue")
        ))
        fig.add_trace(go.Scatter(
            x=prices_df2["timestamp"],
            y=spread2,
            mode="lines",
            name=label2,
            line=dict(color="red")
        ))

    fig.update_layout(
        title=f"{product} - {compare_type.title()} Comparison",
        xaxis_title="Timestamp",
        yaxis_title=compare_type.title(),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=50, r=50, t=80, b=50),
        height=400
    )

    return fig


def volume_profile(prices_df, trades_df, n_bins=50):
    """Create a volume profile chart."""
    if trades_df is None or trades_df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No trade data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False
        )
        return fig

    # Create price bins
    price_min = trades_df["price"].min()
    price_max = trades_df["price"].max()
    bins = np.linspace(price_min, price_max, n_bins + 1)

    # Aggregate volume by price bin
    trades_df["price_bin"] = pd.cut(trades_df["price"], bins=bins)
    volume_by_price = trades_df.groupby("price_bin")["quantity"].sum()

    # Get bin centers
    bin_centers = [(b.left + b.right) / 2 for b in volume_by_price.index]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=volume_by_price.values,
        y=bin_centers,
        orientation="h",
        marker_color="rgba(0, 100, 255, 0.7)",
        name="Volume"
    ))

    fig.update_layout(
        title="Volume Profile",
        xaxis_title="Volume",
        yaxis_title="Price",
        margin=dict(l=50, r=50, t=80, b=50),
        height=400
    )

    return fig
