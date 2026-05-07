"""Cliente Typeform API con cache de Streamlit.

Una sola llamada paginada trae todas las respuestas; las funciones derivan
DataFrames in-memory dentro de la ventana del cache (30s).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pandas as pd
import streamlit as st

from .normalize import normalize_response


TYPEFORM_API = "https://api.typeform.com"


def _token() -> str:
    return st.secrets["TYPEFORM_TOKEN"]


@st.cache_data(ttl=60)
def get_form_definition(form_id: str) -> dict[str, Any] | None:
    """Definición del form (preguntas, refs, hidden). Cache 60s."""
    r = httpx.get(
        f"{TYPEFORM_API}/forms/{form_id}",
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    form = r.json()
    return {
        "form_id": form_id,
        "title": form.get("title"),
        "fields": form.get("fields") or [],
        "hidden": form.get("hidden") or [],
    }


def _field_ref_map() -> dict[str, str]:
    """Lee secrets `field_refs.<nombre> = "<ref>"` y devuelve {nombre: ref}.

    Cada uno se pegará como columna `hidden_<nombre>` en el DataFrame de responses,
    para que las páginas que esperan hidden fields funcionen sin cambios.
    """
    cfg = st.secrets.get("field_refs") or {}
    return {k: v for k, v in cfg.items() if v}


def _attach_field_refs_as_hidden(
    responses: pd.DataFrame, answers: pd.DataFrame
) -> pd.DataFrame:
    """Para cada nombre→ref configurado, agrega columna `hidden_<nombre>` con el valor."""
    mapping = _field_ref_map()
    if not mapping or answers.empty:
        return responses
    for name, ref in mapping.items():
        sub = answers[answers["field_ref"] == ref]
        if sub.empty:
            continue
        # Tomar el primer valor no-nulo por columna, en orden de preferencia.
        # No usamos `or` porque NaN es truthy en Python.
        v = sub["value_choice"]
        for col in ("value_text", "value_number", "value_date", "value_file_url"):
            v = v.where(v.notna(), sub[col])
        m = pd.Series(v.values, index=sub["response_id"].values)
        responses[f"hidden_{name}"] = responses["response_id"].map(m)
    return responses


@st.cache_data(ttl=30, show_spinner="Trayendo respuestas de Typeform…")
def _fetch_all(form_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pagina /forms/{id}/responses, normaliza y devuelve (responses_df, answers_df)."""
    response_rows: list[dict] = []
    answer_rows: list[dict] = []
    before: str | None = None

    with httpx.Client(
        headers={"Authorization": f"Bearer {_token()}"}, timeout=60
    ) as client:
        while True:
            params: dict[str, Any] = {"page_size": 1000, "sort": "submitted_at,desc"}
            if before:
                params["before"] = before
            r = client.get(f"{TYPEFORM_API}/forms/{form_id}/responses", params=params)
            r.raise_for_status()
            page = r.json()
            items = page.get("items") or []
            if not items:
                break
            for item in items:
                item.setdefault("form_id", form_id)
                resp_row, ans_rows = normalize_response(item)
                response_rows.append(resp_row)
                answer_rows.extend(ans_rows)
            before = items[-1].get("token")
            if len(items) < 1000:
                break

    responses = pd.DataFrame(response_rows)
    answers = pd.DataFrame(answer_rows)

    if not responses.empty:
        for col in ("submitted_at", "landed_at"):
            if col in responses.columns:
                responses[col] = pd.to_datetime(
                    responses[col], utc=True, errors="coerce"
                )
        if "landed_at" in responses.columns and "submitted_at" in responses.columns:
            responses["duration_seconds"] = (
                (responses["submitted_at"] - responses["landed_at"]).dt.total_seconds()
            )
        # Expandir hidden a columnas
        if "hidden" in responses.columns:
            hidden_df = pd.json_normalize(
                responses["hidden"].fillna({}).tolist()
            ).add_prefix("hidden_")
            responses = pd.concat(
                [responses.drop(columns=["hidden"]), hidden_df], axis=1
            )

        # Si no hay hidden fields nativos, mapear field_refs configurados como si lo fueran
        responses = _attach_field_refs_as_hidden(responses, answers)

    return responses, answers


def get_responses(
    form_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> pd.DataFrame:
    responses, _ = _fetch_all(form_id)
    if responses.empty:
        return responses
    df = responses
    if since is not None:
        df = df[df["submitted_at"] >= pd.Timestamp(since)]
    if until is not None:
        df = df[df["submitted_at"] <= pd.Timestamp(until)]
    return df


def get_answers(
    form_id: str,
    field_refs: list[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> pd.DataFrame:
    responses, answers = _fetch_all(form_id)
    if answers.empty or responses.empty:
        return answers
    df = answers
    if field_refs:
        df = df[df["field_ref"].isin(field_refs)]
    if since is not None or until is not None:
        valid = responses
        if since is not None:
            valid = valid[valid["submitted_at"] >= pd.Timestamp(since)]
        if until is not None:
            valid = valid[valid["submitted_at"] <= pd.Timestamp(until)]
        df = df[df["response_id"].isin(valid["response_id"])]
    return df


def latest_submitted_at(form_id: str) -> datetime | None:
    responses, _ = _fetch_all(form_id)
    if responses.empty or "submitted_at" not in responses.columns:
        return None
    ts = responses["submitted_at"].max()
    return ts.to_pydatetime() if pd.notna(ts) else None
