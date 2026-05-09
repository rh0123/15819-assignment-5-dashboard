import json
import geopandas as gpd
import pandas as pd
import streamlit as st

# ── Constants ─────────────────────────────────────────────────────────────────

UBER, LYFT = "HV0003", "HV0005"
LATEST     = pd.Period("2024-11", "M")
PREV       = LATEST - 1
PY_MONTH   = LATEST - 12
BOROUGHS   = ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"]

# ── Metric catalogue ──────────────────────────────────────────────────────────

METRICS = [
    ("avg_dist",      "Avg Trip Distance",  lambda v: f"{v:.1f} mi", "pct"),
    ("daily_trips",   "Daily Trips",        lambda v: f"{v:,.0f}",   "pct"),
    ("dpay_per_mile", "Driver Pay / Mile",  lambda v: f"${v:.2f}",   "pct"),
    ("fare_per_mile", "Fare / Mile",        lambda v: f"${v:.2f}",   "pct"),
    ("market_share",  "Trip Share",       lambda v: f"{v:.1f}%",   "pp"),
    ("revenue_share", "Revenue Share",      lambda v: f"{v:.1f}%",   "pp"),
    ("take_rate",     "Take Rate",          lambda v: f"{v:.1f}%",   "pp"),
    ("tip_rate",      "Tip Rate",           lambda v: f"{v:.1f}%",   "pp"),
]
METRIC_KEYS  = [m[0] for m in METRICS]
METRIC_FMT   = {m[0]: m[2] for m in METRICS}
METRIC_DTYPE = {m[0]: m[3] for m in METRICS}

METRIC_HELP = {
    "avg_dist":      "Average trip distance in miles.",
    "daily_trips":   "Total trips in the month divided by number of days.",
    "dpay_per_mile": "Average driver pay divided by average trip distance.",
    "fare_per_mile": "Average passenger fare divided by average trip distance.",
    "market_share":  "Uber's share of total TNC trips (Uber + Lyft combined).",
    "revenue_share": "Uber's share of total gross bookings (trips × avg fare). Higher than trip share means Uber is winning higher-value rides.",
    "take_rate":     "(Fare − driver pay) ÷ fare. Excludes tips, which go directly to drivers.",
    "tip_rate":      "Average tip as a percentage of base fare.",
}

METRIC_LEVEL_UNIT = {
    "avg_dist":      "miles",
    "daily_trips":   "trips/day",
    "dpay_per_mile": "$/mile",
    "fare_per_mile": "$/mile",
    "market_share":  "pp",
    "revenue_share": "pp",
    "take_rate":     "pp",
    "tip_rate":      "pp",
}

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
<style>
#MainMenu, header, footer { visibility: hidden; }
section[data-testid="stSidebar"] { display: none; }
[data-testid="stSidebarNav"]     { display: none; }
.block-container { padding-top: 1.2rem !important; }

/* ── Hero share cards ── */
.hero-wrapper { display: flex; gap: 1.5rem; margin-bottom: 0.5rem; }
.hero-card {
    flex: 1;
    background: rgba(29,185,84,0.07);
    border: 1px solid rgba(29,185,84,0.28);
    border-radius: 12px;
    padding: 1.2rem 2rem;
}
.hero-card-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    opacity: 0.45;
    margin-bottom: 0.4rem;
}
.hero-card-value {
    font-size: 3.8rem;
    font-weight: 800;
    line-height: 1;
    color: #ffffff;
    margin-bottom: 0.9rem;
}
.hero-card-row {
    display: flex;
    justify-content: space-between;
    padding: 0.3rem 0;
    border-top: 1px solid rgba(255,255,255,0.08);
    font-size: 0.88rem;
}
.hero-card-row-lbl { opacity: 0.5; }

/* ── Borough table ── */
.boro-table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
.boro-table th, .boro-table td { padding: 0.65rem 1.1rem; text-align: right; white-space: nowrap; }
.boro-table th:first-child, .boro-table td:first-child { text-align: left; font-weight: 500; opacity: 0.7; }
.boro-table .col-group-uber { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em; opacity: 0.45; padding-bottom: 0.3rem; border-bottom: 1px solid rgba(255,255,255,0.08); }
.boro-table .col-group-lyft { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em; opacity: 0.45; padding-bottom: 0.3rem; border-bottom: 1px solid rgba(255,255,255,0.08); }
.boro-table .col-group-diff { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em; opacity: 0.45; padding-bottom: 0.3rem; border-bottom: 1px solid rgba(255,255,255,0.08); font-weight: 700; color: rgba(255,255,255,0.95); }
.boro-table tbody tr { border-top: 1px solid rgba(255,255,255,0.06); }
.boro-table tbody tr:first-child { border-top: 2px solid rgba(255,255,255,0.12); }
.boro-table tr.total-row td {
    border-top: 2px solid rgba(255,255,255,0.2);
    border-bottom: 2px solid rgba(255,255,255,0.2);
    background: rgba(255,255,255,0.06);
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    opacity: 1 !important;
}
.boro-val   { font-weight: 600; font-size: 0.95rem; color: white; }
.boro-delta { font-size: 0.88rem; font-weight: 600; }
.boro-diff  { font-size: 0.95rem; font-weight: 700; }
.diff-cell  { background: rgba(255,255,255,0.07); border-left: 2px solid rgba(255,255,255,0.18) !important; }
.total-row .diff-cell { background: rgba(255,255,255,0.12) !important; font-size: 1.1rem !important; }
.col-group-diff.diff-cell { border-left: 2px solid rgba(255,255,255,0.18) !important; }

