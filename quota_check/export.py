from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from xml.sax.saxutils import escape

from .config import AppConfig
from .report import ReportResult


REPORT_BASE = "自检额度报告"


def _percent_text(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{round(float(value), 2):g}%"


def _date_text(value: Optional[int], source: Optional[str]) -> str:
    if value is None:
        return ""
    try:
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, TypeError):
        return source or ""


def build_rows(result: ReportResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snapshot in result.accounts:
        alias = next(
            (c.alias for c in result.candidates if c.code_home == snapshot.code_home),
            None,
        )
        related = "、".join(
            f"{item.get('alias') or item.get('label')}"
            for item in snapshot.related
        )
        rows.append(
            {
                "账号邮箱": snapshot.email or "",
                "套餐": snapshot.plan_type or "",
                "快捷方式": alias or snapshot.label,
                "关联目录": related,
                "主额度剩余": _percent_text(
                    snapshot.weekly.remaining_percent if snapshot.weekly else None
                ),
                "主额度重置": _date_text(
                    snapshot.weekly.resets_at_unix if snapshot.weekly else None,
                    snapshot.weekly.raw.get("resets_at") if snapshot.weekly else None,
                ),
                "5小时剩余": _percent_text(
                    snapshot.five_hour.remaining_percent if snapshot.five_hour else None
                ),
                "5小时重置": _date_text(
                    snapshot.five_hour.resets_at_unix if snapshot.five_hour else None,
                    snapshot.five_hour.raw.get("resets_at") if snapshot.five_hour else None,
                ),
                "更新时间": (
                    snapshot.snapshot_at_utc.astimezone().strftime("%Y-%m-%d %H:%M")
                    if snapshot.snapshot_at_utc
                    else ""
                ),
                "状态": snapshot.status,
                "CODEX_HOME": str(snapshot.code_home),
                "错误": snapshot.error or "",
            }
        )
    return rows


def export_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def export_json_bytes(result: ReportResult) -> bytes:
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "codex_available": result.codex_available,
        "accounts": [snapshot.to_dict() for snapshot in result.accounts],
        "refresh_results": [item.to_dict() for item in result.refresh_results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _style_index(column: str, value: str) -> int:
    if column not in ("主额度剩余", "5小时剩余") or not value:
        return 0
    try:
        percent = float(value.rstrip("%"))
    except ValueError:
        return 0
    if percent <= 10:
        return 2
    if percent <= 30:
        return 3
    return 4


def export_xlsx_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        rows = [{}]
    columns = list(rows[0].keys())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            _content_types(),
        )
        archive.writestr("_rels/.rels", _root_rels())
        archive.writestr("xl/workbook.xml", _workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels())
        archive.writestr("xl/styles.xml", _styles())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet(columns, rows))
    return buffer.getvalue()


def write_report_files(
    result: ReportResult,
    config: AppConfig,
    formats: Iterable[str] = ("csv", "xlsx", "json"),
) -> list[Path]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_rows(result)
    written: list[Path] = []

    for fmt in formats:
        target = output_dir / f"{REPORT_BASE}.{fmt}"
        if fmt == "csv":
            target.write_bytes(export_csv_bytes(rows))
        elif fmt == "json":
            target.write_bytes(export_json_bytes(result))
        elif fmt == "xlsx":
            target.write_bytes(export_xlsx_bytes(rows))
        else:
            continue
        written.append(target)
    return written


def _sheet(columns: list[str], rows: list[dict[str, Any]]) -> str:
    column_refs = [chr(ord("A") + index) for index in range(len(columns))]
    header = "".join(
        f'<c r="{ref}1" t="inlineStr" s="1"><is><t>{escape(str(value))}</t></is></c>'
        for ref, value in zip(column_refs, columns)
    )
    body: list[str] = []
    for row_index, row in enumerate(rows, start=2):
        cells: list[str] = []
        for col_index, column in enumerate(columns):
            ref = f"{column_refs[col_index]}{row_index}"
            value = row.get(column, "")
            style = _style_index(column, str(value))
            cells.append(
                f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{escape(str(value))}</t></is></c>'
            )
        body.append(f"<row r=\"{row_index}\">{''.join(cells)}</row>")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<cols>{''.join(f'<col min=\"{i+1}\" max=\"{i+1}\" width=\"{22 if i < 7 else 40}\" customWidth=\"1\"/>' for i in range(len(columns)))}</cols>"
        f"<sheetData><row r=\"1\">{header}</row>{''.join(body)}</sheetData>"
        "</worksheet>"
    )


def _styles() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="4">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font>'
        '<font><color rgb="FF9C0006"/><sz val="11"/><name val="Calibri"/></font>'
        '<font><color rgb="FF9C6500"/><sz val="11"/><name val="Calibri"/></font>'
        "</fonts>"
        '<fills count="5">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFC00000"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFC000"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF00B050"/><bgColor indexed="64"/></patternFill></fill>'
        "</fills>"
        '<borders count="1"><border><left/><right/><top/><bottom/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="5">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        '<xf numFmtId="0" fontId="3" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        '<xf numFmtId="0" fontId="0" fillId="5" borderId="0" xfId="0" applyFill="1"/>'
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def _content_types() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )


def _root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="自检额度报告" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )


def _workbook_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
