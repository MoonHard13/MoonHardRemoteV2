"""Προσωρινή, ελεγχόμενη ανάκτηση σελίδων ERP μέσω του υπάρχοντος WebSocket."""

import logging
import time
from dataclasses import dataclass
from queue import Empty, Queue
from threading import RLock
from uuid import uuid4

from app.provider_diagnostic.api_client import ProviderAPIClient
from app.provider_diagnostic.documents import DocumentFields
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ERPDataset:
    records: tuple
    date_from: str
    date_to: str
    issuer_vat: str
    complete: bool
    coverage_complete: bool
    warnings: tuple = ()


class ERPPageBridge:
    TIMEOUT = 75

    def __init__(self, send):
        self.send = send
        self.pending = {}
        self.lock = RLock()

    def accept(self, payload):
        with self.lock:
            pending = self.pending.get(payload.get("request_id"))
            if not pending or payload.get("type") != "provider_diagnostic_erp_page_result":
                return False
            request, queue = pending
            if any(payload.get(name) != request[name] for name in ("client_code", "bo_connection_id")):
                return False
            if payload.get("success") is True and any(payload.get(name) != request[name]
                    for name in ("issuer_vat", "date_from", "date_to", "source")):
                return False
            if not queue.full():
                queue.put_nowait(payload)
            return True

    def close(self):
        with self.lock:
            for _, queue in self.pending.values():
                if not queue.full():
                    queue.put_nowait({"success": False})
            self.pending.clear()

    def request(self, context, start, end, source, before, cancel):
        request_id, queue = str(uuid4()), Queue(maxsize=1)
        payload = {"type": "provider_diagnostic_erp_page", "request_id": request_id,
            "client_code": context.client_code, "bo_connection_id": context.bo_connection_id,
            "issuer_vat": context.issuer_vat, "date_from": start, "date_to": end,
            "source": source, "before_oid": before}
        with self.lock:
            self.pending[request_id] = payload, queue
        try:
            if cancel.is_set():
                raise ProviderAPIError(ErrorCategory.CANCELLED)
            try:
                sent = self.send(payload) if self.send else False
            except Exception:
                raise ProviderAPIError(ErrorCategory.ERP_CONNECTION) from None
            if sent is False:
                raise ProviderAPIError(ErrorCategory.ERP_CONNECTION)
            deadline = time.monotonic() + self.TIMEOUT
            while time.monotonic() < deadline:
                if cancel.is_set():
                    raise ProviderAPIError(ErrorCategory.CANCELLED)
                try:
                    result = queue.get(timeout=0.1)
                    if result.get("success") is not True:
                        raise ProviderAPIError(ErrorCategory.ERP_READ)
                    return result
                except Empty:
                    continue
            raise ProviderAPIError(ErrorCategory.ERP_TIMEOUT)
        finally:
            with self.lock:
                self.pending.pop(request_id, None)


class ERPLoader:
    MAX_RECORDS = 100000
    MAX_PAGES = 1000
    MAX_BYTES = 128 * 1024 * 1024

    @classmethod
    def load(cls, fetch, context, start, end, cancel, progress=None):
        start, end = ProviderAPIClient._date(start), ProviderAPIClient._date(end)
        if start > end:
            raise ProviderAPIError(ErrorCategory.VALIDATION)
        records, seen, warnings = [], set(), set()
        coverage, pages, size = True, 0, 0
        for source in ("pos", "sales"):
            before = None
            while True:
                if cancel.is_set():
                    raise ProviderAPIError(ErrorCategory.CANCELLED)
                if pages >= cls.MAX_PAGES:
                    raise ProviderAPIError(ErrorCategory.DATA_LIMIT)
                result = fetch(context, start, end, source, before, cancel)
                rows = result.get("records")
                if not isinstance(rows, list) or len(rows) > 200 or type(result.get("has_more")) is not bool:
                    raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                pages += 1
                coverage &= result.get("coverage_complete") is True
                notes = result.get("warnings", [])
                if not isinstance(notes, list) or len(notes) > 20 or any(not isinstance(n, str) or len(n) > 500 for n in notes):
                    raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                warnings.update(notes)
                if len(warnings) > 40:
                    raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                last = before
                for row in rows:
                    if cancel.is_set():
                        raise ProviderAPIError(ErrorCategory.CANCELLED)
                    if not isinstance(row, dict) or row.get("issuer_vat") != context.issuer_vat or row.get("source") != source:
                        raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                    oid = row.get("page_oid")
                    identity = row.get("document_id")
                    if (type(oid) is not int or not 1 <= oid <= 2147483647 or (last is not None and oid >= last)
                            or identity != f"{source}:{oid}" or identity in seen):
                        raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                    issued = DocumentFields.issued_date(row.get("dateIssued"))
                    if issued is None or not start <= issued <= end:
                        raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                    projected = DocumentFields.project(row)
                    if type(row.get("issue_date_verified")) is not bool:
                        raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                    projected.update(issue_date_verified=row["issue_date_verified"], document_id=identity, issuer_vat=context.issuer_vat, source=source,
                        response_status=str(row.get("response_status") or "")[:100])
                    size += sum(len(str(v)) for v in projected.values()) * 4
                    if len(records) >= cls.MAX_RECORDS or size > cls.MAX_BYTES:
                        raise ProviderAPIError(ErrorCategory.DATA_LIMIT)
                    records.append(projected)
                    seen.add(identity)
                    last = oid
                if progress:
                    progress({"stage": "ERP", "pages": pages, "records": len(records)})
                if not result["has_more"]:
                    break
                if (pages >= cls.MAX_PAGES or not rows or type(result.get("next_before_oid")) is not int
                        or result["next_before_oid"] != last):
                    raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
                before = last
        if cancel.is_set():
            raise ProviderAPIError(ErrorCategory.CANCELLED)
        logger.info("Ανάκτηση ERP ολοκληρώθηκε. records=%s coverage=%s", len(records), coverage)
        return ERPDataset(tuple(records), start, end, context.issuer_vat, True, coverage, tuple(sorted(warnings)))
