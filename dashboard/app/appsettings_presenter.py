"""Κοινή ασφαλής μορφοποίηση AppSettings για GUI και CLI."""

import json
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class AppSettingsPresenter:
    """Προβάλλει μόνο τις γνωστές ρυθμίσεις χωρίς αποκάλυψη διαπιστευτηρίων."""

    SECRET_KEYS = {"password", "pwd", "userid", "uid", "user", "username", "clientauth",
                   "clientauthfo", "subscriptionkey", "apikey", "token", "accesstoken",
                   "authorization", "secret", "key"}

    @staticmethod
    def text(value) -> str:
        """Διατηρεί τις μηδενικές τιμές και διακρίνει τα κενά πεδία."""
        return "—" if value is None or value == "" else str(value)

    @classmethod
    def is_secret(cls, key: str) -> bool:
        """Αναγνωρίζει συνηθισμένα ονόματα ευαίσθητων παραμέτρων."""
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        return normalized in cls.SECRET_KEYS or any(
            word in normalized for word in ("password", "subscriptionkey", "clientauth", "token", "secret"))

    @classmethod
    def connection_parts(cls, value: str) -> dict[str, str]:
        """Διαβάζει τα μη ευαίσθητα στοιχεία από το ήδη προστατευμένο connection string."""
        aliases = {"server": "server", "data source": "server", "database": "database",
                   "initial catalog": "database", "integrated security": "integrated",
                   "trusted_connection": "integrated"}
        result = {}
        for part in (value or "").split(";"):
            key, separator, item = part.partition("=")
            if separator and key.strip().lower() in aliases:
                result[aliases[key.strip().lower()]] = item.strip()
        return result

    @classmethod
    def masked_connection(cls, value: str) -> str:
        """Κρύβει ξανά credentials ακόμη και αν παλαιός server επιστρέψει απροστάτευτη τιμή."""
        # Αποκρύπτει και τιμές μέσα σε εισαγωγικά ή άγκιστρα του connection string.
        pattern = r'(?i)(\b(?:user\s*id|uid|user|username|password|pwd|clientauth|subscriptionkey)\s*=\s*)(\{(?:[^}]|}})*\}|"(?:[^"]|"")*"|\x27(?:[^\x27]|\x27\x27)*\x27|[^;]*)'
        return re.sub(pattern, lambda match: match[1] + "***", value or "")

    @classmethod
    def masked_url(cls, value: str) -> str:
        """Προστατεύει credentials μέσα σε URL χωρίς να ανοίγει εξωτερικές συνδέσεις."""
        if not value:
            return ""
        try:
            parts = urlsplit(value)
            netloc = parts.netloc.rsplit("@", 1)[-1]
            if "@" in parts.netloc:
                netloc = "***@" + netloc
            query = urlencode([(key, "***" if cls.is_secret(key) else item)
                               for key, item in parse_qsl(parts.query, keep_blank_values=True)])
            return urlunsplit((parts.scheme, netloc, parts.path, query, "***" if parts.fragment else ""))
        except ValueError:
            return "Μη έγκυρο URL"

    @classmethod
    def safe_data(cls, data: dict) -> dict:
        """Απορρίπτει raw JSON και κρατά μόνο τα αναμενόμενα πεδία του πρωτοκόλλου."""
        def protect(value):
            """Εφαρμόζει απόκρυψη σε όλες τις γνωστές ενότητες."""
            if isinstance(value, dict):
                return {key: bool(item) if key in ("HasDatabaseUser", "HasDatabasePassword") else
                        ("***" if item else "") if cls.is_secret(str(key)) else
                        cls.masked_connection(str(item or "")) if str(key).lower() == "databaseconnection" else
                        cls.masked_url(str(item or "")) if str(key).lower().endswith("url") else protect(item)
                        for key, item in value.items()}
            if isinstance(value, list):
                return [protect(item) for item in value]
            return value

        summary = data.get("appsettings_summary") or {}
        bo_keys = ("ID", "DatabaseConnection", "DatabaseServer", "DatabaseName", "HasDatabaseUser",
                   "HasDatabasePassword", "UserOID", "email", "ClientAuth", "subscriptionKey")
        return protect({
            "file_found": bool(data.get("file_found")), "file_path": data.get("file_path"),
            "last_read_at": data.get("last_read_at"),
            "selected_bo_connection_id": data.get("selected_bo_connection_id"),
            "appsettings_summary": {key: summary.get(key) for key in
                                    ("AllowedHosts", "MaxRetries", "MaxWaitTimePerInvoice", "initialDate")},
            "bo_connections": [{key: item.get(key) for key in bo_keys if key in item}
                               for item in data.get("bo_connections", []) if isinstance(item, dict)],
            "provider_connections": [{key: item.get(key) for key in ("ID", "BaseURL", "OfflineURL")}
                                     for item in data.get("provider_connections", []) if isinstance(item, dict)]
        })

    @classmethod
    def date(cls, value) -> str:
        """Μορφοποιεί την αρχική ημερομηνία χωρίς αλλαγή της αποθηκευμένης τιμής."""
        try:
            return datetime.strptime(str(value), "%Y%m%d").strftime("%d/%m/%Y")
        except ValueError:
            return cls.text(value)

    @classmethod
    def timestamp(cls, value) -> str:
        """Εμφανίζει την ώρα ανάγνωσης με τη ζώνη ώρας που παρέχει ο server."""
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.strftime("%d/%m/%Y %H:%M:%S %Z")
        except ValueError:
            return cls.text(value)

    @classmethod
    def json(cls, data: dict, selected_id=None) -> str:
        """Επιστρέφει ασφαλές JSON για αντιγραφή και αυτοματισμούς."""
        safe = cls.safe_data(data)
        if selected_id is not None:
            safe["selected_bo_connection_id"] = selected_id
        return json.dumps(safe, ensure_ascii=False, indent=2)
