import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import pyodbc


logger = logging.getLogger(__name__)


class AppLogger:
    """
    Lightweight logger adapter για τους ελέγχους σε MoonHard client service.
    """

    @staticmethod
    def info(message: str) -> None:
        logger.info(message)

    @staticmethod
    def error(message: str) -> None:
        logger.error(message)

    @staticmethod
    def exception(message: str) -> None:
        logger.exception(message)


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


class SenarioProsorinonService:
    """
    Εκτελεί τους ελέγχους Σεναρίου Προσωρινών Αποδείξεων
    χρησιμοποιώντας DatabaseConnection από BOConnection.
    """

    def run_checks(
        self,
        database_connection: str,
        timeout: int = 60
    ) -> dict[str, Any]:
        """
        Εκτελεί όλους τους ελέγχους και επιστρέφει serializable αποτέλεσμα για dashboard.
        """

        if not database_connection:
            return {
                "success": False,
                "database_name": "",
                "total": 0,
                "success_count": 0,
                "problem_count": 0,
                "results": [],
                "error": "DatabaseConnection is empty."
            }

        connection = None

        try:
            odbc_connection_string = self._to_odbc_connection_string(database_connection)
            connection = pyodbc.connect(odbc_connection_string, timeout=timeout)

            database_name = self._get_database_name(connection)

            checks = SqlChecks(connection)
            check_results = checks.run_all_checks(include_schema_check=True)

            serialized_results = [
                {
                    "success": bool(result.success),
                    "title": str(result.title),
                    "message": str(result.message)
                }
                for result in check_results
            ]

            success_count = sum(1 for result in serialized_results if result["success"])
            problem_count = len(serialized_results) - success_count

            return {
                "success": True,
                "database_name": database_name,
                "total": len(serialized_results),
                "success_count": success_count,
                "problem_count": problem_count,
                "results": serialized_results,
                "error": ""
            }

        except Exception as exc:
            logger.exception("Senario Prosorinon checks failed.")

            return {
                "success": False,
                "database_name": "",
                "total": 0,
                "success_count": 0,
                "problem_count": 0,
                "results": [],
                "error": str(exc)
            }

        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    logger.exception("Failed to close Senario Prosorinon SQL connection.")

    def _get_database_name(self, connection) -> str:
        """
        Επιστρέφει το όνομα της ενεργής βάσης.
        """

        cursor = connection.cursor()
        cursor.execute("SELECT DB_NAME()")
        row = cursor.fetchone()

        if row and row[0]:
            return str(row[0])

        return ""

    def _to_odbc_connection_string(self, connection_string: str) -> str:
        """
        Μετατρέπει SQL Server connection string από appsettings σε ODBC connection string.
        """

        parts = self._parse_connection_string(connection_string)

        server = parts.get("server", "")
        database = parts.get("database", "")
        user_id = parts.get("user_id", "")
        password = parts.get("password", "")
        trust_server_certificate = self._normalize_yes_no_value(
            parts.get("trustservercertificate"),
            default="yes"
        )

        if not server:
            raise ValueError("Missing SQL Server in connection string.")

        if not database:
            raise ValueError("Missing SQL database in connection string.")

        driver = OdbcDriverHelper.get_best_driver()

        connection_parts = [
            f"DRIVER={{driver}}",
            f"SERVER={server}",
            f"DATABASE={database}",
            "Encrypt=no",
            f"TrustServerCertificate={trust_server_certificate}",
        ]

        if user_id or password:
            connection_parts.append(f"UID={user_id}")
            connection_parts.append(f"PWD={password}")
        else:
            connection_parts.append("Trusted_Connection=yes")

        return ";".join(connection_parts) + ";"

    def _parse_connection_string(self, connection_string: str) -> dict[str, str]:
        """
        Αναλύει SQL Server connection string σε dictionary.
        """

        result: dict[str, str] = {}

        key_map = {
            "server": "server",
            "data source": "server",
            "database": "database",
            "initial catalog": "database",
            "user id": "user_id",
            "uid": "user_id",
            "password": "password",
            "pwd": "password",
            "trustservercertificate": "trustservercertificate"
        }

        for item in connection_string.split(";"):
            if "=" not in item:
                continue

            key, value = item.split("=", 1)
            normalized_key = re.sub(r"\s+", " ", key.strip().lower())
            mapped_key = key_map.get(normalized_key, normalized_key)

            result[mapped_key] = value.strip()

        return result

    def _normalize_yes_no_value(self, value: str | None, default: str = "yes") -> str:
        """
        Μετατρέπει boolean-like τιμές σε yes/no για ODBC.
        """

        if value is None:
            return default

        normalized = str(value).strip().lower()

        if normalized in ("true", "yes", "1", "y"):
            return "yes"

        if normalized in ("false", "no", "0", "n"):
            return "no"

        return default
