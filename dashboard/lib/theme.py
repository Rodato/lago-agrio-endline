"""Tema visual estilo Bloomberg Terminal — fondo negro + acento amber.

Inspirado en `~/Documents/Dev/AMA/Bot_monitoring/src/app.py`.
Expone:
    inject_css()      → inyecta el CSS global
    base_layout(**kw) → layout base para Plotly
    AMBER, CYAN, GREEN, RED, CHART_COLORS, FONT
"""

from __future__ import annotations

import streamlit as st


AMBER = "#FFB300"
CYAN = "#00D4FF"
GREEN = "#00C853"
RED = "#FF1744"
ORANGE = "#FF6D00"
PURPLE = "#AA00FF"
CHART_COLORS = [AMBER, CYAN, GREEN, RED, ORANGE, PURPLE]

FONT = dict(family="IBM Plex Mono, Courier New, monospace", color="#888888", size=11)


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: 'IBM Plex Mono', 'Courier New', monospace !important;
    background-color: #080808 !important;
    color: #C8C8C8 !important;
}

[data-testid="stSidebar"] {
    background-color: #050505 !important;
    border-right: 1px solid #1E1E1E !important;
}
[data-testid="stSidebar"] * {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #888 !important;
}
[data-testid="stSidebar"] label {
    color: #FFB300 !important;
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

h1 {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #FFB300 !important;
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    border-bottom: 1px solid #FFB300;
    padding-bottom: 8px;
    margin-bottom: 4px !important;
}
h2, h3 {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #FFB300 !important;
    font-size: 0.75rem !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.15em;
}

[data-testid="stCaptionContainer"] p {
    color: #555 !important;
    font-size: 0.65rem !important;
    font-family: 'IBM Plex Mono', monospace !important;
}

[data-testid="metric-container"] {
    background: #0D0D0D;
    border: 1px solid #1E1E1E;
    border-left: 3px solid #FFB300;
    padding: 12px 20px !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.65rem !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #666 !important;
}
[data-testid="stMetricValue"] {
    font-size: 2.4rem !important;
    color: #FFB300 !important;
    font-weight: 700 !important;
}

hr {
    border: none !important;
    border-top: 1px solid #1A1A1A !important;
    margin: 12px 0 !important;
}

[data-testid="stSelectbox"] > div > div,
[data-testid="stDateInput"] input,
[data-testid="stMultiSelect"] > div > div {
    background: #0D0D0D !important;
    border: 1px solid #2A2A2A !important;
    color: #C8C8C8 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.75rem !important;
}

[data-testid="stInfo"] {
    background: #0D0D0D !important;
    border: 1px solid #1E1E1E !important;
    color: #555 !important;
    font-size: 0.7rem !important;
}

/* Tabs */
[data-testid="stTabs"] button {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #555 !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.7rem !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #FFB300 !important;
    border-bottom-color: #FFB300 !important;
}

/* Progress bar */
[data-testid="stProgress"] > div > div > div > div {
    background-color: #FFB300 !important;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: #080808; }
::-webkit-scrollbar-thumb { background: #1E1E1E; }

[data-testid="stSelectbox"] svg,
[data-testid="stDateInput"] svg,
button[data-testid="stBaseButton-minimal"] svg { display: none !important; }

/* Restaurar la fuente de los iconos Material de Streamlit. El override monospace
   global de arriba los pisaba y los mostraba como texto (p. ej. la flecha de
   colapsar el sidebar salía como "keyboard_double_arrow_left"). */
.stApp [data-testid="stIconMaterial"],
span.material-symbols-rounded,
span.material-symbols-outlined {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def base_layout(**kwargs) -> dict:
    base = dict(
        paper_bgcolor="#0D0D0D",
        plot_bgcolor="#0D0D0D",
        font=FONT,
        xaxis=dict(
            showgrid=True, gridcolor="#151515", gridwidth=1,
            zeroline=False, tickfont=FONT,
            linecolor="#1E1E1E", linewidth=1,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#151515", gridwidth=1,
            zeroline=False, tickfont=FONT,
            linecolor="#1E1E1E", linewidth=1,
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)", bordercolor="#1E1E1E", borderwidth=1,
            font=dict(family="IBM Plex Mono, monospace", color="#888", size=10),
        ),
        margin=dict(l=0, r=0, t=30, b=0),
        hoverlabel=dict(
            bgcolor="#111111", bordercolor="#333333",
            font=dict(family="IBM Plex Mono, monospace", color="#FFB300", size=11),
        ),
    )
    base.update(kwargs)
    return base


def html_table(
    df, col_defs, medal_col: int | None = None, max_height: int | None = None
) -> str:
    """Render DataFrame as Bloomberg-style HTML table.

    col_defs: list of (attr_name, header_label, align)
    medal_col: índice (0-based) de la columna numérica que tintamos amber para top 3.
    max_height: si se da, la tabla queda en un contenedor scrolleable de esa altura (px)
                con el header fijo (sticky), en vez de estirar la página.
    """
    medal_colors = {1: AMBER, 2: "#888888", 3: "#5A4000"}
    th_sticky = "position:sticky;top:0;background:#0D0D0D;z-index:2;" if max_height else ""
    thead = (
        f'<th style="padding:5px 10px;color:#FFB300;font-size:0.6rem;letter-spacing:0.12em;'
        f'border-bottom:1px solid #2A2A2A;white-space:nowrap;{th_sticky}">#</th>'
    )
    for _, hdr, align in col_defs:
        thead += (
            f'<th style="padding:5px 10px;color:#FFB300;font-size:0.6rem;'
            f'letter-spacing:0.12em;border-bottom:1px solid #2A2A2A;'
            f'text-align:{align};white-space:nowrap;{th_sticky}">{hdr}</th>'
        )

    tbody = ""
    for rank, row in enumerate(df.itertuples(), start=1):
        rank_color = medal_colors.get(rank, "#444")
        rank_weight = "700" if rank <= 3 else "400"
        tr = (
            f'<td style="padding:5px 10px;color:{rank_color};font-weight:{rank_weight};'
            f'text-align:center;border-bottom:1px solid #111;width:28px">#{rank}</td>'
        )
        for i, (attr, _, align) in enumerate(col_defs):
            val = getattr(row, attr)
            cell_color = AMBER if i == medal_col and rank <= 3 else "#C8C8C8"
            tr += (
                f'<td style="padding:5px 10px;color:{cell_color};'
                f'border-bottom:1px solid #111;text-align:{align};white-space:nowrap">{val}</td>'
            )
        tbody += f"<tr>{tr}</tr>"

    height_css = f"max-height:{max_height}px;overflow-y:auto;" if max_height else ""
    return (
        '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.72rem;'
        f'overflow-x:auto;{height_css}background:#0D0D0D;border:1px solid #1E1E1E;padding:4px">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>{thead}</tr></thead>'
        f'<tbody>{tbody}</tbody>'
        '</table></div>'
    )
