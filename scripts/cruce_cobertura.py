#!/usr/bin/env python3
"""Cruce línea de base ↔ línea de salida: reporte de cobertura del endline AMA.

Tira la identidad del endline (Kobo + Typeform), la cruza contra el grupo Tratamiento
de la línea de base y produce:

- `outputs/cobertura_resumen.csv`  — agregado por ciudad/colegio/grado (anónimo).
- `outputs/faltantes.csv`          — lista nominal accionable (PII, gitignored).
- `outputs/endline_no_en_base.csv` — endline sin match en base (nuevos / IDs sucios).
- `dashboard/data/baseline_keys.parquet` — llaves HMAC para el dashboard live (sin PII).

Uso:
    cd ~/Documents/Dev/AMA/Lineasalida2026/lago-agrio
    .venv/bin/python scripts/cruce_cobertura.py

Lee credenciales de `.streamlit/secrets.toml` (igual que el dashboard). El salt HMAC
sale de `COVERAGE_SALT` (env o secrets); sin él se omite el parquet.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
# Para que st.secrets encuentre .streamlit/secrets.toml hay que estar en la raíz del proyecto.
os.chdir(ROOT)

import streamlit as st  # noqa: E402  (solo para leer secrets/credenciales)

from lib import coverage as cov  # noqa: E402
from lib import db, kobo  # noqa: E402

DEFAULT_BASE = ROOT.parent.parent / "Preprocesamiento" / "outputs" / "AMA_encuesta_unificada.csv"
OUT_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "dashboard" / "data"


def fetch_endline() -> pd.DataFrame:
    """Une identidades de Kobo (Iquitos+Lago Agrio) y Typeform (Lago Agrio)."""
    frames: list[pd.DataFrame] = []

    uid = st.secrets.get("KOBO_ASSET_UID")
    if uid and st.secrets.get("KOBO_TOKEN"):
        try:
            k = kobo.get_identities(uid)
            print(f"  Kobo: {len(k)} envíos")
            frames.append(k)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Kobo falló: {e}")

    form_id = st.secrets.get("FORM_ID")
    if form_id and st.secrets.get("TYPEFORM_TOKEN"):
        try:
            t = db.get_identities(form_id)
            print(f"  Typeform: {len(t)} respuestas")
            frames.append(t)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ Typeform falló: {e}")

    return cov.build_endline_identities(*frames)


def main() -> None:
    base_path = Path(os.environ.get("BASELINE_CSV", DEFAULT_BASE))
    print(f"Base: {base_path}")
    baseline = cov.load_baseline(str(base_path))
    print(f"  Tratamiento: {len(baseline)} personas\n")

    print("Trayendo endline…")
    endline = fetch_endline()
    print(f"  Endline único (dedup): {len(endline)}\n")

    print("Cruzando…")
    res = cov.match(baseline, endline)
    mb = res.baseline

    OUT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Agregado anónimo
    res.aggregate.to_csv(OUT_DIR / "cobertura_resumen.csv", index=False)

    # 2) Faltantes nominales (PII)
    faltan = mb[~mb["alcanzado"]][
        ["codigo", "nombre", "documento", "telefono", "colegio", "grado", "ciudad"]
    ].sort_values(["ciudad", "colegio", "grado", "nombre"])
    faltan.to_csv(OUT_DIR / "faltantes.csv", index=False)

    # 3) Endline sin match en base — solo colegios de Tratamiento (señal real de
    #    calidad: posibles estudiantes nuevos o IDs sucios). Los colegios Control del
    #    endline nunca matchean una base filtrada a Tratamiento, así que se excluyen.
    trat_colegios = set(baseline["ncolegio"].dropna())
    nb = res.endline_no_en_base
    nb_trat = nb[nb["ncolegio"].isin(trat_colegios)] if not nb.empty else nb
    nb_trat[
        ["response_id", "fuente", "ciudad", "colegio", "grado", "nombre", "documento", "telefono"]
    ].to_csv(OUT_DIR / "endline_no_en_base.csv", index=False)

    # 4) Llaves HMAC para el dashboard live (si hay salt)
    salt = os.environ.get("COVERAGE_SALT") or st.secrets.get("COVERAGE_SALT")
    if salt:
        cov.build_baseline_keys(baseline, salt).to_parquet(
            DATA_DIR / "baseline_keys.parquet", index=False
        )
        print(f"Llaves HMAC → {DATA_DIR / 'baseline_keys.parquet'}")
    else:
        print("⚠ Sin COVERAGE_SALT: omito baseline_keys.parquet (el dashboard live lo necesita).")

    # ── Resumen ───────────────────────────────────────────────────────────────
    alcanzados = int(mb["alcanzado"].sum())
    meta = len(mb)
    print("\n" + "═" * 60)
    print(f"COBERTURA GLOBAL · {alcanzados}/{meta}  ({alcanzados/meta*100:.1f}%)")
    print("═" * 60)
    for ciudad, sub in mb.groupby("ciudad"):
        a, m = int(sub["alcanzado"].sum()), len(sub)
        print(f"  {ciudad:12} {a:5}/{m:<5} ({a/m*100:5.1f}%)")
    print("\nPor colegio (Tratamiento):")
    for _, row in res.aggregate.groupby("colegio").agg(
        meta=("meta", "sum"), alc=("alcanzados", "sum")
    ).reset_index().sort_values("meta", ascending=False).iterrows():
        m, a = int(row["meta"]), int(row["alc"])
        print(f"  {row['colegio'][:34]:34} {a:5}/{m:<5} ({a/m*100:5.1f}%)")
    print("\nPor método de match:")
    for metodo, n in mb["metodo"].value_counts().items():
        print(f"  {metodo:24} {n}")
    print(
        f"\nFaltan: {len(faltan)}  ·  Endline en colegios Tratamiento sin match: "
        f"{len(nb_trat)} (posibles nuevos / IDs sucios — revisar)"
    )
    print(f"\nReportes → {OUT_DIR}/  (faltantes.csv es PRIVADO, está gitignored)")


if __name__ == "__main__":
    main()
