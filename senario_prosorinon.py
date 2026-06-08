import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pyodbc

try:
    import customtkinter as ctk
    from tkinter import filedialog
except ImportError:
    ctk = None
    filedialog = None


# ==========================================================
# Resource helper για PyInstaller
# ==========================================================

def resource_path(relative_path: str) -> str:
    """Επιστρέφει σωστό path είτε τρέχουμε από Python είτε από PyInstaller exe."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def set_tk_window_icon(window, icon_filename: str = "moonhard.ico") -> None:
    """Ορίζει το εικονίδιο παραθύρου σε Python και PyInstaller."""
    try:
        icon_path = resource_path(icon_filename)

        if os.path.exists(icon_path):
            window.iconbitmap(icon_path)
            AppLogger.info(f"Ορίστηκε window icon: {icon_path}")
        else:
            AppLogger.error(f"Δεν βρέθηκε το window icon: {icon_path}")

    except Exception:
        AppLogger.exception("Σφάλμα κατά τον ορισμό window icon.")


# ==========================================================
# Logging
# ==========================================================

class AppLogger:
    """Κεντρική κλάση διαχείρισης logging."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        log_file = os.path.join(
            self.log_dir,
            f"elegxos_senariou_{datetime.now().strftime('%Y%m%d')}.log"
        )

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            encoding="utf-8",
            force=True
        )

        logging.info("Η εφαρμογή ξεκίνησε.")

    @staticmethod
    def info(message: str) -> None:
        logging.info(message)

    @staticmethod
    def error(message: str) -> None:
        logging.error(message)

    @staticmethod
    def exception(message: str) -> None:
        logging.exception(message)


# ==========================================================
# Models
# ==========================================================

@dataclass
class CheckResult:
    """Μοντέλο αποτελέσματος ελέγχου."""

    success: bool
    title: str
    message: str


@dataclass
class SelfDeliveryTable:
    """Μοντέλο τραπεζιού με TableSelfDelivery = 1."""

    table_oid: int
    table_code: str
    whouse_oid: Optional[int]


@dataclass
class NoteTypeInfo:
    """Μοντέλο τύπου παραστατικού."""

    note_type_oid: int
    note_type_abbr: str
    note_type_descr: str


@dataclass
class GetTablesContext:
    """Παράμετροι εκτέλεσης του GetTables."""

    sales_station_oid: int
    enabled: int
    whouse_oids: List[int]
    whouse_param: str
    source: str


# ==========================================================
# UDL Reader
# ==========================================================

class UdlReader:
    """Κλάση ανάγνωσης και ανάλυσης αρχείου UDL."""

    def __init__(self, udl_path: str):
        self.udl_path = udl_path

    def read_file(self) -> str:
        """Διαβάζει το UDL αρχείο με υποστήριξη UTF-16 και ANSI."""
        if not os.path.exists(self.udl_path):
            raise FileNotFoundError(f"Δεν βρέθηκε το UDL αρχείο: {self.udl_path}")

        encodings = ["utf-16", "utf-8-sig", "cp1253", "latin-1"]

        for encoding in encodings:
            try:
                with open(self.udl_path, "r", encoding=encoding) as file:
                    content = file.read()

                if "Provider=" in content or "Data Source=" in content:
                    AppLogger.info(f"Το UDL διαβάστηκε με encoding: {encoding}")
                    return content
            except UnicodeError:
                continue

        raise ValueError("Δεν ήταν δυνατή η ανάγνωση του UDL αρχείου.")

    def parse(self) -> Dict[str, str]:
        """Μετατρέπει το UDL connection string σε dictionary."""
        content = self.read_file()

        lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("[")
        ]

        connection_line = ""

        for line in lines:
            if "Provider=" in line or "Data Source=" in line:
                connection_line = line
                break

        if not connection_line:
            raise ValueError("Δεν βρέθηκε connection string μέσα στο UDL αρχείο.")

        data: Dict[str, str] = {}

        for part in connection_line.split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                data[key.strip().lower()] = value.strip()

        AppLogger.info(f"Το UDL αναλύθηκε επιτυχώς: {self.udl_path}")
        return data

    def to_sql_config(self) -> Dict[str, object]:
        """Μετατρέπει τα στοιχεία του UDL σε ρυθμίσεις σύνδεσης SQL Server."""
        data = self.parse()

        server = data.get("data source") or data.get("server") or data.get("address") or ""
        database = data.get("initial catalog") or data.get("database") or ""
        username = data.get("user id") or data.get("uid") or ""
        password = data.get("password") or data.get("pwd") or ""

        integrated_security = (
            data.get("integrated security", "")
            or data.get("trusted_connection", "")
        ).lower()

        trusted_connection = integrated_security in ["sspi", "true", "yes"]

        if not username and not password:
            trusted_connection = True

        if not server:
            raise ValueError("Δεν βρέθηκε Server / Data Source μέσα στο UDL.")

        if not database:
            raise ValueError("Δεν βρέθηκε Database / Initial Catalog μέσα στο UDL.")

        return {
            "server": server,
            "database": database,
            "username": username,
            "password": password,
            "trusted_connection": trusted_connection
        }


# ==========================================================
# ODBC Driver helper
# ==========================================================

class OdbcDriverHelper:
    """Κλάση επιλογής διαθέσιμου ODBC Driver."""

    @staticmethod
    def get_best_driver() -> str:
        """Επιλέγει τον καλύτερο διαθέσιμο SQL Server ODBC driver."""
        drivers = pyodbc.drivers()

        preferred_drivers = [
            "ODBC Driver 22 for SQL Server",
            "ODBC Driver 20 for SQL Server",
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server"
        ]

        for driver in preferred_drivers:
            if driver in drivers:
                AppLogger.info(f"Επιλέχθηκε ODBC Driver: {driver}")
                return driver

        raise RuntimeError(
            "Δεν βρέθηκε εγκατεστημένος ODBC Driver για SQL Server. "
            "Εγκατέστησε ODBC Driver 17 ή 18 for SQL Server."
        )


# ==========================================================
# Database connection
# ==========================================================

class SqlServerConnection:
    """Κλάση σύνδεσης με SQL Server."""

    def __init__(
        self,
        server: str,
        database: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        driver: Optional[str] = None,
        trusted_connection: bool = True
    ):
        self.server = server
        self.database = database
        self.username = username or ""
        self.password = password or ""
        self.driver = driver or OdbcDriverHelper.get_best_driver()
        self.trusted_connection = trusted_connection
        self.connection = None

    def build_connection_string(self) -> str:
        """Δημιουργεί ODBC connection string για SQL Server."""
        if self.trusted_connection:
            return (
                f"DRIVER={{{self.driver}}};"
                f"SERVER={self.server};"
                f"DATABASE={self.database};"
                f"Trusted_Connection=yes;"
                f"TrustServerCertificate=yes;"
            )

        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            f"TrustServerCertificate=yes;"
        )

    def connect(self):
        """Ανοίγει σύνδεση με SQL Server."""
        if not self.server:
            raise ValueError("Δεν έχει δηλωθεί SQL Server.")

        if not self.database:
            raise ValueError("Δεν έχει δηλωθεί βάση δεδομένων.")

        try:
            connection_string = self.build_connection_string()
            self.connection = pyodbc.connect(connection_string, timeout=10)

            AppLogger.info(
                f"Επιτυχής σύνδεση στη βάση. Server: {self.server}, Database: {self.database}"
            )

            return self.connection
        except Exception as ex:
            AppLogger.exception("Αποτυχία σύνδεσης στη βάση δεδομένων.")
            raise ex

    def close(self) -> None:
        """Κλείνει τη σύνδεση."""
        if self.connection:
            try:
                self.connection.close()
                AppLogger.info("Η σύνδεση με τη βάση έκλεισε.")
            except Exception:
                AppLogger.exception("Σφάλμα κατά το κλείσιμο της σύνδεσης.")


# ==========================================================
# SQL checks
# ==========================================================