/* ── Borough view labels ── */
.view-title    { font-size: 0.92rem; font-weight: 600; color: rgba(255,255,255,0.8); margin-bottom: 0.4rem; letter-spacing: 0.01em; }
.view-subtitle { font-size: 0.75rem; color: rgba(255,255,255,0.4); margin-bottom: 0.5rem; }
.view-note     { font-size: 0.72rem; color: rgba(255,255,255,0.35); margin-top: 0.5rem; }

/* ── Shared ── */
.pos { color: #1DB954; }
.neg { color: #ff4b4b; }
</style>
"""

# ── Raw data loader ───────────────────────────────────────────────────────────

@st.cache_data
def _load_raw():
    zones = pd.read_csv("data/taxi_zone_lookup.csv")
    df24  = pd.read_parquet("data/trips_pickup_combined_2024.parquet")
    df23  = pd.read_parquet("data/trips_pickup_combined_2023.parquet")
    df = pd.concat([
        df23[df23["request_date"].dt.year == 2023],
        df24[df24["request_date"].dt.year == 2024],
    ], ignore_index=True)
    df["month"] = df["request_date"].dt.to_period("M")
    df = df.merge(
        zones[["LocationID", "Borough", "Zone"]],
        left_on="PULocationID", right_on="LocationID", how="left"
    )
    for col in ["base_passenger_fare", "driver_pay", "tips"]:
        df[f"{col}_ws"] = df[col] * df["trip_count"]
    df["miles_ws"] = df["trip_miles"] * df["trip_count"]
    return df

# ── Citywide monthly data ─────────────────────────────────────────────────────

@st.cache_data
def get_data():
    df = _load_raw()

    monthly = (
        df.groupby(["month", "hvfhs_license_num"])["trip_count"]
        .sum().unstack(fill_value=0)
        .rename(columns={UBER: "uber", LYFT: "lyft"})
        .sort_index()
    )
    monthly["total"]      = monthly["uber"] + monthly["lyft"]
    monthly["uber_share"] = monthly["uber"] / monthly["total"] * 100

    fare_agg = (
        df.groupby(["month", "hvfhs_license_num"])["base_passenger_fare_ws"]
        .sum().unstack(fill_value=0)
        .rename(columns={UBER: "uber_fare", LYFT: "lyft_fare"})
    )
    monthly["uber_revenue_share"] = (
        fare_agg["uber_fare"] / (fare_agg["uber_fare"] + fare_agg["lyft_fare"]) * 100
    )

    return monthly

# ── Borough data ──────────────────────────────────────────────────────────────

@st.cache_data
def get_borough_data():
    df = _load_raw()
    df = df[df["Borough"].isin(BOROUGHS)]

    agg = (
        df.groupby(["month", "Borough", "hvfhs_license_num"])
        .agg(trips=("trip_count","sum"),
             fare_ws=("base_passenger_fare_ws","sum"),
             dpay_ws=("driver_pay_ws","sum"),
             tips_ws=("tips_ws","sum"),
             miles_ws=("miles_ws","sum"))
        .reset_index()
    )

    agg["fare_per_mile"]  = agg["fare_ws"]  / agg["miles_ws"]
    agg["dpay_per_mile"]  = agg["dpay_ws"]  / agg["miles_ws"]
    agg["take_rate"]      = (agg["fare_ws"] - agg["dpay_ws"]) / agg["fare_ws"] * 100
    agg["avg_dist"]       = agg["miles_ws"] / agg["trips"]
    agg["tip_rate"]       = agg["tips_ws"]  / agg["fare_ws"] * 100

    uber = agg[agg["hvfhs_license_num"]==UBER].set_index(["month","Borough"])
    lyft = agg[agg["hvfhs_license_num"]==LYFT].set_index(["month","Borough"])

    cols = ["trips","fare_per_mile","dpay_per_mile","take_rate","avg_dist","tip_rate","fare_ws"]
    wide = uber[cols].rename(columns={c: f"uber_{c}" for c in cols}).join(
           lyft[cols].rename(columns={c: f"lyft_{c}" for c in cols}))

    wide["uber_revenue_share"] = (
        wide["uber_fare_ws"] / (wide["uber_fare_ws"] + wide["lyft_fare_ws"]) * 100
    )
    wide["lyft_revenue_share"] = 100 - wide["uber_revenue_share"]

    days = {p: p.days_in_month for p in wide.index.get_level_values("month").unique()}
    wide["uber_daily_trips"] = wide.apply(lambda r: r["uber_trips"] / days[r.name[0]], axis=1)
    wide["lyft_daily_trips"] = wide.apply(lambda r: r["lyft_trips"] / days[r.name[0]], axis=1)

    wide["uber_market_share"] = wide["uber_trips"] / (wide["uber_trips"] + wide["lyft_trips"]) * 100
    wide["lyft_market_share"] = 100 - wide["uber_market_share"]

    return wide.sort_index()

# ── Borough GeoJSON ───────────────────────────────────────────────────────────

@st.cache_data
def get_borough_geojson():
    gdf = gpd.read_file("data/taxi_zones/taxi_zones.shp")
    gdf = (gdf[gdf["borough"].isin(BOROUGHS)]
           .dissolve(by="borough")
           .reset_index()[["borough","geometry"]]
           .to_crs(epsg=4326))
    return json.loads(gdf.to_json())

# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_month(p): return p.strftime("%b %Y")

def pp_chg(curr, prior):
    d = curr - prior
    return d, f"{'+'if d>=0 else ''}{d:.1f} pp"

def delta_str(val, dtype):
    sign = "+" if val >= 0 else ""
    if dtype == "pp":
        return val, f"{sign}{val:.1f} pp"
    return val, f"{sign}{val:.1f}%"
