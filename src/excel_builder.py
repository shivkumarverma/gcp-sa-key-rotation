"""
Build an .xlsx report of service account key scan/rotation results.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.rotator import RotationRecord

# Status → fill colour (ARGB hex)
_STATUS_FILLS = {
    "Rotated":  PatternFill(fill_type="solid", fgColor="C6EFCE"),   # green
    "OK":       PatternFill(fill_type="solid", fgColor="C6EFCE"),   # green
    "Expiring": PatternFill(fill_type="solid", fgColor="FFEB9C"),   # orange/amber
    "Error":    PatternFill(fill_type="solid", fgColor="FFC7CE"),   # red
}

_HEADER_FILL = PatternFill(fill_type="solid", fgColor="175CD3")
_HEADER_FONT = Font(bold=True, color="FFFFFF", name="Segoe UI", size=11)
_BODY_FONT   = Font(name="Segoe UI", size=10)

_VALIDATION_FILLS = {
    True:  PatternFill(fill_type="solid", fgColor="C6EFCE"),   # green — pass
    False: PatternFill(fill_type="solid", fgColor="FFC7CE"),   # red   — fail
}

_COLUMNS = [
    ("Project ID",          18),
    ("Service Account",     38),
    ("Key ID",              36),
    ("Expiry Date",         20),
    ("Days Remaining",      16),
    ("Status",              14),
    ("New Key ID",          36),
    ("Storage Location",    50),
    ("Rotation Timestamp",  22),
    ("Error",               40),
    ("Key Validation",      16),
]

_KEY_VALIDATION_COL = len(_COLUMNS)  # 1-based index of the Key Validation column


def build_report(
    records: list[RotationRecord],
    output_path: Path,
    rotation_enabled: bool,
) -> Path:
    """Write an .xlsx report and return its path."""
    wb = Workbook()
    ws = wb.active
    ws.title = "SA Key Rotation Report" if rotation_enabled else "SA Key Scan Report"

    # Header row
    for col_idx, (header, width) in enumerate(_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"

    # Data rows
    for row_idx, rec in enumerate(records, start=2):
        expiry_str = rec.expiry_date.strftime("%Y-%m-%d %H:%M UTC") if rec.expiry_date else "N/A"
        days_str = str(rec.days_remaining) if rec.days_remaining is not None else "N/A"
        rot_ts_str = rec.rotation_timestamp.strftime("%Y-%m-%d %H:%M UTC") if rec.rotation_timestamp else ""

        if rec.key_valid is None:
            validation_str = ""
        else:
            validation_str = "Pass" if rec.key_valid else "Fail"

        row_values = [
            rec.project_id,
            rec.sa_email,
            rec.old_key_id,
            expiry_str,
            days_str,
            rec.status,
            rec.new_key_id,
            rec.storage_location,
            rot_ts_str,
            rec.error_message,
            validation_str,
        ]

        row_fill = _STATUS_FILLS.get(rec.status)
        for col_idx, value in enumerate(row_values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _BODY_FONT
            cell.alignment = Alignment(vertical="center", wrap_text=False)
            if col_idx == _KEY_VALIDATION_COL:
                if rec.key_valid is not None:
                    cell.fill = _VALIDATION_FILLS[rec.key_valid]
            elif row_fill:
                cell.fill = row_fill

    # Auto-filter on header row
    ws.auto_filter.ref = ws.dimensions

    wb.save(output_path)
    return output_path
