import logging
import re
from threading import RLock
from urllib.parse import quote


class SecretRedactor:
    """Αποκρύπτει ονομαστικά secrets και γνωστές τιμές πριν από την καταγραφή."""

    PATTERN = re.compile(
        r"(?i)([\"']?(?:api[_-]?key|subscription[_-]?key|client[_-]?secret|"
        r"clientauth(?:fo)?|(?:bearer|refresh|access|bootstrap|client_instance|dashboard)[_-]?token|"
        r"sql[_-]?password|password|pwd|authorization)[\"']?\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^;,}\]&\r\n]+)"
    )
    BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;\"']+")

    def __init__(self) -> None:
        self._values: set[str] = set()
        self._lock = RLock()

    def register(self, value: str) -> None:
        if value and set(value) != {"*"}:
            with self._lock:
                self._values.update((value, quote(value, safe="")))

    def redact(self, value: object) -> str:
        text = str(value)
        with self._lock:
            secrets = tuple(sorted(self._values, key=len, reverse=True))
        for secret in secrets:
            text = text.replace(secret, "********")
        text = self.BEARER.sub("Bearer ********", text)
        return self.PATTERN.sub(lambda match: match.group(1) + "********", text)

    def redact_object(self, value):
        """Διατηρεί έγκυρο JSON αποκρύπτοντας secrets πριν από το serialization."""
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                sensitive = normalized in {"apikey", "subscriptionkey", "clientsecret", "clientauth",
                    "clientauthfo", "bearertoken", "refreshtoken", "accesstoken", "sqlpassword",
                    "password", "pwd", "authorization", "dashboardtoken", "bootstraptoken", "clientinstancetoken"}
                result[key] = "********" if sensitive else self.redact_object(item)
            return result
        if isinstance(value, list):
            return [self.redact_object(item) for item in value]
        return self.redact(value) if isinstance(value, str) else value


SECRET_REDACTOR = SecretRedactor()


class SecretRedactingFormatter(logging.Formatter):
    """Αποκρύπτει secrets και από το τελικό κείμενο των tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return SECRET_REDACTOR.redact(super().format(record))