class SqlChecks:
    """Κλάση που περιέχει όλους τους ελέγχους της βάσης."""

    def __init__(self, connection):
        self.connection = connection
        self.self_delivery_tables: List[SelfDeliveryTable] = []
        self.cached_gettables_context: Optional[GetTablesContext] = None

    # ----------------------------------------------------------
    # Generic helpers
    # ----------------------------------------------------------

    def get_current_database_name(self) -> str:
        """Επιστρέφει το όνομα της ενεργής βάσης δεδομένων."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT DB_NAME()")
        row = cursor.fetchone()

        if row is None or not row[0]:
            raise ValueError("Δεν ήταν δυνατή η ανάγνωση του ονόματος της βάσης.")

        return str(row[0])

    def bracket_sql_name(self, name: str) -> str:
        """Κάνει ασφαλές ένα SQL Server object name με brackets."""
        clean_name = str(name).replace("]", "]]" )
        return f"[{clean_name}]"

    def table_exists(self, table_name: str) -> bool:
        """Ελέγχει αν υπάρχει φυσικός πίνακας στη βάση."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = ?
            """,
            table_name
        )
        return cursor.fetchone() is not None

    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Ελέγχει αν υπάρχει πεδίο σε πίνακα."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
              AND COLUMN_NAME = ?
            """,
            table_name,
            column_name
        )
        return cursor.fetchone() is not None

    def extract_int_from_sql_value(self, value: Any) -> Optional[int]:
        """Εξάγει ακέραιο από τιμές όπως 2, (2), '2', '(4)', ((4))."""
        if value is None:
            return None

        text = str(value).strip()

        if not text:
            return None

        for _ in range(10):
            changed = False

            if text.startswith("(") and text.endswith(")") and len(text) >= 2:
                text = text[1:-1].strip()
                changed = True

            if text.startswith("'") and text.endswith("'") and len(text) >= 2:
                text = text[1:-1].strip()
                changed = True

            if not changed:
                break

        match = re.search(r"-?\d+", text)

        if not match:
            return None

        return int(match.group(0))

    def build_whouse_param_for_gettables(self, whouse_oids: Sequence[int]) -> str:
        """Δημιουργεί το @WHouseOID parameter για GetTables σε μορφή (4) ή (4,5)."""
        clean_oids = sorted({int(oid) for oid in whouse_oids if oid is not None})

        if not clean_oids:
            return "(4)"

        return "(" + ",".join(str(oid) for oid in clean_oids) + ")"

    def execute_scalar_int(self, query: str, params: Sequence[Any] = ()) -> Optional[int]:
        """Εκτελεί query και επιστρέφει τον πρώτο ακέραιο."""
        cursor = self.connection.cursor()
        cursor.execute(query, *params)
        row = cursor.fetchone()

        if row is None or row[0] is None:
            return None

        return int(row[0])

    # ----------------------------------------------------------
    # Shared business helpers
    # ----------------------------------------------------------

    def load_self_delivery_tables(self) -> List[SelfDeliveryTable]:
        """Φορτώνει όλα τα τραπέζια με TableSelfDelivery = 1."""
        query = """
        SELECT
            TableOID,
            TableCode,
            WHouseOID
        FROM TblSnTable WITH (NOLOCK)
        WHERE TableSelfDelivery = 1
        ORDER BY TableCode
        """

        cursor = self.connection.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        self.self_delivery_tables = []

        for row in rows:
            table_oid = int(row[0])
            table_code = str(row[1]).strip() if row[1] is not None else ""
            whouse_oid = int(row[2]) if row[2] is not None else None

            if table_code:
                self.self_delivery_tables.append(
                    SelfDeliveryTable(
                        table_oid=table_oid,
                        table_code=table_code,
                        whouse_oid=whouse_oid
                    )
                )

        AppLogger.info(
            f"Φορτώθηκαν {len(self.self_delivery_tables)} τραπέζια με TableSelfDelivery = 1."
        )
        return self.self_delivery_tables

    def ensure_self_delivery_tables(self) -> List[SelfDeliveryTable]:
        """Επιστρέφει τα self delivery tables, φορτώνοντάς τα αν χρειάζεται."""
        if not self.self_delivery_tables:
            self.load_self_delivery_tables()

        return self.self_delivery_tables

    def get_sales_station_oid_from_data(self) -> Optional[int]:
        """Βρίσκει SalesStationOID από πραγματική σύνδεση των self-delivery tables."""
        self_delivery_tables = self.ensure_self_delivery_tables()

        if not self_delivery_tables:
            return None

        table_oids = [table.table_oid for table in self_delivery_tables]
        placeholders = ",".join("?" for _ in table_oids)

        query = f"""
        SELECT TOP 1
            SalesStationOID
        FROM TblSnSalesStationTable WITH (NOLOCK)
        WHERE TableOID IN ({placeholders})
        ORDER BY SalesStationOID
        """

        cursor = self.connection.cursor()
        cursor.execute(query, *table_oids)
        row = cursor.fetchone()

        if row is None or row[0] is None:
            return None

        return int(row[0])

    def get_whouse_oids_from_self_delivery_tables(self) -> List[int]:
        """Επιστρέφει τα WHouseOID από τα self-delivery tables."""
        self_delivery_tables = self.ensure_self_delivery_tables()
        whouse_oids = sorted({
            int(table.whouse_oid)
            for table in self_delivery_tables
            if table.whouse_oid is not None
        })
        return whouse_oids

    def get_gettables_context_from_metadata(self) -> Optional[GetTablesContext]:
        """Προσπαθεί να διαβάσει παραμέτρους GetTables από metadata."""
        database_name = self.get_current_database_name()
        safe_database_name = self.bracket_sql_name(database_name)

        query = (
            f"EXEC {safe_database_name}..sp_procedure_params_rowset "
            "N'GetTables', 1, NULL, NULL"
        )

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)

            if not cursor.description:
                return None

            columns_original = [column[0] for column in cursor.description]
            columns = [column.lower() for column in columns_original]
            rows = cursor.fetchall()

            AppLogger.info("GetTables metadata columns: " + ", ".join(columns_original))

            if not rows:
                return None

            column_index = {name: index for index, name in enumerate(columns)}

            parameter_name_col = (
                column_index.get("parameter_name")
                or column_index.get("column_name")
                or column_index.get("name")
            )
            ordinal_col = (
                column_index.get("ordinal_position")
                or column_index.get("parameter_ordinal")
                or column_index.get("ordinal")
            )

            value_col = None
            for possible_col in [
                "column_def",
                "parameter_default",
                "default_value",
                "default",
                "parameter_value",
                "value"
            ]:
                if possible_col in column_index:
                    value_col = column_index[possible_col]
                    break

            if value_col is None:
                AppLogger.info("Δεν βρέθηκε default/value column στο metadata GetTables.")
                return None

            values_by_name: Dict[str, Any] = {}
            values_by_ordinal: Dict[int, Any] = {}

            for row in rows:
                parameter_name = ""

                if parameter_name_col is not None and row[parameter_name_col] is not None:
                    parameter_name = str(row[parameter_name_col]).strip().lower()

                ordinal = None

                if ordinal_col is not None and row[ordinal_col] is not None:
                    try:
                        ordinal = int(row[ordinal_col])
                    except Exception:
                        ordinal = None

                value = row[value_col]

                if parameter_name and parameter_name not in ["@return_value", "return_value"]:
                    values_by_name[parameter_name] = value

                if ordinal is not None:
                    values_by_ordinal[ordinal] = value

            sales_station_value = (
                values_by_name.get("@salesstationoid")
                or values_by_name.get("salesstationoid")
                or values_by_ordinal.get(1)
            )
            enabled_value = (
                values_by_name.get("@enabled")
                or values_by_name.get("enabled")
                or values_by_ordinal.get(2)
            )
            whouse_value = (
                values_by_name.get("@whouseoid")
                or values_by_name.get("whouseoid")
                or values_by_ordinal.get(3)
            )

            sales_station_oid = self.extract_int_from_sql_value(sales_station_value)
            enabled = self.extract_int_from_sql_value(enabled_value)
            whouse_oid = self.extract_int_from_sql_value(whouse_value)

            if sales_station_oid is None or enabled is None or whouse_oid is None:
                return None

            return GetTablesContext(
                sales_station_oid=sales_station_oid,
                enabled=enabled,
                whouse_oids=[whouse_oid],
                whouse_param=self.build_whouse_param_for_gettables([whouse_oid]),
                source="metadata"
            )
        except Exception:
            AppLogger.exception("Αποτυχία ανάγνωσης GetTables metadata.")
            return None

    def get_gettables_execution_context(self) -> GetTablesContext:
        """Επιστρέφει ασφαλείς παραμέτρους για EXEC GetTables."""
        if self.cached_gettables_context is not None:
            return self.cached_gettables_context

        metadata_context = self.get_gettables_context_from_metadata()

        if metadata_context is not None:
            self.cached_gettables_context = metadata_context
            return metadata_context

        sales_station_oid = self.get_sales_station_oid_from_data() or 2
        whouse_oids = self.get_whouse_oids_from_self_delivery_tables() or [4]

        context = GetTablesContext(
            sales_station_oid=sales_station_oid,
            enabled=0,
            whouse_oids=whouse_oids,
            whouse_param=self.build_whouse_param_for_gettables(whouse_oids),
            source="data" if sales_station_oid != 2 or whouse_oids != [4] else "fallback"
        )

        AppLogger.info(
            "GetTables context: "
            f"SalesStationOID={context.sales_station_oid}, "
            f"Enabled={context.enabled}, "
            f"WHouseOID={context.whouse_param}, "
            f"Source={context.source}"
        )

        self.cached_gettables_context = context
        return context

    def get_default_closure_note_type(self, require_unique: bool = True) -> NoteTypeInfo:
        """Βρίσκει τον τύπο παραστατικού με NoteTypeMyDATADefaultForClosure = 1."""
        query = """
        SELECT
            NoteTypeOID,
            NoteTypeAbbr,
            NoteTypeDescr
        FROM TblSnNoteType WITH (NOLOCK)
        WHERE NoteTypeMyDATADefaultForClosure = 1
        ORDER BY NoteTypeOID
        """

        cursor = self.connection.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            raise ValueError("Δεν βρέθηκε τύπος παραστατικού με NoteTypeMyDATADefaultForClosure = 1.")

        if require_unique and len(rows) > 1:
            details = []
            for row in rows:
                details.append(
                    f"- NoteTypeOID: {row[0]} | "
                    f"Abbr: {str(row[1]).strip() if row[1] is not None else ''} | "
                    f"Descr: {str(row[2]).strip() if row[2] is not None else ''}"
                )
            raise ValueError(
                "Βρέθηκαν περισσότεροι από ένας τύποι παραστατικού με "
                "NoteTypeMyDATADefaultForClosure = 1.\n" + "\n".join(details)
            )

        if len(rows) > 1:
            AppLogger.info(
                "Βρέθηκαν πολλοί default closure note types. "
                f"Χρησιμοποιείται ο πρώτος: NoteTypeOID={rows[0][0]}"
            )

        return NoteTypeInfo(
            note_type_oid=int(rows[0][0]),
            note_type_abbr=str(rows[0][1]).strip() if rows[0][1] is not None else "",
            note_type_descr=str(rows[0][2]).strip() if rows[0][2] is not None else ""
        )

    def get_closure_note_type_by_rules(self) -> NoteTypeInfo:
        """Βρίσκει τον closure note type με τους τελικούς κανόνες του σεναρίου."""
        query = """
        SELECT
            NoteTypeOID,
            NoteTypeAbbr,
            NoteTypeDescr
        FROM TblSnNoteType WITH (NOLOCK)
        WHERE NoteTypeGroupPos = 3
          AND NoteTypeCredits = 0
          AND NoteTypeCanc = 0
          AND NoteTypeMyDATADefaultForClosure = 1
        ORDER BY NoteTypeOID
        """

        cursor = self.connection.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            raise ValueError(
                "Δεν βρέθηκε τύπος παραστατικού με:\n"
                "NoteTypeGroupPos = 3\n"
                "NoteTypeCredits = 0\n"
                "NoteTypeCanc = 0\n"
                "NoteTypeMyDATADefaultForClosure = 1"
            )

        if len(rows) > 1:
            details = []
            for row in rows:
                details.append(
                    f"- NoteTypeOID: {row[0]} | "
                    f"Abbr: {str(row[1]).strip() if row[1] is not None else ''} | "
                    f"Descr: {str(row[2]).strip() if row[2] is not None else ''}"
                )
            raise ValueError(
                "Βρέθηκαν περισσότεροι από ένας τύποι παραστατικού closure.\n" +
                "\n".join(details)
            )

        return NoteTypeInfo(
            note_type_oid=int(rows[0][0]),
            note_type_abbr=str(rows[0][1]).strip() if rows[0][1] is not None else "",
            note_type_descr=str(rows[0][2]).strip() if rows[0][2] is not None else ""
        )

    def get_kitchen_note_type(self) -> NoteTypeInfo:
        """Βρίσκει τον πρώτο τύπο παραστατικού εντολής/κουζίνας."""
        query = """
        SELECT
            NoteTypeOID,
            NoteTypeAbbr,
            NoteTypeDescr
        FROM TblSnNoteType WITH (NOLOCK)
        WHERE NoteTypeGroupPos = 2
          AND NoteTypeIssue = 0
          AND NoteTypeCanc = 0
          AND NoteTypeCredits = 0
        ORDER BY NoteTypeOID
        """

        cursor = self.connection.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            raise ValueError(
                "Δεν βρέθηκε τύπος παραστατικού με:\n"
                "NoteTypeGroupPos = 2\n"
                "NoteTypeIssue = 0\n"
                "NoteTypeCanc = 0\n"
                "NoteTypeCredits = 0"
            )

        if len(rows) > 1:
            AppLogger.info(
                "Βρέθηκαν πολλοί kitchen/order note types. "
                f"Χρησιμοποιείται ο πρώτος: NoteTypeOID={rows[0][0]}"
            )

        return NoteTypeInfo(
            note_type_oid=int(rows[0][0]),
            note_type_abbr=str(rows[0][1]).strip() if rows[0][1] is not None else "",
            note_type_descr=str(rows[0][2]).strip() if rows[0][2] is not None else ""
        )

    def get_self_delivery_note_type(self) -> NoteTypeInfo:
        """Βρίσκει τον πρώτο τύπο παραστατικού με MyDATA_NoteTypeSubCategOID = 16."""
        query = """
        SELECT
            NoteTypeOID,
            NoteTypeAbbr,
            NoteTypeDescr
        FROM TblSnNoteType WITH (NOLOCK)
        WHERE MyDATA_NoteTypeSubCategOID = 16
        ORDER BY NoteTypeOID
        """

        cursor = self.connection.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            raise ValueError("Δεν βρέθηκε τύπος παραστατικού με MyDATA_NoteTypeSubCategOID = 16.")

        if len(rows) > 1:
            AppLogger.info(
                "Βρέθηκαν πολλοί note types με MyDATA_NoteTypeSubCategOID = 16. "
                f"Χρησιμοποιείται ο πρώτος: NoteTypeOID={rows[0][0]}"
            )

        return NoteTypeInfo(
            note_type_oid=int(rows[0][0]),
            note_type_abbr=str(rows[0][1]).strip() if rows[0][1] is not None else "",
            note_type_descr=str(rows[0][2]).strip() if rows[0][2] is not None else ""
        )

    # ----------------------------------------------------------
    # Checks
    # ----------------------------------------------------------

    def check_required_schema(self) -> CheckResult:
        """Ελέγχει ότι υπάρχουν οι βασικοί πίνακες και στήλες που χρειάζεται το εργαλείο."""
        required_columns = {
            "TblSnTable": ["TableOID", "TableCode", "WHouseOID", "TableSelfDelivery"],
            "TblSnSalesStation": ["SalesStationOID", "SalesStationNo", "SalesStationDescr", "SalesStationClosureNoteOID"],
            "TblSnSalesStationTable": ["SalesStationOID", "TableOID", "SalesStationTableOID"],
            "TblSnSStTblNotes": ["SStTblNotesOID", "SalesStationTableOID", "NoteTypeOID"],
            "TblSnNoteType": [
                "NoteTypeOID",
                "NoteTypeAbbr",
                "NoteTypeDescr",
                "NoteTypeGroupPos",
                "NoteTypeIssue",
                "NoteTypeCanc",
                "NoteTypeCredits",
                "NoteTypeMyDATADefaultForClosure",
                "MyDATA_NoteTypeSubCategOID",
                "MyDATA_NoteTypeSpecialCategOID"
            ],
            "TblSnNoteNext": ["NoteTypeOID", "NextNoteTypeOID"],
            "TblSnMyDATA_NoteTypeSubCateg": ["MyDATA_NoteTypeSubCategOID", "MyDATA_NoteTypeSubCategCode"]
        }

        try:
            missing = []

            for table_name, columns in required_columns.items():
                if not self.table_exists(table_name):
                    missing.append(f"Λείπει ο πίνακας: {table_name}")
                    continue

                for column_name in columns:
                    if not self.column_exists(table_name, column_name):
                        missing.append(f"Λείπει το πεδίο: {table_name}.{column_name}")

            if missing:
                return CheckResult(
                    success=False,
                    title="Τεχνικός έλεγχος δομής βάσης",
                    message="\n".join(missing)
                )

            return CheckResult(
                success=True,
                title="Τεχνικός έλεγχος δομής βάσης",
                message="Οι απαραίτητοι πίνακες και στήλες υπάρχουν στη βάση."
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα στον τεχνικό έλεγχο δομής βάσης.")
            return CheckResult(
                success=False,
                title="SQL Error",
                message=f"Προέκυψε σφάλμα στον τεχνικό έλεγχο δομής βάσης:\n{ex}"
            )

    def check_self_delivery_tables(self) -> CheckResult:
        """Ελέγχει αν υπάρχουν τραπέζια με TableSelfDelivery = 1."""
        try:
            tables = self.load_self_delivery_tables()

            if not tables:
                return CheckResult(
                    success=False,
                    title="Έλεγχος για τραπέζι Αυτοπαράδοσης",
                    message="Δεν βρέθηκε κανένα τραπέζι Αυτοπαράδοσης."
                )

            lines = [
                "Βρέθηκαν τραπέζια με Αυτοπαράδοσης:",
                ""
            ]

            for table in tables:
                lines.append(
                    f"- TableCode: {table.table_code} | "
                    f"TableOID: {table.table_oid} | "
                    f"WHouseOID: {table.whouse_oid}"
                )

            return CheckResult(
                success=True,
                title="Έλεγχος για τραπέζι Αυτοπαράδοσης",
                message="\n".join(lines)
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο για τραπέζι Αυτοπαράδοσης.")
            return CheckResult(
                success=False,
                title="SQL Error",
                message=f"Προέκυψε σφάλμα κατά τον έλεγχο για τραπέζι Αυτοπαράδοσης:\n{ex}"
            )

    def check_gettables_self_delivery_inform(self) -> CheckResult:
        """Ελέγχει αν τα self-delivery τραπέζια εμφανίζονται στο GetTables με inform = 1."""
        try:
            tables = self.ensure_self_delivery_tables()

            if not tables:
                return CheckResult(
                    success=False,
                    title="Έλεγχος ενεργοποίησης στο σημείο πώλησης του τραπεζιού Αυτοπαράδοσης",
                    message="Δεν υπάρχουν τραπέζια Αυτοπαράδοσης για να ελεγχθούν στο GetTables."
                )

            context = self.get_gettables_execution_context()

            exec_query = """
            EXEC GetTables
                @SalesStationOID = ?,
                @Enabled = ?,
                @WHouseOID = ?,
                @HallOID = DEFAULT
            """

            cursor = self.connection.cursor()
            cursor.execute(
                exec_query,
                context.sales_station_oid,
                context.enabled,
                context.whouse_param
            )

            found_resultset = False
            available_columns: List[str] = []
            gettables_rows: List[Dict[str, Any]] = []

            while True:
                if cursor.description:
                    columns = [column[0].lower() for column in cursor.description]
                    available_columns = columns

                    if "tablecode" in columns and "inform" in columns:
                        found_resultset = True
                        tablecode_index = columns.index("tablecode")
                        inform_index = columns.index("inform")

                        for row in cursor.fetchall():
                            gettables_rows.append(
                                {
                                    "TableCode": str(row[tablecode_index]).strip(),
                                    "Inform": row[inform_index]
                                }
                            )
                        break

                if not cursor.nextset():
                    break

            if not found_resultset:
                return CheckResult(
                    success=False,
                    title="Έλεγχος ενεργοποίησης στο σημείο πώλησης του τραπεζιού Αυτοπαράδοσης",
                    message=(
                        "Το GetTables εκτελέστηκε, αλλά δεν επέστρεψε result set "
                        "με στήλες tablecode και inform.\n"
                        f"Τελευταίες στήλες που βρέθηκαν: {available_columns}"
                    )
                )

            gettables_by_tablecode = {
                item["TableCode"]: item["Inform"]
                for item in gettables_rows
            }

            missing_tables = []
            wrong_inform_tables = []

            for table in tables:
                if table.table_code not in gettables_by_tablecode:
                    missing_tables.append(table)
                    continue

                inform_value = gettables_by_tablecode[table.table_code]

                if inform_value != 1:
                    wrong_inform_tables.append((table, inform_value))

            if missing_tables or wrong_inform_tables:
                lines = [
                    "Βρέθηκαν προβλήματα στο GetTables για τραπέζια με TableSelfDelivery = 1:",
                    ""
                ]

                if missing_tables:
                    lines.append("Δεν βρέθηκαν στο αποτέλεσμα του GetTables:")
                    lines.append("")

                    for table in missing_tables:
                        lines.append(f"- TableCode: {table.table_code} | TableOID: {table.table_oid}")

                if wrong_inform_tables:
                    if missing_tables:
                        lines.append("")

                    lines.append("Βρέθηκαν με inform διαφορετικό από 1:")
                    lines.append("")

                    for table, inform_value in wrong_inform_tables:
                        lines.append(
                            f"- TableCode: {table.table_code} | "
                            f"TableOID: {table.table_oid} | Inform: {inform_value}"
                        )

                return CheckResult(
                    success=False,
                    title="Έλεγχος ενεργοποίησης στο σημείο πώλησης του τραπεζιού Αυτοπαράδοσης",
                    message="\n".join(lines)
                )

            return CheckResult(
                success=True,
                title="Έλεγχος ενεργοποίησης στο σημείο πώλησης του τραπεζιού Αυτοπαράδοσης",
                message="Όλα τα τραπέζια Αυτοπαράδοσης εμφανίζονται ενεργοποιημένα στο GetTables."
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο GetTables / inform.")
            return CheckResult(
                success=False,
                title="SQL Error",
                message=f"Προέκυψε σφάλμα κατά τον έλεγχο GetTables:\n{ex}"
            )

    def check_self_delivery_note_types(self) -> CheckResult:
        """Ελέγχει αν τα self-delivery τραπέζια έχουν τους απαραίτητους τύπους παραστατικών."""
        try:
            tables = self.ensure_self_delivery_tables()

            if not tables:
                return CheckResult(
                    success=False,
                    title="Έλεγχος απαραίτητων τύπων παραστατικών στο τραπέζι Αυτοπαράδοσης",
                    message="Δεν υπάρχουν τραπέζια Αυτοπαράδοσης για να ελεγχθούν."
                )

            context = self.get_gettables_execution_context()
            sales_station_oid = context.sales_station_oid
            kitchen_note_type = self.get_kitchen_note_type()
            self_delivery_note_type = self.get_self_delivery_note_type()
            required_note_types = [kitchen_note_type, self_delivery_note_type]

            cursor = self.connection.cursor()
            missing_items = []
            tables_without_salesstation_link = []

            for table in tables:
                cursor.execute(
                    """
                    SELECT SalesStationTableOID
                    FROM TblSnSalesStationTable WITH (NOLOCK)
                    WHERE SalesStationOID = ?
                      AND TableOID = ?
                    """,
                    sales_station_oid,
                    table.table_oid
                )
                sales_station_table_row = cursor.fetchone()

                if sales_station_table_row is None:
                    tables_without_salesstation_link.append(table)
                    continue

                sales_station_table_oid = int(sales_station_table_row[0])

                for note_type in required_note_types:
                    cursor.execute(
                        """
                        SELECT SStTblNotesOID
                        FROM TblSnSStTblNotes WITH (NOLOCK)
                        WHERE SalesStationTableOID = ?
                          AND NoteTypeOID = ?
                        """,
                        sales_station_table_oid,
                        note_type.note_type_oid
                    )

                    if cursor.fetchone() is None:
                        missing_items.append((table, sales_station_table_oid, note_type))

            if tables_without_salesstation_link:
                AppLogger.info(
                    "SelfDelivery τραπέζια χωρίς σύνδεση στο TblSnSalesStationTable: "
                    + ", ".join(
                        f"{table.table_code} (TableOID={table.table_oid})"
                        for table in tables_without_salesstation_link
                    )
                )

            if missing_items:
                lines = [
                    "Βρέθηκαν τραπέζια με TableSelfDelivery = 1 που δεν έχουν όλους τους απαραίτητους τύπους παραστατικών:",
                    ""
                ]

                for table, sales_station_table_oid, note_type in missing_items:
                    lines.append(
                        f"- TableCode: {table.table_code} | "
                        f"Λείπει NoteTypeOID: {note_type.note_type_oid} "
                        f"({note_type.note_type_descr})"
                    )

                return CheckResult(
                    success=False,
                    title="Έλεγχος απαραίτητων τύπων παραστατικών στο τραπέζι Αυτοπαράδοσης",
                    message="\n".join(lines)
                )

            return CheckResult(
                success=True,
                title="Έλεγχος απαραίτητων τύπων παραστατικών στο τραπέζι Αυτοπαράδοσης",
                message="Όλα τα τραπέζια Αυτοπαράδοσης έχουν συνδεδεμένους τους απαραίτητους τύπους παραστατικών."
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο απαραίτητων τύπων παραστατικών στο τραπέζι Αυτοπαράδοσης.")
            return CheckResult(
                success=False,
                title="SQL Error",
                message=f"Προέκυψε σφάλμα κατά τον έλεγχο απαραίτητων τύπων παραστατικών στο τραπέζι Αυτοπαράδοσης:\n{ex}"
            )

    def check_closure_receipt_mydata_default(self) -> CheckResult:
        """Ελέγχει αν υπάρχει σωστός closure note type με βάση τους τελικούς κανόνες."""
        try:
            self.get_closure_note_type_by_rules()
            return CheckResult(
                success=True,
                title="Έλεγχος ύπαρξης Απόδειξης Κλεισίματος",
                message="Βρέθηκε σωστά Απόδειξη Κλεισίματο."
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο ύπαρξης Απόδειξης Κλεισίματος.")
            return CheckResult(
                success=False,
                title="Έλεγχος ύπαρξης Απόδειξης Κλεισίματος",
                message=str(ex)
            )

    def check_salesstations_closure_note_oid(self) -> CheckResult:
        """Ελέγχει όλα τα Sales Stations και επιβεβαιώνει ότι έχουν SalesStationClosureNoteOID."""
        try:
            query = """
            SELECT
                SalesStationOID,
                SalesStationNo,
                SalesStationDescr,
                SalesStationClosureNoteOID
            FROM TblSnSalesStation WITH (NOLOCK)
            ORDER BY SalesStationOID
            """

            cursor = self.connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            if not rows:
                return CheckResult(
                    success=False,
                    title="Έλεγχος Σημείου Πώλησης για Απόδειξη Κλεισίματος",
                    message="Δεν βρέθηκαν εγγραφές στο Σημείο Πώλησης."
                )

            invalid_salesstations = []

            for row in rows:
                closure_note_oid = row[3]

                if closure_note_oid is None or str(closure_note_oid).strip() == "":
                    invalid_salesstations.append(
                        {
                            "SalesStationOID": row[0],
                            "SalesStationNo": row[1],
                            "SalesStationDescr": str(row[2]).strip() if row[2] is not None else ""
                        }
                    )

            if invalid_salesstations:
                lines = [
                    "Βρέθηκαν Σημεία Πώλησης χωρίς τιμή στο SalesStationClosureNoteOID:",
                    ""
                ]

                for item in invalid_salesstations:
                    lines.append(
                        f"- OID: {item['SalesStationOID']} | "
                        f"No: {item['SalesStationNo']} | "
                        f"Περιγραφή: {item['SalesStationDescr']}"
                    )

                return CheckResult(
                    success=False,
                    title="Έλεγχος Σημείου Πώλησης για Απόδειξη Κλεισίματος",
                    message="\n".join(lines)
                )

            return CheckResult(
                success=True,
                title="Έλεγχος Σημείου Πώλησης για Απόδειξη Κλεισίματος",
                message="Όλα τα Σημεία Πώλησης έχουν τιμή στο SalesStationClosureNoteOID."
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο Σημείου Πώλησης για Απόδειξη Κλεισίματος.")
            return CheckResult(
                success=False,
                title="SQL Error",
                message=f"Προέκυψε σφάλμα κατά τον έλεγχο Σημείου Πώλησης για Απόδειξη Κλεισίματος:\n{ex}"
            )

    def check_order_note_next_to_closure_note(self) -> CheckResult:
        """Ελέγχει αν τα δελτία παραγγελίας έχουν συνέχεια προς το default closure note type."""
        try:
            cursor = self.connection.cursor()
            closure_note_type = self.get_default_closure_note_type(require_unique=True)

            order_note_types_query = """
            SELECT
                NoteTypeOID,
                NoteTypeAbbr,
                NoteTypeDescr
            FROM TblSnNoteType WITH (NOLOCK)
            WHERE MyDATA_NoteTypeSubCategOID = 49
              AND NoteTypeCanc = 0
              AND NoteTypeCredits = 0
            ORDER BY NoteTypeOID
            """

            cursor.execute(order_note_types_query)
            order_note_type_rows = cursor.fetchall()

            if not order_note_type_rows:
                return CheckResult(
                    success=False,
                    title="Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης για Απόδειξη Κλεισίματος",
                    message=(
                        "Δεν βρέθηκε τύπος παραστατικού Προσωρινής Απόδειξης"
                    )
                )

            missing_links = []

            for row in order_note_type_rows:
                source_note_type_oid = int(row[0])
                source_note_type_abbr = str(row[1]).strip() if row[1] is not None else ""
                source_note_type_descr = str(row[2]).strip() if row[2] is not None else ""

                cursor.execute(
                    """
                    SELECT NoteTypeOID, NextNoteTypeOID
                    FROM TblSnNoteNext WITH (NOLOCK)
                    WHERE NoteTypeOID = ?
                      AND NextNoteTypeOID = ?
                    """,
                    source_note_type_oid,
                    closure_note_type.note_type_oid
                )

                if cursor.fetchone() is None:
                    missing_links.append(
                        {
                            "NoteTypeOID": source_note_type_oid,
                            "NoteTypeAbbr": source_note_type_abbr,
                            "NoteTypeDescr": source_note_type_descr
                        }
                    )

            if missing_links:
                lines = [
                    "Δεν βρέθηκε σωστός μετασχηματισμός για τα παρακάτω παραστατικά:",
                    "",
                    f"Αναμενόμενο NextNoteTypeOID = {closure_note_type.note_type_oid} ({closure_note_type.note_type_descr})",
                    ""
                ]

                for item in missing_links:
                    lines.append(
                        f"- NoteTypeOID: {item['NoteTypeOID']} | "
                        f"Abbr: {item['NoteTypeAbbr']} | "
                        f"Descr: {item['NoteTypeDescr']}"
                    )

                return CheckResult(
                    success=False,
                    title="Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης",
                    message="\n".join(lines)
                )

            return CheckResult(
                success=True,
                title="Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης για Απόδειξη Κλεισίματος",
                message="Όλοι οι τύποι παραστατικών Προσωρινής Απόδειξης έχουν μετασχηματισμό προς τον τύπο παραστατικού κλεισίματος."
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο Μετασχηματισμών Προσωρινής Απόδειξης για Απόδειξη Κλεισίματος.")
            return CheckResult(
                success=False,
                title="SQL Error",
                message=f"Προέκυψε σφάλμα κατά τον έλεγχο Μετασχηματισμών Προσωρινής Απόδειξης για Απόδειξη Κλεισίματος:\n{ex}"
            )

    def check_order_note_types_group_pos(self) -> CheckResult:
        """
        Ελέγχει αν όλοι οι τύποι παραστατικών Προσωρινής Απόδειξης
        με MyDATA_NoteTypeSubCategOID = 49 έχουν NoteTypeGroupPos = 2.
        """

        try:
            query = """
            SELECT
                NoteTypeOID,
                NoteTypeAbbr,
                NoteTypeDescr,
                NoteTypeGroupPos
            FROM TblSnNoteType WITH (NOLOCK)
            WHERE MyDATA_NoteTypeSubCategOID = 49
            ORDER BY NoteTypeOID
            """

            cursor = self.connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            if not rows:
                return CheckResult(
                    success=False,
                    title="Έλεγχος Ομάδας Προσωρινής Απόδειξης",
                    message=(
                        "Δεν βρέθηκαν τύποι παραστατικών Προσωρινής Απόδειξης "
                        "με MyDATA_NoteTypeSubCategOID = 49."
                    )
                )

            invalid_rows = []

            for row in rows:
                note_type_oid = int(row[0])
                note_type_abbr = str(row[1]).strip() if row[1] is not None else ""
                note_type_descr = str(row[2]).strip() if row[2] is not None else ""
                note_type_group_pos = row[3]

                if note_type_group_pos != 2:
                    invalid_rows.append(
                        {
                            "NoteTypeOID": note_type_oid,
                            "NoteTypeAbbr": note_type_abbr,
                            "NoteTypeDescr": note_type_descr,
                            "NoteTypeGroupPos": note_type_group_pos
                        }
                    )

            if invalid_rows:
                lines = [
                    "Βρέθηκαν τύποι παραστατικών Προσωρινής Απόδειξης "
                    "με λάθος NoteTypeGroupPos.",
                    "",
                    "Το σωστό είναι NoteTypeGroupPos = 2.",
                    "",
                    "Παραστατικά με πρόβλημα:",
                    ""
                ]

                for item in invalid_rows:
                    lines.append(
                        f"- NoteTypeOID: {item['NoteTypeOID']} | "
                        f"Abbr: {item['NoteTypeAbbr']} | "
                        f"Descr: {item['NoteTypeDescr']} | "
                        f"NoteTypeGroupPos: {item['NoteTypeGroupPos']}"
                    )

                return CheckResult(
                    success=False,
                    title="Έλεγχος Ομάδας Προσωρινής Απόδειξης",
                    message="\n".join(lines)
                )

            return CheckResult(
                success=True,
                title="Έλεγχος Ομάδας Προσωρινής Απόδειξης",
                message=(
                    "Όλοι οι τύποι παραστατικών Προσωρινής Απόδειξης "
                    "έχουν σωστά NoteTypeGroupPos = 2."
                )
            )

        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο Ομάδας Προσωρινής Απόδειξης.")

            return CheckResult(
                success=False,
                title="SQL Error",
                message=(
                    "Προέκυψε σφάλμα κατά τον έλεγχο Ομάδας Προσωρινής Απόδειξης:\n"
                    f"{ex}"
                )
            )

    def check_all_tables_have_closure_note_type(self) -> CheckResult:
        """
        Ελέγχει αν όλα τα κανονικά τραπέζια που είναι ενεργά στο GetTables
        με inform = 1 έχουν συνδεδεμένο τον default closure τύπο παραστατικού.

        Εξαιρεί:
        - τραπέζια Αυτοπαράδοσης με TableSelfDelivery = 1
        - τραπέζια που στο GetTables έχουν inform = 0 ή δεν επιστρέφονται
        """

        try:
            context = self.get_gettables_execution_context()
            sales_station_oid = context.sales_station_oid

            closure_note_type = self.get_default_closure_note_type(require_unique=False)
            cursor = self.connection.cursor()

            # ==========================================================
            # 1. Εκτελούμε GetTables και κρατάμε τα TableCode με inform = 1.
            # ==========================================================

            gettables_query = """
            EXEC GetTables
                @SalesStationOID = ?,
                @Enabled = ?,
                @WHouseOID = ?,
                @HallOID = DEFAULT
            """

            cursor.execute(
                gettables_query,
                context.sales_station_oid,
                context.enabled,
                context.whouse_param
            )

            found_resultset = False
            informed_table_codes = set()
            available_columns = []

            while True:
                if cursor.description:
                    columns = [column[0].lower() for column in cursor.description]
                    available_columns = columns

                    if "tablecode" in columns and "inform" in columns:
                        found_resultset = True

                        tablecode_index = columns.index("tablecode")
                        inform_index = columns.index("inform")

                        rows = cursor.fetchall()

                        for row in rows:
                            table_code = str(row[tablecode_index]).strip()
                            inform_value = row[inform_index]

                            try:
                                inform_value_int = int(inform_value)
                            except Exception:
                                inform_value_int = 0

                            if table_code and inform_value_int == 1:
                                informed_table_codes.add(table_code)

                        break

                if not cursor.nextset():
                    break

            if not found_resultset:
                return CheckResult(
                    success=False,
                    title="Έλεγχος Closure NoteType στα τραπέζια",
                    message=(
                        "Το GetTables εκτελέστηκε, αλλά δεν επέστρεψε result set "
                        "με στήλες tablecode και inform.\n"
                        f"Τελευταίες στήλες που βρέθηκαν: {available_columns}"
                    )
                )

            if not informed_table_codes:
                return CheckResult(
                    success=False,
                    title="Έλεγχος Closure NoteType στα τραπέζια",
                    message=(
                        "Το GetTables δεν επέστρεψε κανένα τραπέζι με inform = 1.\n"
                        "Δεν υπάρχουν ενεργά τραπέζια για έλεγχο Απόδειξης Κλεισίματος."
                    )
                )

            # ==========================================================
            # 2. Φορτώνουμε όλα τα κανονικά τραπέζια του σημείου πώλησης.
            #    Δεν χρησιμοποιούμε TableInformed γιατί δεν υπάρχει στη βάση.
            # ==========================================================

            cursor.execute(
                """
                SELECT
                    t.TableOID,
                    t.TableCode,
                    t.WHouseOID,
                    sst.SalesStationTableOID
                FROM TblSnSalesStationTable sst WITH (NOLOCK)
                INNER JOIN TblSnTable t WITH (NOLOCK)
                    ON sst.TableOID = t.TableOID
                WHERE sst.SalesStationOID = ?
                AND ISNULL(t.TableSelfDelivery, 0) <> 1
                ORDER BY t.TableCode
                """,
                sales_station_oid
            )

            table_rows = cursor.fetchall()

            if not table_rows:
                return CheckResult(
                    success=False,
                    title="Έλεγχος Closure NoteType στα τραπέζια",
                    message=(
                        "Δεν βρέθηκαν κανονικά τραπέζια για έλεγχο.\n"
                        "Εξαιρούνται τα τραπέζια Αυτοπαράδοσης."
                    )
                )

            missing_tables = []
            skipped_not_informed_tables = []

            # ==========================================================
            # 3. Ελέγχουμε μόνο όσα κανονικά τραπέζια έχουν inform = 1
            #    στο αποτέλεσμα του GetTables.
            # ==========================================================

            for row in table_rows:
                table_oid = int(row[0])
                table_code = str(row[1]).strip() if row[1] is not None else ""
                whouse_oid = row[2]
                sales_station_table_oid = int(row[3])

                if table_code not in informed_table_codes:
                    skipped_not_informed_tables.append(table_code)
                    continue

                cursor.execute(
                    """
                    SELECT SStTblNotesOID
                    FROM TblSnSStTblNotes WITH (NOLOCK)
                    WHERE SalesStationTableOID = ?
                    AND NoteTypeOID = ?
                    """,
                    sales_station_table_oid,
                    closure_note_type.note_type_oid
                )

                if cursor.fetchone() is None:
                    missing_tables.append(
                        {
                            "TableCode": table_code,
                            "TableOID": table_oid,
                            "WHouseOID": whouse_oid,
                            "SalesStationTableOID": sales_station_table_oid
                        }
                    )

            if skipped_not_informed_tables:
                AppLogger.info(
                    "Τραπέζια που εξαιρέθηκαν από Closure NoteType έλεγχο επειδή δεν έχουν inform = 1 στο GetTables: "
                    + ", ".join(sorted(set(skipped_not_informed_tables)))
                )

            if missing_tables:
                lines = [
                    "Βρέθηκαν ενεργά κανονικά τραπέζια που δεν έχουν συνδεδεμένο τον τύπο παραστατικού κλεισίματος:",
                    "",
                    f"Closure NoteTypeOID: {closure_note_type.note_type_oid}",
                    f"Closure NoteTypeDescr: {closure_note_type.note_type_descr}",
                    "",
                    "Τραπέζια με πρόβλημα:",
                    ""
                ]

                for item in missing_tables:
                    lines.append(
                        f"- TableCode: {item['TableCode']} | "
                        f"TableOID: {item['TableOID']} | "
                        f"WHouseOID: {item['WHouseOID']} | "
                        f"SalesStationTableOID: {item['SalesStationTableOID']}"
                    )

                return CheckResult(
                    success=False,
                    title="Έλεγχος Closure NoteType στα τραπέζια",
                    message="\n".join(lines)
                )

            return CheckResult(
                success=True,
                title="Έλεγχος Closure NoteType στα τραπέζια",
                message=(
                    "Όλα τα ενεργά κανονικά τραπέζια έχουν συνδεδεμένο τον τύπο παραστατικού κλεισίματος.\n"
                    "Τα τραπέζια Αυτοπαράδοσης και τα τραπέζια που δεν έχουν inform = 1 στο GetTables εξαιρέθηκαν."
                )
            )

        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο Closure NoteType στα τραπέζια.")

            return CheckResult(
                success=False,
                title="SQL Error",
                message=(
                    "Προέκυψε σφάλμα κατά τον έλεγχο Closure NoteType στα τραπέζια:\n"
                    f"{ex}"
                )
            )

    def check_mydata_86_notetype_issue(self) -> CheckResult:
        """Ελέγχει ότι οι τύποι myDATA 8.6 δεν έχουν NoteTypeIssue = 0."""
        try:
            query = """
            SELECT
                nt.NoteTypeOID,
                nt.NoteTypeAbbr,
                nt.NoteTypeDescr,
                nt.NoteTypeIssue
            FROM TblSnNoteType nt WITH (NOLOCK)
            INNER JOIN TblSnMyDATA_NoteTypeSubCateg sc WITH (NOLOCK)
                ON nt.MyDATA_NoteTypeSubCategOID = sc.MyDATA_NoteTypeSubCategOID
            WHERE sc.MyDATA_NoteTypeSubCategCode = ?
            ORDER BY nt.NoteTypeOID
            """

            cursor = self.connection.cursor()
            cursor.execute(query, "8.6")
            rows = cursor.fetchall()

            if not rows:
                return CheckResult(
                    success=False,
                    title="Έλεγχος Εκδιδόμενου για παραστατικά Προσωρινών",
                    message="Δεν βρέθηκαν τύποι παραστατικών Προσωρινής Απόδειξης."
                )

            invalid_rows = []

            for row in rows:
                if row[3] == 0:
                    invalid_rows.append(
                        {
                            "NoteTypeOID": row[0],
                            "NoteTypeAbbr": str(row[1]).strip() if row[1] is not None else "",
                            "NoteTypeDescr": str(row[2]).strip() if row[2] is not None else ""
                        }
                    )

            if invalid_rows:
                lines = [
                    "Βρέθηκαν τύποι παραστατικών myDATA 8.6 με NoteTypeIssue = 0:",
                    ""
                ]

                for item in invalid_rows:
                    lines.append(
                        f"- NoteTypeOID: {item['NoteTypeOID']} | "
                        f"Abbr: {item['NoteTypeAbbr']} | "
                        f"Descr: {item['NoteTypeDescr']}"
                    )

                return CheckResult(
                    success=False,
                    title="Έλεγχος Εκδιδόμενου για παραστατικά Προσωρινών",
                    message="\n".join(lines)
                )

            return CheckResult(
                success=True,
                title="Έλεγχος Εκδιδόμενου για παραστατικά Προσωρινών",
                message="Όλοι οι τύποι παραστατικών myDATA 8.6 είναι Εκδιδόμενα."
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο Εκδιδόμενου για παραστατικά Προσωρινών.")
            return CheckResult(
                success=False,
                title="SQL Error",
                message=f"Προέκυψε σφάλμα κατά τον έλεγχο Εκδιδόμενου για παραστατικά Προσωρινών:\n{ex}"
            )

    def check_mydata_special_category_not_null(self) -> CheckResult:
        """Ελέγχει αν οι επιλεγμένες myDATA κατηγορίες έχουν MyDATA_NoteTypeSpecialCategOID."""
        try:
            query = """
            SELECT
                nt.NoteTypeOID,
                nt.NoteTypeAbbr,
                nt.NoteTypeDescr,
                nt.MyDATA_NoteTypeSpecialCategOID,
                sc.MyDATA_NoteTypeSubCategCode
            FROM TblSnNoteType nt WITH (NOLOCK)
            INNER JOIN TblSnMyDATA_NoteTypeSubCateg sc WITH (NOLOCK)
                ON nt.MyDATA_NoteTypeSubCategOID = sc.MyDATA_NoteTypeSubCategOID
            WHERE sc.MyDATA_NoteTypeSubCategCode IN (?, ?, ?, ?, ?, ?, ?)
            ORDER BY sc.MyDATA_NoteTypeSubCategCode, nt.NoteTypeOID
            """

            target_codes = ["1.1", "11.1", "11.2", "11.4", "5.1", "5.2", "8.6"]
            cursor = self.connection.cursor()
            cursor.execute(query, *target_codes)
            rows = cursor.fetchall()

            if not rows:
                return CheckResult(
                    success=False,
                    title="Έλεγχος myDATA Special Category 12",
                    message="Δεν βρέθηκαν τύποι παραστατικών για τις myDATA κατηγορίες:\n" + ", ".join(target_codes)
                )

            invalid_rows = []

            for row in rows:
                if row[3] is None:
                    invalid_rows.append(
                        {
                            "NoteTypeOID": row[0],
                            "NoteTypeAbbr": str(row[1]).strip() if row[1] is not None else "",
                            "NoteTypeDescr": str(row[2]).strip() if row[2] is not None else "",
                            "SubCategoryCode": str(row[4]).strip() if row[4] is not None else ""
                        }
                    )

            if invalid_rows:
                lines = [
                    "Βρέθηκαν τύποι παραστατικών με κενό MyDATA_NoteTypeSpecialCategOID:",
                    ""
                ]

                for item in invalid_rows:
                    lines.append(
                        f"- {item['NoteTypeDescr']} "
                        f"(NoteTypeOID: {item['NoteTypeOID']}, "
                        f"Abbr: {item['NoteTypeAbbr']}, "
                        f"myDATA: {item['SubCategoryCode']})"
                    )

                return CheckResult(
                    success=False,
                    title="Έλεγχος myDATA Special Category 12",
                    message="\n".join(lines)
                )

            return CheckResult(
                success=True,
                title="Έλεγχος myDATA Special Category 12",
                message="Όλοι οι τύποι παραστατικών των επιλεγμένων myDATA κατηγοριών έχουν συμπληρωμένο MyDATA_NoteTypeSpecialCategOID 12."
            )
        except Exception as ex:
            AppLogger.exception("Σφάλμα κατά τον έλεγχο myDATA Special Category 12.")
            return CheckResult(
                success=False,
                title="SQL Error",
                message=f"Προέκυψε σφάλμα κατά τον έλεγχο myDATA Special Category 12:\n{ex}"
            )

    def run_all_checks(self, include_schema_check: bool = True) -> List[CheckResult]:
        """Εκτελεί όλους τους ελέγχους με σταθερή σειρά."""
        results: List[CheckResult] = []

        if include_schema_check:
            schema_result = self.check_required_schema()
            results.append(schema_result)

            if not schema_result.success:
                return results

        results.extend(
            [
                self.check_self_delivery_tables(),
                self.check_gettables_self_delivery_inform(),
                self.check_self_delivery_note_types(),
                self.check_closure_receipt_mydata_default(),
                self.check_salesstations_closure_note_oid(),
                self.check_order_note_next_to_closure_note(),
                self.check_order_note_types_group_pos(),
                self.check_all_tables_have_closure_note_type(),
                self.check_mydata_86_notetype_issue(),
                self.check_mydata_special_category_not_null(),
            ]
        )

        return results

    # ----------------------------------------------------------
    # Backward-compatible aliases για παλιότερο κώδικα / CLI
    # ----------------------------------------------------------

    def check_autop_self_delivery(self) -> CheckResult:
        """Alias για συμβατότητα με παλιό όνομα."""
        return self.check_self_delivery_tables()

    def check_gettables_autop_inform(self) -> CheckResult:
        """Alias για συμβατότητα με παλιό όνομα."""
        return self.check_gettables_self_delivery_inform()

    def check_autop_note_types(self) -> CheckResult:
        """Alias για συμβατότητα με παλιό όνομα."""
        return self.check_self_delivery_note_types()


# ==========================================================
# CLI application
# ==========================================================

class CliApp:
    """CLI έκδοση της εφαρμογής."""

    def __init__(self, args):
        self.args = args

    def run(self) -> int:
        """Εκτελεί όλους τους ελέγχους από γραμμή εντολών."""
        if self.args.udl:
            sql_config = UdlReader(self.args.udl).to_sql_config()
            db = SqlServerConnection(
                server=str(sql_config["server"]),
                database=str(sql_config["database"]),
                username=str(sql_config["username"]),
                password=str(sql_config["password"]),
                driver=self.args.driver or None,
                trusted_connection=bool(sql_config["trusted_connection"])
            )
        else:
            db = SqlServerConnection(
                server=self.args.server,
                database=self.args.database,
                username=self.args.username,
                password=self.args.password,
                driver=self.args.driver or None,
                trusted_connection=self.args.trusted
            )

        try:
            connection = db.connect()
            checks = SqlChecks(connection)
            results = checks.run_all_checks(include_schema_check=True)
            has_error = any(not result.success for result in results)

            print(format_results(results))
            return 1 if has_error else 0
        finally:
            db.close()


# ==========================================================
# GUI application
# ==========================================================

class SqlCheckerGui:
    """CustomTkinter GUI για τους SQL ελέγχους με UDL σύνδεση."""

    def __init__(self):
        if ctk is None:
            raise ImportError(
                "Το customtkinter δεν είναι εγκατεστημένο. "
                "Τρέξε: pip install customtkinter"
            )

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Έλεγχος Σεναρίου Προσωρινών Αποδείξεων")
        self.set_window_icon(self.root)
        self.root.geometry("980x720")
        self.root.minsize(900, 620)

        self.connection = None
        self.db: Optional[SqlServerConnection] = None

        self.udl_path_var = ctk.StringVar(value="")
        self.server_var = ctk.StringVar(value="")
        self.database_var = ctk.StringVar(value="")
        self.driver_var = ctk.StringVar(value="")
        self.auth_var = ctk.StringVar(value="")
        self.username_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="Δεν υπάρχει σύνδεση.")
        self.summary_status_var = ctk.StringVar(value="Έτοιμο για έλεγχο")
        self.summary_total_var = ctk.StringVar(value="Σύνολο: -")
        self.summary_success_var = ctk.StringVar(value="Επιτυχείς: -")
        self.summary_error_var = ctk.StringVar(value="Προβλήματα: -")
        self.detail_title_var = ctk.StringVar(value="Οδηγίες")

        self.summary_frame = None
        self.results_list_frame = None
        self.detail_box = None
        self.result_cards: List[Any] = []
        self.results_window: Optional[Any] = None

        self.build_ui()
        self.bind_shortcuts()
        AppLogger.info("Το GUI άνοιξε.")

    def set_window_icon(self, window) -> None:
        """Ορίζει το εικονίδιο του κύριου ή βοηθητικού παραθύρου."""
        set_tk_window_icon(window, "moonhard.ico")

    def build_ui(self) -> None:
        """Δημιουργεί το κύριο παράθυρο χωρίς panel αποτελεσμάτων."""
        main_frame = ctk.CTkFrame(self.root, corner_radius=18)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_label = ctk.CTkLabel(
            main_frame,
            text="Έλεγχος Σεναρίου Προσωρινών Αποδείξεων",
            font=("Arial", 26, "bold")
        )
        title_label.pack(pady=(20, 4))

        subtitle_label = ctk.CTkLabel(
            main_frame,
            text="Σύνδεση μέσω UDL και έλεγχος σωστών ρυθμίσεων σεναρίου",
            font=("Arial", 14)
        )
        subtitle_label.pack(pady=(0, 15))

        udl_frame = ctk.CTkFrame(main_frame, corner_radius=14)
        udl_frame.pack(fill="x", padx=20, pady=10)

        self.add_readonly_entry(udl_frame, "UDL File:", self.udl_path_var)

        open_udl_button = ctk.CTkButton(
            udl_frame,
            text="Άνοιγμα UDL",
            width=160,
            command=self.open_udl_file
        )
        open_udl_button.pack(anchor="w", padx=20, pady=(5, 15))

        info_frame = ctk.CTkFrame(main_frame, corner_radius=14)
        info_frame.pack(fill="x", padx=20, pady=10)

        self.add_readonly_entry(info_frame, "Server:", self.server_var)
        self.add_readonly_entry(info_frame, "Database:", self.database_var)
        self.add_readonly_entry(info_frame, "ODBC Driver:", self.driver_var)
        self.add_readonly_entry(info_frame, "Authentication:", self.auth_var)
        self.add_readonly_entry(info_frame, "Username:", self.username_var)

        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=15)

        check_button = ctk.CTkButton(
            button_frame,
            text="Άνοιγμα Ελέγχου",
            width=170,
            command=self.run_all_checks
        )
        check_button.pack(side="left", padx=5)

        clear_button = ctk.CTkButton(
            button_frame,
            text="Καθαρισμός",
            width=130,
            command=self.clear_result
        )
        clear_button.pack(side="left", padx=5)

        status_card = ctk.CTkFrame(main_frame, corner_radius=16)
        status_card.pack(fill="both", expand=True, padx=20, pady=12)
        status_card.grid_columnconfigure(0, weight=1)

        status_title = ctk.CTkLabel(
            status_card,
            text="Κατάσταση",
            font=("Arial", 18, "bold"),
            anchor="w"
        )
        status_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))

        status_label = ctk.CTkLabel(
            status_card,
            textvariable=self.status_var,
            font=("Arial", 15, "bold"),
            anchor="w",
            justify="left",
            wraplength=820
        )
        status_label.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        instructions = ctk.CTkLabel(
            status_card,
            text=(
                "1. Πάτησε Άνοιγμα UDL και επίλεξε το αρχείο της βάσης.\n"
                "2. Η σύνδεση γίνεται αυτόματα.\n"
                "3. Πάτησε Άνοιγμα Ελέγχου.\n"
                "4. Τα αποτελέσματα θα ανοίξουν σε νέο παράθυρο dashboard."
            ),
            font=("Arial", 14),
            anchor="w",
            justify="left",
            wraplength=820
        )
        instructions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))

        shortcuts_label = ctk.CTkLabel(
            main_frame,
            text=(
                "Shortcuts: Ctrl+O = Άνοιγμα UDL | "
                "Ctrl+R = Άνοιγμα Ελέγχου | Ctrl+K = Καθαρισμός | Esc = Έξοδος"
            ),
            font=("Arial", 12)
        )
        shortcuts_label.pack(pady=(0, 10))

    def add_readonly_entry(self, parent, label_text: str, variable) -> None:
        """Προσθέτει readonly πεδίο στο GUI."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=6)

        label = ctk.CTkLabel(row, text=label_text, width=135, anchor="w")
        label.pack(side="left")

        entry = ctk.CTkEntry(row, textvariable=variable, state="readonly")
        entry.pack(side="left", fill="x", expand=True)

    def bind_shortcuts(self) -> None:
        """Ορίζει keyboard shortcuts."""
        self.root.bind("<Control-o>", lambda event: self.open_udl_file())
        self.root.bind("<Control-O>", lambda event: self.open_udl_file())
        self.root.bind("<Control-r>", lambda event: self.run_all_checks())
        self.root.bind("<Control-R>", lambda event: self.run_all_checks())
        self.root.bind("<Control-k>", lambda event: self.clear_result())
        self.root.bind("<Control-K>", lambda event: self.clear_result())
        self.root.bind("<Escape>", lambda event: self.root.destroy())

    def open_udl_file(self) -> None:
        """Ανοίγει επιλογή UDL και συνδέεται αυτόματα στη βάση."""
        default_udl_dir = r"C:\ProgramData\Sunsoft\BackOffice"
        initial_dir = default_udl_dir if os.path.exists(default_udl_dir) else os.getcwd()

        file_path = filedialog.askopenfilename(
            title="Επιλογή UDL αρχείου",
            initialdir=initial_dir,
            filetypes=[("UDL files", "*.udl"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            self.close_existing_connection()
            sql_config = UdlReader(file_path).to_sql_config()
            driver = OdbcDriverHelper.get_best_driver()

            self.udl_path_var.set(file_path)
            self.server_var.set(str(sql_config["server"]))
            self.database_var.set(str(sql_config["database"]))
            self.driver_var.set(driver)

            if sql_config["trusted_connection"]:
                self.auth_var.set("Windows Authentication")
                self.username_var.set("")
            else:
                self.auth_var.set("SQL Authentication")
                self.username_var.set(str(sql_config["username"]))

            self.status_var.set("Το UDL φορτώθηκε. Γίνεται αυτόματη σύνδεση...")
            self.write_result(
                "✅ Το UDL αρχείο φορτώθηκε επιτυχώς.\n\n"
                f"UDL: {file_path}\n"
                f"Server: {sql_config['server']}\n"
                f"Database: {sql_config['database']}\n"
                f"Authentication: {self.auth_var.get()}\n\n"
                "Γίνεται αυτόματη σύνδεση στη βάση..."
            )

            AppLogger.info(f"Φορτώθηκε UDL: {file_path}")
            self.connect_database()
        except Exception as ex:
            self.status_var.set("Σφάλμα UDL.")
            self.write_result(f"❌ Σφάλμα κατά την ανάγνωση του UDL:\n\n{ex}")
            AppLogger.exception("Σφάλμα κατά την ανάγνωση του UDL.")

    def get_loaded_udl_config(self) -> Dict[str, object]:
        """Διαβάζει ξανά το UDL και επιστρέφει τις ρυθμίσεις σύνδεσης."""
        udl_path = self.udl_path_var.get().strip()

        if not udl_path:
            raise ValueError("Δεν έχει επιλεγεί UDL αρχείο.")

        return UdlReader(udl_path).to_sql_config()

    def connect_database(self) -> None:
        """Συνδέεται στη βάση χρησιμοποιώντας το επιλεγμένο UDL."""
        try:
            self.close_existing_connection()
            sql_config = self.get_loaded_udl_config()

            db = SqlServerConnection(
                server=str(sql_config["server"]),
                database=str(sql_config["database"]),
                username=str(sql_config["username"]),
                password=str(sql_config["password"]),
                driver=self.driver_var.get().strip() or None,
                trusted_connection=bool(sql_config["trusted_connection"])
            )

            self.connection = db.connect()
            self.db = db

            self.status_var.set("Σύνδεση επιτυχής.")
            self.write_result(
                "✅ Η σύνδεση με τη βάση έγινε επιτυχώς μέσω UDL.\n\n"
                f"Server: {sql_config['server']}\n"
                f"Database: {sql_config['database']}\n"
                f"Authentication: {self.auth_var.get()}"
            )
        except Exception as ex:
            self.connection = None
            self.db = None
            self.status_var.set("Αποτυχία σύνδεσης.")
            self.write_result(f"❌ Σφάλμα σύνδεσης:\n\n{ex}")
            AppLogger.exception("Αποτυχία σύνδεσης μέσω UDL.")

    def close_existing_connection(self) -> None:
        """Κλείνει προηγούμενη σύνδεση πριν δημιουργηθεί νέα."""
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                AppLogger.exception("Σφάλμα στο κλείσιμο προηγούμενης σύνδεσης.")

        self.connection = None
        self.db = None

    def run_all_checks(self) -> None:
        """Εκτελεί όλους τους ελέγχους και ανοίγει νέο dashboard παράθυρο."""
        if self.connection is None:
            self.status_var.set(
                "❌ Δεν υπάρχει ενεργή σύνδεση στη βάση. Πρώτα άνοιξε UDL. Η σύνδεση γίνεται αυτόματα."
            )
            return

        try:
            self.status_var.set("Εκτελείται ο έλεγχος...")
            self.root.update_idletasks()

            checks = SqlChecks(self.connection)
            results = checks.run_all_checks(include_schema_check=True)
            has_error = any(not result.success for result in results)

            if self.results_window is not None:
                try:
                    self.results_window.destroy()
                except Exception:
                    pass

            self.results_window = ResultsDashboardWindow(
                parent=self.root,
                results=results,
                database_name=self.database_var.get().strip(),
                server_name=self.server_var.get().strip()
            )

            if has_error:
                self.status_var.set("Ο έλεγχος ολοκληρώθηκε. Βρέθηκαν προβλήματα στο dashboard.")
            else:
                self.status_var.set("Ο έλεγχος ολοκληρώθηκε. Όλα είναι σωστά.")

        except Exception as ex:
            self.status_var.set("❌ Προέκυψε σφάλμα κατά τον έλεγχο.")
            AppLogger.exception("Σφάλμα κατά την εκτέλεση των ελέγχων από το GUI.")
            ResultsDashboardWindow(
                parent=self.root,
                results=[
                    CheckResult(
                        success=False,
                        title="SQL Error",
                        message=f"Προέκυψε σφάλμα κατά την εκτέλεση των ελέγχων:\n{ex}"
                    )
                ],
                database_name=self.database_var.get().strip(),
                server_name=self.server_var.get().strip()
            )

    def clear_result(self) -> None:
        """Καθαρίζει την κατάσταση και κλείνει το dashboard αν είναι ανοιχτό."""
        if self.results_window is not None:
            try:
                self.results_window.destroy()
            except Exception:
                pass
            self.results_window = None

        self.status_var.set("Το αποτέλεσμα καθαρίστηκε.")
        AppLogger.info("Καθαρίστηκε η κατάσταση στο GUI.")

    def write_result(self, message: str) -> None:
        """Κρατά συμβατότητα με παλιότερες κλήσεις χωρίς log textbox."""
        if message:
            AppLogger.info(message.replace("\n", " | "))

    def clear_result_cards(self) -> None:
        """Καθαρίζει τις κάρτες αποτελεσμάτων."""
        if self.results_list_frame is None:
            return

        for widget in self.results_list_frame.winfo_children():
            widget.destroy()

        self.result_cards = []

    def render_results_dashboard(self, results: Iterable[CheckResult]) -> None:
        """Εμφανίζει τα αποτελέσματα σαν dashboard με κάρτες και panel λεπτομερειών."""
        result_list = list(results)
        success_count = sum(1 for result in result_list if result.success)
        error_count = len(result_list) - success_count

        if error_count:
            self.summary_status_var.set("❌ Βρέθηκαν προβλήματα που χρειάζονται έλεγχο")
        else:
            self.summary_status_var.set("✅ Όλοι οι έλεγχοι ολοκληρώθηκαν επιτυχώς")

        self.summary_total_var.set(f"Σύνολο: {len(result_list)}")
        self.summary_success_var.set(f"✅ Επιτυχείς: {success_count}")
        self.summary_error_var.set(f"❌ Προβλήματα: {error_count}")

        self.clear_result_cards()

        failed_results = [result for result in result_list if not result.success]
        successful_results = [result for result in result_list if result.success]

        row_index = 0
        if failed_results:
            row_index = self.add_results_section_title("Προβλήματα", row_index)
            for original_index, result in [(result_list.index(item) + 1, item) for item in failed_results]:
                self.create_result_card(row_index, original_index, result)
                row_index += 1

        row_index = self.add_results_section_title("Επιτυχημένοι έλεγχοι", row_index)
        for original_index, result in [(result_list.index(item) + 1, item) for item in successful_results]:
            self.create_result_card(row_index, original_index, result)
            row_index += 1

        if failed_results:
            self.select_result_card(1, failed_results[0])
        elif result_list:
            self.select_result_card(1, result_list[0])
        else:
            self.write_result("Δεν υπάρχουν αποτελέσματα.")

    def add_results_section_title(self, title: str, row_index: int) -> int:
        """Προσθέτει τίτλο ενότητας στη λίστα ελέγχων."""
        if self.results_list_frame is None:
            return row_index

        label = ctk.CTkLabel(
            self.results_list_frame,
            text=title,
            font=("Arial", 14, "bold"),
            anchor="w"
        )
        label.grid(row=row_index, column=0, sticky="ew", padx=8, pady=(10, 4))
        return row_index + 1

    def create_result_card(self, row_index: int, display_index: int, result: CheckResult) -> None:
        """Δημιουργεί μία κάρτα αποτελέσματος."""
        if self.results_list_frame is None:
            return

        icon = "✅" if result.success else "❌"
        status_text = "OK" if result.success else "Θέλει διόρθωση"
        short_message = self.get_short_message(result.message)

        card = ctk.CTkFrame(self.results_list_frame, corner_radius=14)
        card.grid(row=row_index, column=0, sticky="ew", padx=6, pady=5)
        card.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            card,
            text=f"{icon} {display_index}. {result.title}",
            font=("Arial", 13, "bold"),
            anchor="w",
            wraplength=330,
            justify="left"
        )
        title.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))

        status = ctk.CTkLabel(
            card,
            text=status_text,
            font=("Arial", 12, "bold"),
            anchor="w"
        )
        status.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 2))

        preview = ctk.CTkLabel(
            card,
            text=short_message,
            font=("Arial", 12),
            anchor="w",
            wraplength=330,
            justify="left"
        )
        preview.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        for widget in (card, title, status, preview):
            widget.bind("<Button-1>", lambda event, idx=display_index, res=result: self.select_result_card(idx, res))

        self.result_cards.append(card)

    def select_result_card(self, display_index: int, result: CheckResult) -> None:
        """Εμφανίζει τις λεπτομέρειες του επιλεγμένου ελέγχου."""
        icon = "✅" if result.success else "❌"
        explanation = CHECK_EXPLANATIONS.get(result.title, "Δεν υπάρχει διαθέσιμη περιγραφή για αυτόν τον έλεγχο.")
        self.detail_title_var.set(f"{icon} {display_index}. {result.title}")

        details = [
            "ΤΙ ΕΛΕΓΧΕΙ",
            explanation,
            "",
            "ΑΠΟΤΕΛΕΣΜΑ",
            result.message.strip()
        ]

        if not result.success:
            details.extend([
                "",
                "ΤΙ ΝΑ ΚΑΝΕΙΣ",
                self.get_fix_hint(result.title)
            ])

        self.write_result("\n".join(details))

    def get_short_message(self, message: str) -> str:
        """Επιστρέφει σύντομη περίληψη αποτελέσματος."""
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        if not lines:
            return "Δεν υπάρχουν λεπτομέρειες."

        text = lines[0]
        if len(text) > 120:
            return text[:117] + "..."

        return text

    def get_fix_hint(self, title: str) -> str:
        """Επιστρέφει σύντομη οδηγία διόρθωσης ανά έλεγχο."""
        hints = {
            "Τεχνικός έλεγχος δομής βάσης": "Έλεγξε αν η βάση είναι σωστής έκδοσης και αν λείπουν πίνακες ή πεδία.",
            "Έλεγχος για τραπέζι Αυτοπαράδοσης": "Δημιούργησε ή όρισε ένα τραπέζι Αυτοπαράδοσης με TableSelfDelivery = 1.",
            "Έλεγχος ενεργοποίησης στο σημείο πώλησης του τραπεζιού Αυτοπαράδοσης": "Έλεγξε τη σύνδεση του τραπεζιού με το σημείο πώλησης και το αποτέλεσμα του GetTables.",
            "Έλεγχος απαραίτητων τύπων παραστατικών στο τραπέζι Αυτοπαράδοσης": "Σύνδεσε τους απαραίτητους τύπους παραστατικών στο τραπέζι Αυτοπαράδοσης.",
            "Έλεγχος ύπαρξης Απόδειξης Κλεισίματος": "Έλεγξε ότι υπάρχει ένας σωστός τύπος Απόδειξης Κλεισίματος με τις απαιτούμενες παραμέτρους.",
            "Έλεγχος Σημείου Πώλησης για Απόδειξη Κλεισίματος": "Συμπλήρωσε το SalesStationClosureNoteOID στο σημείο πώλησης που εμφανίζεται στο αποτέλεσμα.",
            "Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης για Απόδειξη Κλεισίματος": "Πρόσθεσε τον σωστό μετασχηματισμό στο TblSnNoteNext.",
            "Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης": "Πρόσθεσε τον σωστό μετασχηματισμό στο TblSnNoteNext.",
            "Έλεγχος Closure NoteType στα τραπέζια": "Σύνδεσε την Απόδειξη Κλεισίματος στα κανονικά τραπέζια. Τα τραπέζια Αυτοπαράδοσης εξαιρούνται.",
            "Έλεγχος Εκδιδόμενου για παραστατικά Προσωρινών": "Άλλαξε το NoteTypeIssue ώστε οι τύποι προσωρινής απόδειξης να είναι εκδιδόμενοι.",
            "Έλεγχος Ομάδας Προσωρινής Απόδειξης": (
                "Άλλαξε το NoteTypeGroupPos σε 2 στα παραστατικά Προσωρινής Απόδειξης "
                "που εμφανίζονται στο αποτέλεσμα."
            ),            
            "Έλεγχος myDATA Special Category 12": "Συμπλήρωσε τη σωστή ειδική κατηγορία myDATA στα παραστατικά που εμφανίζονται.",
            "SQL Error": "Δες το μήνυμα SQL και το log για την ακριβή τεχνική αιτία."
        }
        return hints.get(title, "Έλεγξε τις λεπτομέρειες του αποτελέσματος και διόρθωσε τη σχετική ρύθμιση.")

    def run(self) -> None:
        """Ξεκινάει το GUI."""
        try:
            self.root.mainloop()
        finally:
            self.close_existing_connection()
            AppLogger.info("Η εφαρμογή έκλεισε.")



# ==========================================================
# Results dashboard window
# ==========================================================

class ResultsDashboardWindow(ctk.CTkToplevel):
    """Ξεχωριστό παράθυρο dashboard για τα αποτελέσματα των ελέγχων."""

    def __init__(self, parent, results: Iterable[CheckResult], database_name: str = "", server_name: str = ""):
        super().__init__(parent)

        self.results = list(results)
        self.database_name = database_name
        self.server_name = server_name
        self.result_cards: List[Any] = []
        self.results_list_frame = None
        self.detail_box = None
        self.detail_title_var = ctk.StringVar(value="Λεπτομέρειες")
        self.summary_status_var = ctk.StringVar(value="")
        self.summary_total_var = ctk.StringVar(value="")
        self.summary_success_var = ctk.StringVar(value="")
        self.summary_error_var = ctk.StringVar(value="")

        self.title("Αποτελέσματα Ελέγχου Σεναρίου")
        set_tk_window_icon(self, "moonhard.ico")
        self.geometry("1180x760")
        self.minsize(980, 660)
        self.transient(parent)
        self.focus()

        self.build_ui()
        self.render_results_dashboard()
        self.bind("<Escape>", lambda event: self.destroy())

    def build_ui(self) -> None:
        """Δημιουργεί το dashboard αποτελεσμάτων."""
        main_frame = ctk.CTkFrame(self, corner_radius=18)
        main_frame.pack(fill="both", expand=True, padx=18, pady=18)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header_frame,
            text="Αποτελέσματα Ελέγχου Σεναρίου Προσωρινών Αποδείξεων",
            font=("Arial", 24, "bold"),
            anchor="w"
        )
        title.grid(row=0, column=0, sticky="ew")

        db_text = ""
        if self.database_name or self.server_name:
            db_text = f"Server: {self.server_name or '-'}    Database: {self.database_name or '-'}"

        subtitle = ctk.CTkLabel(
            header_frame,
            text=db_text,
            font=("Arial", 13),
            anchor="w"
        )
        subtitle.grid(row=1, column=0, sticky="ew", pady=(3, 0))

        close_button = ctk.CTkButton(
            header_frame,
            text="Κλείσιμο",
            width=120,
            command=self.destroy
        )
        close_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))

        summary_frame = ctk.CTkFrame(main_frame, corner_radius=16)
        summary_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        summary_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            summary_frame,
            textvariable=self.summary_status_var,
            font=("Arial", 19, "bold"),
            anchor="w"
        ).grid(row=0, column=0, columnspan=4, sticky="ew", padx=16, pady=(14, 8))

        ctk.CTkLabel(summary_frame, textvariable=self.summary_total_var, font=("Arial", 14, "bold")).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))
        ctk.CTkLabel(summary_frame, textvariable=self.summary_success_var, font=("Arial", 14, "bold")).grid(row=1, column=1, sticky="w", padx=16, pady=(0, 14))
        ctk.CTkLabel(summary_frame, textvariable=self.summary_error_var, font=("Arial", 14, "bold")).grid(row=1, column=2, sticky="w", padx=16, pady=(0, 14))

        results_area = ctk.CTkFrame(main_frame, fg_color="transparent")
        results_area.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))
        results_area.grid_columnconfigure(0, weight=1)
        results_area.grid_columnconfigure(1, weight=2)
        results_area.grid_rowconfigure(0, weight=1)

        list_container = ctk.CTkFrame(results_area, corner_radius=16)
        list_container.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        list_container.grid_rowconfigure(1, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            list_container,
            text="Λίστα Ελέγχων",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))

        self.results_list_frame = ctk.CTkScrollableFrame(list_container, corner_radius=12)
        self.results_list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.results_list_frame.grid_columnconfigure(0, weight=1)

        details_container = ctk.CTkFrame(results_area, corner_radius=16)
        details_container.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        details_container.grid_rowconfigure(1, weight=1)
        details_container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            details_container,
            textvariable=self.detail_title_var,
            font=("Arial", 16, "bold"),
            anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))

        self.detail_box = ctk.CTkTextbox(
            details_container,
            font=("Consolas", 13),
            wrap="word"
        )
        self.detail_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def render_results_dashboard(self) -> None:
        """Εμφανίζει τα αποτελέσματα σαν dashboard με κάρτες και panel λεπτομερειών."""
        success_count = sum(1 for result in self.results if result.success)
        error_count = len(self.results) - success_count

        if error_count:
            self.summary_status_var.set("❌ Βρέθηκαν προβλήματα που χρειάζονται έλεγχο")
        else:
            self.summary_status_var.set("✅ Όλοι οι έλεγχοι ολοκληρώθηκαν επιτυχώς")

        self.summary_total_var.set(f"Σύνολο: {len(self.results)}")
        self.summary_success_var.set(f"✅ Επιτυχείς: {success_count}")
        self.summary_error_var.set(f"❌ Προβλήματα: {error_count}")

        self.clear_result_cards()

        failed_results = [result for result in self.results if not result.success]
        successful_results = [result for result in self.results if result.success]

        row_index = 0
        if failed_results:
            row_index = self.add_results_section_title("Προβλήματα", row_index)
            for original_index, result in [(self.results.index(item) + 1, item) for item in failed_results]:
                self.create_result_card(row_index, original_index, result)
                row_index += 1

        row_index = self.add_results_section_title("Επιτυχημένοι έλεγχοι", row_index)
        for original_index, result in [(self.results.index(item) + 1, item) for item in successful_results]:
            self.create_result_card(row_index, original_index, result)
            row_index += 1

        if failed_results:
            self.select_result_card(self.results.index(failed_results[0]) + 1, failed_results[0])
        elif self.results:
            self.select_result_card(1, self.results[0])
        else:
            self.write_detail("Δεν υπάρχουν αποτελέσματα.")

    def add_results_section_title(self, title: str, row_index: int) -> int:
        """Προσθέτει τίτλο ενότητας στη λίστα ελέγχων."""
        if self.results_list_frame is None:
            return row_index

        label = ctk.CTkLabel(
            self.results_list_frame,
            text=title,
            font=("Arial", 14, "bold"),
            anchor="w"
        )
        label.grid(row=row_index, column=0, sticky="ew", padx=8, pady=(10, 4))
        return row_index + 1

    def create_result_card(self, row_index: int, display_index: int, result: CheckResult) -> None:
        """Δημιουργεί μία κάρτα αποτελέσματος."""
        if self.results_list_frame is None:
            return

        icon = "✅" if result.success else "❌"
        status_text = "OK" if result.success else "Θέλει διόρθωση"
        short_message = self.get_short_message(result.message)

        card = ctk.CTkFrame(self.results_list_frame, corner_radius=14)
        card.grid(row=row_index, column=0, sticky="ew", padx=6, pady=5)
        card.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            card,
            text=f"{icon} {display_index}. {result.title}",
            font=("Arial", 13, "bold"),
            anchor="w",
            wraplength=360,
            justify="left"
        )
        title.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))

        status = ctk.CTkLabel(
            card,
            text=status_text,
            font=("Arial", 12, "bold"),
            anchor="w"
        )
        status.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 2))

        preview = ctk.CTkLabel(
            card,
            text=short_message,
            font=("Arial", 12),
            anchor="w",
            wraplength=360,
            justify="left"
        )
        preview.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        for widget in (card, title, status, preview):
            widget.bind("<Button-1>", lambda event, idx=display_index, res=result: self.select_result_card(idx, res))

        self.result_cards.append(card)

    def select_result_card(self, display_index: int, result: CheckResult) -> None:
        """Εμφανίζει τις λεπτομέρειες του επιλεγμένου ελέγχου."""
        icon = "✅" if result.success else "❌"
        explanation = CHECK_EXPLANATIONS.get(result.title, "Δεν υπάρχει διαθέσιμη περιγραφή για αυτόν τον έλεγχο.")
        self.detail_title_var.set(f"{icon} {display_index}. {result.title}")

        details = [
            "ΤΙ ΕΛΕΓΧΕΙ",
            explanation,
            "",
            "ΑΠΟΤΕΛΕΣΜΑ",
            result.message.strip()
        ]

        if not result.success:
            details.extend([
                "",
                "ΤΙ ΝΑ ΚΑΝΕΙΣ",
                self.get_fix_hint(result.title)
            ])

        self.write_detail("\n".join(details))

    def write_detail(self, message: str) -> None:
        """Γράφει κείμενο στο panel λεπτομερειών."""
        if self.detail_box is None:
            return
        self.detail_box.delete("1.0", "end")
        self.detail_box.insert("end", message)

    def clear_result_cards(self) -> None:
        """Καθαρίζει τις κάρτες αποτελεσμάτων."""
        if self.results_list_frame is None:
            return
        for widget in self.results_list_frame.winfo_children():
            widget.destroy()
        self.result_cards = []

    def get_short_message(self, message: str) -> str:
        """Επιστρέφει σύντομη περίληψη αποτελέσματος."""
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        if not lines:
            return "Δεν υπάρχουν λεπτομέρειες."
        text = lines[0]
        if len(text) > 120:
            return text[:117] + "..."
        return text

    def get_fix_hint(self, title: str) -> str:
        """Επιστρέφει σύντομη οδηγία διόρθωσης ανά έλεγχο."""
        hints = {
            "Τεχνικός έλεγχος δομής βάσης": "Έλεγξε αν η βάση είναι σωστής έκδοσης και αν λείπουν πίνακες ή πεδία.",
            "Έλεγχος για τραπέζι Αυτοπαράδοσης": "Δημιούργησε ή όρισε ένα τραπέζι Αυτοπαράδοσης με TableSelfDelivery = 1.",
            "Έλεγχος ενεργοποίησης στο σημείο πώλησης του τραπεζιού Αυτοπαράδοσης": "Έλεγξε τη σύνδεση του τραπεζιού με το σημείο πώλησης και το αποτέλεσμα του GetTables.",
            "Έλεγχος απαραίτητων τύπων παραστατικών στο τραπέζι Αυτοπαράδοσης": "Σύνδεσε τους απαραίτητους τύπους παραστατικών στο τραπέζι Αυτοπαράδοσης.",
            "Έλεγχος ύπαρξης Απόδειξης Κλεισίματος": "Έλεγξε ότι υπάρχει ένας σωστός τύπος Απόδειξης Κλεισίματος με τις απαιτούμενες παραμέτρους.",
            "Έλεγχος Σημείου Πώλησης για Απόδειξη Κλεισίματος": "Συμπλήρωσε το SalesStationClosureNoteOID στο σημείο πώλησης που εμφανίζεται στο αποτέλεσμα.",
            "Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης για Απόδειξη Κλεισίματος": "Πρόσθεσε τον σωστό μετασχηματισμό στο TblSnNoteNext.",
            "Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης": "Πρόσθεσε τον σωστό μετασχηματισμό στο TblSnNoteNext.",
            "Έλεγχος Closure NoteType στα τραπέζια": "Σύνδεσε την Απόδειξη Κλεισίματος στα κανονικά τραπέζια. Τα τραπέζια Αυτοπαράδοσης εξαιρούνται.",
            "Έλεγχος Εκδιδόμενου για παραστατικά Προσωρινών": "Άλλαξε το NoteTypeIssue ώστε οι τύποι προσωρινής απόδειξης να είναι εκδιδόμενοι.",
            "Έλεγχος Ομάδας Προσωρινής Απόδειξης": (
                "Άλλαξε το NoteTypeGroupPos σε 2 στα παραστατικά Προσωρινής Απόδειξης "
                "που εμφανίζονται στο αποτέλεσμα."
            ),            
            "Έλεγχος myDATA Special Category 12": "Συμπλήρωσε τη σωστή ειδική κατηγορία myDATA στα παραστατικά που εμφανίζονται.",
            "SQL Error": "Δες το μήνυμα SQL και το log για την ακριβή τεχνική αιτία."
        }
        return hints.get(title, "Έλεγξε τις λεπτομέρειες του αποτελέσματος και διόρθωσε τη σχετική ρύθμιση.")

# ==========================================================
# Formatting helpers
# ==========================================================

CHECK_EXPLANATIONS = {
    "Τεχνικός έλεγχος δομής βάσης": (
        "Ελέγχει αν υπάρχουν στη βάση όλοι οι απαραίτητοι πίνακες και πεδία "
        "που χρειάζεται το σενάριο προσωρινών αποδείξεων."
    ),

    "Έλεγχος για τραπέζι Αυτοπαράδοσης": (
        "Ελέγχει αν υπάρχει τουλάχιστον ένα τραπέζι Αυτοπαράδοσης. "
        "Αυτά είναι τα τραπέζια που χρησιμοποιούνται για το σενάριο προσωρινών αποδείξεων."
    ),

    "Έλεγχος ενεργοποίησης στο σημείο πώλησης του τραπεζιού Αυτοπαράδοσης": (
        "Εκτελεί το GetTables και ελέγχει αν τα τραπέζια Αυτοπαράδοσης "
        "είναι ενεργοποιημένα στο σημείο πώλησης."
    ),

    "Έλεγχος απαραίτητων τύπων παραστατικών στο τραπέζι Αυτοπαράδοσης": (
        "Ελέγχει αν τα τραπέζια Αυτοπαράδοσης έχουν συνδεδεμένους "
        "τους απαραίτητους τύπους παραστατικών: τον τύπο εντολής κουζίνας "
        "και τον τύπο αυτοπαράδοσης."
    ),

    "Έλεγχος ύπαρξης Απόδειξης Κλεισίματος": (
        "Ελέγχει αν υπάρχει σωστά ο τύπος παραστατικού που χρησιμοποιείται "
        "ως Απόδειξη Κλεισίματος."
    ),

    "Έλεγχος Σημείου Πώλησης για Απόδειξη Κλεισίματος": (
        "Ελέγχει αν όλα τα Σημεία Πώλησης έχουν συμπληρωμένο το πεδίο "
        "SalesStationClosureNoteOID, ώστε να ξέρουν ποια Απόδειξη Κλεισίματος "
        "θα χρησιμοποιήσουν."
    ),

    "Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης για Απόδειξη Κλεισίματος": (
        "Ελέγχει αν οι Προσωρινές Αποδείξεις έχουν σωστό μετασχηματισμό "
        "προς την Απόδειξη Κλεισίματος."
    ),

    "Έλεγχος Μετασχηματισμών Προσωρινής Απόδειξης": (
        "Ελέγχει αν οι Προσωρινές Αποδείξεις έχουν σωστό μετασχηματισμό "
        "προς την Απόδειξη Κλεισίματος."
    ),

    "Έλεγχος Closure NoteType στα τραπέζια": (
        "Ελέγχει αν όλα τα κανονικά τραπέζια έχουν συνδεδεμένο τον τύπο "
        "παραστατικού κλεισίματος. Τα τραπέζια Αυτοπαράδοσης, δηλαδή όσα έχουν "
        "TableSelfDelivery = 1, εξαιρούνται από αυτόν τον έλεγχο."
    ),

    "Έλεγχος Εκδιδόμενου για παραστατικά Προσωρινών": (
        "Ελέγχει όλους τους τύπους παραστατικών που ανήκουν στη myDATA κατηγορία 8.6 "
        "και επιβεβαιώνει ότι κανένας δεν είναι μη εκδιδόμενος."
    ),

    "Έλεγχος myDATA Special Category 12": (
        "Ελέγχει αν οι βασικές myDATA κατηγορίες παραστατικών έχουν συμπληρωμένο "
        "το MyDATA_NoteTypeSpecialCategOID με την απαιτούμενη ειδική κατηγορία."
    ),
    
    "Έλεγχος Ομάδας Προσωρινής Απόδειξης": (
        "Ελέγχει αν όλοι οι τύποι παραστατικών Προσωρινής Απόδειξης "
        "με MyDATA_NoteTypeSubCategOID = 49 έχουν NoteTypeGroupPos = 2."
    ),    

    "SQL Error": (
        "Εμφανίζεται όταν κάποιος έλεγχος δεν μπόρεσε να ολοκληρωθεί λόγω SQL ή τεχνικού σφάλματος."
    ),
}

def format_results(results: Iterable[CheckResult]) -> str:
    """Μορφοποιεί τα αποτελέσματα ελέγχων για GUI/CLI με επεξήγηση ανά έλεγχο."""
    result_list = list(results)
    output_lines: List[str] = []
    success_count = 0
    error_count = 0

    for index, result in enumerate(result_list, start=1):
        icon = "✅" if result.success else "❌"
        explanation = CHECK_EXPLANATIONS.get(
            result.title,
            "Δεν υπάρχει διαθέσιμη περιγραφή για αυτόν τον έλεγχο."
        )

        output_lines.append(f"{index}. {icon} {result.title}")
        output_lines.append("")
        output_lines.append("Τι ελέγχει:")
        output_lines.append(explanation)
        output_lines.append("")
        output_lines.append("Αποτέλεσμα:")
        output_lines.append(result.message.strip())
        output_lines.append("-" * 70)

        if result.success:
            success_count += 1
        else:
            error_count += 1

    output_lines.append("Σύνοψη:")
    output_lines.append(f"✅ Επιτυχημένοι έλεγχοι: {success_count}")
    output_lines.append(f"❌ Προβλήματα: {error_count}")

    return "\n".join(output_lines)

# ==========================================================
# Argument parser
# ==========================================================

def parse_args():
    """Διαβάζει τα CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Έλεγχος Σεναρίου Προσωρινών Αποδείξεων"
    )

    parser.add_argument("--udl", default="", help="Path σε UDL αρχείο")
    parser.add_argument("--server", default=r".\SQLEXPRESS", help="SQL Server name")
    parser.add_argument("--database", default="", help="Database name")
    parser.add_argument("--driver", default="", help="ODBC Driver")
    parser.add_argument("--username", default="", help="SQL username")
    parser.add_argument("--password", default="", help="SQL password")
    parser.add_argument("--trusted", action="store_true", help="Χρήση Windows Authentication στο CLI")
    parser.add_argument("--cli", action="store_true", help="Εκτέλεση από γραμμή εντολών αντί για GUI")

    return parser.parse_args()


# ==========================================================
# Main
# ==========================================================

def main() -> None:
    """Κεντρικό σημείο εκκίνησης εφαρμογής."""
    AppLogger()
    args = parse_args()

    if args.cli:
        if not args.udl and not args.database:
            print("Για CLI mode πρέπει να δηλώσεις --udl ή --database.")
            sys.exit(1)

        cli = CliApp(args)
        exit_code = cli.run()
        sys.exit(exit_code)

    app = SqlCheckerGui()
    app.run()


if __name__ == "__main__":
    main()
