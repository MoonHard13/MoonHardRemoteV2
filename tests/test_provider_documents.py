"""Δοκιμές πλήρους ανάκτησης χωρίς πραγματικό Provider, SQL ή credentials."""

import asyncio
import importlib
import io
import json
import sys
import types
import unittest
import urllib.error
from pathlib import Path
from threading import Event
import time
import tempfile
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

from app.provider_diagnostic.api_client import ProviderAPIClient
from app.provider_diagnostic.diagnostics import APIDiagnosticStore
from app.provider_diagnostic.documents import DocumentDataset, DocumentFields, DocumentLoader
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError
from app.provider_diagnostic.models import DocumentPage, VerifiedProviderCredentials
from app.provider_diagnostic.tasks import BackgroundTask


def row(number="1", **kwargs):
    return {"series": "ΑΑ", "number": number, "invoiceType": "11.1", "mark": "123",
            "totalAmount": 0.1, "totalVatAmount": 0.02, "dateIssued": "2026-09-17T12:00:00", **kwargs}


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.base_url = "https://einvoice.impact.gr/api/invoice/getdocuments"
        self.client._date = ProviderAPIClient._date
        self.loader = DocumentLoader(self.client)
        self.cancel = Event()

    def load(self, progress=None):
        return self.loader.load("20260901", "20260917", "EL012345678", self.cancel, progress)

    def next_url(self, page=2, host="einvoice.impact.gr", query="From=20260831&dateTo=20260918"):
        return f"https://{host}/api/invoice/getdocuments/EL012345678/{page}/?{query}"

    def test_all_pages_follow_header_and_reconstruct_safe_requests(self):
        self.client.get_documents_page.side_effect = [DocumentPage([row()], self.next_url()),
            DocumentPage([row("2")], "/api/invoice/getdocuments/EL012345678/3/?From=20260831&To=20260918"),
            DocumentPage([row("3")])]
        progress = Mock()
        dataset = self.load(progress)
        self.assertEqual(dataset.pages, 3)
        self.assertEqual([r["number"] for r in dataset.records], ["1", "2", "3"])
        self.assertEqual([call.args[2] for call in self.client.get_documents_page.call_args_list], [1, 2, 3])
        self.assertEqual(progress.call_args.args[0], {"pages": 3, "records": 3, "fetched_records": 3})

    def test_one_hundred_records_without_header_does_not_guess_another_page(self):
        self.client.get_documents_page.return_value = DocumentPage([row(str(n)) for n in range(100)])
        self.assertEqual(len(self.load().records), 100)
        self.client.get_documents_page.assert_called_once()

    def test_eleven_pages_then_404_keep_filtered_data_without_claiming_completeness(self):
        pages = [DocumentPage([row(str(p * 100 + n), dateIssued=(
            "2026-09-16T00:00:00" if n % 2 else "2026-08-31T23:59:59")) for n in range(100)], str(p + 2))
            for p in range(11)]
        self.client.get_documents_page.side_effect = pages + [ProviderAPIError(ErrorCategory.NOT_FOUND, 404)]
        result = self.load()
        self.assertEqual((len(result.records), result.fetched_records, result.pages), (550, 1100, 11))
        self.assertEqual(result.excluded_by_date, 550)
        self.assertFalse(result.complete)
        self.assertEqual(result.termination, "next_page_404")
        self.assertIn("404", result.warning)
        self.assertEqual(result.summary()["complete"], False)

    def test_dates_change_results_even_when_provider_returns_identical_rows(self):
        self.client.get_documents_page.return_value = DocumentPage([
            row("start", dateIssued="2026-09-16T00:00:00+03:00"),
            row("end", dateIssued="2026-09-17T23:59:59.999999+03:00"),
            row("outside", dateIssued="2026-09-18"),
            row("compact", dateIssued="20260917"),
            row("missing", dateIssued=None), row("invalid", dateIssued="2026-09-31")])
        result = self.loader.load("20260916", "20260917", "EL012345678", self.cancel)
        self.assertEqual([r["number"] for r in result.records], ["start", "end", "compact"])
        self.assertEqual((result.excluded_by_date, result.invalid_date_count), (1, 2))
        self.assertIn("2", result.warning)
        result = self.loader.load("20260918", "20260918", "EL012345678", self.cancel)
        self.assertEqual([r["number"] for r in result.records], ["outside"])
        result = self.loader.load("20260101", "20260101", "EL012345678", self.cancel)
        self.assertEqual(len(result.records), 0)

    def test_utc_midnight_documents_are_included_and_daily_totals_add_up(self):
        rows = [row(str(n), dateIssued="2026-09-16T12:00:00", dateUpdated="2026-09-16T09:00:00")
            for n in range(42)]
        rows += [row(str(n + 42), dateIssued=f"2026-09-17T00:{n + 1:02d}:00",
            dateUpdated=f"2026-09-16T21:{n + 1:02d}:00") for n in range(5)]
        rows += [row(str(n + 47), dateIssued="2026-09-17T12:00:00", dateUpdated="2026-09-17T09:00:00")
            for n in range(2)]
        def fetch(start, end, page, cancel):
            if page > 1:
                raise ProviderAPIError(ErrorCategory.NOT_FOUND, 404)
            found = [r for r in rows if start <= r["dateUpdated"][:10].replace("-", "") <= end]
            return DocumentPage(found, "2")
        self.client.get_documents_page.side_effect = fetch
        first = self.loader.load("20260916", "20260916", "EL012345678", self.cancel)
        second = self.loader.load("20260917", "20260917", "EL012345678", self.cancel)
        together = self.loader.load("20260916", "20260917", "EL012345678", self.cancel)
        self.assertEqual([len(result.records) for result in (first, second, together)], [42, 7, 49])
        self.assertEqual({r["number"] for r in first.records + second.records},
            {r["number"] for r in together.records})
        self.assertEqual((second.date_from, second.date_to), ("20260917", "20260917"))
        self.assertEqual((second.summary()["api_date_from"], second.summary()["api_date_to"]),
            ("20260916", "20260918"))
        self.assertFalse(second.complete)

    def test_padded_window_is_used_on_every_page_and_header_validation(self):
        self.client.get_documents_page.side_effect = [DocumentPage([row()], self.next_url()),
            DocumentPage([row("2")])]
        self.load()
        for call in self.client.get_documents_page.call_args_list:
            self.assertEqual(call.args[:2], ("20260831", "20260918"))

    def test_request_window_handles_month_year_leap_day_and_calendar_limits(self):
        for start, end, expected in (
            ("20260101", "20260101", ("20251231", "20260102")),
            ("20240301", "20240301", ("20240229", "20240302")),
            ("00010101", "99991231", ("00010101", "99991231"))):
            with self.subTest(start=start, end=end):
                self.assertEqual(DocumentLoader._request_window(start, end), expected)

    def test_first_page_404_remains_an_error(self):
        self.client.get_documents_page.side_effect = ProviderAPIError(ErrorCategory.NOT_FOUND, 404)
        with self.assertRaises(ProviderAPIError) as error:
            self.load()
        self.assertEqual(error.exception.category, ErrorCategory.NOT_FOUND)

    def test_filtered_out_rows_still_count_towards_record_limit(self):
        self.client.get_documents_page.return_value = DocumentPage([row(dateIssued="2026-01-01")])
        with patch.object(self.loader, "MAX_RECORDS", 0), self.assertRaises(ProviderAPIError) as error:
            self.load()
        self.assertEqual(error.exception.category, ErrorCategory.DATA_LIMIT)

    def test_cancellation_during_terminal_404_discards_data(self):
        def fetch(start, end, page, cancel):
            if page == 1:
                return DocumentPage([row()], "2")
            cancel.set()
            raise ProviderAPIError(ErrorCategory.NOT_FOUND, 404)
        self.client.get_documents_page.side_effect = fetch
        with self.assertRaises(ProviderAPIError) as error:
            self.load()
        self.assertEqual(error.exception.category, ErrorCategory.CANCELLED)

    def test_empty_result_is_a_complete_dataset(self):
        self.client.get_documents_page.return_value = DocumentPage([])
        dataset = self.load()
        self.assertEqual(dataset.summary()["records"], 0)
        self.assertEqual(dataset.pages, 1)

    def test_untrusted_changed_or_repeating_next_links_stop_before_another_request(self):
        links = [self.next_url(host="evil.invalid"), self.next_url(page=1), self.next_url(page=3),
                 self.next_url().replace("EL012345678", "EL987654321"),
                 self.next_url(query="From=20260902&dateTo=20260917"),
                 self.next_url(query="From=20260901&From=20260901"),
                 self.next_url(query="From=20260901&dateTo=20260917&APIKey=private"),
                 self.next_url().replace("https://", "http://"),
                 self.next_url().replace("https://", "https://user@"),
                 self.next_url() + "#fragment", "\n2"]
        for link in links:
            with self.subTest(link=link):
                self.client.get_documents_page.reset_mock()
                self.client.get_documents_page.return_value = DocumentPage([row()], link)
                with self.assertRaises(ProviderAPIError) as error:
                    self.load()
                self.assertEqual(error.exception.category, ErrorCategory.MALFORMED_RESPONSE)
                self.client.get_documents_page.assert_called_once()

    def test_numeric_next_page_is_strictly_sequential(self):
        self.client.get_documents_page.side_effect = [DocumentPage([row()], "2"), DocumentPage([row("2")])]
        self.assertEqual(self.load().pages, 2)

    def test_repeated_payload_is_detected_even_with_advancing_links(self):
        self.client.get_documents_page.side_effect = [DocumentPage([row()], self.next_url()), DocumentPage([row()])]
        with self.assertRaises(ProviderAPIError):
            self.load()

    def test_second_page_failure_does_not_return_partial_dataset(self):
        self.client.get_documents_page.side_effect = [DocumentPage([row()], self.next_url()),
            ProviderAPIError(ErrorCategory.TIMEOUT)]
        with self.assertRaises(ProviderAPIError) as error:
            self.load()
        self.assertEqual(error.exception.category, ErrorCategory.TIMEOUT)

    def test_cancel_between_pages_or_after_last_page_never_returns_complete_data(self):
        for link in (self.next_url(), ""):
            with self.subTest(link=link):
                self.cancel.clear()
                self.client.get_documents_page.reset_mock()
                self.client.get_documents_page.return_value = DocumentPage([row()], link)
                with self.assertRaises(ProviderAPIError) as error:
                    self.load(lambda _: self.cancel.set())
                self.assertEqual(error.exception.category, ErrorCategory.CANCELLED)
                self.client.get_documents_page.assert_called_once()

    def test_invalid_dates_do_not_contact_provider(self):
        for start, end in (("20260230", "20260917"), ("20260918", "20260917")):
            with self.assertRaises(ProviderAPIError):
                self.loader.load(start, end, "EL012345678", self.cancel)
        self.client.get_documents_page.assert_not_called()

    def test_page_record_and_memory_limits_report_incomplete_load(self):
        for limit, value in (("MAX_PAGES", 1), ("MAX_RECORDS", 0), ("MAX_BYTES", 1)):
            with self.subTest(limit=limit), patch.object(self.loader, limit, value):
                self.client.get_documents_page.side_effect = None
                self.client.get_documents_page.return_value = DocumentPage([row()], self.next_url())
                with self.assertRaises(ProviderAPIError) as error:
                    self.load()
                self.assertEqual(error.exception.category, ErrorCategory.DATA_LIMIT)

    def test_real_client_records_diagnostics_for_every_loaded_page(self):
        class Response(io.BytesIO):
            def __init__(self, rows, link=""):
                super().__init__(json.dumps(rows).encode())
                self.headers = {"NextPage": link}
            def getcode(self):
                return 200
        store, opener = APIDiagnosticStore(), Mock()
        credentials = VerifiedProviderCredentials("CLIENT", 1, "EL012345678", "fixture-key", "test", "https://einvoiceapi.impact.gr")
        client = ProviderAPIClient(credentials, store, opener=opener)
        opener.open.side_effect = [Response([row()], self.next_url()), Response([row("2")])]
        dataset = DocumentLoader(client).load("20260901", "20260917", credentials.issuer_vat, self.cancel)
        self.assertEqual(dataset.pages, 2)
        self.assertEqual([d.http_status for d in store.entries()], [200, 200])
        self.assertTrue(all(d.records == 1 for d in store.entries()))
        self.assertEqual([d.operation for d in store.entries()], [
            "GetDocumentsPage page=1 From=20260831 dateTo=20260918",
            "GetDocumentsPage page=2 From=20260831 dateTo=20260918"])

    def test_real_terminal_404_remains_a_failed_diagnostic(self):
        class Response(io.BytesIO):
            headers = {"NextPage": "2"}
            def getcode(self):
                return 200
        store, opener = APIDiagnosticStore(), Mock()
        credentials = VerifiedProviderCredentials("CLIENT", 1, "EL012345678", "fixture-key", "test", "https://einvoiceapi.impact.gr")
        opener.open.side_effect = [Response(json.dumps([row()]).encode()),
            urllib.error.HTTPError("https://einvoice.impact.gr", 404, "", {}, None)]
        result = DocumentLoader(ProviderAPIClient(credentials, store, opener=opener)).load(
            "20260901", "20260917", credentials.issuer_vat, self.cancel)
        self.assertFalse(result.complete)
        self.assertEqual([d.http_status for d in store.entries()], [200, 404])
        self.assertFalse(store.entries()[-1].success)

    def test_explicit_provider_page_limit_completes_dataset_and_keeps_http_diagnostic(self):
        class Response(io.BytesIO):
            headers = {"NextPage": "2"}
            def getcode(self):
                return 200
        store, opener = APIDiagnosticStore(), Mock()
        credentials = VerifiedProviderCredentials("CLIENT", 1, "EL012345678", "fixture-key", "test", "https://einvoiceapi.impact.gr")
        opener.open.side_effect = [Response(json.dumps([row()]).encode()),
            urllib.error.HTTPError("", 404, "", {}, io.BytesIO(b'{"Message":"Page > TotalPageSize"}'))]
        result = DocumentLoader(ProviderAPIClient(credentials, store, opener=opener)).load(
            "20260901", "20260917", credentials.issuer_vat, self.cancel)
        self.assertTrue(result.complete)
        self.assertEqual(result.termination, "provider_page_limit")
        self.assertEqual((len(result.records), result.pages), (1, 1))
        self.assertEqual(result.warning, "")
        self.assertIn("Provider", result.status_text)
        self.assertEqual(store.entries()[-1].http_status, 404)
        self.assertEqual(store.entries()[-1].error_category, "end_of_list")
        self.assertFalse(store.entries()[-1].success)

    def test_json_amount_precision_survives_loading_and_summary(self):
        class Response(io.BytesIO):
            headers = {}
            def getcode(self):
                return 200
        opener, store = Mock(), APIDiagnosticStore()
        opener.open.return_value = Response(b'[{"dateIssued":"2026-09-17","totalAmount":123456789012345.12,"totalVatAmount":0.01}]')
        credentials = VerifiedProviderCredentials("CLIENT", 1, "EL012345678", "fixture-key", "test", "https://einvoiceapi.impact.gr")
        client = ProviderAPIClient(credentials, store, opener=opener)
        result = DocumentLoader(client).load("20260901", "20260917", credentials.issuer_vat, self.cancel)
        self.assertEqual(result.summary()["total_amount"], "123456789012345.12")


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.dataset = DocumentDataset(tuple(DocumentFields.project(r) for r in (
            row("1"), row("2", totalAmount=0.2, mark="1234"),
            row("3", invoiceType="1.1", mark=None, totalAmount=None, totalVatAmount=None))),
            "20260901", "20260917", 1, "2026-09-17T12:00:00+00:00")

    def test_summary_uses_decimal_and_tracks_missing_values(self):
        summary = self.dataset.summary()
        self.assertEqual(summary["total_amount"], "0.3")
        self.assertEqual(summary["with_mark"], 2)
        self.assertEqual(summary["without_mark"], 1)
        self.assertEqual(summary["missing_amounts"], 1)
        self.assertEqual(summary["invoice_types"], {"11.1": 2, "1.1": 1})

    def test_filters_combine_substrings_and_exact_type_and_mark(self):
        self.assertEqual(len(self.dataset.filtered(series=" αα ", invoice_type="11.1")), 2)
        self.assertEqual(len(self.dataset.filtered(mark="123")), 1)
        self.assertEqual(len(self.dataset.filtered(number="2", invoice_type="11.1", mark="1234")), 1)
        self.assertEqual(len(self.dataset.filtered(invoice_type="1")), 0)

    def test_raw_credentials_unknown_fields_and_unsafe_url_are_discarded(self):
        projected = DocumentFields.project(row(APIKey="private", raw_json={"password": "private"},
            url="javascript:private", isViewed=False, isAccepted="false"))
        self.assertNotIn("private", json.dumps(projected))
        self.assertIs(projected["isViewed"], False)
        self.assertIsNone(projected["isAccepted"])

    def test_missing_nonfinite_or_boolean_amount_is_not_misrepresented_as_zero(self):
        for value in (None, True, float("nan"), "Infinity", "bad", "1e50"):
            self.assertIsNone(DocumentFields.amount(value))
        self.assertEqual(str(DocumentFields.amount(-12.4)), "-12.4")

    def test_only_https_official_document_links_can_be_opened(self):
        self.assertEqual(DocumentFields.safe_url("https://einvoice.impact.gr/v/test"), "https://einvoice.impact.gr/v/test")
        for url in ("file:///tmp/test", "http://einvoice.impact.gr/v/test", "https://einvoice.impact.gr.evil.invalid/v/test",
                    "https://user@einvoice.impact.gr/v/test", "https://einvoice.impact.gr:8443/v/test"):
            self.assertEqual(DocumentFields.safe_url(url), "")


