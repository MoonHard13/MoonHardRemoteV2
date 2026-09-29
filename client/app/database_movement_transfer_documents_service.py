from __future__ import annotations

from typing import Any

from app.database_movement_transfer_service import MovementTransferDatabaseService


class MovementTransferDocumentsService(MovementTransferDatabaseService):
    """Extends movement transfer with document-list search by date or number."""

    def _validate_parameters(
        self,
        action: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        if action != self.RECEIPT_SEARCH_ACTION:
            return super()._validate_parameters(action, parameters)

        note_no_raw = str(parameters.get("note_no") or "").strip()
        search_date_raw = str(parameters.get("search_date") or "").strip()

        if not note_no_raw and not search_date_raw:
            raise ValueError("Enter a document number or restaurant date.")

        note_no = (
            self._validate_int_string(note_no_raw, "note_no", allow_zero=True)
            if note_no_raw
            else None
        )
        search_date = (
            self._validate_yyyymmdd(search_date_raw, "search_date")
            if search_date_raw
            else ""
        )

        return {
            "note_no": note_no,
            "search_date": search_date,
            "station_oid": self._validate_optional_oid(parameters.get("station_oid")),
        }

    def _search_receipts(self, cursor, parameters: dict[str, Any]) -> dict[str, Any]:
        """Searches current first, then adds only history rows not already present."""

        current_rows = self._receipt_rows(cursor, "current", parameters)
        history_rows = self._receipt_rows(cursor, "history", parameters)

        rows: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for row in [*current_rows, *history_rows]:
            key = (
                row.get("pos_hdr"),
                row.get("note_no"),
                row.get("note_code"),
                row.get("init_date"),
                row.get("station_oid"),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

        rows.sort(
            key=lambda item: (
                str(item.get("init_date") or ""),
                int(item.get("note_no") or 0),
                int(item.get("note_code") or 0),
                int(item.get("pos_hdr") or 0),
            ),
            reverse=True,
        )

        return {
            "message": f"Found {len(rows)} document(s).",
            "source": "mixed" if current_rows and history_rows else (
                "current" if current_rows else ("history" if history_rows else None)
            ),
            "receipts": rows,
        }

    def _receipt_rows(
        self,
        cursor,
        source: str,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        trans, pos, _payway, _transfers = self._tables(source)
        where: list[str] = []
        values: list[Any] = []

        if parameters["note_no"] is not None:
            where.append("s.SalesTransNoteNo = ?")
            values.append(parameters["note_no"])
        if parameters["search_date"]:
            where.append("s.SalesTransInitDate = ?")
            values.append(parameters["search_date"])
        if parameters["station_oid"] is not None:
            where.append("s.SalesStationOID = ?")
            values.append(parameters["station_oid"])

        if not where:
            raise ValueError("Document search requires a number or restaurant date.")

        sql = f"""
            SELECT TOP (1000)
                p.SalesTransPosHdr,
                s.SalesTransNoteNo,
                s.SalesTransNoteCode,
                s.SalesTransInitDate,
                s.SalesTransRealDate,
                s.SalesStationOID,
                st.SalesStationNo,
                st.SalesStationDescr,
                COUNT_BIG(DISTINCT s.SalesTransOID) AS MovementRows,
                MAX(s.SalesTransFinPayVal) AS DocumentValue
            FROM dbo.{trans} AS s
            INNER JOIN dbo.{pos} AS p ON p.SalesTransOID = s.SalesTransOID
            LEFT JOIN dbo.TblSnSalesStation AS st ON st.SalesStationOID = s.SalesStationOID
            WHERE {' AND '.join(where)}
            GROUP BY
                p.SalesTransPosHdr,
                s.SalesTransNoteNo,
                s.SalesTransNoteCode,
                s.SalesTransInitDate,
                s.SalesTransRealDate,
                s.SalesStationOID,
                st.SalesStationNo,
                st.SalesStationDescr
            ORDER BY s.SalesTransInitDate DESC, s.SalesTransNoteNo DESC,
                     s.SalesTransNoteCode, p.SalesTransPosHdr DESC
        """
        cursor.execute(sql, *values)

        result: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            result.append(
                {
                    "source": source,
                    "pos_hdr": int(row[0]),
                    "note_no": int(row[1]) if row[1] is not None else 0,
                    "note_code": int(row[2]) if row[2] is not None else 0,
                    "init_date": self._date_value(row[3]),
                    "real_date": self._date_value(row[4]),
                    "station_oid": int(row[5]) if row[5] is not None else 0,
                    "station_no": int(row[6]) if row[6] is not None else None,
                    "station_descr": str(row[7] or "").strip(),
                    "movement_rows": int(row[8]) if row[8] is not None else 0,
                    "value": float(row[9]) if row[9] is not None else None,
                }
            )
        return result
