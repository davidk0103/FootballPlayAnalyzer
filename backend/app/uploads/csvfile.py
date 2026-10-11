"""Content-based CSV validation. The file extension and browser MIME type are ignored.

A file is accepted only if it decodes as UTF-8, contains no NUL bytes (binary files
and UTF-16 do), has a delimiter we can detect, a unique non-empty header, and stays
within the column and row limits. Cells are only ever parsed as text.
"""

import codecs
import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

import pandas as pd

DELIMITERS = ",;\t|"
SNIFF_BYTES = 64 * 1024
MAX_HEADER_LENGTH = 100
MAX_CELL_LENGTH = 1000


class CsvValidationError(ValueError):
    def __init__(self, message: str, code: str = "invalid_csv") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CsvInfo:
    delimiter: str
    columns: list[str]
    preview: list[list[str]]
    row_count: int


def _text_stream(stream: BinaryIO) -> io.TextIOWrapper:
    return io.TextIOWrapper(stream, encoding="utf-8-sig", errors="strict", newline="")


def _sniff_delimiter(sample: str) -> str:
    first_line = sample.splitlines()[0] if sample else ""
    if not first_line.strip():
        raise CsvValidationError("The file is empty or the first line is blank", "empty_file")
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        counts = {d: first_line.count(d) for d in DELIMITERS}
        best = max(counts, key=lambda d: counts[d])
        if counts[best] == 0:
            raise CsvValidationError(
                "Could not find a delimiter (comma, semicolon, tab, or pipe) in the header",
                "no_delimiter",
            ) from None
        return best


def _check_header(header: list[str], max_columns: int) -> list[str]:
    columns = [h.strip() for h in header]
    if len(columns) < 2:
        raise CsvValidationError("The header must have at least two columns", "bad_header")
    if len(columns) > max_columns:
        raise CsvValidationError(
            f"The file has {len(columns)} columns; the limit is {max_columns}", "too_many_columns"
        )
    if any(not c for c in columns):
        raise CsvValidationError("Every header column needs a name", "bad_header")
    if any(len(c) > MAX_HEADER_LENGTH for c in columns):
        raise CsvValidationError(
            f"Header names must be at most {MAX_HEADER_LENGTH} characters", "bad_header"
        )
    lowered = [c.lower() for c in columns]
    dupes = sorted({c for c in columns if lowered.count(c.lower()) > 1})
    if dupes:
        raise CsvValidationError(f"Duplicate column names: {', '.join(dupes)}", "bad_header")
    return columns


def _rows(text: io.TextIOWrapper, delimiter: str) -> Iterator[list[str]]:
    reader = csv.reader(text, delimiter=delimiter, strict=True)
    try:
        yield from reader
    except UnicodeDecodeError:
        raise CsvValidationError("The file is not valid UTF-8 text", "not_utf8") from None
    except csv.Error as exc:
        raise CsvValidationError(
            f"Malformed CSV near line {reader.line_num}: {exc}", "malformed_csv"
        ) from None


def inspect_csv(stream: BinaryIO, *, max_columns: int, max_rows: int, preview_rows: int) -> CsvInfo:
    """Validate the whole file and return its shape plus a preview of the first rows."""
    head = stream.read(SNIFF_BYTES)
    if b"\x00" in head:
        raise CsvValidationError("This looks like a binary file, not CSV text", "binary_file")
    try:
        sample = codecs.getincrementaldecoder("utf-8-sig")().decode(head, final=False)
    except UnicodeDecodeError:
        raise CsvValidationError("The file is not valid UTF-8 text", "not_utf8") from None
    delimiter = _sniff_delimiter(sample)
    stream.seek(0)
    text = _text_stream(stream)
    try:
        return _scan(_rows(text, delimiter), delimiter, max_columns, max_rows, preview_rows)
    finally:
        text.detach()  # leave the caller's binary stream open


def _scan(
    rows: Iterator[list[str]], delimiter: str, max_columns: int, max_rows: int, preview_rows: int
) -> CsvInfo:
    header = next(rows, None)
    if header is None:
        raise CsvValidationError("The file is empty", "empty_file")
    columns = _check_header(header, max_columns)

    preview: list[list[str]] = []
    count = 0
    for line, row in enumerate(rows, start=2):
        if not any(cell.strip() for cell in row):
            continue
        if "\x00" in "".join(row):
            raise CsvValidationError("The file contains NUL bytes", "binary_file")
        if len(row) != len(columns):
            raise CsvValidationError(
                f"Line {line} has {len(row)} fields; the header has {len(columns)}",
                "ragged_rows",
            )
        if any(len(cell) > MAX_CELL_LENGTH for cell in row):
            raise CsvValidationError(
                f"Line {line} has a value longer than {MAX_CELL_LENGTH} characters",
                "cell_too_long",
            )
        count += 1
        if count > max_rows:
            raise CsvValidationError(
                f"The file has more than {max_rows:,} data rows", "too_many_rows"
            )
        if len(preview) < preview_rows:
            preview.append(row)
    if count == 0:
        raise CsvValidationError("The file has a header but no data rows", "no_rows")
    return CsvInfo(delimiter=delimiter, columns=columns, preview=preview, row_count=count)


def read_frame(stream: BinaryIO, delimiter: str, *, nrows: int | None = None) -> pd.DataFrame:
    """All cells as stripped strings (blank = "").

    ``row_number`` counts non-blank data rows from 1, matching the preview and the
    row numbers shown in validation feedback.
    """
    text = _text_stream(stream)
    try:
        df = _read(text, delimiter, nrows)
    except UnicodeDecodeError:
        raise CsvValidationError("The file is not valid UTF-8 text", "not_utf8") from None
    finally:
        text.detach()
    df.columns = [str(c).strip() for c in df.columns]
    df = pd.DataFrame({c: df[c].str.strip() for c in df.columns})
    if len(df):
        df = df[(df != "").any(axis=1)]
    df = df.reset_index(drop=True)
    df.insert(0, "row_number", range(1, len(df) + 1))
    return df


def _read(text: io.TextIOWrapper, delimiter: str, nrows: int | None) -> pd.DataFrame:
    return pd.read_csv(
        text,
        sep=delimiter,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        skip_blank_lines=True,
        nrows=nrows,
    )
