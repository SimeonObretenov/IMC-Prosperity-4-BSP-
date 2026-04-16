"""
Prosperity 4 Trading Dashboard
Visualize market data, orderbook, and PnL for IMC Prosperity 4 competition.
"""
from dash import Dash, html, Input, Output, dcc, State, ctx, callback_context
import pandas as pd
import json
from io import StringIO
import plotly.graph_objects as go


def read_json_store(json_str):
    """Read JSON from dcc.Store, handling newer pandas versions."""
    if json_str is None:
        return None
    return pd.read_json(StringIO(json_str), orient="split")
from graph import (
    price_graph, pnl_graph, orderbook_table, stats_table,
    compare_graph, add_vertical_line, volume_profile
)
from lib import (
    list_rounds, list_days, list_products, get_product_data,
    get_orderbook_at_timestamp, compute_stats
)

external_stylesheets = ["https://codepen.io/chriddyp/pen/bWLwgP.css"]
app = Dash(__name__, external_stylesheets=external_stylesheets)

app.title = "Prosperity 4 Dashboard"


def serve_layout():
    rounds = list_rounds()
    default_round = rounds[0] if rounds else None

    return html.Div([
        # Header
        html.H1("Prosperity 4 Trading Dashboard",
                style={"textAlign": "center", "marginBottom": "20px"}),

        # Data stores
        dcc.Store(id="prices-data"),
        dcc.Store(id="trades-data"),
        dcc.Store(id="current-timestamp", data=0),

        # Main controls
        html.Div([
            html.Div([
                html.Label("Round:"),
                dcc.Dropdown(
                    id="round-dropdown",
                    options=[{"label": r, "value": r} for r in rounds],
                    value=default_round,
                    clearable=False,
                    style={"width": "150px"}
                )
            ], style={"display": "inline-block", "marginRight": "20px"}),

            html.Div([
                html.Label("Day:"),
                dcc.Dropdown(
                    id="day-dropdown",
                    options=[],
                    value=None,
                    clearable=False,
                    style={"width": "100px"}
                )
            ], style={"display": "inline-block", "marginRight": "20px"}),

            html.Div([
                html.Label("Product:"),
                dcc.Dropdown(
                    id="product-dropdown",
                    options=[],
                    value=None,
                    clearable=False,
                    style={"width": "200px"}
                )
            ], style={"display": "inline-block", "marginRight": "20px"}),

            html.Div([
                html.Label("Timestamp:"),
                html.Div([
                    html.Button("<< 1000", id="btn-prev-1000", n_clicks=0,
                               style={"marginRight": "5px"}),
                    html.Button("< 100", id="btn-prev-100", n_clicks=0,
                               style={"marginRight": "5px"}),
                    dcc.Input(
                        id="timestamp-input",
                        type="number",
                        value=0,
                        style={"width": "100px", "marginRight": "5px"}
                    ),
                    html.Button("100 >", id="btn-next-100", n_clicks=0,
                               style={"marginRight": "5px"}),
                    html.Button("1000 >>", id="btn-next-1000", n_clicks=0),
                ])
            ], style={"display": "inline-block"})
        ], style={"marginBottom": "20px", "padding": "10px",
                  "backgroundColor": "#f8f9fa", "borderRadius": "5px"}),

        # Main content area
        html.Div([
            # Left column - Charts
            html.Div([
                dcc.Graph(id="price-graph", figure=go.Figure()),
                dcc.Graph(id="pnl-graph", figure=go.Figure())
            ], style={"width": "70%", "display": "inline-block",
                      "verticalAlign": "top"}),

            # Right column - Orderbook and Stats
            html.Div([
                html.H4("Orderbook", style={"textAlign": "center"}),
                html.Div(id="orderbook-container"),
                html.Hr(),
                html.H4("Statistics", style={"textAlign": "center"}),
                html.Div(id="stats-container")
            ], style={"width": "28%", "display": "inline-block",
                      "verticalAlign": "top", "marginLeft": "2%",
                      "padding": "10px", "backgroundColor": "#f8f9fa",
                      "borderRadius": "5px"})
        ]),

        html.Hr(),

        # Comparison section
        html.H3("Compare Days/Products"),
        html.Div([
            html.Div([
                html.Label("Compare Type:"),
                dcc.Dropdown(
                    id="compare-type",
                    options=[
                        {"label": "Price", "value": "price"},
                        {"label": "PnL", "value": "pnl"},
                        {"label": "Spread", "value": "spread"}
                    ],
                    value="price",
                    clearable=False,
                    style={"width": "150px"}
                )
            ], style={"display": "inline-block", "marginRight": "30px"}),

            html.Div([
                html.Label("Dataset 1:"),
                html.Div([
                    dcc.Dropdown(id="compare-day-1", options=[], value=None,
                                style={"width": "100px", "display": "inline-block"}),
                    dcc.Dropdown(id="compare-product-1", options=[], value=None,
                                style={"width": "180px", "display": "inline-block",
                                       "marginLeft": "10px"})
                ])
            ], style={"display": "inline-block", "marginRight": "30px"}),

            html.Div([
                html.Label("Dataset 2:"),
                html.Div([
                    dcc.Dropdown(id="compare-day-2", options=[], value=None,
                                style={"width": "100px", "display": "inline-block"}),
                    dcc.Dropdown(id="compare-product-2", options=[], value=None,
                                style={"width": "180px", "display": "inline-block",
                                       "marginLeft": "10px"})
                ])
            ], style={"display": "inline-block"})
        ], style={"marginBottom": "20px"}),

        dcc.Graph(id="compare-graph", figure=go.Figure()),

        html.Hr(),

        # Volume profile section
        html.H3("Volume Profile"),
        dcc.Graph(id="volume-profile-graph", figure=go.Figure())

    ], style={"padding": "20px", "maxWidth": "1400px", "margin": "auto"})


