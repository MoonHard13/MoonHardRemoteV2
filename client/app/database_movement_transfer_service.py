from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.database_duplicate_mark_service import DuplicateMarkDatabaseMaintenanceService


class MovementTransferDatabaseService(DuplicateMarkDatabaseMaintenanceService):
    """Adds controlled movement-transfer actions to the existing database service."""

    STATIONS_ACTION = "movement_stations"
    RECEIPT_SEARCH_ACTION = "movement_receipt_search"
    DATE_TRANSFER_ACTION = "movement_transfer_date"
    RECEIPT_TRANSFER_ACTION = "movement_transfer_receipt"

    ACTIONS = frozenset(
        set(DuplicateMarkDatabaseMaintenanceService.ACTIONS)
        | {
            STATIONS_ACTION,
            RECEIPT_SEARCH_ACTION,
            DATE_TRANSFER_ACTION,
            RECEIPT_TRANSFER_ACTION,
        }
    )

    def _validate_parameters(
        self,
        action: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        if action == self.STATIONS_ACTION:
            return {}

        if action == self.RECEIPT_SEARCH_ACTION:
            note_no = self._validate_int_string(parameters.get("note_no"), "note_no", allow_zero=True)
            search_date_raw = str(parameters.get("search_date") or "").strip()
            search_date = (
                self._validate_yyyymmdd(search_date_raw, "search_date")
                if search_date_raw
                else ""
            )
            station_oid = self._validate_optional_oid(parameters.get("station_oid"))
            return {
                "note_no": note_no,
                "search_date": search_date,
                "station_oid": station_oid,
            }

        if action == self.DATE_TRANSFER_ACTION:
            mode = str(parameters.get("mode") or "").strip().lower()
            if mode not in {"rest", "real"}:
                raise ValueError("Invalid movement transfer mode.")

            old_date = self._validate_yyyymmdd(parameters.get("old_date"), "old_date")
            new_date = self._validate_yyyymmdd(parameters.get("new_date"), "new_date")
            real_date_raw = str(parameters.get("real_date") or "").strip()
            if mode == "real":
                real_date = self._validate_yyyymmdd(real_date_raw, "real_date")
            else:
                if real_date_raw:
                    raise ValueError("real_date must be empty for restaurant-date mode.")
                real_date = ""

            if old_date == new_date:
                raise ValueError("old_date and new_date must be different.")

            return {
                "mode": mode,
                "old_date": old_date,
                "real_date": real_date,
                "new_date": new_date,
                "station_oid": self._validate_optional_oid(parameters.get("station_oid")),
            }

        if action == self.RECEIPT_TRANSFER_ACTION:
            source = str(parameters.get("source") or "").strip().lower()
            if source not in {"current", "history"}:
                raise ValueError("Invalid receipt source.")

            old_date = self._validate_yyyymmdd(parameters.get("old_date"), "old_date")
            new_date = self._validate_yyyymmdd(parameters.get("new_date"), "new_date")
            if old_date == new_date:
                raise ValueError("old_date and new_date must be different.")

            return {
                "source": source,
                "pos_hdr": self._validate_int_string(parameters.get("pos_hdr"), "pos_hdr"),
                "note_no": self._validate_int_string(parameters.get("note_no"), "note_no", allow_zero=True),
                "note_code": self._validate_int_string(parameters.get("note_code"), "note_code", allow_zero=True),
                "old_date": old_date,
                "new_date": new_date,
                "station_oid": self._validate_int_string(parameters.get("station_oid"), "station_oid"),
            }

        return super()._validate_parameters(action, parameters)

    def _execute_action(
        self,
        cursor,
        action: str,
        parameters: dict[str, Any],
        database_name: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if action == self.STATIONS_ACTION:
            return self._load_stations(cursor)
        if action == self.RECEIPT_SEARCH_ACTION:
            return self._search_receipts(cursor, parameters)
        if action == self.DATE_TRANSFER_ACTION:
            return self._transfer_by_date(cursor, parameters, progress_callback)
        if action == self.RECEIPT_TRANSFER_ACTION:
            return self._transfer_receipt(cursor, parameters, progress_callback)
        return super()._execute_action(
            cursor=cursor,
            action=action,
            parameters=parameters,
            database_name=database_name,
            progress_callback=progress_callback,
        )

    def _load_stations(self, cursor) -> dict[str, Any]:
        cursor.execute(
            """
            SELECT SalesStationOID, SalesStationNo, SalesStationDescr, SalesStationRestDate
            FROM dbo.TblSnSalesStation
            ORDER BY SalesStationDescr, SalesStationNo, SalesStationOID
            """
        )
        stations = []
        for row in cursor.fetchall():
            stations.append(
                {
                    "oid": int(row[0]),
                    "number": int(row[1]) if row[1] is not None else None,
                    "description": str(row[2] or "").strip(),
                    "rest_date": self._date_value(row[3]),
                }
            )
        return {
            "message": f"Loaded {len(stations)} SalesStation(s).",
            "stations": stations,
        }

    def _search_receipts(self, cursor, parameters: dict[str, Any]) -> dict[str, Any]:
        for source in ("current", "history"):
            rows = self._receipt_rows(cursor, source, parameters)
            if rows:
                return {
                    "message": f"Found {len(rows)} receipt candidate(s) in {source} tables.",
                    "source": source,
                    "receipts": rows,
                }
        return {
            "message": "No matching receipt was found in current or history tables.",
            "source": None,
            "receipts": [],
        }

    def _receipt_rows(
        self,
        cursor,
        source: str,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        trans, pos, _payway, _transfers = self._tables(source)
        where = ["s.SalesTransNoteNo = ?"]
        values: list[Any] = [parameters["note_no"]]

        if parameters["search_date"]:
            where.append("s.SalesTransInitDate = ?")
            values.append(parameters["search_date"])
        if parameters["station_oid"] is not None:
            where.append("s.SalesStationOID = ?")
            values.append(parameters["station_oid"])

        sql = f"""
            SELECT TOP (100)
                p.SalesTransPosHdr,
                s.SalesTransNoteNo,
                s.SalesTransNoteCode,
                s.SalesTransInitDate,
                s.SalesTransRealDate,
                s.SalesStationOID,
                st.SalesStationNo,
                st.SalesStationDescr,
                COUNT_BIG(DISTINCT s.SalesTransOID) AS MovementRows,
                MAX(s.SalesTransFinPayVal) AS ReceiptValue
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
            ORDER BY s.SalesTransInitDate DESC, s.SalesTransNoteCode, p.SalesTransPosHdr DESC
        """
        cursor.execute(sql, *values)
        result = []
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

    def _transfer_by_date(
        self,
        cursor,
        parameters: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        source = self._resolve_date_source(cursor, parameters)
        if not source:
            return {
                "success": False,
                "error": "No matching movements were found in current or history tables.",
                "message": "No matching movements were found.",
            }

        self._emit_transfer_progress(progress_callback, 10, "Preparing movement transfer...")
        trans, pos, payway, transfers = self._tables(source)
        predicate, predicate_values = self._date_predicate("s", parameters)
        transfer_predicate, transfer_values = self._transfer_date_predicate(parameters)

        try:
            cursor.execute("SET XACT_ABORT ON; BEGIN TRANSACTION;")

            self._emit_transfer_progress(progress_callback, 30, "Updating payments...")
            cursor.execute(
                f"""
                UPDATE pw
                SET pw.SalesPWInitDate = ?
                FROM dbo.{payway} AS pw
                WHERE pw.SalesPWPosHdr IN (
                    SELECT DISTINCT p.SalesTransPosHdr
                    FROM dbo.{pos} AS p
                    INNER JOIN dbo.{trans} AS s ON p.SalesTransOID = s.SalesTransOID
                    WHERE {predicate}
                )
                """,
                parameters["new_date"],
                *predicate_values,
            )
            payment_rows = self._safe_rowcount(cursor)

            self._emit_transfer_progress(progress_callback, 55, "Updating sales movements...")
            cursor.execute(
                f"""
                UPDATE s
                SET s.SalesTransInitDate = ?
                FROM dbo.{trans} AS s
                WHERE {predicate}
                """,
                parameters["new_date"],
                *predicate_values,
            )
            movement_rows = self._safe_rowcount(cursor)

            self._emit_transfer_progress(progress_callback, 80, "Updating transfers...")
            cursor.execute(
                f"""
                UPDATE tr
                SET tr.SalesTransfersInitDate = ?
                FROM dbo.{transfers} AS tr
                WHERE {transfer_predicate}
                """,
                parameters["new_date"],
                *transfer_values,
            )
            transfer_rows = self._safe_rowcount(cursor)

            cursor.execute("COMMIT TRANSACTION;")
        except Exception:
            try:
                cursor.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;")
            except Exception:
                pass
            raise

        self._emit_transfer_progress(progress_callback, 100, "Movement transfer completed.")
        return {
            "message": "Movement transfer completed successfully.",
            "source": source,
            "mode": parameters["mode"],
            "old_date": parameters["old_date"],
            "real_date": parameters["real_date"],
            "new_date": parameters["new_date"],
            "station_oid": parameters["station_oid"],
            "payment_rows": payment_rows,
            "movement_rows": movement_rows,
            "transfer_rows": transfer_rows,
        }

    def _transfer_receipt(
        self,
        cursor,
        parameters: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        trans, pos, payway, transfers = self._tables(parameters["source"])
        verify_sql = f"""
            SELECT COUNT_BIG(DISTINCT s.SalesTransOID)
            FROM dbo.{trans} AS s
            INNER JOIN dbo.{pos} AS p ON p.SalesTransOID = s.SalesTransOID
            WHERE p.SalesTransPosHdr = ?
              AND s.SalesTransNoteNo = ?
              AND s.SalesTransNoteCode = ?
              AND s.SalesTransInitDate = ?
              AND s.SalesStationOID = ?
        """
        cursor.execute(
            verify_sql,
            parameters["pos_hdr"],
            parameters["note_no"],
            parameters["note_code"],
            parameters["old_date"],
            parameters["station_oid"],
        )
        row = cursor.fetchone()
        matching_rows = int(row[0]) if row and row[0] is not None else 0
        if matching_rows < 1:
            return {
                "success": False,
                "error": "The selected receipt no longer matches the database state.",
                "message": "Receipt verification failed.",
            }

        self._emit_transfer_progress(progress_callback, 10, "Verified selected receipt.")
        try:
            cursor.execute("SET XACT_ABORT ON; BEGIN TRANSACTION;")

            self._emit_transfer_progress(progress_callback, 35, "Updating receipt payments...")
            cursor.execute(
                f"""
                UPDATE dbo.{payway}
                SET SalesPWInitDate = ?
                WHERE SalesPWPosHdr = ?
                """,
                parameters["new_date"],
                parameters["pos_hdr"],
            )
            payment_rows = self._safe_rowcount(cursor)

            self._emit_transfer_progress(progress_callback, 60, "Updating receipt movements...")
            cursor.execute(
                f"""
                UPDATE s
                SET s.SalesTransInitDate = ?
                FROM dbo.{trans} AS s
                INNER JOIN dbo.{pos} AS p ON p.SalesTransOID = s.SalesTransOID
                WHERE p.SalesTransPosHdr = ?
                  AND s.SalesTransNoteNo = ?
                  AND s.SalesTransNoteCode = ?
                  AND s.SalesTransInitDate = ?
                  AND s.SalesStationOID = ?
                """,
                parameters["new_date"],
                parameters["pos_hdr"],
                parameters["note_no"],
                parameters["note_code"],
                parameters["old_date"],
                parameters["station_oid"],
            )
            movement_rows = self._safe_rowcount(cursor)

            self._emit_transfer_progress(progress_callback, 82, "Updating receipt transfers...")
            cursor.execute(
                f"""
                UPDATE dbo.{transfers}
                SET SalesTransfersInitDate = ?
                WHERE SalesTransfersInitDate = ?
                  AND SalesTransfersNoteCode = ?
                  AND SalesTransfersNoteNo = ?
                  AND SalesTransfersSStOID = ?
                """,
                parameters["new_date"],
                parameters["old_date"],
                parameters["note_code"],
                parameters["note_no"],
                parameters["station_oid"],
            )
            transfer_rows = self._safe_rowcount(cursor)

            cursor.execute("COMMIT TRANSACTION;")
        except Exception:
            try:
                cursor.execute("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;")
            except Exception:
                pass
            raise

        self._emit_transfer_progress(progress_callback, 100, "Receipt transfer completed.")
        return {
            "message": "Receipt transfer completed successfully.",
            "source": parameters["source"],
            "mode": "receipt",
            "note_no": parameters["note_no"],
            "note_code": parameters["note_code"],
            "pos_hdr": parameters["pos_hdr"],
            "old_date": parameters["old_date"],
            "new_date": parameters["new_date"],
            "station_oid": parameters["station_oid"],
            "payment_rows": payment_rows,
            "movement_rows": movement_rows,
            "transfer_rows": transfer_rows,
        }

    def _resolve_date_source(self, cursor, parameters: dict[str, Any]) -> str | None:
        for source in ("current", "history"):
            trans, _pos, _payway, _transfers = self._tables(source)
            predicate, values = self._date_predicate("s", parameters)
            cursor.execute(
                f"SELECT COUNT_BIG(*) FROM dbo.{trans} AS s WHERE {predicate}",
                *values,
            )
            row = cursor.fetchone()
            if row and int(row[0] or 0) > 0:
                return source
        return None

    @staticmethod
    def _tables(source: str) -> tuple[str, str, str, str]:
        if source == "current":
            return (
                "TblSnSalesTrans",
                "TblSnSalesTransPos",
                "TblSnSalesPayWay",
                "TblSnSalesTransfers",
            )
        if source == "history":
            return (
                "TblSnSalesTransHist",
                "TblSnSalesTransPosHist",
                "TblSnSalesPayWayHist",
                "TblSnSalesTransfersHist",
            )
        raise ValueError("Unsupported movement source.")

    @staticmethod
    def _date_predicate(alias: str, parameters: dict[str, Any]) -> tuple[str, list[Any]]:
        parts = [f"{alias}.SalesTransInitDate = ?"]
        values: list[Any] = [parameters["old_date"]]
        if parameters["mode"] == "real":
            parts.append(f"{alias}.SalesTransRealDate = ?")
            values.append(parameters["real_date"])
        if parameters["station_oid"] is not None:
            parts.append(f"{alias}.SalesStationOID = ?")
            values.append(parameters["station_oid"])
        return " AND ".join(parts), values

    @staticmethod
    def _transfer_date_predicate(parameters: dict[str, Any]) -> tuple[str, list[Any]]:
        parts = ["tr.SalesTransfersInitDate = ?"]
        values: list[Any] = [parameters["old_date"]]
        if parameters["mode"] == "real":
            parts.append("tr.SalesTransfersRealDate = ?")
            values.append(parameters["real_date"])
        if parameters["station_oid"] is not None:
            parts.append("tr.SalesTransfersSStOID = ?")
            values.append(parameters["station_oid"])
        return " AND ".join(parts), values

    @staticmethod
    def _validate_int_string(value: Any, field_name: str, allow_zero: bool = False) -> int:
        clean = str(value or "").strip()
        if not clean.isdigit():
            raise ValueError(f"Invalid {field_name}.")
        parsed = int(clean)
        minimum = 0 if allow_zero else 1
        if not minimum <= parsed <= 2147483647:
            raise ValueError(f"Invalid {field_name}.")
        return parsed

    def _validate_optional_oid(self, value: Any) -> int | None:
        clean = str(value or "").strip()
        if not clean:
            return None
        return self._validate_int_string(clean, "station_oid")

    @staticmethod
    def _safe_rowcount(cursor) -> int | None:
        value = getattr(cursor, "rowcount", -1)
        return int(value) if type(value) is int and value >= 0 else None

    @staticmethod
    def _date_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y%m%d")
        clean = str(value).strip()
        return clean[:10].replace("-", "") if clean else ""

    @staticmethod
    def _emit_transfer_progress(
        callback: Callable[[dict[str, Any]], None] | None,
        percent: int,
        message: str,
    ) -> None:
        if callback:
            callback(
                {
                    "stage": "movement_transfer",
                    "percent": percent,
                    "message": message,
                }
            )
