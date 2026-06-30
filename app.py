"""
GVIX — Global Volatility Index
A 30-day rolling volatility dashboard comparing custom portfolios
against the Butterfly benchmark (SPY / GLD / BIL / AGG / DBC).
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ── Brand / SEO constants ─────────────────────────────────────────────────────

ASSETS_DIR  = Path(__file__).parent / "assets"
BRAND_MARK  = ASSETS_DIR / "cp_mark.svg"   # gold Charts & Parts mark (favicon)
BRAND_FULL  = ASSETS_DIR / "cp_logo.svg"   # full lockup (top-left logo)

SITE_URL    = os.environ.get("GVIX_SITE_URL", "https://chartsandparts.com")
PAGE_TITLE  = "GVIX — Global Volatility Index | Charts & Parts"
PAGE_DESC   = (
    "GVIX tracks 30-day rolling annualised volatility and Sharpe ratios, "
    "benchmarking your custom portfolio against the Butterfly (SPY / GLD / BIL / "
    "AGG / DBC). A Charts & Parts market-risk dashboard."
)
PAGE_KEYWORDS = (
    "GVIX, global volatility index, portfolio volatility, rolling volatility, "
    "Sharpe ratio, Butterfly portfolio, market risk, Charts and Parts"
)

# ── Constants ─────────────────────────────────────────────────────────────────

BUTTERFLY: dict[str, float] = {
    "SPY": 0.20,   # US Large-Cap Equities
    "GLD": 0.20,   # Gold
    "BIL": 0.20,   # Short-term T-Bills (cash proxy)
    "AGG": 0.20,   # US Aggregate Bonds
    "DBC": 0.20,   # Broad Commodities
}

TICKER_LABELS: dict[str, str] = {
    "SPY": "S&P 500",
    "GLD": "Gold",
    "BIL": "T-Bills",
    "AGG": "US Bonds",
    "DBC": "Commodities",
}

# Series colours tuned for readability on a white surface, with GLD mapped
# to the brand gold and DBC to the brand warning orange.
ASSET_COLORS: dict[str, str] = {
    "SPY": "#2563EB",   # blue
    "GLD": "#E7B73B",   # brand gold-dark
    "BIL": "#16A34A",   # green
    "AGG": "#8B5CF6",   # purple
    "DBC": "#FF8400",   # brand warning orange
}

# ── Brand palette (mirrors charts-and-parts-webapp colours.ts) ────────────────
BRAND_GOLD       = "#E7B73B"   # gold-dark — hero accent on white
BRAND_GOLD_FILL  = "rgba(244, 209, 121, 0.20)"
BRAND_NAVY       = "#32415C"   # contrast series (user portfolio)
BRAND_TEXT       = "#171819"
BRAND_MUTED      = "#737D89"
BRAND_GRID       = "#E0E1E2"
BRAND_BG         = "#FFFFFF"

VOL_WINDOW   = 30          # trading days
ANNUALIZE    = np.sqrt(252)

PERIOD_MAP: dict[str, timedelta] = {
    "30D":  timedelta(days=45),
    "1Y":   timedelta(days=365),
    "3Y":   timedelta(days=365 * 3),
    "5Y":   timedelta(days=365 * 5),
    "10Y":  timedelta(days=365 * 10),
}

# ── SEO: patch Streamlit's static shell so crawlers see real <head> tags ──────
# Streamlit renders client-side from a single index.html. By injecting brand
# meta/OG/Twitter tags into that file's <head> (once, idempotently) we give
# crawlers a real title, description, canonical and social-share preview —
# the closest thing to native SEO without a prerender/reverse-proxy layer.

def inject_seo_meta() -> None:
    marker = "<!-- gvix-seo -->"
    head_tags = f"""{marker}
    <title>{PAGE_TITLE}</title>
    <meta name="description" content="{PAGE_DESC}" />
    <meta name="keywords" content="{PAGE_KEYWORDS}" />
    <meta name="author" content="Charts & Parts" />
    <meta name="robots" content="index, follow" />
    <meta name="theme-color" content="#F4D179" />
    <link rel="canonical" href="{SITE_URL}/gvix" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Charts & Parts" />
    <meta property="og:title" content="{PAGE_TITLE}" />
    <meta property="og:description" content="{PAGE_DESC}" />
    <meta property="og:url" content="{SITE_URL}/gvix" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{PAGE_TITLE}" />
    <meta name="twitter:description" content="{PAGE_DESC}" />
    """
    try:
        index_html = Path(st.__file__).parent / "static" / "index.html"
        html = index_html.read_text(encoding="utf-8")
        if marker in html:
            return
        # Drop Streamlit's placeholder <title> so ours is canonical, then
        # insert our tags immediately after <head>.
        html = html.replace("<title>Streamlit</title>", "")
        html = html.replace("<head>", "<head>\n    " + head_tags, 1)
        index_html.write_text(html, encoding="utf-8")
    except Exception:
        # Read-only filesystem or a Streamlit layout change — degrade silently.
        pass


inject_seo_meta()

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GVIX — Global Volatility Index",
    page_icon=str(BRAND_MARK) if BRAND_MARK.exists() else "📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "about": (
            "**GVIX — Global Volatility Index**\n\n"
            "A 30-day rolling volatility dashboard comparing custom portfolios "
            "against the Butterfly benchmark (SPY / GLD / BIL / AGG / DBC).\n\n"
            "Part of the Charts & Parts suite. Not financial advice."
        ),
        "report a bug": None,
        "get help": None,
    },
)

# Brand logo (top-left + sidebar) — falls back gracefully on older Streamlit.
if hasattr(st, "logo") and BRAND_FULL.exists():
    try:
        st.logo(str(BRAND_FULL), icon_image=str(BRAND_MARK), size="large")
    except TypeError:        # older signature without `size`
        st.logo(str(BRAND_FULL), icon_image=str(BRAND_MARK))

# Brand styling — light theme, flat cards, gold accents, generous type.
st.markdown(
    """
    <style>
    /* Comfortable reading width + breathing room for the dashboard.
       Generous top padding so the header clears Streamlit's fixed top bar
       (which is taller once st.logo is shown) instead of being cut off. */
    .block-container { max-width: 1320px; padding-top: 4.75rem; padding-bottom: 3rem; }
    /* Keep the fixed header transparent so it never masks the title underneath */
    [data-testid="stHeader"] { background: transparent; }

    /* Typography — match the site's near-black headings */
    h1, h2, h3, h4 { color: #171819; font-weight: 700; letter-spacing: -0.015em; }
    h1 { font-size: 2.1rem; }
    [data-testid="stCaptionContainer"] p { color: #737D89; }

    /* Metric cards: flat white panels, hairline border, gold top-accent on hover */
    [data-testid="stMetric"] {
        border: 1px solid #E0E1E2;
        border-radius: 6px;
        padding: 14px 16px;
        background: #FFFFFF;
        box-shadow: 0 1px 2px rgba(23,24,25,0.04);
        transition: border-color .15s ease, box-shadow .15s ease;
        min-height: 108px;            /* align cards across a row */
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    [data-testid="stMetric"]:hover {
        border-color: #F3CA60;
        box-shadow: 0 2px 8px rgba(23,24,25,0.06);
    }
    [data-testid="stMetricLabel"] { min-height: 1.9em; }   /* room for a 2-line label */
    [data-testid="stMetricLabel"] p {
        font-size: 0.72rem !important;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #737D89;
        line-height: 1.25;
        white-space: nowrap;          /* keep "GVIX Vol" etc. on one line */
    }
    /* Bigger, firmer value type so the figures are easy to read */
    [data-testid="stMetricValue"] { color: #171819; font-weight: 700; font-size: 1.7rem; line-height: 1.15; }
    [data-testid="stMetricDelta"] { font-size: 0.78rem; }
    [data-testid="stMetricDelta"] div { white-space: nowrap; }
    div[data-testid="stHorizontalBlock"] > div { gap: 0.7rem; }

    /* Buttons — brand gold, 6px radius, no uppercase (matches the site) */
    .stButton > button {
        border-radius: 6px;
        font-weight: 700;
        border: 1px solid #D4D4D4;
        transition: all .15s ease;
    }
    .stButton > button:hover {
        border-color: #E7B73B;
        background: #FFFBEF;
        color: #171819;
    }
    .stButton > button[kind="primary"] {
        background: #F4D179;
        border-color: #F4D179;
        color: #171819;
    }
    .stButton > button[kind="primary"]:hover { background: #E7B73B; border-color: #E7B73B; }

    /* Sidebar — light panel matching the site's surfaces */
    section[data-testid="stSidebar"] { background: #F9FAFB; border-right: 1px solid #E0E1E2; }
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 { color: #171819; }

    /* Inputs — subtle, gold focus ring */
    [data-testid="stSidebar"] input {
        border-radius: 6px !important;
    }

    /* Tidy the chrome for a more product-like feel */
    [data-testid="stToolbar"] { right: 0.5rem; }
    footer { visibility: hidden; }
    [data-testid="stDecoration"] { background: linear-gradient(90deg, #F4D179, #E7B73B); }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Data layer ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_prices(tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    """Download adjusted close prices via yfinance, return a tidy DataFrame."""
    if not tickers:
        return pd.DataFrame()

    raw = yf.download(
        list(tickers),
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    if raw.empty:
        return pd.DataFrame()

    # yfinance returns MultiIndex columns when >1 ticker: (field, ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
        if isinstance(close, pd.Series):          # only one ticker came back
            close = close.to_frame(name=tickers[0])
    else:
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})

    return close.dropna(how="all")


# ── Calculations ──────────────────────────────────────────────────────────────

def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna()


def rolling_vol(prices: pd.DataFrame, window: int = VOL_WINDOW) -> pd.DataFrame:
    """Per-asset 30-day rolling annualised volatility."""
    return daily_returns(prices).rolling(window).std() * ANNUALIZE


def portfolio_rolling_vol(
    prices: pd.DataFrame,
    weights: dict[str, float],
    window: int = VOL_WINDOW,
) -> pd.Series:
    """
    30-day rolling annualised volatility of a portfolio.
    Computes portfolio daily returns first, then rolls std.
    """
    tickers = [t for t in weights if t in prices.columns]
    if not tickers:
        return pd.Series(dtype=float)

    w = np.array([weights[t] for t in tickers], dtype=float)
    w /= w.sum()

    port_ret = daily_returns(prices[tickers]).dot(w)
    return (port_ret.rolling(window).std() * ANNUALIZE).rename("vol")


def portfolio_rolling_sharpe(
    prices: pd.DataFrame,
    weights: dict[str, float],
    rf_prices: pd.DataFrame,
    window: int = VOL_WINDOW,
) -> pd.Series:
    """
    30-day rolling annualised Sharpe ratio.
    Excess return = portfolio return - BIL (risk-free) return.
    Sharpe = annualised mean excess return / annualised std of excess return.
    """
    tickers = [t for t in weights if t in prices.columns]
    if not tickers:
        return pd.Series(dtype=float)

    w = np.array([weights[t] for t in tickers], dtype=float)
    w /= w.sum()

    port_ret = daily_returns(prices[tickers]).dot(w)

    if "BIL" in rf_prices.columns:
        rf_ret = daily_returns(rf_prices[["BIL"]])["BIL"].reindex(port_ret.index).fillna(0)
    else:
        rf_ret = pd.Series(0.0, index=port_ret.index)

    excess = port_ret - rf_ret
    roll_mean = excess.rolling(window).mean() * 252
    roll_std  = excess.rolling(window).std() * ANNUALIZE

    return (roll_mean / roll_std.replace(0, np.nan)).rename("sharpe")


def zscore_normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Z-score each column relative to its own period-wide mean and std."""
    return df.apply(lambda s: (s - s.mean()) / s.std(), axis=0)


# ── Sidebar — controls & portfolio builder ────────────────────────────────────

with st.sidebar:
    st.markdown("## GVIX Controls")

    period = st.radio(
        "Look-back Period",
        list(PERIOD_MAP.keys()),
        index=1,
        horizontal=True,
    )

    st.divider()
    st.markdown("### Your Portfolio")
    st.caption("Enter tickers and allocation weights (must sum to 100 %).")

    # Initialise session rows
    if "portfolio_rows" not in st.session_state:
        st.session_state.portfolio_rows = [
            {"ticker": "SPY",  "weight": 60.0},
            {"ticker": "AGG",  "weight": 40.0},
        ]

    rows_to_keep = []
    for i, row in enumerate(st.session_state.portfolio_rows):
        c1, c2, c3 = st.columns([3, 2, 1])
        new_ticker = c1.text_input(
            "Ticker", value=row["ticker"], key=f"tk_{i}",
            label_visibility="collapsed", placeholder="e.g. AAPL",
        ).upper().strip()
        new_weight = c2.number_input(
            "Wt %", min_value=0.0, max_value=100.0,
            value=float(row["weight"]), step=5.0, key=f"wt_{i}",
            label_visibility="collapsed",
        )
        remove = c3.button("✕", key=f"rm_{i}", help="Remove row")
        if not remove:
            rows_to_keep.append({"ticker": new_ticker, "weight": new_weight})

    # Guard: always keep at least one row
    if not rows_to_keep:
        rows_to_keep = [{"ticker": "", "weight": 100.0}]
    st.session_state.portfolio_rows = rows_to_keep

    if st.button("＋ Add Ticker", width="stretch"):
        st.session_state.portfolio_rows.append({"ticker": "", "weight": 0.0})
        st.rerun()

    total_w = sum(r["weight"] for r in st.session_state.portfolio_rows)
    if abs(total_w - 100.0) < 0.05:
        st.success(f"Weights: {total_w:.1f} % ✓")
    else:
        st.warning(f"Weights sum to {total_w:.1f} % — need 100 %")
        if st.button("Normalize to 100 %", width="stretch"):
            if total_w > 0:
                for r in st.session_state.portfolio_rows:
                    r["weight"] = round(r["weight"] / total_w * 100, 2)
            st.rerun()

    st.divider()
    st.markdown("### Butterfly Benchmark")
    for tk, label in TICKER_LABELS.items():
        st.markdown(
            f"<span style='color:{ASSET_COLORS[tk]}'>■</span> "
            f"**{tk}** — {label} (20 %)",
            unsafe_allow_html=True,
        )

# ── Date range ────────────────────────────────────────────────────────────────

today       = datetime.today()
period_end  = today
period_start = today - PERIOD_MAP[period]
# Warm-up buffer so the first in-period point has a full 30-day window
fetch_start = period_start - timedelta(days=60)

# ── Fetch data ────────────────────────────────────────────────────────────────

user_tickers = tuple(
    r["ticker"] for r in st.session_state.portfolio_rows if r["ticker"]
)
all_tickers = tuple(sorted(set(list(BUTTERFLY.keys()) + list(user_tickers))))

with st.spinner("Loading market data…"):
    try:
        prices = fetch_prices(
            all_tickers,
            fetch_start.strftime("%Y-%m-%d"),
            period_end.strftime("%Y-%m-%d"),
        )
    except Exception as exc:
        st.error(f"Data fetch failed: {exc}")
        st.stop()

if prices.empty:
    st.error("No price data returned. Check your internet connection and try again.")
    st.stop()

# Warn about any unrecognised user tickers
bad_tickers = [t for t in user_tickers if t and t not in prices.columns]
if bad_tickers:
    st.warning(
        f"Could not load data for: **{', '.join(bad_tickers)}** — "
        "these tickers will be skipped."
    )

# ── Butterfly (GVIX) vol ──────────────────────────────────────────────────────

butterfly_prices = prices[list(BUTTERFLY.keys())].dropna()
gvix_full  = portfolio_rolling_vol(butterfly_prices, BUTTERFLY)
gvix_chart = gvix_full[gvix_full.index >= pd.Timestamp(period_start)]

# ── User portfolio vol ────────────────────────────────────────────────────────

valid_user: dict[str, float] = {
    r["ticker"]: r["weight"]
    for r in st.session_state.portfolio_rows
    if r["ticker"] and r["ticker"] in prices.columns
}

user_port_chart: pd.Series | None = None
if valid_user:
    user_prices = prices[list(valid_user.keys())].dropna()
    user_full   = portfolio_rolling_vol(user_prices, valid_user)
    user_port_chart = user_full[user_full.index >= pd.Timestamp(period_start)]

# ── Sharpe ratios ─────────────────────────────────────────────────────────────

gvix_sharpe_full  = portfolio_rolling_sharpe(butterfly_prices, BUTTERFLY, butterfly_prices)
gvix_sharpe_chart = gvix_sharpe_full[gvix_sharpe_full.index >= pd.Timestamp(period_start)]

user_sharpe_chart: pd.Series | None = None
if valid_user:
    user_sharpe_full  = portfolio_rolling_sharpe(user_prices, valid_user, butterfly_prices)
    user_sharpe_chart = user_sharpe_full[user_sharpe_full.index >= pd.Timestamp(period_start)]

# ── Asset rolling vol (Z-score) ───────────────────────────────────────────────

asset_vol_full   = rolling_vol(butterfly_prices)
asset_vol_period = asset_vol_full[asset_vol_full.index >= pd.Timestamp(period_start)]
asset_vol_z      = zscore_normalize(asset_vol_period)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <div style="border-left:4px solid #F4D179; padding:2px 0 2px 16px; margin-bottom:6px;">
      <div style="font-size:0.72rem; font-weight:700; letter-spacing:0.12em;
                  text-transform:uppercase; color:#737D89;">
        Charts &amp; Parts · Market Risk
      </div>
      <h1 style="margin:2px 0 6px; font-size:2.1rem; color:#171819;">
        GVIX — Global Volatility Index
      </h1>
      <p style="margin:0; max-width:640px; color:#737D89; font-size:0.95rem; line-height:1.5;">
        Track 30-day rolling annualised volatility and Sharpe ratios, and benchmark your
        own portfolio against the Butterfly (SPY · GLD · BIL · AGG · DBC).
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    f"{period} view · Data through {today.strftime('%b %d, %Y')}"
)

# Headline metrics, top row: portfolio-level figures kept wide so the numbers
# read clearly (GVIX vs your portfolio). Per-asset cards go on their own row
# below — nine cards on one line crushed every value.
p_cols = st.columns(4)

cur_gvix        = None
cur_gvix_sharpe = None

# GVIX vol + Sharpe
if not gvix_chart.dropna().empty:
    cur_gvix  = gvix_chart.dropna().iloc[-1] * 100
    prev_gvix = gvix_chart.dropna().iloc[-2] * 100 if len(gvix_chart.dropna()) > 1 else cur_gvix
    cur_gvix_sharpe = gvix_sharpe_chart.dropna().iloc[-1] if not gvix_sharpe_chart.dropna().empty else None
    p_cols[0].metric("GVIX Vol", f"{cur_gvix:.1f}%", f"{cur_gvix - prev_gvix:+.2f}%")
    p_cols[1].metric("GVIX Sharpe", f"{cur_gvix_sharpe:.2f}" if cur_gvix_sharpe is not None else "—")

# User portfolio vol + Sharpe
if user_port_chart is not None and not user_port_chart.dropna().empty:
    cur_u        = user_port_chart.dropna().iloc[-1] * 100
    delta_vol    = cur_u - cur_gvix if cur_gvix is not None else 0
    cur_u_sharpe = user_sharpe_chart.dropna().iloc[-1] if user_sharpe_chart is not None and not user_sharpe_chart.dropna().empty else None
    delta_sharpe = (cur_u_sharpe - cur_gvix_sharpe) if (cur_u_sharpe is not None and cur_gvix_sharpe is not None) else None
    p_cols[2].metric("Your Vol", f"{cur_u:.1f}%", f"{delta_vol:+.2f}% vs GVIX")
    p_cols[3].metric(
        "Your Sharpe",
        f"{cur_u_sharpe:.2f}" if cur_u_sharpe is not None else "—",
        f"{delta_sharpe:+.2f} vs GVIX" if delta_sharpe is not None else None,
    )

# Per-asset 30-day vol on its own row — one card per Butterfly component, so
# each value has room to breathe.
st.markdown(
    "<div style='margin:0.9rem 0 0.35rem; font-size:0.72rem; font-weight:700; "
    "letter-spacing:0.06em; text-transform:uppercase; color:#737D89;'>"
    "Butterfly components · 30-day volatility</div>",
    unsafe_allow_html=True,
)
a_cols = st.columns(len(BUTTERFLY))
for i, ticker in enumerate(BUTTERFLY.keys()):
    col = a_cols[i]
    if ticker in asset_vol_period.columns and not asset_vol_period[ticker].dropna().empty:
        last_vol = asset_vol_period[ticker].dropna().iloc[-1] * 100
        last_z   = asset_vol_z[ticker].dropna().iloc[-1] if ticker in asset_vol_z.columns else 0
        col.metric(
            ticker,
            f"{last_vol:.1f}%",
            f"z={last_z:+.2f}",
            help=f"{TICKER_LABELS[ticker]} — z-score vs the selected period",
        )

st.divider()

# ── Chart 1 — Portfolio vol vs GVIX ──────────────────────────────────────────

fig1 = go.Figure()

# GVIX shaded area
fig1.add_trace(go.Scatter(
    x=gvix_chart.index,
    y=(gvix_chart * 100).round(2),
    name="GVIX (Butterfly)",
    mode="lines",
    line=dict(color=BRAND_GOLD, width=2.5),
    fill="tozeroy",
    fillcolor=BRAND_GOLD_FILL,
    hovertemplate="%{y:.2f}%<extra>GVIX</extra>",
))

# User portfolio vol line
if user_port_chart is not None and not user_port_chart.dropna().empty:
    fig1.add_trace(go.Scatter(
        x=user_port_chart.index,
        y=(user_port_chart * 100).round(2),
        name="Your Portfolio Vol",
        mode="lines",
        line=dict(color=BRAND_NAVY, width=2, dash="dash"),
        hovertemplate="%{y:.2f}%<extra>Your Portfolio Vol</extra>",
    ))

# GVIX Sharpe (secondary axis) — gold, dotted (groups visually with GVIX vol)
if not gvix_sharpe_chart.dropna().empty:
    fig1.add_trace(go.Scatter(
        x=gvix_sharpe_chart.index,
        y=gvix_sharpe_chart.round(3),
        name="GVIX Sharpe",
        mode="lines",
        line=dict(color=BRAND_GOLD, width=1.5, dash="dot"),
        yaxis="y2",
        hovertemplate="%{y:.2f}<extra>GVIX Sharpe</extra>",
    ))

# User portfolio Sharpe (secondary axis) — navy, dotted
if user_sharpe_chart is not None and not user_sharpe_chart.dropna().empty:
    fig1.add_trace(go.Scatter(
        x=user_sharpe_chart.index,
        y=user_sharpe_chart.round(3),
        name="Your Portfolio Sharpe",
        mode="lines",
        line=dict(color=BRAND_NAVY, width=1.5, dash="dot"),
        yaxis="y2",
        hovertemplate="%{y:.2f}<extra>Your Sharpe</extra>",
    ))

fig1.update_layout(
    title=dict(
        text="30-Day Rolling Annualised Volatility & Sharpe Ratio",
        font=dict(size=16),
    ),
    xaxis_title="",
    yaxis=dict(
        title="Annualised Vol (%)",
        ticksuffix="%",
        side="left",
    ),
    yaxis2=dict(
        title="Sharpe Ratio",
        overlaying="y",
        side="right",
        showgrid=False,
        zeroline=True,
        zerolinecolor="rgba(23,24,25,0.15)",
        zerolinewidth=1,
    ),
    template="plotly_white",
    paper_bgcolor=BRAND_BG,
    plot_bgcolor=BRAND_BG,
    font=dict(color=BRAND_TEXT),
    height=420,
    hovermode="x unified",
    margin=dict(t=55, b=35, l=55, r=65),
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="right",  x=1,
    ),
)

st.plotly_chart(fig1, width="stretch")

# ── Chart 2 — Asset vol Z-score ───────────────────────────────────────────────

fig2 = go.Figure()

for ticker in BUTTERFLY.keys():
    if ticker not in asset_vol_z.columns:
        continue
    series = asset_vol_z[ticker].dropna()
    if series.empty:
        continue
    fig2.add_trace(go.Scatter(
        x=series.index,
        y=series.round(3),
        name=f"{ticker} ({TICKER_LABELS[ticker]})",
        mode="lines",
        line=dict(color=ASSET_COLORS[ticker], width=2),
        hovertemplate="%{y:.2f}σ<extra>" + ticker + "</extra>",
    ))

# Reference lines
for level, label, alpha in [(0, "mean", 0.45), (1, "+1σ", 0.30), (-1, "−1σ", 0.30)]:
    fig2.add_hline(
        y=level,
        line_dash="dot" if level == 0 else "dash",
        line_color=f"rgba(23,24,25,{alpha})",
        annotation_text=label,
        annotation_position="right",
        annotation_font_color=f"rgba(23,24,25,{alpha + 0.2})",
        annotation_font_size=11,
    )

fig2.update_layout(
    title=dict(
        text="Asset Volatility — Z-Score Normalised (vs Selected Period)",
        font=dict(size=16),
    ),
    xaxis_title="",
    yaxis_title="Z-Score (σ)",
    template="plotly_white",
    paper_bgcolor=BRAND_BG,
    plot_bgcolor=BRAND_BG,
    font=dict(color=BRAND_TEXT),
    height=420,
    hovermode="x unified",
    margin=dict(t=55, b=35, l=55, r=80),
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="right",  x=1,
    ),
)

st.plotly_chart(fig2, width="stretch")

# ── Footer ────────────────────────────────────────────────────────────────────

st.caption(
    "Data via Yahoo Finance (yfinance). "
    "Volatility = 30-day rolling std of daily returns × √252. "
    "Sharpe = 30-day rolling annualised excess return ÷ annualised vol, using BIL as risk-free rate. "
    "Z-score computed relative to the selected look-back period. "
    "Not financial advice."
)
