"""Suggest and check a mapping from standard fields to the uploaded file's columns."""

import re

from app.uploads.schema import FIELDS, FIELDS_BY_NAME, REQUIRED_FIELDS

Mapping = dict[str, str]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def suggest_mapping(columns: list[str]) -> Mapping:
    """Exact (case/punctuation-insensitive) alias matches only; each column used once."""
    by_norm = {_norm(c): c for c in columns}
    used: set[str] = set()
    out: Mapping = {}
    for spec in FIELDS:
        for alias in spec.aliases:
            column = by_norm.get(_norm(alias))
            if column is not None and column not in used:
                out[spec.name] = column
                used.add(column)
                break
    return out


def mapping_errors(mapping: Mapping, columns: list[str]) -> list[str]:
    errors: list[str] = []
    available = set(columns)
    for field, column in mapping.items():
        if field not in FIELDS_BY_NAME:
            errors.append(f"Unknown field '{field}'")
        elif column not in available:
            errors.append(f"{FIELDS_BY_NAME[field].label}: column '{column}' is not in the file")
    for field in REQUIRED_FIELDS:
        if not mapping.get(field):
            errors.append(f"{FIELDS_BY_NAME[field].label} is required; map a column to it")
    seen: dict[str, str] = {}
    for field, column in mapping.items():
        if field not in FIELDS_BY_NAME:
            continue
        label = FIELDS_BY_NAME[field].label
        if column in seen:
            errors.append(f"Column '{column}' is mapped to both {seen[column]} and {label}")
        else:
            seen[column] = label
    return errors
