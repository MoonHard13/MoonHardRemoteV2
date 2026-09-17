"""Σύγκριση ασφαλών στιγμιοτύπων με περιορισμένες αμφίβολες αντιστοιχίσεις."""

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.provider_diagnostic.documents import DocumentDataset, DocumentFields
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError


logger = logging.getLogger(__name__)


STATUS_LABELS = {"matched": "Συμφωνούν", "differences": "Διαφορές",
    "matched_missing_fields": "Αντιστοιχίστηκαν · ελλιπή πεδία", "erp_only": "Μόνο ERP",
    "provider_only": "Μόνο Provider", "ambiguous": "Αμφίβολη αντιστοίχιση"}


@dataclass(frozen=True)
class ReconciliationDataset(DocumentDataset):
    erp_records: int = 0
    provider_records: int = 0
    erp_coverage_complete: bool = False
    erp_warnings: tuple = ()

    def filtered(self, series="", number="", invoice_type="", mark="", status=""):
        return [r for r in super().filtered(series, number, invoice_type, mark)
                if not status or r["status"] == status]

    def summary(self):
        return {"records": len(self.records), "erp_records": self.erp_records,
            "provider_records": self.provider_records, "statuses": dict(Counter(r["status"] for r in self.records)),
            "confirmed_erp_only": sum(r["status"] == "erp_only" and r["confirmed"] for r in self.records),
            "confirmed_provider_only": sum(r["status"] == "provider_only" and r["confirmed"] for r in self.records),
            "provider_complete": self.complete, "completion_verified": self.completion_verified,
            "completion_inferred": self.completion_inferred, "termination": self.termination,
            "erp_coverage_complete": self.erp_coverage_complete, "erp_warnings": list(self.erp_warnings),
            "pages": self.pages, "api_date_from": self.api_date_from, "api_date_to": self.api_date_to}


