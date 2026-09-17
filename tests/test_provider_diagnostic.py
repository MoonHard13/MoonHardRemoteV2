"""Δοκιμές Phase 1 χωρίς πραγματικά credentials, δίκτυο, SQL Server ή Tk window."""

import ast
import io
import importlib
import json
import logging
import socket
import ssl
import sys
import time
import types
import unittest
import urllib.error
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

from app.provider_diagnostic.api_client import NoRedirectHandler, ProviderAPIClient
from app.provider_diagnostic.context import CustomerContextAdapter
from app.provider_diagnostic.diagnostics import APIDiagnosticStore
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError
from app.provider_diagnostic.models import APIDiagnostic, VerifiedProviderCredentials, ProviderEndpoint
from app.provider_diagnostic.security import SecretRedactor, SecretRedactingFormatter, SECRET_REDACTOR
from app.provider_diagnostic.service import ProviderDiagnosticService
from app.provider_diagnostic.tasks import BackgroundTask


class Response(io.BytesIO):
    """Αντικαθιστά απάντηση HTTPS με πραγματικό buffered byte reader."""

    def __init__(self, body=b"[]", headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def getcode(self):
        return 200


def binding(client="client-one", bo=1):
    return VerifiedProviderCredentials(client, bo, "EL123456789", "fixture-key-only", "test-fixture", "https://einvoice.impact.gr")


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.client = {"client_code": "client-one", "display_name": "Εγκατάσταση", "ws_connected": True}
        self.bo = {"ID": 1, "DatabaseName": "InitialTest", "DatabaseServer": "SQL01",
                   "subscriptionKey": "subscription-is-not-provider-key", "ClientAuth": "***"}
        self.adapter = CustomerContextAdapter(lambda: self.client, lambda: self.bo,
                                               lambda: 1, lambda _: {})

    def test_snapshot_contains_no_secrets_or_guessed_vat(self):
        context = self.adapter.snapshot()
        text = json.dumps(context.to_dict())
        self.assertNotIn("subscription", text.lower())
        self.assertEqual(context.issuer_vat, "")
        self.assertEqual(context.database_name, "InitialTest")
        self.assertFalse(context.provider_ready)

    def test_fallback_to_wrong_bo_is_rejected(self):
        self.bo["ID"] = 2
        context = self.adapter.snapshot()
        self.assertIsNone(context.bo_connection_id)
        self.assertEqual(context.database_name, "")

    def test_verified_binding_must_match_client_and_bo(self):
        for credentials in (binding("another-client"), binding(bo=2)):
            with self.assertRaises(ValueError):
                self.adapter.bind(self.adapter.snapshot(), credentials)

    def test_live_request_is_gated_without_verified_source(self):
        service = ProviderDiagnosticService(self.adapter)
        with self.assertRaises(ProviderAPIError) as result:
            service.probe(service.snapshot(), Event())
        self.assertEqual(result.exception.category, ErrorCategory.CONFIGURATION)
        self.assertEqual(service.diagnostics.entries(), [])

    def test_resolver_makes_only_matching_context_ready(self):
        service = ProviderDiagnosticService(self.adapter, lambda _: binding())
        self.assertTrue(service.snapshot().provider_ready)
        other = ProviderDiagnosticService(self.adapter, lambda _: binding(bo=2))
        self.assertFalse(other.snapshot().provider_ready)

    def test_invalid_or_crashing_resolver_is_safely_gated(self):
        service = ProviderDiagnosticService(self.adapter, lambda _: "wrong-type")
        self.assertFalse(service.snapshot().provider_ready)
        service = ProviderDiagnosticService(self.adapter, Mock(side_effect=ValueError("sensitive")))
        self.assertFalse(service.snapshot().provider_ready)

    def test_masked_or_header_injection_key_is_rejected(self):
        for key in ("***", "", "test\r\nAPIKey: another"):
            with self.assertRaises(ValueError):
                VerifiedProviderCredentials("client-one", 1, "EL123456789", key, "fixture", "https://einvoice.impact.gr")
        self.assertNotIn("fixture-key-only", repr(binding()))


class APIClientTests(unittest.TestCase):
    def setUp(self):
        self.store = APIDiagnosticStore()
        self.opener = Mock()
        self.client = ProviderAPIClient(binding(), self.store, opener=self.opener)

    def test_only_documented_https_get_with_company_key(self):
        self.opener.open.return_value = Response(b'[{"series":"A","number":"1"}]', {"NextPage": "next"})
        page = self.client.get_documents_page("20260901", "20260917")
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "https://einvoice.impact.gr/api/invoice/getdocuments/EL123456789/1/?From=20260901&dateTo=20260917")
        self.assertEqual(request.get_header("Apikey"), "fixture-key-only")
        self.assertEqual(page.next_page, "next")
        self.assertEqual(len(page.documents), 1)
        self.assertTrue(self.store.entries()[0].success)
        self.assertNotIn("fixture-key-only", json.dumps(self.store.entries()[0].to_dict()))

    def test_invalid_date_or_page_produces_no_api_diagnostic(self):
        for start, end, page in (("20260230", "20260301", 1), ("20260917", "20260901", 1),
                                  ("20260901", "20260917", 0), ("20260901", "20260917", True)):
            with self.assertRaises(ProviderAPIError):
                self.client.get_documents_page(start, end, page)
        self.opener.open.assert_not_called()
        self.assertEqual(self.store.entries(), [])

    def test_cancel_before_request_produces_no_api_diagnostic(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(ProviderAPIError) as result:
            self.client.get_documents_page("20260901", "20260917", cancel=cancel)
        self.assertEqual(result.exception.category, ErrorCategory.CANCELLED)
        self.opener.open.assert_not_called()
        self.assertEqual(self.store.entries(), [])

    def test_next_page_404_requires_explicit_page_limit_message(self):
        for body in (b'Page > TotalPageSize', b'{"Message":"Page > TotalPageSize"}',
                b'{"error":"Page number is out of range."}', b'"Page exceeds total page count"'):
            with self.subTest(body=body):
                self.opener.open.side_effect = urllib.error.HTTPError("secret-url", 404, "", {}, io.BytesIO(body))
                with self.assertRaises(ProviderAPIError) as result:
                    self.client.get_documents_page("20260901", "20260917", page=2)
                self.assertEqual(result.exception.category, ErrorCategory.END_OF_LIST)
                self.assertEqual(result.exception.status, 404)
                self.assertNotIn("secret", json.dumps(self.store.entries()[-1].to_dict()))

    def test_generic_or_untrusted_404_body_never_confirms_page_limit(self):
        for body in (b'', b'Not Found', b'{"Message":"Not Found"}',
                b'<html>Page > TotalPageSize</html>', b'{"api_key":"Page > TotalPageSize"}',
                b'{"Message":"fixture-key-only Page > TotalPageSize"}',
                b'{"Message":"Page > TotalPageSize",', b'["Page > TotalPageSize"]',
                b'Page > TotalPageSize' + b' ' * 4096, b'\xff'):
            with self.subTest(body=body):
                self.opener.open.side_effect = urllib.error.HTTPError("secret-url", 404, "", {}, io.BytesIO(body))
                with self.assertRaises(ProviderAPIError) as result:
                    self.client.get_documents_page("20260901", "20260917", page=2)
                self.assertEqual(result.exception.category, ErrorCategory.NOT_FOUND)
                self.assertNotIn("fixture-key-only", json.dumps(self.store.entries()[-1].to_dict()))

    def test_first_page_or_other_status_is_never_classified_as_end_of_list(self):
        for status, page, expected in ((404, 1, ErrorCategory.NOT_FOUND),
                (401, 2, ErrorCategory.AUTHENTICATION), (403, 2, ErrorCategory.AUTHORIZATION),
                (400, 2, ErrorCategory.VALIDATION)):
            with self.subTest(status=status, page=page):
                self.opener.open.side_effect = urllib.error.HTTPError("", status, "", {},
                    io.BytesIO(b'Page > TotalPageSize'))
                with self.assertRaises(ProviderAPIError) as result:
                    self.client.get_documents_page("20260901", "20260917", page=page)
                self.assertEqual(result.exception.category, expected)

    def test_page_limit_body_read_is_bounded_and_read_failure_stays_404(self):
        response = Mock()
        response.read.return_value = b'Page > TotalPageSize'
        self.assertTrue(self.client._declares_page_limit(response))
        response.read.assert_called_once_with(4097)
        response.read.side_effect = TimeoutError()
        self.assertFalse(self.client._declares_page_limit(response))

    def test_cancel_during_error_body_read_never_reports_completion(self):
        cancel = Event()
        class Body(io.BytesIO):
            def read(self, size):
                cancel.set()
                return super().read(size)
        self.opener.open.side_effect = urllib.error.HTTPError("", 404, "", {}, Body(b'Page > TotalPageSize'))
        with self.assertRaises(ProviderAPIError) as result:
            self.client.get_documents_page("20260901", "20260917", page=2, cancel=cancel)
        self.assertEqual(result.exception.category, ErrorCategory.CANCELLED)

    def test_401_and_403_are_not_retried_or_leaked(self):
        for status, category in ((401, ErrorCategory.AUTHENTICATION), (403, ErrorCategory.AUTHORIZATION)):
            with self.subTest(status=status):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = urllib.error.HTTPError("secret-url", status, "secret-body", {}, None)
                with self.assertRaises(ProviderAPIError) as result:
                    self.client.get_documents_page("20260901", "20260917")
                self.assertEqual(result.exception.category, category)
                self.assertEqual(self.opener.open.call_count, 1)
                self.assertNotIn("secret", str(result.exception))

    def test_retry_records_each_real_attempt(self):
        self.opener.open.side_effect = [urllib.error.HTTPError("", 503, "", {}, None), Response()]
        cancel = Mock()
        cancel.is_set.return_value = False
        cancel.wait.return_value = False
        self.client.get_documents_page("20260901", "20260917", cancel=cancel)
        self.assertEqual([row.http_status for row in self.store.entries()], [503, 200])
        cancel.wait.assert_called_once_with(0.5)

    def test_retry_limit_and_exponential_backoff(self):
        self.opener.open.side_effect = urllib.error.URLError(socket.timeout())
        cancel = Mock()
        cancel.is_set.return_value = False
        cancel.wait.return_value = False
        with self.assertRaises(ProviderAPIError) as result:
            self.client.get_documents_page("20260901", "20260917", cancel=cancel)
        self.assertEqual(result.exception.category, ErrorCategory.TIMEOUT)
        self.assertEqual(self.opener.open.call_count, 3)
        self.assertEqual([call.args[0] for call in cancel.wait.call_args_list], [0.5, 1.0])

    def test_certificate_errors_are_not_retried(self):
        self.opener.open.side_effect = urllib.error.URLError(ssl.SSLCertVerificationError("private-detail"))
        with self.assertRaises(ProviderAPIError):
            self.client.get_documents_page("20260901", "20260917")
        self.assertEqual(self.opener.open.call_count, 1)

    def test_invalid_json_and_malformed_or_incomplete_responses(self):
        for response, category in ((Response(b"not json"), ErrorCategory.INVALID_JSON),
                (Response(b"{}"), ErrorCategory.MALFORMED_RESPONSE),
                (Response(b"[1]"), ErrorCategory.MALFORMED_RESPONSE),
                (Response(b"\xff"), ErrorCategory.MALFORMED_RESPONSE),
                (Response(headers={"Content-Length": "99"}), ErrorCategory.INCOMPLETE_RESPONSE)):
            with self.subTest(category=category):
                self.opener.open.return_value = response
                with self.assertRaises(ProviderAPIError) as result:
                    self.client.get_documents_page("20260901", "20260917")
                self.assertEqual(result.exception.category, category)

    def test_oversized_response_is_rejected(self):
        self.client.MAX_RESPONSE_BYTES = 3
        self.opener.open.return_value = Response(b"[{},{}]")
        with self.assertRaises(ProviderAPIError) as result:
            self.client.get_documents_page("20260901", "20260917")
        self.assertEqual(result.exception.category, ErrorCategory.INCOMPLETE_RESPONSE)

    def test_cancellation_during_backoff_prevents_retry(self):
        self.opener.open.side_effect = urllib.error.HTTPError("", 503, "", {}, None)
        cancel = Mock()
        cancel.is_set.return_value = False
        cancel.wait.return_value = True
        with self.assertRaises(ProviderAPIError) as result:
            self.client.get_documents_page("20260901", "20260917", cancel=cancel)
        self.assertEqual(result.exception.category, ErrorCategory.CANCELLED)
        self.assertEqual(self.opener.open.call_count, 1)

    def test_redirect_handler_never_forwards_key(self):
        self.assertIsNone(NoRedirectHandler().redirect_request(None, None, 302, "", {}, "https://another-host"))

    def test_uat_request_and_diagnostics_use_the_configured_host(self):
        credentials = replace(binding(), provider_base_url="https://einvoiceapiuat.impact.gr/")
        client = ProviderAPIClient(credentials, self.store, opener=self.opener)
        self.opener.open.return_value = Response()
        client.get_documents_page("20260901", "20260917")
        request = self.opener.open.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://einvoiceapiuat.impact.gr/"))
        self.assertNotIn("https://einvoice.impact.gr", request.full_url)
        self.assertEqual(request.get_header("Apikey"), "fixture-key-only")
        self.assertTrue(self.store.entries()[0].endpoint.startswith("https://einvoiceapiuat.impact.gr/"))

    def test_production_api_configuration_uses_documented_retrieval_host(self):
        credentials = replace(binding(), provider_base_url="https://einvoiceapi.impact.gr/")
        client = ProviderAPIClient(credentials, self.store, opener=self.opener)
        self.opener.open.return_value = Response()
        client.get_documents_page("20260901", "20260917")
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url,
            "https://einvoice.impact.gr/api/invoice/getdocuments/EL123456789/1/?From=20260901&dateTo=20260917")
        self.assertEqual(request.get_header("Apikey"), "fixture-key-only")
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertEqual(credentials.provider_base_url, "https://einvoiceapi.impact.gr")
        self.assertEqual(self.store.entries()[0].endpoint,
            "https://einvoice.impact.gr" + ProviderAPIClient.ENDPOINT)

    def test_404_has_specific_diagnostic_without_retry_or_alternate_host(self):
        self.opener.open.side_effect = urllib.error.HTTPError("secret-url", 404, "secret-body", {}, None)
        with self.assertRaises(ProviderAPIError) as result:
            self.client.get_documents_page("20260901", "20260917")
        self.assertEqual(result.exception.category, ErrorCategory.NOT_FOUND)
        self.assertIn("404", result.exception.message)
        self.assertNotIn("secret", result.exception.message)
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertEqual(self.store.entries()[0].error_category, "not_found")

    def test_provider_urls_reject_untrusted_targets_before_network(self):
        for url in ("http://einvoiceapiuat.impact.gr/", "https://einvoiceapiuat.impact.gr.evil.invalid/",
                    "https://einvoiceapiuat.impact.gr:8443/", "https://user@einvoiceapiuat.impact.gr/",
                    "https://einvoiceapiuat.impact.gr/?key=value", "https://einvoiceapiuat.impact.gr/other"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                replace(binding(), provider_base_url=url)
        self.opener.open.assert_not_called()

    def test_provider_url_normalization_and_environment(self):
        self.assertEqual(ProviderEndpoint.normalize("https://einvoiceapiuat.impact.gr/api/"),
                         "https://einvoiceapiuat.impact.gr")
        self.assertEqual(ProviderEndpoint.environment("https://einvoiceapiuat.impact.gr/"), "UAT")
        self.assertEqual(ProviderEndpoint.environment("https://einvoiceapi.impact.gr/"), "PRODUCTION")


class DiagnosticsAndSecurityTests(unittest.TestCase):
    def test_store_is_bounded_filterable_and_close_blocks_late_writes(self):
        store = APIDiagnosticStore(limit=2)
        for status in (200, 503, 401):
            store.add(APIDiagnostic(datetime.now(timezone.utc), "endpoint", "read", 1, status, 0, status == 200))
        self.assertEqual(len(store.entries()), 2)
        self.assertEqual(len(store.entries("Errors", "end", "401")), 1)
        store.close()
        store.add(APIDiagnostic(datetime.now(timezone.utc), "endpoint", "read", 1, 200, 0, True))
        self.assertEqual(store.entries(), [])

    def test_named_secrets_and_known_unlabelled_values_are_redacted(self):
        redactor = SecretRedactor()
        for text in ("APIKey=hidden;", "subscriptionKey=hidden;", "ClientSecret='hidden'",
                     "SQLPassword=hidden;", "PWD=hidden with spaces;", "Authorization: Bearer hidden",
                     '{"RefreshToken":"hidden"}'):
            self.assertNotIn("hidden", redactor.redact(text))
        redactor.register("fixture-value")
        self.assertNotIn("fixture-value", redactor.redact("Exception says fixture-value"))
        safe = redactor.redact_object({"APIKey": "hidden", "Message": "APIKey=hidden"})
        self.assertNotIn("hidden", json.dumps(safe))
        self.assertEqual(json.loads(json.dumps(safe)), safe)

    def test_formatter_scrubs_tracebacks(self):
        SECRET_REDACTOR.register("traceback-fixture-secret")
        try:
            raise ValueError("traceback-fixture-secret")
        except ValueError:
            record = logging.LogRecord("test", logging.ERROR, "", 0, "Failed", (), sys.exc_info())
        self.assertNotIn("traceback-fixture-secret", SecretRedactingFormatter().format(record))

    def test_worker_result_is_polled_and_parallel_start_is_rejected(self):
        task = BackgroundTask()
        release = Event()
        self.assertTrue(task.start(lambda _: release.wait(1)))
        self.assertFalse(task.start(lambda _: None))
        release.set()
        deadline = time.monotonic() + 2
        result = None
        while result is None and time.monotonic() < deadline:
            result = task.poll()
            if result is None:
                Event().wait(0.001)
        self.assertEqual(result, (True, None))
        self.assertFalse(task.busy)
        task.close()
        self.assertFalse(task.start(lambda _: None))


class IntegrationTests(unittest.TestCase):
    def test_new_tab_is_adjacent_and_existing_provider_stays(self):
        source = (ROOT / "dashboard/app/views/client_manage_window.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        build = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_build_ui")
        tabs = [node.value.args[0].value for node in build.body if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "add"]
        self.assertEqual(tabs[tabs.index("Provider") + 1], "Provider Diagnostic Center")


class CLITests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Απομονώνουμε μόνο το .env loader, χωρίς πραγματικές ρυθμίσεις ή πρόσβαση.
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = Mock()
        with patch.dict(sys.modules, {"dotenv": dotenv}):
            cls.cli = importlib.import_module("app.provider_diagnostic.cli")

    async def test_context_ignores_other_client_results_and_returns_only_safe_fields(self):
        messages = [
            {"type": "clients_list", "clients": [{"client_code": "client-one", "pc_name": "PC", "ws_connected": True}]},
            {"type": "client_appsettings_result", "client_code": "other", "success": False},
            {"type": "client_appsettings_result", "client_code": "client-one", "success": True,
             "appsettings": {"bo_connections": [{"ID": 2, "DatabaseName": "Wrong"},
                 {"ID": 1, "DatabaseName": "InitialTest", "subscriptionKey": "secret-fixture"}]}}]

        class WebSocket:
            send = AsyncMock()
            recv = AsyncMock(return_value=json.dumps({"type": "dashboard_connected"}))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def __aiter__(self):
                async def replies():
                    for reply in messages:
                        yield json.dumps(reply)
                    request = json.loads(self.send.call_args.args[0])
                    yield json.dumps({**request, "type": "provider_diagnostic_context_result",
                        "success": True, "companies": [{"issuer_vat": "EL012345678", "company_name": "Εταιρεία Α"}],
                        "sql_verified": True, "provider_base_url": "https://einvoice.impact.gr"})
                return replies()

        config = types.SimpleNamespace(dashboard_token="token-fixture", dashboard_websocket_url="wss://fixture.invalid")
        with patch.object(self.cli.websockets, "connect", return_value=WebSocket()):
            result = await self.cli.ProviderDiagnosticCLI().context(config, "client-one", 1)
        self.assertEqual(result["database_name"], "InitialTest")
        self.assertFalse(result["provider_ready"])
        self.assertEqual(result["companies"][0]["issuer_vat"], "EL012345678")
        self.assertNotIn("secret-fixture", json.dumps(result))

    async def _company_cli(self, companies, chosen="", probe=True, documents=None, complete=True):
        class WebSocket:
            def __init__(self):
                self.send = AsyncMock()
                self.recv = AsyncMock(return_value=json.dumps({"type": "dashboard_connected"}))
                self.requests = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def __aiter__(self):
                async def replies():
                    yield json.dumps({"type": "clients_list", "clients": [{"client_code": "client-one", "ws_connected": True}]})
                    yield json.dumps({"type": "client_appsettings_result", "client_code": "client-one", "success": True,
                                      "appsettings": {"bo_connections": [{"ID": 1, "DatabaseName": "InitialTest"}]}})
                    for _ in range(2):
                        request = json.loads(self.send.call_args.args[0])
                        self.requests.append(request)
                        reply = {**request, "type": "provider_diagnostic_context_result", "success": True,
                                 "companies": companies, "sql_verified": True, "provider_base_url": "https://einvoice.impact.gr"}
                        if request.get("issuer_vat"):
                            reply["api_key"] = "cli-private-fixture"
                        yield json.dumps(reply)
                return replies()

        websocket = WebSocket()
        config = types.SimpleNamespace(dashboard_token="token-fixture", dashboard_websocket_url="wss://fixture.invalid")
        from app.provider_diagnostic.documents import DocumentDataset, DocumentFields
        dataset = DocumentDataset(tuple(DocumentFields.project({"series": "AA", "number": number,
            "mark": "123", "invoiceType": "11.1", "totalAmount": 0.1, "totalVatAmount": 0.02,
            "url": "https://einvoice.impact.gr/v/fixture"}) for number in ("1", "2")),
            "20260901", "20260917", 2, "now", complete=complete,
            termination="next_page_absent" if complete else "next_page_404")
        with patch.object(self.cli.websockets, "connect", return_value=websocket), \
                patch.object(self.cli.ProviderDiagnosticService, "probe", return_value={"records": 2}) as request, \
                patch.object(self.cli.ProviderDiagnosticService, "documents", return_value=dataset) as document_request:
            result = await self.cli.ProviderDiagnosticCLI().context(config, "client-one", 1, chosen, probe, documents)
        return result, websocket.requests, document_request if documents is not None else request

    async def test_cli_full_documents_auto_selects_vat_filters_and_exports_safe_fields(self):
        options = {"date_from": "20260901", "date_to": "20260917", "filters": {"number": "2"}}
        result, requests, operation = await self._company_cli([{"issuer_vat": "EL012345678"}],
            probe=False, documents=options)
        self.assertTrue(result["success"])
        self.assertEqual(requests[-1]["issuer_vat"], "EL012345678")
        self.assertEqual(result["summary"]["records"], 2)
        self.assertEqual(result["summary"]["total_amount"], "0.2")
        self.assertEqual(result["visible_records"], 1)
        self.assertEqual(result["documents"][0]["number"], "2")
        self.assertNotIn("cli-private-fixture", json.dumps(result))
        self.assertEqual(operation.call_args.args[1:3], ("20260901", "20260917"))

    async def test_cli_document_url_opening_uses_filtered_record_without_headers(self):
        options = {"date_from": "20260901", "date_to": "20260917", "filters": {"number": "2"}, "open_document": 1}
        with patch.object(self.cli.webbrowser, "open", return_value=True) as browser:
            result, _, _ = await self._company_cli([{"issuer_vat": "EL012345678"}], probe=False, documents=options)
        self.assertTrue(result["success"])
        browser.assert_called_once_with("https://einvoice.impact.gr/v/fixture", new=2)

    async def test_cli_partial_documents_are_available_with_explicit_warning(self):
        result, _, _ = await self._company_cli([{"issuer_vat": "EL012345678"}], probe=False,
            documents={"date_from": "20260901", "date_to": "20260917"}, complete=False)
        self.assertFalse(result["complete"])
        self.assertFalse(result["summary"]["complete"])
        self.assertEqual(len(result["documents"]), 2)
        self.assertIn("404", result["warning"])

    async def test_cli_documents_requires_selection_when_multiple_vats_exist(self):
        result, requests, operation = await self._company_cli(
            [{"issuer_vat": "EL012345678"}, {"issuer_vat": "EL987654321"}],
            probe=False, documents={"date_from": "20260901", "date_to": "20260917"})
        self.assertFalse(result["success"])
        self.assertEqual(len(requests), 1)
        operation.assert_not_called()

    async def test_cli_many_vats_requires_explicit_selection_and_makes_no_provider_call(self):
        companies = [{"issuer_vat": "EL012345678"}, {"issuer_vat": "EL987654321"}]
        result, requests, probe = await self._company_cli(companies)
        self.assertFalse(result["success"])
        self.assertEqual(len(requests), 1)
        self.assertIn("--issuer-vat", result["error"])
        probe.assert_not_called()

    async def test_cli_explicit_company_uses_correct_vat_and_never_exports_key(self):
        companies = [{"issuer_vat": "EL012345678"}, {"issuer_vat": "EL987654321"}]
        result, requests, probe = await self._company_cli(companies, "987654321")
        self.assertTrue(result["success"])
        self.assertEqual(result["issuer_vat"], "EL987654321")
        self.assertEqual(requests[-1]["issuer_vat"], "EL987654321")
        self.assertNotIn("cli-private-fixture", json.dumps(result))
        probe.assert_called_once()

    async def test_cli_single_company_is_automatically_selected(self):
        result, requests, probe = await self._company_cli([{"issuer_vat": "EL012345678"}])
        self.assertTrue(result["success"])
        self.assertEqual(result["issuer_vat"], "EL012345678")
        self.assertEqual(len(requests), 2)
        probe.assert_called_once()

    def test_cli_filters_an_explicit_export(self):
        args = types.SimpleNamespace(diagnostics_file=Mock(), outcome="Errors", endpoint="getdocuments", status="401")
        args.diagnostics_file.stat.return_value.st_size = 100
        args.diagnostics_file.read_text.return_value = json.dumps([
            {"Result": "Failure", "Endpoint": "getdocuments", "HTTP Status": "401"},
            {"Result": "Success", "Endpoint": "getdocuments", "HTTP Status": "200"}])
        self.assertEqual(len(self.cli.ProviderDiagnosticCLI.diagnostics(args)), 1)


class UILogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctk = types.ModuleType("customtkinter")
        ctk.CTkFrame = type("FrameFixture", (), {})
        with patch.dict(sys.modules, {"customtkinter": ctk}):
            cls.module = importlib.import_module("app.provider_diagnostic.ui")

    def test_shortcuts_do_not_capture_hidden_tab_or_entry_copy(self):
        view = self.module.ProviderDiagnosticTab.__new__(self.module.ProviderDiagnosticTab)
        top = Mock()
        callbacks = {}
        top.bind.side_effect = lambda sequence, handler, **kwargs: callbacks.setdefault(sequence, handler)
        view.winfo_toplevel = Mock(return_value=top)
        view._bindings = []
        view._is_active = Mock(return_value=False)
        for method in ("refresh_context", "load_companies", "_focus_company", "_focus_section", "probe", "cancel", "_search", "copy_selected", "export"):
            setattr(view, method, Mock())
        view.tree = Mock()
        view.documents_view = Mock()
        view.tree.winfo_toplevel.return_value = top
        view._bind_shortcuts()
        event = types.SimpleNamespace(widget=view.tree, keysym="F5")
        self.assertIsNone(callbacks["<F5>"](event))
        view.refresh_context.assert_not_called()
        view._is_active.return_value = True
        self.assertEqual(callbacks["<F5>"](event), "break")
        event.keysym = "c"
        entry = Mock()
        entry.winfo_toplevel.return_value = top
        event.widget = entry
        self.assertIsNone(callbacks["<Control-c>"](event))
        view.copy_selected.assert_not_called()

    def test_gui_single_vat_is_selected_without_user_action(self):
        from app.provider_diagnostic.session import ProviderContextSession
        for vats in (("EL012345678",), ("EL012345678", "EL987654321")):
            view = self.module.ProviderDiagnosticTab.__new__(self.module.ProviderDiagnosticTab)
            context = CustomerContextAdapter(lambda: {"client_code": "client-one", "ws_connected": True},
                lambda: {"ID": 1}, lambda: 1, lambda _: {}).snapshot()
            view.session = ProviderContextSession()
            request = view.session.request(context)
            view._closed = False
            view.service = Mock()
            view.service.context.snapshot.return_value = context
            view.company, view.status, view.cancel_button = Mock(), Mock(), Mock()
            view._task = Mock()
            view._task.busy = False
            view.refresh_context = Mock()
            view._request_provider_context = Mock()
            view.handle_context_result({**request, "success": True,
                "companies": [{"issuer_vat": vat, "company_name": "Εταιρεία"} for vat in vats],
                "provider_base_url": "https://einvoiceapiuat.impact.gr", "sql_verified": True})
            if len(vats) == 1:
                view._request_provider_context.assert_called_once_with(vats[0])
            else:
                view._request_provider_context.assert_not_called()

    def test_stale_background_result_does_not_update_new_context_status(self):
        view = self.module.ProviderDiagnosticTab.__new__(self.module.ProviderDiagnosticTab)
        view._closed = False
        view.session = Mock()
        view.session.expire_pending.return_value = False
        view._last_ready = False
        view._scope, view._running_scope = ("client", 2), ("client", 1)
        view._task = Mock()
        view._task.poll.return_value = ({"records": 1}, None)
        view.status, view.probe_button, view.cancel_button = Mock(), Mock(), Mock()
        view.documents_view = Mock()
        view._context = types.SimpleNamespace(provider_ready=False)
        view.refresh_diagnostics, view.after = Mock(), Mock()
        view._poll()
        view.status.configure.assert_not_called()
        view.refresh_diagnostics.assert_called_once()


if __name__ == "__main__":
    unittest.main()
