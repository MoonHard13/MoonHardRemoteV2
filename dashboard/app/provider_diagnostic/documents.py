"""Κοινή ανάκτηση, προβολή και φιλτράρισμα παραστατικών για GUI και CMD."""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from threading import Event
from urllib.parse import parse_qsl, urljoin, urlsplit

from app.provider_diagnostic.api_client import ProviderAPIClient
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError


logger = logging.getLogger(__name__)


class DocumentFields:
    TEXT = ("series", "number", "branchCode", "posId", "dateIssued", "counterPartyVAT",
            "mark", "uid", "authenticationCode", "invoiceType", "dateUpdated")
    FLAGS = ("isViewed", "isAccepted", "isArchivedByIssuer")
    URL_HOSTS = frozenset(("einvoice.impact.gr", "einvoiceportal.impact.gr",
                          "einvoiceportaluat.impact.gr", "einvoiceapp.softonecloud.com"))

    @staticmethod
    def amount(value):
        if isinstance(value, bool) or value is None or len(str(value)) > 50:
            return None
        try:
            result = Decimal(str(value))
            return result if result.is_finite() and -20 <= result.as_tuple().exponent <= 20 and abs(result) < Decimal("1e20") else None
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def safe_url(cls, value):
        if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 33 or ord(c) == 127 for c in value):
            return ""
        try:
            parts = urlsplit(value)
            if (parts.scheme == "https" and parts.hostname in cls.URL_HOSTS
                    and parts.port in (None, 443) and parts.username is None and parts.password is None):
                return value
        except ValueError:
            pass
        return ""

    @classmethod
    def project(cls, row):
        # Κρατάμε μόνο τεκμηριωμένα πεδία και ποτέ ολόκληρο το raw response.
        result = {}
        for name in cls.TEXT:
            value = row.get(name)
            result[name] = str(value)[:500] if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""
        for name in ("totalAmount", "totalVatAmount"):
            value = cls.amount(row.get(name))
            result[name] = str(value) if value is not None else None
        result.update({name: row.get(name) if type(row.get(name)) is bool else None for name in cls.FLAGS})
        result["url"] = cls.safe_url(row.get("url"))
        return result


@dataclass(frozen=True)
class DocumentDataset:
    records: tuple
    date_from: str
    date_to: str
    pages: int
    loaded_at: str

    def filtered(self, series="", number="", invoice_type="", mark=""):
        filters = [(name, value.strip() if name in ("invoiceType", "mark") else value.strip().casefold())
            for name, value in (("series", series), ("number", number), ("invoiceType", invoice_type), ("mark", mark))
            if value.strip()]
        return [row for row in self.records if all(
            (str(row.get(name, "")) == value if name in ("invoiceType", "mark") else
             value in str(row.get(name, "")).casefold()) for name, value in filters)]

    def summary(self):
        total = vat = Decimal(0)
        missing_amounts = missing_vat = with_mark = 0
        types = {}
        for row in self.records:
            amount, tax = DocumentFields.amount(row.get("totalAmount")), DocumentFields.amount(row.get("totalVatAmount"))
            if amount is None:
                missing_amounts += 1
            else:
                total += amount
            if tax is None:
                missing_vat += 1
            else:
                vat += tax
            with_mark += bool(row.get("mark") and row["mark"] != "0")
            name = row.get("invoiceType") or "Μη διαθέσιμο"
            types[name] = types.get(name, 0) + 1
        return {"records": len(self.records), "pages": self.pages, "total_amount": str(total),
                "total_vat": str(vat), "with_mark": with_mark, "without_mark": len(self.records) - with_mark,
                "missing_amounts": missing_amounts, "missing_vat": missing_vat, "invoice_types": types}


class DocumentLoader:
    MAX_PAGES = 1000
    MAX_RECORDS = 100000
    MAX_BYTES = 128 * 1024 * 1024

    def __init__(self, client: ProviderAPIClient):
        self.client = client

    def _next_page(self, value, current, issuer, start, end):
        # Ελέγχουμε το NextPage χωρίς να στέλνουμε κλειδί σε URL της απάντησης.
        if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 33 or ord(c) == 127 for c in value):
            raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
        if value.isascii() and value.isdigit():
            valid = value == str(current + 1)
        else:
            try:
                origin = urlsplit(self.client.base_url)
                parts = urlsplit(urljoin(self.client.base_url + "/", value))
                expected = f"{origin.path}/{issuer}/{current + 1}"
                pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
                names = [name.lower() for name, _ in pairs]
                valid = (parts.scheme == origin.scheme and parts.hostname == origin.hostname
                    and parts.port in (None, 443) and parts.username is None and parts.password is None
                    and not parts.fragment and parts.path.rstrip("/").casefold() == expected.casefold()
                    and len(names) == len(set(names))
                    and not ("to" in names and "dateto" in names)
                    and all(name.lower() in ("from", "to", "dateto") and
                        date == (start if name.lower() == "from" else end) for name, date in pairs))
            except ValueError:
                valid = False
        if not valid:
            raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
        return current + 1

    def load(self, start, end, issuer, cancel: Event, progress=None):
        start, end = self.client._date(start), self.client._date(end)
        if start > end:
            raise ProviderAPIError(ErrorCategory.VALIDATION)
        records, hashes, size, page_number = [], set(), 0, 1
        logger.info("Έναρξη πλήρους ανάκτησης παραστατικών.")
        while True:
            if cancel.is_set():
                raise ProviderAPIError(ErrorCategory.CANCELLED)
            page = self.client.get_documents_page(start, end, page_number, cancel)
            encoded = json.dumps(page.documents, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
            size += len(encoded)
            if size > self.MAX_BYTES or len(records) + len(page.documents) > self.MAX_RECORDS:
                raise ProviderAPIError(ErrorCategory.DATA_LIMIT)
            if page.documents:
                fingerprint = hashlib.sha256(encoded).digest()
                if fingerprint in hashes:
                    raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                hashes.add(fingerprint)
            for row in page.documents:
                if cancel.is_set():
                    raise ProviderAPIError(ErrorCategory.CANCELLED)
                records.append(DocumentFields.project(row))
            if progress:
                progress({"pages": page_number, "records": len(records)})
            logger.info("Ανάκτηση σελίδας παραστατικών. page=%s records=%s", page_number, len(page.documents))
            if not page.next_page:
                break
            if page_number >= self.MAX_PAGES:
                raise ProviderAPIError(ErrorCategory.DATA_LIMIT)
            page_number = self._next_page(page.next_page, page_number, issuer, start, end)
        if cancel.is_set():
            raise ProviderAPIError(ErrorCategory.CANCELLED)
        logger.info("Πλήρης ανάκτηση ολοκληρώθηκε. pages=%s records=%s", page_number, len(records))
        return DocumentDataset(tuple(records), start, end, page_number, datetime.now(timezone.utc).isoformat(timespec="seconds"))