app.layout = serve_layout


# Callbacks
@app.callback(
    Output("day-dropdown", "options"),
    Output("day-dropdown", "value"),
    Input("round-dropdown", "value")
)
def update_day_options(round_name):
    if not round_name:
        return [], None
    days = list_days(round_name)
    options = [{"label": f"Day {d}", "value": d} for d in days]
    value = days[0] if days else None
    return options, value


@app.callback(
    Output("product-dropdown", "options"),
    Output("product-dropdown", "value"),
    Input("round-dropdown", "value"),
    Input("day-dropdown", "value")
)
def update_product_options(round_name, day):
    if not round_name or day is None:
        return [], None
    products = list_products(round_name, day)
    options = [{"label": p, "value": p} for p in products]
    value = products[0] if products else None
    return options, value


@app.callback(
    Output("prices-data", "data"),
    Output("trades-data", "data"),
    Input("round-dropdown", "value"),
    Input("day-dropdown", "value"),
    Input("product-dropdown", "value")
)
def load_data(round_name, day, product):
    if not round_name or day is None or not product:
        return None, None

    prices_df, trades_df = get_product_data(round_name, day, product)

    prices_json = prices_df.to_json(date_format="iso", orient="split") if prices_df is not None else None
    trades_json = trades_df.to_json(date_format="iso", orient="split") if trades_df is not None else None

    return prices_json, trades_json


@app.callback(
    Output("timestamp-input", "value"),
    Input("btn-prev-1000", "n_clicks"),
    Input("btn-prev-100", "n_clicks"),
    Input("btn-next-100", "n_clicks"),
    Input("btn-next-1000", "n_clicks"),
    Input("price-graph", "clickData"),
    State("timestamp-input", "value"),
    State("prices-data", "data"),
    prevent_initial_call=True
)
def update_timestamp(prev1000, prev100, next100, next1000, click_data,
                     current_ts, prices_json):
    triggered = ctx.triggered_id

    if prices_json is None:
        return current_ts or 0

    prices_df = read_json_store(prices_json)
    min_ts = prices_df["timestamp"].min()
    max_ts = prices_df["timestamp"].max()

    new_ts = current_ts or 0

    if triggered == "btn-prev-1000":
        new_ts = max(min_ts, new_ts - 1000)
    elif triggered == "btn-prev-100":
        new_ts = max(min_ts, new_ts - 100)
    elif triggered == "btn-next-100":
        new_ts = min(max_ts, new_ts + 100)
    elif triggered == "btn-next-1000":
        new_ts = min(max_ts, new_ts + 1000)
    elif triggered == "price-graph" and click_data:
        new_ts = click_data["points"][0]["x"]

    return new_ts


