"""Turn raw uploaded rows (all strings) into standard plays plus rejected rows.

Pure pandas, vectorized per column. A row is rejected when a required field is blank
or any mapped value cannot be parsed or is out of range; the reason names the field
and the offending value. Blank optional values become unknown (<NA>), never 0/False.
"""

import re
from dataclasses import dataclass, field

import pandas as pd

from app.uploads.mapping import Mapping
from app.uploads.schema import (
    FIELDS,
    PLAY_TYPE_SYNONYMS,
    PLAY_TYPES,
    SEASON_TYPES,
    FieldSpec,
    Kind,
)

TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y"})
FALSE_VALUES = frozenset({"0", "false", "f", "no", "n"})
TEAM_RE = re.compile(r"^[A-Z0-9]{1,5}$")
MAX_REASON = 300
MAX_RAW_VALUE = 200

PLAY_COLUMNS = tuple(f.name for f in FIELDS)


@dataclass
class Normalized:
    plays: pd.DataFrame  # PLAY_COLUMNS + row_number, one row per accepted play
    rejected: pd.DataFrame  # row_number, reason
    warnings: list[str] = field(default_factory=list)


def _show(value: object) -> str:
    text = str(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _parse(spec: FieldSpec, raw: "pd.Series[str]") -> tuple[pd.Series, "pd.Series[bool]"]:
    """(parsed values, invalid mask). Blank cells are never invalid here."""
    blank = raw == ""
    if spec.kind == Kind.TEXT:
        values = raw.astype("string").mask(blank)
        bad = ~blank & (raw.str.len() > (spec.max_length or 60))
        return values, bad
    if spec.kind == Kind.TEAM:
        upper = raw.str.upper()
        bad = ~blank & ~upper.str.match(TEAM_RE)
        return upper.astype("string").mask(blank | bad), bad
    if spec.kind == Kind.PLAY_TYPE:
        lowered = raw.str.lower().str.replace("-", "_")
        mapped = lowered.map(lambda v: PLAY_TYPE_SYNONYMS.get(v.replace("_", " "), v))
        bad = ~blank & ~mapped.isin(PLAY_TYPES)
        return mapped.astype("string").mask(blank | bad), bad
    if spec.kind == Kind.SEASON_TYPE:
        upper = raw.str.upper()
        mapped = upper.where(upper.isin(("REG", "POST", "PRE")), raw.str.lower().map(SEASON_TYPES))
        bad = ~blank & mapped.isna()
        return mapped.astype("string").mask(blank | bad), bad
    if spec.kind == Kind.BOOLEAN:
        lowered = raw.str.lower()
        lookup = {**dict.fromkeys(TRUE_VALUES, True), **dict.fromkeys(FALSE_VALUES, False)}
        flags = lowered.map(lookup).astype("boolean")
        bad = ~blank & flags.isna()
        return flags, bad
    numbers = pd.to_numeric(raw.mask(blank), errors="coerce")
    bad = ~blank & numbers.isna()
    if spec.kind == Kind.INTEGER:
        bad |= numbers.notna() & (numbers.round() != numbers)
    if spec.minimum is not None:
        bad |= numbers < spec.minimum
    if spec.maximum is not None:
        bad |= numbers > spec.maximum
    numbers = numbers.mask(bad)
    if spec.kind == Kind.INTEGER:
        return numbers.round().astype("Int64"), bad
    return numbers.astype("Float64"), bad


def _reason(spec: FieldSpec) -> str:
    if spec.kind == Kind.TEAM:
        return f"{spec.label} must be a 1-5 character team code"
    if spec.kind == Kind.PLAY_TYPE:
        return f"{spec.label} must be one of: {', '.join(PLAY_TYPES)}"
    if spec.kind == Kind.SEASON_TYPE:
        return f"{spec.label} must be REG, POST, or PRE"
    if spec.kind == Kind.BOOLEAN:
        return f"{spec.label} must be 1/0, true/false, or yes/no"
    if spec.kind == Kind.TEXT:
        return f"{spec.label} is longer than {spec.max_length} characters"
    kind = "a whole number" if spec.kind == Kind.INTEGER else "a number"
    if spec.minimum is not None and spec.maximum is not None:
        return f"{spec.label} must be {kind} from {spec.minimum:g} to {spec.maximum:g}"
    return f"{spec.label} must be {kind}"


def _derive(plays: pd.DataFrame, mapping: Mapping) -> list[str]:
    warnings: list[str] = []
    derived: set[str] = set()
    if "success" not in mapping and "epa" in mapping:
        plays["success"] = (plays["epa"] > 0).astype("boolean").mask(plays["epa"].isna())
        warnings.append("Success was derived from EPA (success = EPA > 0).")
        derived.add("success")
    if "third_down_converted" not in mapping and "first_down" in mapping and "down" in mapping:
        third = (plays["down"] == 3).fillna(False).astype(bool)
        plays["third_down_converted"] = plays["first_down"].where(third).astype("boolean")
        warnings.append("Third-down conversions were derived from the First down column.")
        derived.add("third_down_converted")
    unmapped = [
        f.label
        for f in FIELDS
        if not f.required and f.name not in mapping and f.name not in derived
    ]
    if unmapped:
        warnings.append(
            "Not in this dataset (metrics that need them show as unavailable): "
            + ", ".join(unmapped)
        )
    return warnings


def normalize(raw: pd.DataFrame, mapping: Mapping) -> Normalized:
    """``raw`` comes from ``csvfile.read_frame``; ``mapping`` must already be valid."""
    reasons = pd.Series("", index=raw.index, dtype="string")
    plays = pd.DataFrame({"row_number": raw["row_number"]}, index=raw.index)

    def add_reason(mask: "pd.Series[bool]", text: "str | pd.Series[str]") -> None:
        mask = mask.fillna(False).astype(bool)
        if not mask.any():
            return
        current = reasons[mask]
        addition = text[mask] if isinstance(text, pd.Series) else text
        reasons[mask] = current + current.map(lambda r: "; " if r else "") + addition

    for spec in FIELDS:
        column = mapping.get(spec.name)
        if column is None:
            plays[spec.name] = pd.NA
            continue
        values, bad = _parse(spec, raw[column])
        plays[spec.name] = values
        if bad.any():
            got = raw[column].map(_show)
            add_reason(bad, _reason(spec) + " (got '" + got + "')")
        if spec.required:
            add_reason(raw[column] == "", f"{spec.label} is blank")

    same_team = (plays["offense"] == plays["defense"]).fillna(False).astype(bool)
    add_reason(same_team, "Offense and defense are the same team")

    rejected_mask = (reasons != "").astype(bool)
    rejected = pd.DataFrame(
        {
            "row_number": raw.loc[rejected_mask, "row_number"],
            "reason": reasons[rejected_mask].str.slice(0, MAX_REASON),
        }
    )
    accepted = plays[~rejected_mask].copy()
    warnings = _derive(accepted, mapping)
    return Normalized(
        plays=accepted.reset_index(drop=True),
        rejected=rejected.reset_index(drop=True),
        warnings=warnings,
    )


def raw_values(raw: pd.DataFrame, row_numbers: list[int]) -> dict[int, dict[str, str]]:
    """The original cells of the given rows, truncated, for the quarantine view."""
    subset = raw[raw["row_number"].isin(row_numbers)]
    out: dict[int, dict[str, str]] = {}
    for record in subset.to_dict("records"):
        number = int(record.pop("row_number"))
        out[number] = {str(k): str(v)[:MAX_RAW_VALUE] for k, v in record.items()}
    return out
