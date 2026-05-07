"""Cálculos de % de completitud por pregunta del form."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


def _all_ids(field: dict[str, Any]) -> set[str]:
    """ID del field + IDs de subfields (matrix, group). En matrices, las answers
    llegan con el ID de cada subpregunta, no del contenedor."""
    ids = {field["id"]}
    sub = (field.get("properties") or {}).get("fields") or []
    for sf in sub:
        if "id" in sf:
            ids.add(sf["id"])
    return ids


def completion_by_question(
    form_def: dict, answers: pd.DataFrame, response_ids: list[str]
) -> pd.DataFrame:
    """% de respuestas (únicas) que respondieron cada pregunta.

    Agrupa por título exacto (las preguntas con branching condicional —
    p. ej. las 6 variantes de "¿En qué grado estás?" — quedan en una sola fila).
    Una matriz cuenta como "respondida" si la persona contestó al menos una fila.
    Conserva el orden del form.
    """
    fields = form_def.get("fields") or []
    if not fields or not response_ids:
        return pd.DataFrame()

    title_to_ids: dict[str, set[str]] = defaultdict(set)
    title_order: list[str] = []
    for f in fields:
        title = (f.get("title") or "").strip()
        if not title:
            continue
        if title not in title_to_ids:
            title_order.append(title)
        title_to_ids[title].update(_all_ids(f))

    total = len(set(response_ids))
    rows = []
    answered_by_response = (
        answers[answers["response_id"].isin(response_ids)]
        if not answers.empty
        else answers
    )

    for title in title_order:
        fids = title_to_ids[title]
        if answered_by_response.empty:
            n = 0
        else:
            n = answered_by_response.loc[
                answered_by_response["field_id"].isin(fids), "response_id"
            ].nunique()
        pct = (n / total * 100) if total else 0
        rows.append(
            {
                "pregunta": title,
                "respondidas": n,
                "total": total,
                "pct": round(pct, 1),
            }
        )

    return pd.DataFrame(rows)
