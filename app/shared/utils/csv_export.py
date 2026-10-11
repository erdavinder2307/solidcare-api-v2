"""Helpers for turning report rows into downloadable CSV responses."""

import csv
import io
from datetime import UTC, datetime
from typing import Any, Sequence

from fastapi.responses import StreamingResponse


def rows_to_csv(columns: Sequence[tuple[str, str]], rows: Sequence[dict[str, Any]]) -> str:
    """Render rows as CSV text.

    `columns` is a sequence of (key, header) pairs — the key is looked up in each
    row dict, the header is written to the first line.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header for _, header in columns])
    for row in rows:
        writer.writerow(["" if row.get(key) is None else row.get(key) for key, _ in columns])
    return buffer.getvalue()


def csv_response(csv_text: str, filename_prefix: str) -> StreamingResponse:
    """Wrap CSV text in a StreamingResponse with a timestamped download filename."""
    filename = f"{filename_prefix}-{datetime.now(UTC):%Y%m%d-%H%M%S}.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
