"""Dashboard de la encuesta de línea de salida del Programa AMA.

Estilo Bloomberg Terminal — fondo negro, acento amber.
Dos fuentes seleccionables (Typeform / KoboToolbox) que comparten los mismos
tabs: AVANCE y COMPLETITUD.
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

from lib import kobo
from lib.completion import completion_by_question
from lib.db import get_answers, get_form_definition, get_responses
from lib.theme import AMBER, CHART_COLORS, CYAN, GREEN, RED, base_layout, html_table, inject_css


APP_TITLE = "ENCUESTA DE LÍNEA SALIDA · PROGRAMA AMA"

st.set_page_config(
    page_title="AMA · ENCUESTA DE SALIDA",
    page_icon="▣",
    layout="wide",
)

inject_css()
st_autorefresh(interval=30 * 1000, key="global_refresh")

tz = ZoneInfo("America/Bogota")


# ── Selector de fuente ──────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ▣ FUENTE")
    fuente = st.radio(
        "FUENTE DE DATOS",
        ["TYPEFORM", "KOBO"],
        label_visibility="collapsed",
    )


# ── Carga de datos según la fuente ──────────────────────────────────────────────
# Cada rama deja: `responses` (df con response_id, submitted_at y hidden_* opcionales),
# `source_title`, `goal_total` y `compute_comp(df)` → df [pregunta, respondidas, total, pct].

if fuente == "TYPEFORM":
    FORM_ID = st.secrets.get("FORM_ID")
    if not FORM_ID:
        st.error("Falta `FORM_ID` en `.streamlit/secrets.toml`.")
        st.stop()
    form_def = get_form_definition(FORM_ID)
    if form_def is None:
        st.error("No encontré ese FORM_ID en Typeform. Verifica el ID y el token.")
        st.stop()
    responses = get_responses(FORM_ID)
    answers = get_answers(FORM_ID)
    source_title = form_def.get("title") or "Encuesta de salida (Typeform)"
    goal_total = (st.secrets.get("goals") or {}).get("total")

    def compute_comp(df):
        return completion_by_question(form_def, answers, df["response_id"].tolist())

else:  # KOBO
    KOBO_UID = st.secrets.get("KOBO_ASSET_UID")
    if not KOBO_UID or not st.secrets.get("KOBO_TOKEN"):
        st.error("Faltan `KOBO_ASSET_UID` / `KOBO_TOKEN` en `.streamlit/secrets.toml`.")
        st.stop()
    asset = kobo.get_asset(KOBO_UID)
    if asset is None:
        st.error("No encontré ese KOBO_ASSET_UID en Kobo. Verifica el UID y el token.")
        st.stop()
    responses = kobo.get_responses(KOBO_UID)
    records = kobo.get_submissions(KOBO_UID)
    source_title = asset.get("title") or "Encuesta de salida (Kobo)"
    goal_total = (st.secrets.get("kobo_goals") or {}).get("total")

    def compute_comp(df):
        return kobo.completion_by_label(asset, records, df["response_id"].tolist())


if responses.empty:
    st.title(APP_TITLE)
    st.caption(f"{fuente}  ·  {source_title.upper()}")
    st.info("AÚN NO HAY RESPUESTAS")
    st.stop()


# ── Sidebar · filtros ───────────────────────────────────────────────────────────

with st.sidebar:
    st.divider()
    st.markdown("### ▣ FILTROS")

    # Ciudad (solo si la fuente la trae — p. ej. Kobo)
    ciudad_filter = None
    if "hidden_ciudad" in responses.columns:
        ciudad_options = ["TODAS LAS CIUDADES"] + sorted(
            responses["hidden_ciudad"].dropna().unique()
        )
        ciudad_sel = st.selectbox("CIUDAD", ciudad_options)
        ciudad_filter = None if ciudad_sel == "TODAS LAS CIUDADES" else ciudad_sel

    # Colegio (cascada: opciones según la ciudad elegida)
    pre = responses
    if ciudad_filter and "hidden_ciudad" in pre.columns:
        pre = pre[pre["hidden_ciudad"] == ciudad_filter]
    colegio_options = ["TODOS LOS COLEGIOS"]
    if "hidden_colegio" in pre.columns:
        colegio_options += sorted(pre["hidden_colegio"].dropna().unique())
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
    st.caption(f"UPDATED · {datetime.now(tz).strftime('%Y-%m-%d %H:%M')}")


# ── Aplicar filtros ───────────────────────────────────────────────────────────

df = responses.copy()
df = df[df["submitted_at"].dt.date <= date_to]
if ciudad_filter and "hidden_ciudad" in df.columns:
    df = df[df["hidden_ciudad"] == ciudad_filter]
if colegio_filter and "hidden_colegio" in df.columns:
    df = df[df["hidden_colegio"] == colegio_filter]


# ── Header ────────────────────────────────────────────────────────────────────

st.title(APP_TITLE)
ctx = []
if ciudad_filter:
    ctx.append(ciudad_filter.upper())
ctx.append((colegio_filter or "TODOS LOS COLEGIOS").upper())
rango = f"{min_date.strftime('%d/%m/%Y')} → {date_to.strftime('%d/%m/%Y')}"
st.caption(
    f"{fuente} · {source_title.upper()}  ·  {' · '.join(ctx)}  ·  "
    f"{rango}  ·  {datetime.now(tz).strftime('%H:%M:%S')} COT"
)

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
        ult_24h = (df["submitted_at"] >= last_24h).sum()
        ritmo = round(ult_24h / 24, 1)

        # 3er KPI adaptativo: encuestadores (Typeform) o colegios (Kobo).
        has_encuestador = "hidden_encuestador" in df.columns
        if has_encuestador:
            kpi3_label = "ENCUESTADORES"
            kpi3_val = df["hidden_encuestador"].nunique()
        else:
            kpi3_label = "COLEGIOS"
            kpi3_val = df["hidden_colegio"].nunique() if "hidden_colegio" in df.columns else 0

        kpi_cols = st.columns(4)
        kpi_cols[0].metric("RESPUESTAS TOTAL", total)
        kpi_cols[1].metric("HOY", int(hoy))
        kpi_cols[2].metric(kpi3_label, int(kpi3_val))
        kpi_cols[3].metric("RITMO · RESP/H 24H", ritmo)

        # ── Meta opcional ─────────────────────────────────────────────────────
        if goal_total:
            pct = min(total / goal_total * 100, 100)
            st.progress(
                pct / 100,
                text=f"AVANCE GLOBAL · {total} / {goal_total}  ({pct:.1f}%)",
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

        # ── Ranking por colegio (ambas fuentes) ───────────────────────────────
        if "hidden_colegio" in df.columns:
            group_col, rank_title, first_hdr = "hidden_colegio", "RANKING · COLEGIOS", "COLEGIO"
        else:
            group_col = None

        if group_col:
            st.subheader(rank_title)
            st.caption("ORDENADO POR RESPUESTAS RECOLECTADAS")

            grp = df.dropna(subset=[group_col]).groupby(group_col)
            rank_df = grp.agg(
                respuestas=("response_id", "count"),
                hoy=("submitted_at", lambda s: int((s.dt.date == today_d).sum())),
                primera=("submitted_at", "min"),
                ultima=("submitted_at", "max"),
            ).reset_index()
            rank_df = rank_df.sort_values("respuestas", ascending=False).head(50)
            rank_df["primera"] = rank_df["primera"].dt.strftime("%d/%m %H:%M")
            rank_df["ultima"] = rank_df["ultima"].dt.strftime("%d/%m %H:%M")
            rank_df = rank_df.rename(columns={group_col: "dim"})

            st.markdown(
                html_table(
                    rank_df,
                    col_defs=[
                        ("dim", first_hdr, "left"),
                        ("respuestas", "RESPUESTAS", "right"),
                        ("hoy", "HOY", "right"),
                        ("primera", "PRIMERA", "right"),
                        ("ultima", "ÚLTIMA", "right"),
                    ],
                    medal_col=1,
                    max_height=360,
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

        comp = compute_comp(df)
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
            # Contenedor de altura fija → scroll vertical cuando hay muchas preguntas.
            with st.container(height=520):
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
                    max_height=360,
                ),
                unsafe_allow_html=True,
            )