@app.callback(
    Output("price-graph", "figure"),
    Input("prices-data", "data"),
    Input("trades-data", "data"),
    Input("timestamp-input", "value"),
    State("product-dropdown", "value")
)
def update_price_graph(prices_json, trades_json, timestamp, product):
    if prices_json is None:
        return go.Figure()

    prices_df = read_json_store(prices_json)
    trades_df = read_json_store(trades_json)

    fig = price_graph(prices_df, trades_df, product or "")

    if timestamp:
        fig = add_vertical_line(fig, timestamp)

    return fig


@app.callback(
    Output("pnl-graph", "figure"),
    Input("prices-data", "data"),
    Input("timestamp-input", "value"),
    State("product-dropdown", "value")
)
def update_pnl_graph(prices_json, timestamp, product):
    if prices_json is None:
        return go.Figure()

    prices_df = read_json_store(prices_json)
    fig = pnl_graph(prices_df, product or "")

    if timestamp:
        fig = add_vertical_line(fig, timestamp)

    return fig


@app.callback(
    Output("orderbook-container", "children"),
    Input("prices-data", "data"),
    Input("timestamp-input", "value")
)
def update_orderbook(prices_json, timestamp):
    if prices_json is None:
        return html.Div("No data loaded")

    prices_df = read_json_store(prices_json)
    orderbook = get_orderbook_at_timestamp(prices_df, timestamp or 0)
    return orderbook_table(orderbook)


@app.callback(
    Output("stats-container", "children"),
    Input("prices-data", "data"),
    Input("trades-data", "data")
)
def update_stats(prices_json, trades_json):
    if prices_json is None:
        return html.Div("No data loaded")

    prices_df = read_json_store(prices_json)
    trades_df = read_json_store(trades_json)

    stats = compute_stats(prices_df, trades_df)
    return stats_table(stats)


@app.callback(
    Output("volume-profile-graph", "figure"),
    Input("prices-data", "data"),
    Input("trades-data", "data")
)
def update_volume_profile(prices_json, trades_json):
    if prices_json is None:
        return go.Figure()

    prices_df = read_json_store(prices_json)
    trades_df = read_json_store(trades_json)

    return volume_profile(prices_df, trades_df)


# Comparison callbacks
@app.callback(
    Output("compare-day-1", "options"),
    Output("compare-day-1", "value"),
    Output("compare-day-2", "options"),
    Output("compare-day-2", "value"),
    Input("round-dropdown", "value")
)
def update_compare_day_options(round_name):
    if not round_name:
        return [], None, [], None

    days = list_days(round_name)
    options = [{"label": f"Day {d}", "value": d} for d in days]

    val1 = days[0] if len(days) > 0 else None
    val2 = days[1] if len(days) > 1 else (days[0] if days else None)

    return options, val1, options, val2


@app.callback(
    Output("compare-product-1", "options"),
    Output("compare-product-1", "value"),
    Input("round-dropdown", "value"),
    Input("compare-day-1", "value")
)
def update_compare_product_1(round_name, day):
    if not round_name or day is None:
        return [], None
    products = list_products(round_name, day)
    options = [{"label": p, "value": p} for p in products]
    return options, products[0] if products else None


@app.callback(
    Output("compare-product-2", "options"),
    Output("compare-product-2", "value"),
    Input("round-dropdown", "value"),
    Input("compare-day-2", "value")
)
def update_compare_product_2(round_name, day):
    if not round_name or day is None:
        return [], None
    products = list_products(round_name, day)
    options = [{"label": p, "value": p} for p in products]
    return options, products[0] if products else None


@app.callback(
    Output("compare-graph", "figure"),
    Input("round-dropdown", "value"),
    Input("compare-type", "value"),
    Input("compare-day-1", "value"),
    Input("compare-product-1", "value"),
    Input("compare-day-2", "value"),
    Input("compare-product-2", "value")
)
def update_compare_graph(round_name, compare_type, day1, product1, day2, product2):
    if not round_name or day1 is None or not product1 or day2 is None or not product2:
        return go.Figure()

    prices_df1, _ = get_product_data(round_name, day1, product1)
    prices_df2, _ = get_product_data(round_name, day2, product2)

    if prices_df1 is None or prices_df2 is None:
        return go.Figure()

    label1 = f"Day {day1} - {product1}"
    label2 = f"Day {day2} - {product2}"

    return compare_graph(prices_df1, prices_df2, compare_type, product1, label1, label2)


if __name__ == "__main__":
    print("Starting Prosperity 4 Dashboard...")
    print("Open http://127.0.0.1:8050 in your browser")
    app.run(debug=True, port=8050)
