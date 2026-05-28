"""Cliente KoboToolbox API con cache de Streamlit.

Espejo de `db.py` pero para Kobo. Una llamada paginada trae todos los envíos;
las funciones derivan DataFrames in-memory dentro de la ventana del cache (30s).

A diferencia de Typeform, los envíos de Kobo son dicts planos con claves
`grupo/pregunta` (p. ej. `datos_colegio/colegio_final`). El form de salida AMA no
captura encuestador (`_submitted_by` es None, envíos vía web), pero sí ciudad y
colegio, así que exponemos `hidden_ciudad` y `hidden_colegio`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import httpx
import pandas as pd
import streamlit as st


DEFAULT_BASE = "https://kf.kobotoolbox.org"

# Tipos del survey que NO son preguntas reales contestables.
_SKIP_TYPES = {
    "note",
    "calculate",
    "start",
    "end",
    "today",
    "begin_group",
    "end_group",
    "begin_repeat",
    "end_repeat",
    "audit",
    "deviceid",
}


def _base() -> str:
    return st.secrets.get("KOBO_BASE", DEFAULT_BASE).rstrip("/")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Token {st.secrets['KOBO_TOKEN']}"}


def _first(label: Any) -> str | None:
    """Las etiquetas de Kobo a veces vienen como lista (una por idioma)."""
    if isinstance(label, list):
        return label[0] if label else None
    return label


def _rid(record: dict[str, Any]) -> str | None:
    rid = record.get("_uuid") or record.get("_id")
    return str(rid) if rid is not None else None


def _nonempty(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return str(v).strip() != ""


@st.cache_data(ttl=60)
def get_asset(uid: str) -> dict[str, Any] | None:
    """Definición del form: preguntas reales (ordenadas) + mapas de etiquetas. Cache 60s."""
    r = httpx.get(
        f"{_base()}/api/v2/assets/{uid}/?format=json",
        headers=_headers(),
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    form = r.json()
    content = form.get("content") or {}
    survey = content.get("survey") or []

    # choices: list_name -> {value: label}
    choices: dict[str, dict[str, str]] = defaultdict(dict)
    for ch in content.get("choices") or []:
        list_name = ch.get("list_name")
        value = ch.get("name")
        if list_name and value is not None:
            choices[list_name][value] = _first(ch.get("label")) or value

    # Recorre el survey manteniendo la pila de grupos para construir `grupo/pregunta`.
    questions: list[dict[str, str]] = []
    list_by_name: dict[str, str] = {}
    stack: list[str] = []
    for row in survey:
        rtype = row.get("type")
        name = row.get("name")
        if rtype in ("begin_group", "begin_repeat"):
            if name:
                stack.append(name)
            continue
        if rtype in ("end_group", "end_repeat"):
            if stack:
                stack.pop()
            continue
        if rtype in _SKIP_TYPES or not name:
            continue
        label = (_first(row.get("label")) or name).strip()
        full_key = "/".join([*stack, name]) if stack else name
        questions.append({"name": name, "full_key": full_key, "label": label})
        list_name = row.get("select_from_list_name")
        if list_name:
            list_by_name[name] = list_name

    # colegio_final es un calculate (coalesce de las variantes por ciudad); su valor
    # vive en las listas de las preguntas colegio_iquitos / colegio_lagoagrio.
    colegio_map: dict[str, str] = {}
    for qname in ("colegio_iquitos", "colegio_lagoagrio"):
        list_name = list_by_name.get(qname)
        if list_name:
            colegio_map.update(choices.get(list_name, {}))
    ciudad_map = dict(choices.get(list_by_name.get("ciudad", ""), {}))

    return {
        "uid": uid,
        "title": form.get("name") or "Encuesta de salida AMA",
        "submission_count": form.get("deployment__submission_count"),
        "questions": questions,
        "colegio_value_to_label": colegio_map,
        "ciudad_value_to_label": ciudad_map,
    }


@st.cache_data(ttl=30, show_spinner="Trayendo envíos de KoboToolbox…")
def _fetch(uid: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Pagina /assets/{uid}/data/ siguiendo `next`; devuelve (responses_df, records)."""
    asset = get_asset(uid) or {}
    colegio_map = asset.get("colegio_value_to_label") or {}
    ciudad_map = asset.get("ciudad_value_to_label") or {}

    records: list[dict[str, Any]] = []
    url: str | None = f"{_base()}/api/v2/assets/{uid}/data/?format=json&limit=30000"
    with httpx.Client(headers=_headers(), timeout=120) as client:
        while url:
            r = client.get(url)
            r.raise_for_status()
            page = r.json()
            records.extend(page.get("results") or [])
            url = page.get("next")

    rows: list[dict[str, Any]] = []
    for rec in records:
        code = (
            rec.get("datos_colegio/colegio_final")
            or rec.get("datos_colegio/colegio_iquitos")
            or rec.get("datos_colegio/colegio_lagoagrio")
        )
        colegio = colegio_map.get(code, code) if code else None
        ciudad_code = rec.get("datos_personales/ciudad")
        ciudad = ciudad_map.get(ciudad_code) or rec.get("ciudad_label")
        rows.append(
            {
                "response_id": _rid(rec),
                "submitted_at": rec.get("_submission_time"),
                "hidden_colegio": colegio,
                "hidden_ciudad": ciudad,
            }
        )

    responses = pd.DataFrame(rows)
    if not responses.empty:
        responses["submitted_at"] = pd.to_datetime(
            responses["submitted_at"], utc=True, errors="coerce"
        )
    return responses, records


def get_responses(uid: str) -> pd.DataFrame:
    responses, _ = _fetch(uid)
    return responses


def get_submissions(uid: str) -> list[dict[str, Any]]:
    _, records = _fetch(uid)
    return records


def completion_by_label(
    asset: dict, records: list[dict[str, Any]], response_ids: list[str]
) -> pd.DataFrame:
    """% de envíos que respondieron cada pregunta. Misma forma que
    `completion.completion_by_question`: columnas [pregunta, respondidas, total, pct].

    Agrupa por etiqueta exacta, así las preguntas con branching condicional
    (las ~15 variantes de "¿En qué grado estás?" y las 2 de colegio) quedan en una
    sola fila. Una pregunta cuenta como "respondida" si cualquiera de sus claves tiene
    valor no vacío. Conserva el orden del form.
    """
    questions = asset.get("questions") or []
    total = len(set(response_ids))
    if not questions or not total:
        return pd.DataFrame()

    label_keys: dict[str, list[str]] = defaultdict(list)
    label_order: list[str] = []
    for q in questions:
        label = q["label"]
        if label not in label_keys:
            label_order.append(label)
        label_keys[label].append(q["full_key"])

    rid_set = set(response_ids)
    recs = [r for r in records if _rid(r) in rid_set]

    rows = []
    for label in label_order:
        keys = label_keys[label]
        n = sum(1 for r in recs if any(_nonempty(r.get(k)) for k in keys))
        pct = (n / total * 100) if total else 0
        rows.append(
            {
                "pregunta": label,
                "respondidas": n,
                "total": total,
                "pct": round(pct, 1),
            }
        )

    return pd.DataFrame(rows)
