"""Dashboard de la línea de salida AMA Lago Agrio.

Estilo Bloomberg Terminal — fondo negro, acento amber.
Una sola página con tabs: AVANCE y COMPLETITUD.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

sys.path.insert(0, str(Path(__file__).parent))

from lib.completion import completion_by_question
from lib.db import get_answers, get_form_definition, get_responses
from lib.theme import AMBER, CHART_COLORS, CYAN, GREEN, RED, base_layout, html_table, inject_css


st.set_page_config(
    page_title="AMA · LÍNEA DE SALIDA",
    page_icon="▣",
    layout="wide",
)

inject_css()
st_autorefresh(interval=30 * 1000, key="global_refresh")

# ── Config ────────────────────────────────────────────────────────────────────

FORM_ID = st.secrets.get("FORM_ID")
if not FORM_ID:
    st.error("Falta `FORM_ID` en `.streamlit/secrets.toml`.")
    st.stop()

form_def = get_form_definition(FORM_ID)
if form_def is None:
    st.error("No encontré ese FORM_ID en Typeform. Verifica el ID y el token.")
    st.stop()


# ── Datos ─────────────────────────────────────────────────────────────────────

responses = get_responses(FORM_ID)
answers = get_answers(FORM_ID)

if responses.empty:
    st.title("AMA · LÍNEA DE SALIDA · LAGO AGRIO")
    st.info("AÚN NO HAY RESPUESTAS")
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ▣ FILTROS")

    # Colegio
    colegio_options = ["TODOS LOS COLEGIOS"]
    if "hidden_colegio" in responses.columns:
        colegio_options += sorted(
            [c for c in responses["hidden_colegio"].dropna().unique()]
        )
    colegio_label = st.selectbox("COLEGIO", colegio_options)
    colegio_filter = None if colegio_label == "TODOS LOS COLEGIOS" else colegio_label

    st.divider()

    # Rango de fechas
    min_date = responses["submitted_at"].min().date()
    today = date.today()
    st.caption(f"DESDE · {min_date.strftime('%d/%m/%Y')}")
    date_to = st.date_input(
        "HASTA",
        value=today,
        min_value=min_date,
        max_value=today,
    )

    st.divider()
    tz = ZoneInfo("America/Bogota")
    st.caption(f"UPDATED · {datetime.now(tz).strftime('%Y-%m-%d %H:%M')}")


# ── Aplicar filtros ───────────────────────────────────────────────────────────

df = responses.copy()
df = df[df["submitted_at"].dt.date <= date_to]
if colegio_filter and "hidden_colegio" in df.columns:
    df = df[df["hidden_colegio"] == colegio_filter]


# ── Header ────────────────────────────────────────────────────────────────────

tz = ZoneInfo("America/Bogota")
title = (form_def.get("title") or "AMA · LÍNEA DE SALIDA").upper()
st.title(title)
ctx = (colegio_filter or "TODOS LOS COLEGIOS").upper()
rango = f"{min_date.strftime('%d/%m/%Y')} → {date_to.strftime('%d/%m/%Y')}"
st.caption(f"{ctx}  ·  {rango}  ·  {datetime.now(tz).strftime('%H:%M:%S')} COT")

st.divider()


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["▣  AVANCE", "▣  COMPLETITUD POR PREGUNTA"])


# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — AVANCE
# ════════════════════════════════════════════════════════════════════════════════

with tab1:
    if df.empty:
        st.info("NO HAY RESPUESTAS CON LOS FILTROS APLICADOS")
    else:
        # ── KPIs ──────────────────────────────────────────────────────────────
        now = datetime.now(tz)
        today_d = now.date()
        last_24h = datetime.now(df["submitted_at"].dt.tz) - timedelta(hours=24)

        total = len(df)
        hoy = (df["submitted_at"].dt.date == today_d).sum()
        n_encuestadores = (
            df["hidden_encuestador"].nunique()
            if "hidden_encuestador" in df.columns
            else 0
        )
        ult_24h = (df["submitted_at"] >= last_24h).sum()
        ritmo = round(ult_24h / 24, 1)

        kpi_cols = st.columns(4)
        kpi_cols[0].metric("RESPUESTAS TOTAL", total)
        kpi_cols[1].metric("HOY", int(hoy))
        kpi_cols[2].metric("ENCUESTADORES", n_encuestadores)
        kpi_cols[3].metric("RITMO · RESP/H 24H", ritmo)

        # ── Meta opcional ─────────────────────────────────────────────────────
        goals = st.secrets.get("goals") or {}
        meta_total = goals.get("total")
        if meta_total:
            pct = min(total / meta_total * 100, 100)
            st.progress(
                pct / 100,
                text=f"AVANCE GLOBAL · {total} / {meta_total}  ({pct:.1f}%)",
            )

        st.divider()

        # ── Distribución por colegio + ritmo diario ───────────────────────────
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("RESPUESTAS · POR COLEGIO")
            if "hidden_colegio" in df.columns:
                by_col = (
                    df["hidden_colegio"]
                    .fillna("(SIN DATO)")
                    .value_counts()
                    .reset_index()
                )
                by_col.columns = ["colegio", "n"]
                by_col = by_col.sort_values("n", ascending=True)
                fig = go.Figure(
                    go.Bar(
                        x=by_col["n"],
                        y=by_col["colegio"],
                        orientation="h",
                        marker=dict(color=AMBER, line=dict(color="#080808", width=0.5)),
                        text=by_col["n"],
                        textposition="outside",
                        textfont=dict(family="IBM Plex Mono, monospace", color=AMBER, size=11),
                        hovertemplate="<b>%{y}</b><br>%{x} respuestas<extra></extra>",
                    )
                )
                fig.update_layout(
                    **base_layout(
                        yaxis=dict(
                            categoryorder="total ascending",
                            showgrid=False,
                            tickfont=dict(family="IBM Plex Mono, monospace", color="#888", size=10),
                            linecolor="#1E1E1E",
                        ),
                        xaxis=dict(showgrid=False, tickfont=dict(family="IBM Plex Mono, monospace", color="#888", size=10), linecolor="#1E1E1E"),
                        height=max(220, 40 * len(by_col) + 60),
                        margin=dict(l=0, r=40, t=10, b=0),
                    )
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("NO DATA")

        with col_right:
            st.subheader("RITMO DIARIO")
            by_day = (
                df.groupby(df["submitted_at"].dt.date)
                .size()
                .reset_index(name="n")
                .rename(columns={"submitted_at": "fecha"})
            )
            by_day.columns = ["fecha", "n"]
            by_day["acumulado"] = by_day["n"].cumsum()
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=by_day["fecha"],
                    y=by_day["n"],
                    name="DIARIO",
                    marker=dict(color=CYAN),
                    hovertemplate="<b>%{x}</b><br>%{y} respuestas<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=by_day["fecha"],
                    y=by_day["acumulado"],
                    name="ACUMULADO",
                    mode="lines+markers",
                    yaxis="y2",
                    line=dict(color=AMBER, width=2),
                    marker=dict(color=AMBER, size=6),
                    hovertemplate="<b>%{x}</b><br>%{y} acumuladas<extra></extra>",
                )
            )
            fig.update_layout(
                **base_layout(
                    yaxis=dict(title="DIARIO", rangemode="tozero", showgrid=True, gridcolor="#151515"),
                    yaxis2=dict(title="ACUMULADO", overlaying="y", side="right", rangemode="tozero", showgrid=False),
                    xaxis=dict(showgrid=False),
                    legend=dict(orientation="h", x=0.5, xanchor="center", y=1.05, bgcolor="rgba(0,0,0,0)"),
                    height=max(220, 40 * len(by_col) + 60) if "hidden_colegio" in df.columns else 320,
                    margin=dict(l=0, r=0, t=10, b=0),
                )
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Ranking de encuestadores ──────────────────────────────────────────
        if "hidden_encuestador" in df.columns:
            st.subheader("RANKING · ENCUESTADORES")
            st.caption("ORDENADO POR RESPUESTAS RECOLECTADAS")

            grp = df.dropna(subset=["hidden_encuestador"]).groupby("hidden_encuestador")
            rank_df = grp.agg(
                respuestas=("response_id", "count"),
                hoy=("submitted_at", lambda s: int((s.dt.date == today_d).sum())),
                primera=("submitted_at", "min"),
                ultima=("submitted_at", "max"),
            ).reset_index()
            rank_df = rank_df.sort_values("respuestas", ascending=False).head(50)
            rank_df["primera"] = rank_df["primera"].dt.strftime("%d/%m %H:%M")
            rank_df["ultima"] = rank_df["ultima"].dt.strftime("%d/%m %H:%M")
            rank_df = rank_df.rename(columns={"hidden_encuestador": "encuestador"})

            st.markdown(
                html_table(
                    rank_df,
                    col_defs=[
                        ("encuestador", "ENCUESTADOR", "left"),
                        ("respuestas", "RESPUESTAS", "right"),
                        ("hoy", "HOY", "right"),
                        ("primera", "PRIMERA", "right"),
                        ("ultima", "ÚLTIMA", "right"),
                    ],
                    medal_col=1,
                ),
                unsafe_allow_html=True,
            )


# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMPLETITUD POR PREGUNTA
# ════════════════════════════════════════════════════════════════════════════════

with tab2:
    if df.empty:
        st.info("NO HAY RESPUESTAS CON LOS FILTROS APLICADOS")
    else:
        st.subheader("% DE RESPUESTAS QUE CONTESTARON CADA PREGUNTA")
        st.caption(
            "Las preguntas con menor % suelen ser las que más se saltan o las "
            "que solo aplican condicionalmente (branching)."
        )

        comp = completion_by_question(form_def, answers, df["response_id"].tolist())
        if comp.empty:
            st.info("NO DATA")
        else:
            # KPI
            full = (comp["pct"] == 100).sum()
            promedio = comp["pct"].mean()
            kpi_cols = st.columns(3)
            kpi_cols[0].metric("PREGUNTAS TOTAL", len(comp))
            kpi_cols[1].metric("100% COMPLETAS", int(full))
            kpi_cols[2].metric("COMPLETITUD MEDIA", f"{promedio:.1f}%")

            st.divider()

            # Bar chart horizontal con color por umbral
            comp_sorted = comp.sort_values("pct", ascending=True)

            def color_for(pct: float) -> str:
                if pct < 50:
                    return RED
                if pct < 90:
                    return AMBER
                return GREEN

            colors = [color_for(p) for p in comp_sorted["pct"]]
            preguntas_short = [
                (q if len(q) <= 90 else q[:87] + "…") for q in comp_sorted["pregunta"]
            ]

            fig = go.Figure(
                go.Bar(
                    x=comp_sorted["pct"],
                    y=preguntas_short,
                    orientation="h",
                    marker=dict(color=colors, line=dict(color="#080808", width=0.5)),
                    text=[f"{p:.1f}%" for p in comp_sorted["pct"]],
                    textposition="outside",
                    textfont=dict(family="IBM Plex Mono, monospace", color="#C8C8C8", size=10),
                    hovertemplate="<b>%{y}</b><br>%{x:.1f}%<extra></extra>",
                    customdata=comp_sorted[["respondidas", "total"]],
                )
            )
            fig.update_layout(
                **base_layout(
                    xaxis=dict(
                        title="% DE RESPUESTAS QUE CONTESTARON",
                        range=[0, 110],
                        showgrid=True,
                        gridcolor="#151515",
                        ticksuffix="%",
                    ),
                    yaxis=dict(
                        showgrid=False,
                        tickfont=dict(family="IBM Plex Mono, monospace", color="#888", size=9),
                    ),
                    height=max(400, 22 * len(comp_sorted) + 80),
                    margin=dict(l=0, r=60, t=10, b=40),
                )
            )
            st.plotly_chart(fig, use_container_width=True)

            st.divider()

            # Tabla detallada
            st.subheader("DETALLE")
            comp_table = comp.sort_values("pct", ascending=True).copy()
            comp_table["completitud"] = comp_table["pct"].map(lambda p: f"{p:.1f}%")
            comp_table["pregunta"] = comp_table["pregunta"].map(
                lambda q: q if len(q) <= 100 else q[:97] + "…"
            )
            comp_table["fraccion"] = (
                comp_table["respondidas"].astype(str) + " / " + comp_table["total"].astype(str)
            )
            st.markdown(
                html_table(
                    comp_table,
                    col_defs=[
                        ("pregunta", "PREGUNTA", "left"),
                        ("fraccion", "RESPONDIDAS", "right"),
                        ("completitud", "%", "right"),
                    ],
                    medal_col=2,
                ),
                unsafe_allow_html=True,
            )
