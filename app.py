import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from utils import (CSS, LATEST, PREV, PY_MONTH, BOROUGHS,
                   METRICS, METRIC_KEYS, METRIC_FMT, METRIC_DTYPE,
                   METRIC_HELP, METRIC_LEVEL_UNIT, fmt_month,
                   get_data, get_borough_data, get_borough_geojson,
                   pp_chg, delta_str)

st.set_page_config(page_title="Uber NYC — Competitive Landscape", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

st.title("Uber NYC — Monthly Competitive Landscape")
st.caption(f"Reporting period: **{fmt_month(LATEST)}**  ·  Source: NYC TLC")

# ── Data ──────────────────────────────────────────────────────────────────────

monthly = get_data()
borough_data = get_borough_data()
geojson      = get_borough_geojson()

# ── Hero: Trip Share + Revenue Share ─────────────────────────────────────────

def hero_card(label, value_str, rows):
    rows_html = "".join(
        f'<div class="hero-card-row">'
        f'<span class="hero-card-row-lbl">{lbl}</span>'
        f'<span class="{css}">{val}</span>'
        f'</div>'
        for lbl, val, css in rows
    )
    return (
        f'<div class="hero-card">'
        f'<div class="hero-card-label">{label}</div>'
        f'<div class="hero-card-value">{value_str}</div>'
        f'{rows_html}'
        f'</div>'
    )

trip_share_now  = monthly.loc[LATEST,    "uber_share"]
trip_share_prev = monthly.loc[PREV,      "uber_share"]
trip_share_py   = monthly.loc[PY_MONTH,  "uber_share"]
_, trip_mom_t   = pp_chg(trip_share_now, trip_share_prev)
_, trip_py_t    = pp_chg(trip_share_now, trip_share_py)
trip_mom_v, _   = pp_chg(trip_share_now, trip_share_prev)
trip_py_v,  _   = pp_chg(trip_share_now, trip_share_py)

rev_share_now  = monthly.loc[LATEST,   "uber_revenue_share"]
rev_share_prev = monthly.loc[PREV,     "uber_revenue_share"]
rev_share_py   = monthly.loc[PY_MONTH, "uber_revenue_share"]
_, rev_mom_t   = pp_chg(rev_share_now, rev_share_prev)
_, rev_py_t    = pp_chg(rev_share_now, rev_share_py)
rev_mom_v, _   = pp_chg(rev_share_now, rev_share_prev)
rev_py_v,  _   = pp_chg(rev_share_now, rev_share_py)

def pcss(v): return "pos" if v >= 0 else "neg"

trip_card = hero_card(
    "Trip Share",
    f"{trip_share_now:.1f}%",
    [("vs. Prior Month",    trip_mom_t, pcss(trip_mom_v)),
     (f"vs. {fmt_month(PY_MONTH)}", trip_py_t,  pcss(trip_py_v))],
)
rev_card = hero_card(
    "Revenue Share",
    f"{rev_share_now:.1f}%",
    [("vs. Prior Month",    rev_mom_t, pcss(rev_mom_v)),
     (f"vs. {fmt_month(PY_MONTH)}",  rev_py_t,  pcss(rev_py_v))],
)

st.markdown(f'<div class="hero-wrapper">{trip_card}{rev_card}</div>', unsafe_allow_html=True)
st.caption("Trip share: Uber % of total rides. Revenue share: Uber % of total gross bookings (rides × avg fare).")

st.divider()

# ── KPI section (reactive fragment) ──────────────────────────────────────────

@st.fragment
def kpi_section():
    # ── KPI selector ──────────────────────────────────────────────────────────
    _default_kpi = [m[1] for m in METRICS].index("Trip Share")
    sc1, _, _ = st.columns(3)
    with sc1:
        metric_label = st.selectbox("KPI", options=[m[1] for m in METRICS], index=_default_kpi)

    metric   = METRIC_KEYS[[m[1] for m in METRICS].index(metric_label)]
    dtype    = METRIC_DTYPE[metric]
    fmt      = METRIC_FMT[metric]
    lvl_unit = METRIC_LEVEL_UNIT[metric]

    st.markdown(
        f'<div style="font-size:0.8rem;color:rgba(255,255,255,0.45);margin-top:-0.4rem;margin-bottom:0.6rem">'
        f'{METRIC_HELP.get(metric,"")}</div>',
        unsafe_allow_html=True,
    )

    # ── LTM chart ─────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="view-title" style="margin-top:0.5rem">{metric_label} — Total NYC, Last 12 Months</div>'
        f'<div class="view-subtitle">Dec 2023 – Nov 2024</div>',
        unsafe_allow_html=True,
    )

    ltm_range = pd.period_range(end=LATEST, periods=12, freq="M")
    bd = borough_data.reset_index()
    bd_ltm = bd[bd["month"].isin(ltm_range) & bd["Borough"].isin(BOROUGHS)]

    if metric == "market_share":
        def _share(g):
            u, l = g["uber_trips"].sum(), g["lyft_trips"].sum()
            return pd.Series({"uber": u/(u+l)*100, "lyft": l/(u+l)*100})
        ltm_vals = bd_ltm.groupby("month").apply(_share)
    elif metric == "revenue_share":
        def _rev(g):
            u, l = g["uber_fare_ws"].sum(), g["lyft_fare_ws"].sum()
            return pd.Series({"uber": u/(u+l)*100, "lyft": l/(u+l)*100})
        ltm_vals = bd_ltm.groupby("month").apply(_rev)
    elif metric == "daily_trips":
        ltm_vals = bd_ltm.groupby("month").agg(
            uber=("uber_daily_trips","sum"), lyft=("lyft_daily_trips","sum"))
    else:
        def _wagg(g):
            u = (g[f"uber_{metric}"]*g["uber_trips"]).sum()/g["uber_trips"].sum()
            l = (g[f"lyft_{metric}"]*g["lyft_trips"]).sum()/g["lyft_trips"].sum()
            return pd.Series({"uber": u, "lyft": l})
        ltm_vals = bd_ltm.groupby("month").apply(_wagg)

    x_ltm  = [fmt_month(m) for m in ltm_vals.index]
    is_lat = [m == LATEST for m in ltm_vals.index]

    fig_ltm = go.Figure()
    fig_ltm.add_trace(go.Scatter(
        x=x_ltm, y=ltm_vals["uber"].values, name="Uber",
        mode="lines+markers", line=dict(color="white", width=2.5),
        marker=dict(color=["#1DB954" if f else "rgba(255,255,255,0.45)" for f in is_lat],
                    size=[11 if f else 6 for f in is_lat],
                    line=dict(color="white", width=1.5)),
        hovertemplate=f"%{{x}}<br>Uber: %{{y:.2f}}<extra></extra>",
        showlegend=False,
    ))
    fig_ltm.add_trace(go.Scatter(
        x=x_ltm, y=ltm_vals["lyft"].values, name="Lyft",
        mode="lines+markers",
        line=dict(color="rgba(255,255,255,0.35)", width=2, dash="dot"),
        marker=dict(color="rgba(255,255,255,0.35)", size=6),
        hovertemplate=f"%{{x}}<br>Lyft: %{{y:.2f}}<extra></extra>",
        showlegend=False,
    ))
    fig_ltm.add_annotation(
        x=x_ltm[-1], y=ltm_vals["uber"].iloc[-1], showarrow=False,
        text="  Uber", xanchor="left",
        font=dict(color="rgba(255,255,255,0.85)", size=12),
    )
    fig_ltm.add_annotation(
        x=x_ltm[-1], y=ltm_vals["lyft"].iloc[-1], showarrow=False,
        text="  Lyft", xanchor="left",
        font=dict(color="rgba(255,255,255,0.4)", size=12),
    )
    # For %-value metrics the axis shows actual % values, not pp deltas
    chart_yunit = "%" if dtype == "pp" else lvl_unit
    fig_ltm.update_layout(
        yaxis=dict(
            title=dict(text=chart_yunit, font=dict(color="rgba(255,255,255,0.45)", size=11)),
            showgrid=True, gridcolor="rgba(255,255,255,0.07)", color="rgba(255,255,255,0.55)",
        ),
        xaxis=dict(showgrid=False, color="rgba(255,255,255,0.55)"),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        margin=dict(l=40, r=60, t=10, b=0), height=220,
        hovermode="x unified",
    )
    st.plotly_chart(fig_ltm, use_container_width=True, config={"displayModeBar": False})

    # ── Borough table + map ────────────────────────────────────────────────────
    st.divider()

    tc1, tc2 = st.columns([1.15, 0.85], gap="large")
    with tc1:
        comparison = st.selectbox("Compare to",
                                  options=["Prior Month", "Prior Year Month"], index=0)
    with tc2:
        map_view = st.selectbox("Map shows",
                                options=["Level differential", "Change differential"], index=1)

    prior_p  = PREV if comparison == "Prior Month" else PY_MONTH
    comp_lbl = fmt_month(prior_p)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def nyc_total(period, provider):
        sub = borough_data.loc[period]
        if metric == "daily_trips":
            return sub[f"{provider}_daily_trips"].sum()
        if metric in ("market_share", "revenue_share"):
            if metric == "market_share":
                u, l = sub["uber_trips"].sum(), sub["lyft_trips"].sum()
            else:
                u, l = sub["uber_fare_ws"].sum(), sub["lyft_fare_ws"].sum()
            return u/(u+l)*100 if provider=="uber" else l/(u+l)*100
        col, wt = f"{provider}_{metric}", f"{provider}_trips"
        return (sub[col]*sub[wt]).sum()/sub[wt].sum()

    def fmt_level_diff(d):
        s = "+" if d >= 0 else ""
        if metric == "daily_trips": return f"{s}{d:,.0f}"
        if metric in ("fare_per_mile","dpay_per_mile"):
            return f"{'+' if d>=0 else '-'}${abs(d):.2f}"
        if dtype == "pp": return f"{s}{d:.1f} pp"
        return f"{s}{d:.1f}"

    # ── Compute rows ──────────────────────────────────────────────────────────
    rows, map_level, map_change = [], {}, {}

    for label, borough in [("Total NYC", None)] + [(b, b) for b in BOROUGHS]:
        if borough is None:
            u_cur = nyc_total(LATEST, "uber");  u_pri = nyc_total(prior_p, "uber")
            l_cur = nyc_total(LATEST, "lyft");  l_pri = nyc_total(prior_p, "lyft")
        else:
            u_cur = borough_data.loc[(LATEST,  borough), f"uber_{metric}"]
            u_pri = borough_data.loc[(prior_p, borough), f"uber_{metric}"]
            l_cur = borough_data.loc[(LATEST,  borough), f"lyft_{metric}"]
            l_pri = borough_data.loc[(prior_p, borough), f"lyft_{metric}"]

        u_dv, u_dt = delta_str((u_cur-u_pri)/abs(u_pri)*100 if dtype=="pct" else u_cur-u_pri, dtype)
        l_dv, l_dt = delta_str((l_cur-l_pri)/abs(l_pri)*100 if dtype=="pct" else l_cur-l_pri, dtype)
        lvl_dv = u_cur - l_cur
        lvl_dt = fmt_level_diff(lvl_dv)
        chg_dv = u_dv - l_dv
        chg_dt = f"{'+' if chg_dv>=0 else ''}{chg_dv:.1f} pp"

        if borough:
            map_level[borough]  = lvl_dv
            map_change[borough] = chg_dv
        rows.append((label, borough, u_cur, u_dv, u_dt, l_cur, l_dv, l_dt, lvl_dv, lvl_dt, chg_dv, chg_dt))

    # ── Labels row ────────────────────────────────────────────────────────────
    lbl_l, lbl_r = st.columns([1.15, 0.85], gap="large")
    lbl_l.markdown(
        f'<div class="view-title">Borough Breakdown</div>'
        f'<div class="view-subtitle">vs. {comp_lbl}</div>',
        unsafe_allow_html=True,
    )
    is_level_map = map_view == "Level differential"
    map_mode_str = f"Level differential ({lvl_unit})" if is_level_map else "Change differential (pp)"
    lbl_r.markdown(
        f'<div class="view-title">{metric_label}</div>'
        f'<div class="view-subtitle">{map_mode_str} · Uber minus Lyft · vs. {comp_lbl}</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.15, 0.85], gap="large")

    # ── Table ─────────────────────────────────────────────────────────────────
    with left:
        header = (
            f'<table class="boro-table"><thead>'
            f'<tr>'
            f'<th rowspan="2"></th>'
            f'<th colspan="2" class="col-group-uber" style="text-align:center;padding-bottom:0.3rem">Uber</th>'
            f'<th colspan="2" class="col-group-lyft" style="text-align:center;padding-bottom:0.3rem">Lyft</th>'
            f'<th class="col-group-diff diff-cell" style="text-align:center;padding-bottom:0.3rem">Level Diff</th>'
            f'<th class="col-group-diff diff-cell" style="text-align:center;padding-bottom:0.3rem">Change Diff</th>'
            f'</tr><tr>'
            f'<th class="col-group-uber">{fmt_month(LATEST)}</th>'
            f'<th class="col-group-uber">vs. {comp_lbl}</th>'
            f'<th class="col-group-lyft">{fmt_month(LATEST)}</th>'
            f'<th class="col-group-lyft">vs. {comp_lbl}</th>'
            f'<th class="col-group-diff diff-cell">Uber − Lyft ({lvl_unit})</th>'
            f'<th class="col-group-diff diff-cell">Uber Δ − Lyft Δ (pp)</th>'
            f'</tr></thead><tbody>'
        )
        body = ""
        for (label, borough, u_cur, u_dv, u_dt, l_cur, l_dv, l_dt, lvl_dv, lvl_dt, chg_dv, chg_dt) in rows:
            row_cls = "total-row" if borough is None else ""
            body += (
                f'<tr class="{row_cls}">'
                f'<td>{label}</td>'
                f'<td class="boro-val">{fmt(u_cur)}</td>'
                f'<td class="boro-delta {"pos" if u_dv>=0 else "neg"}">{u_dt}</td>'
                f'<td class="boro-val" style="opacity:0.6">{fmt(l_cur)}</td>'
                f'<td class="boro-delta {"pos" if l_dv>=0 else "neg"}">{l_dt}</td>'
                f'<td class="boro-diff {"pos" if lvl_dv>=0 else "neg"} diff-cell">{lvl_dt}</td>'
                f'<td class="boro-diff {"pos" if chg_dv>=0 else "neg"} diff-cell">{chg_dt}</td>'
                f'</tr>'
            )
        st.markdown(
            header + body + "</tbody></table>"
            f'<div class="view-note">Level diff: Uber minus Lyft in {lvl_unit} &nbsp;·&nbsp; '
            f'Change diff: Uber % change minus Lyft % change (pp)</div>',
            unsafe_allow_html=True,
        )

    # ── Map ───────────────────────────────────────────────────────────────────
    with right:
        is_level = is_level_map
        map_vals = map_level if is_level else map_change
        unit_str = lvl_unit if is_level else "pp"

        map_df = pd.DataFrame([
            {"borough": b, "value": v,
             "label": f"{'+' if v>=0 else ''}{v:.1f} {unit_str}  ({'Uber leads' if v>=0 else 'Lyft leads'})"}
            for b, v in map_vals.items()
        ])
        max_abs = max(abs(map_df["value"].max()), abs(map_df["value"].min()), 0.1)

        stepped = [
            [0.0,  "#7F1818"], [0.20, "#7F1818"],
            [0.20, "#D85C5C"], [0.40, "#D85C5C"],
            [0.40, "#4A4D55"], [0.60, "#4A4D55"],
            [0.60, "#5FCC6E"], [0.80, "#5FCC6E"],
            [0.80, "#1B7A2C"], [1.0,  "#1B7A2C"],
        ]
        fig_map = px.choropleth_mapbox(
            map_df, geojson=geojson, locations="borough",
            featureidkey="properties.borough",
            color="value", color_continuous_scale=stepped,
            range_color=[-max_abs, max_abs],
            hover_name="borough",
            hover_data={"value": False, "label": True, "borough": False},
            mapbox_style="carto-darkmatter",
            zoom=8.8, center={"lat": 40.70, "lon": -73.94},
            opacity=0.75, labels={"label": ""},
        )
        fig_map.update_layout(
            margin=dict(l=0, r=0, t=0, b=0), height=420,
            coloraxis_colorbar=dict(
                title=dict(text=unit_str,
                           font=dict(color="rgba(255,255,255,0.5)", size=11)),
                len=0.5, thickness=12,
                ticksuffix=f" {unit_str}",
                tickfont=dict(color="rgba(255,255,255,0.6)", size=11),
            ),
            paper_bgcolor="#0e1117",
        )
        st.plotly_chart(fig_map, use_container_width=True, config={"displayModeBar": False})
        st.markdown(
            '<div class="view-note">Green = Uber leads &nbsp;·&nbsp; Red = Lyft leads &nbsp;·&nbsp; Darker = larger differential</div>',
            unsafe_allow_html=True,
        )

kpi_section()