class ReconciliationEngine:
    @staticmethod
    def token(row, name):
        value = str(row.get(name) or "").strip()
        return value.upper() if name == "uid" else ("" if name == "mark" and value == "0" else value)

    @classmethod
    def identity(cls, row):
        if row.get("issue_date_verified") is False:
            return None
        number = cls.token(row, "number")
        number = str(int(number)) if number.isascii() and number.isdigit() else number
        key = (cls.token(row, "series"), number, cls.token(row, "invoiceType"),
               DocumentFields.issued_date(row.get("dateIssued")))
        return key if all(key) else None

    @classmethod
    def index(cls, rows, key):
        result = defaultdict(list)
        for i, row in enumerate(rows):
            token = cls.identity(row) if key == "identity" else cls.token(row, key)
            if token:
                result[token].append(i)
        return result

    @classmethod
    def differences(cls, erp, provider):
        result, unavailable = {}, []
        for name in ("totalAmount", "totalVatAmount", "series", "number", "invoiceType", "dateIssued", "counterPartyVAT", "mark", "uid"):
            a, b = erp.get(name), provider.get(name)
            if name == "dateIssued" and erp.get("issue_date_verified") is False:
                unavailable.append(name)
                continue
            if name in ("totalAmount", "totalVatAmount"):
                a, b = DocumentFields.amount(a), DocumentFields.amount(b)
                if a is not None and b is not None:
                    a, b = (v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for v in (a, b))
            elif name in ("mark", "uid"):
                a, b = cls.token(erp, name), cls.token(provider, name)
            elif name == "dateIssued":
                a, b = DocumentFields.issued_date(a), DocumentFields.issued_date(b)
            else:
                a, b = str(a or "").strip(), str(b or "").strip()
                if name == "counterPartyVAT":
                    a, b = (v.upper().removeprefix("EL").removeprefix("GR") for v in (a, b))
                if name == "number":
                    a, b = (str(int(v)) if v.isascii() and v.isdigit() else v for v in (a, b))
            if a is None or b is None or a == "" or b == "":
                unavailable.append(name)
            elif a != b:
                result[name] = {"erp": str(a), "provider": str(b)}
                if isinstance(a, Decimal):
                    result[name]["delta"] = str(a - b)
        return result, unavailable

    @classmethod
    def compare(cls, erp, provider, cancel):
        if (erp.date_from, erp.date_to) != (provider.date_from, provider.date_to) or not erp.complete:
            raise ProviderAPIError(ErrorCategory.CONFIGURATION)
        e, p = erp.records, provider.records
        coverage_keys = {key: all(cls.token(row, key) for row in p) for key in ("mark", "uid")}
        identity_coverage = all(cls.identity(row) for row in p)
        def missing_confirmed(row):
            return (provider.completion_verified and not provider.invalid_date_count and row.get("issue_date_verified") is not False and
                (not p or any(cls.token(row, key) and coverage_keys[key] for key in coverage_keys)
                    or bool(cls.identity(row) and identity_coverage)))
        ei = {key: cls.index(e, key) for key in ("mark", "uid", "identity")}
        pi = {key: cls.index(p, key) for key in ("mark", "uid", "identity")}
        edges, reverse = {}, defaultdict(set)
        duplicate_e, duplicate_p = set(), set()
        for indexes, duplicates in ((ei, duplicate_e), (pi, duplicate_p)):
            for key in ("mark", "uid"):
                for group in indexes[key].values():
                    if len(group) > 1:
                        duplicates.update(group)
        bases, large_candidates, ambiguous_p = {}, set(), set()
        # Οι μεγάλες ομάδες fallback σημειώνονται μία φορά, χωρίς τετραγωνικές ακμές.
        large_identity = {key for key, group in pi["identity"].items() if len(group) > 20}
        for key in large_identity:
            ambiguous_p.update(pi["identity"][key])
        for i, row in enumerate(e):
            if cancel.is_set():
                raise ProviderAPIError(ErrorCategory.CANCELLED)
            candidates, basis = set(), []
            for key in ("mark", "uid"):
                hits = pi[key].get(cls.token(row, key), [])
                if hits:
                    candidates.update(hits[:20])
                    if len(hits) > 20:
                        large_candidates.add(i)
                    basis.append(key)
            if not candidates:
                identity = cls.identity(row)
                if identity in large_identity:
                    large_candidates.add(i)
                for j in pi["identity"].get(identity, [])[:20]:
                    # Δεν παρακάμπτουμε αντικρουόμενα ισχυρά αναγνωριστικά μέσω αριθμού/σειράς.
                    if not any(cls.token(row, k) and cls.token(p[j], k) and cls.token(row, k) != cls.token(p[j], k)
                            for k in ("mark", "uid")):
                        candidates.add(j)
                        basis = ["series_number_type_date"]
            edges[i], bases[i] = candidates, "+".join(basis)
            for j in candidates:
                reverse[j].add(i)
        result, consumed = [], set()
        def output(a, b, status, basis="", differences=None, unavailable=None, confirmed=False, candidates=None):
            display = a or b
            result.append({**{k: display.get(k) for k in ("series", "number", "invoiceType", "dateIssued", "mark")},
                "status": status, "status_label": STATUS_LABELS[status] + (" · μη επιβεβαιωμένο" if status in ("erp_only", "provider_only") and not confirmed else ""),
                "match_basis": basis, "confirmed": confirmed, "differences": differences or {},
                "unavailable_fields": unavailable or [], "erp": a, "provider": b,
                "candidate_provider_indexes": candidates or [], "erp_amount": a.get("totalAmount") if a else None,
                "provider_amount": b.get("totalAmount") if b else None,
                "erp_vat": a.get("totalVatAmount") if a else None, "provider_vat": b.get("totalVatAmount") if b else None,
                "url": b.get("url", "") if b else ""})
        for i, row in enumerate(e):
            if cancel.is_set():
                raise ProviderAPIError(ErrorCategory.CANCELLED)
            candidates = edges[i]
            if i in duplicate_e or i in large_candidates or len(candidates) > 1 or any(j in duplicate_p or len(reverse[j]) != 1 for j in candidates):
                output(row, None, "ambiguous", bases[i], candidates=sorted(candidates))
            elif candidates:
                j = next(iter(candidates))
                differences, unavailable = cls.differences(row, p[j])
                output(row, p[j], "differences" if differences else "matched_missing_fields" if unavailable else "matched",
                    bases[i], differences, unavailable, confirmed=True)
                consumed.add(j)
            else:
                output(row, None, "erp_only", confirmed=missing_confirmed(row))
        for j, row in enumerate(p):
            if cancel.is_set():
                raise ProviderAPIError(ErrorCategory.CANCELLED)
            if j not in consumed:
                output(None, row, "ambiguous" if j in duplicate_p or j in ambiguous_p or reverse[j] else "provider_only",
                    confirmed=(not (j in duplicate_p or j in ambiguous_p or reverse[j]) and erp.complete and erp.coverage_complete))
        logger.info("Σύγκριση ERP–Provider ολοκληρώθηκε. erp=%s provider=%s results=%s", len(e), len(p), len(result))
        return ReconciliationDataset(records=tuple(result), date_from=provider.date_from, date_to=provider.date_to,
            pages=provider.pages, loaded_at=provider.loaded_at, complete=provider.complete, termination=provider.termination,
            invalid_date_count=provider.invalid_date_count, api_date_from=provider.api_date_from,
            api_date_to=provider.api_date_to, last_page_records=provider.last_page_records,
            erp_records=len(e), provider_records=len(p), erp_coverage_complete=erp.coverage_complete, erp_warnings=erp.warnings)