class ProgressTests(unittest.TestCase):
    def test_progress_retains_only_latest_update(self):
        task = BackgroundTask()
        for page in range(1000):
            task.report_progress({"pages": page})
        self.assertEqual(task.poll_progress(), {"pages": 999})
        self.assertIsNone(task.poll_progress())

    def test_cancel_winning_at_completion_drops_success_result(self):
        task = BackgroundTask()
        def operation(cancel):
            cancel.set()
            return "completed"
        task.start(operation)
        result = None
        deadline = time.monotonic() + 2
        while result is None and time.monotonic() < deadline:
            result = task.poll()
            if result is None:
                Event().wait(0.001)
        self.assertIsNone(result[0])
        self.assertEqual(result[1].category, ErrorCategory.CANCELLED)

    def test_new_task_discards_progress_from_old_task(self):
        task = BackgroundTask()
        task.report_progress({"pages": 99})
        task.start(lambda _: None)
        self.assertIsNone(task.poll_progress())
        task.close()

    def test_cancel_after_worker_finished_but_before_gui_poll_drops_queued_data(self):
        task = BackgroundTask()
        task.start(lambda _: "finished-dataset")
        task._thread.join(timeout=1)
        task.cancel()
        value, error = task.poll()
        self.assertIsNone(value)
        self.assertEqual(error.category, ErrorCategory.CANCELLED)


class PhaseTwoUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = types.ModuleType("customtkinter")
        fixture.CTkFrame = type("FrameFixture", (), {})
        with patch.dict(sys.modules, {"customtkinter": fixture}):
            cls.module = importlib.import_module("app.provider_diagnostic.ui")

    def view(self):
        view = self.module.ProviderDiagnosticTab.__new__(self.module.ProviderDiagnosticTab)
        view._closed, view._last_ready = False, False
        view.session = Mock()
        view.session.expire_pending.return_value = False
        view._task = Mock()
        view._task.poll_progress.return_value = None
        view._scope = view._running_scope = ("CLIENT", 1, "EL012345678")
        view._context = types.SimpleNamespace(provider_ready=True)
        view._running_kind = "documents"
        for name in ("status", "probe_button", "cancel_button", "documents_view", "document_totals",
                     "refresh_diagnostics", "after"):
            setattr(view, name, Mock())
        return view

    def test_complete_dataset_installs_table_and_actual_overview_counts(self):
        view = self.view()
        dataset = DocumentDataset((DocumentFields.project(row()),), "20260901", "20260917", 2, "now")
        view._task.poll.return_value = (dataset, None)
        view._poll()
        view.documents_view.set_dataset.assert_called_once_with(dataset)
        self.assertIn("Παραστατικά: 1", view.document_totals.configure.call_args.kwargs["text"])
        self.assertIn("Σελίδες API: 2", view.document_totals.configure.call_args.kwargs["text"])

    def test_cancelled_or_stale_result_never_installs_table(self):
        for stale in (True, False):
            view = self.view()
            if stale:
                view._running_scope = ("OLD", 1)
            view._task.poll.return_value = (None, ProviderAPIError(ErrorCategory.CANCELLED))
            view._poll()
            view.documents_view.set_dataset.assert_not_called()

    def test_terminal_404_installs_available_data_and_warns_in_status_and_overview(self):
        view = self.view()
        dataset = DocumentDataset((DocumentFields.project(row()),), "20260901", "20260917", 1, "now",
            fetched_records=2, excluded_by_date=1, complete=False, termination="next_page_404")
        view._task.poll.return_value = (dataset, None)
        view._poll()
        view.documents_view.set_dataset.assert_called_once_with(dataset)
        self.assertIn("πληρότητα", view.status.configure.call_args.kwargs["text"])
        overview = view.document_totals.configure.call_args.kwargs["text"]
        self.assertIn("Εκτός διαστήματος: 1", overview)
        self.assertIn("404", overview)
        self.assertNotIn("πλήρης", overview)

    def test_shortcut_closures_keep_their_own_section_rules(self):
        view = self.view()
        top, callbacks = Mock(), {}
        top.bind.side_effect = lambda key, handler, **_: callbacks.setdefault(key, handler)
        view.winfo_toplevel = Mock(return_value=top)
        view._is_active = Mock(return_value=True)
        view._bindings = []
        view.section, view.tree = Mock(), Mock()
        view.section.get.return_value = "Overview"
        view.load_documents = Mock()
        view._bind_shortcuts()
        widget = Mock()
        widget.winfo_toplevel.return_value = top
        event = types.SimpleNamespace(widget=widget, keysym="l")
        self.assertEqual(callbacks["<Control-l>"](event), "break")
        self.assertIsNone(callbacks["<Control-o>"](event))
        view.documents_view.open_url.assert_not_called()
        view.section.get.return_value = "Documents"
        self.assertEqual(callbacks["<Control-o>"](event), "break")

    def test_changing_customer_or_company_clears_dataset_and_cancels_worker(self):
        from app.provider_diagnostic.models import DiagnosticContext
        view = self.view()
        context = DiagnosticContext("NEW", "Εγκατάσταση", 2, "SQL", "DB", True)
        view.service = Mock()
        view.service.snapshot.return_value = context
        view.session.scope.return_value = ("NEW", 2, "SQL", "DB")
        view.session.issuer_vat = "EL012345678"
        view.session.provider_base_url = "https://einvoice.impact.gr"
        view.session.generation = 3
        view.session.sql_verified = True
        view._scope = ("OLD", 1, "SQL", "DB", "EL012345678", "https://einvoice.impact.gr", 2)
        view.context_text = Mock()
        view._update_company_options = Mock()
        view.refresh_context()
        view.documents_view.clear.assert_called_once()
        view._task.cancel.assert_called_once()
        view.session.clear.assert_called_once()


class DocumentsViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = types.ModuleType("customtkinter")
        fixture.CTkFrame = type("FrameFixture", (), {})
        with patch.dict(sys.modules, {"customtkinter": fixture}):
            cls.module = importlib.import_module("app.provider_diagnostic.documents_view")

    def view(self, count=501):
        view = self.module.DocumentsView.__new__(self.module.DocumentsView)
        class Tree:
            def __init__(self):
                self.rows = {}
                self.selected = []
            def get_children(self):
                return tuple(self.rows)
            def delete(self, *children):
                for child in children:
                    del self.rows[child]
                self.selected = []
            def insert(self, parent, position, iid, values):
                self.rows[iid] = values
            def selection(self):
                return self.selected
        view.tree = Tree()
        view._render_job = view._filter_job = None
        view._rows, view._sort_reverse = [], {}
        view.details, view.count, view._status = Mock(), Mock(), Mock()
        view.filters = {name: Mock() for name in ("series", "number", "invoice_type", "mark")}
        for entry in view.filters.values():
            entry.get.return_value = ""
        view.jobs = {}
        def after(delay, callback):
            key = str(len(view.jobs) + 1)
            view.jobs[key] = callback
            return key
        view.after = after
        view.after_cancel = lambda key: view.jobs.pop(key, None)
        dataset = DocumentDataset(tuple(DocumentFields.project(row(str(index))) for index in range(count)),
            "20260901", "20260917", 6, "now")
        view.set_dataset(dataset)
        return view

    def test_large_table_renders_in_batches_and_clear_cancels_pending_insertions(self):
        view = self.view()
        self.assertEqual(len(view.tree.rows), 200)
        while view.jobs:
            key = next(iter(view.jobs))
            callback = view.jobs.pop(key)
            callback()
        self.assertEqual(len(view.tree.rows), 501)
        view.apply_filters()
        self.assertTrue(view.jobs)
        view.clear()
        self.assertFalse(view.jobs)
        self.assertFalse(view.tree.rows)
        self.assertIsNone(view.dataset)

    def test_export_preserves_filter_and_incomplete_metadata(self):
        view = self.view(2)
        view.dataset = DocumentDataset(view.dataset.records, "20260901", "20260917", 1, "now",
            fetched_records=100, excluded_by_date=98, complete=False, termination="next_page_404")
        view.filters["number"].get.return_value = "1"
        view.apply_filters()
        view.winfo_toplevel = Mock()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "documents.json"
            with patch.object(self.module.filedialog, "asksaveasfilename", return_value=str(path)):
                view.export()
            result = json.loads(path.read_text())
        self.assertFalse(result["complete"])
        self.assertEqual(result["summary"]["fetched_records"], 100)
        self.assertIn("404", result["warning"])
        self.assertEqual([r["number"] for r in result["records"]], ["1"])

    def test_filter_sort_and_selected_details_keep_the_correct_record(self):
        view = self.view(20)
        view.filters["number"].get.return_value = "1"
        view.apply_filters()
        view.sort("number")
        self.assertEqual([row["number"] for row in view._rows], ["1", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19"])
        view.tree.selected = ["0"]
        view.show_details()
        self.assertIn('"number": "1"', view.details.insert.call_args.args[1])
        view.sort("number")
        self.assertEqual(view._rows[0]["number"], "19")

    def test_missing_or_unsafe_selected_url_does_not_launch_browser(self):
        view = self.view(1)
        view.tree.selected = ["0"]
        view._rows[0]["url"] = "https://untrusted.invalid"
        with patch.object(self.module.webbrowser, "open") as browser:
            view.open_url()
        browser.assert_not_called()
        view._status.assert_called_once()


if __name__ == "__main__":
    unittest.main()
