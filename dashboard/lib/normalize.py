"""Normalización de answers de Typeform a filas planas para DataFrames."""

from __future__ import annotations

import json
from typing import Any


TEXT_TYPES = {"text", "short_text", "long_text", "email", "phone_number", "url"}


def normalize_answer(response_id: str, answer: dict[str, Any]) -> dict[str, Any]:
    field = answer.get("field", {})
    atype = answer.get("type")
    row: dict[str, Any] = {
        "response_id": response_id,
        "field_id": field.get("id"),
        "field_ref": field.get("ref"),
        "field_type": field.get("type") or atype,
        "value_text": None,
        "value_number": None,
        "value_choice": None,
        "value_choices": None,
        "value_boolean": None,
        "value_date": None,
        "value_file_url": None,
    }

    if atype in TEXT_TYPES:
        row["value_text"] = (
            answer.get("text")
            or answer.get("email")
            or answer.get("phone_number")
            or answer.get("url")
        )
    elif atype == "number":
        row["value_number"] = answer.get("number")
    elif atype == "boolean":
        row["value_boolean"] = answer.get("boolean")
    elif atype == "date":
        row["value_date"] = answer.get("date")
    elif atype == "choice":
        choice = answer.get("choice") or {}
        row["value_choice"] = choice.get("label") or choice.get("other")
    elif atype == "choices":
        choices = answer.get("choices") or {}
        labels = choices.get("labels") or []
        if not labels and choices.get("other"):
            labels = [choices["other"]]
        row["value_choices"] = labels
    elif atype == "file_url":
        row["value_file_url"] = answer.get("file_url")
    else:
        row["value_text"] = json.dumps(answer, ensure_ascii=False)

    return row


def normalize_response(form_response: dict[str, Any]) -> tuple[dict, list[dict]]:
    """De un `form_response` (item del GET /responses), devuelve (response_row, answer_rows)."""
    response_id = form_response.get("token") or form_response.get("response_id")
    if not response_id:
        raise ValueError("form_response sin token/response_id")

    response_row = {
        "response_id": response_id,
        "form_id": form_response.get("form_id"),
        "landed_at": form_response.get("landed_at"),
        "submitted_at": form_response.get("submitted_at"),
        "hidden": form_response.get("hidden"),
        "metadata": form_response.get("metadata"),
        "response_url": form_response.get("response_url"),
    }

    answer_rows = [
        normalize_answer(response_id, a) for a in form_response.get("answers") or []
    ]
    return response_row, answer_rows
