"""Δοκιμές εταιρειών, απομόνωσης κλειδιών και αποκλειστικής δρομολόγησης."""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

from app.provider_diagnostic.models import DiagnosticContext
from app.provider_diagnostic.session import ProviderContextSession


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


odbc = types.ModuleType("pyodbc")
odbc.connect = Mock()
with patch.dict(sys.modules, {"pyodbc": odbc}):
    reader_module = load_module("diagnostic_context_reader_fixture", "client/app/provider/diagnostic_context.py")
base_router = load_module("diagnostic_base_router_fixture", "server/app/websocket/transmitted_requests.py")
with patch.dict(sys.modules, {"app.websocket.transmitted_requests": base_router}):
    router_module = load_module("diagnostic_router_fixture", "server/app/websocket/provider_diagnostic_requests.py")


def context(bo=1, database="InitialTest"):
    return DiagnosticContext("CLIENT-1", "Εγκατάσταση", bo, "SQL01", database, True)


COMPANIES = [{"issuer_vat": "EL012345678", "company_name": "Εταιρεία Α"},
             {"issuer_vat": "EL987654321", "company_name": "Εταιρεία Β"}]


class CompanyReaderTests(unittest.TestCase):
    def setUp(self):
        odbc.connect.reset_mock()
        self.settings, self.provider, self.connection, self.cursor = Mock(), Mock(), Mock(), Mock()
        self.settings.read_appsettings_production.return_value = {"bo_connections": [
            {"ID": 2, "subscriptionKey": "WRONG-KEY", "DatabaseConnection": "WRONG-DB"},
            {"ID": 1, "subscriptionKey": "fixture-key", "DatabaseConnection": "RIGHT-DB"}],
            "provider_connections": [{"ID": 1, "BaseURL": "https://einvoice.impact.gr/"}]}
        self.provider._to_odbc_connection_string.return_value = "ODBC"
        odbc.connect.return_value = self.connection
        self.connection.cursor.return_value = self.cursor
        self.reader = reader_module.ProviderDiagnosticContextReader(self.settings, self.provider)
        self.cursor.fetchall.side_effect = [[("CompanyAFM",), ("CompanyName",), ("CompanyCode",)],
            [("012345678   ", "Εταιρεία Α", "A"), ("EL012345678", "Υποκατάστημα", "B"),
             ("987654321", "Εταιρεία Β", "C"), (None, "Χωρίς ΑΦΜ", "D"), ("abc", "Λάθος", "E")]]

    def test_multiple_vats_are_distinct_and_initial_zero_survives(self):
        result = self.reader.read(1)
        self.assertTrue(result["success"])
        self.assertEqual([row["issuer_vat"] for row in result["companies"]], ["EL012345678", "EL987654321"])
        self.assertIn("Υποκατάστημα", result["companies"][0]["company_name"])
        self.assertEqual(result["invalid_afm_count"], 2)
        self.assertNotIn("api_key", result)
        self.provider._to_odbc_connection_string.assert_called_once_with("RIGHT-DB")
        self.connection.close.assert_called_once()
        self.cursor.close.assert_called_once()
        self.assertEqual(self.connection.timeout, 30)

    def test_subscription_key_is_taken_from_exact_bo_after_vat_selection(self):
        result = self.reader.read(1, "EL012345678")
        self.assertEqual(result["api_key"], "fixture-key")
        self.assertNotIn("WRONG", json.dumps(result))
        self.assertNotIn("DatabaseConnection", result)

    def test_unknown_company_cannot_receive_key(self):
        result = self.reader.read(1, "EL111111111")
        self.assertFalse(result["success"])
        self.assertNotIn("api_key", result)

    def test_missing_or_duplicate_bo_is_rejected_before_sql(self):
        for rows in ([], [{"ID": 1}, {"ID": 1}]):
            self.settings.read_appsettings_production.return_value = {"bo_connections": rows}
            self.assertFalse(self.reader.read(1)["success"])
        odbc.connect.assert_not_called()

    def test_only_afm_column_is_required(self):
        self.cursor.fetchall.side_effect = [[("CompanyAFM",)], [("GR012345678", "", "")]]
        result = self.reader.read(1)
        self.assertEqual(result["companies"], [{"issuer_vat": "EL012345678", "company_name": ""}])

    def test_errors_never_expose_odbc_details(self):
        odbc.connect.side_effect = RuntimeError("password=private-fixture;server=private-host")
        try:
            with self.assertLogs(reader_module.logger, level="WARNING") as logs:
                result = self.reader.read(1)
            self.assertNotIn("private", json.dumps(result) + " ".join(logs.output))
        finally:
            odbc.connect.side_effect = None

    def test_missing_schema_and_sql_failure_close_resources(self):
        self.cursor.fetchall.side_effect = [[("CompanyCode",)]]
        self.assertFalse(self.reader.read(1)["success"])
        self.connection.close.assert_called_once()
        self.cursor.close.assert_called_once()

    def test_masked_key_is_rejected(self):
        self.settings.read_appsettings_production.return_value["bo_connections"][1]["subscriptionKey"] = "***"
        result = self.reader.read(1, "EL012345678")
        self.assertFalse(result["success"])
        self.assertTrue(result["sql_verified"])
        self.assertNotIn("api_key", result)

    def test_uat_and_production_follow_provider_configuration(self):
        for host in ("einvoiceapiuat.impact.gr", "einvoiceapi.impact.gr", "einvoice.impact.gr"):
            with self.subTest(host=host):
                self.cursor.fetchall.side_effect = [[("CompanyAFM",)], [("012345678", "", "")]]
                self.settings.read_appsettings_production.return_value["provider_connections"] = [
                    {"ID": 1, "BaseURL": f"https://{host}/"}]
                result = self.reader.read(1, "EL012345678")
                self.assertTrue(result["success"])
                self.assertEqual(result["provider_base_url"], f"https://{host}")

    def test_explicit_provider_mapping_does_not_pick_first_or_matching_bo_id(self):
        data = self.settings.read_appsettings_production.return_value
        data["bo_connections"][1]["ProviderConnectionID"] = 7
        data["provider_connections"] = [
            {"ID": 1, "BaseURL": "https://einvoiceapi.impact.gr/"},
            {"ID": 7, "BaseURL": "https://einvoiceapiuat.impact.gr/"}]
        result = self.reader.read(1, "EL012345678")
        self.assertEqual(result["provider_base_url"], "https://einvoiceapiuat.impact.gr")

    def test_missing_ambiguous_or_untrusted_provider_never_releases_key(self):
        for providers in ([], [{"ID": 1, "BaseURL": "https://untrusted.invalid/"}],
                          [{"ID": 1, "BaseURL": "https://einvoiceapi.impact.gr/"},
                           {"ID": 2, "BaseURL": "https://einvoiceapiuat.impact.gr/"}]):
            self.settings.read_appsettings_production.return_value["provider_connections"] = providers
            result = self.reader.read(1, "EL012345678")
            self.assertFalse(result["success"])
            self.assertNotIn("api_key", result)
        odbc.connect.assert_not_called()


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.session = ProviderContextSession()
        request = self.session.request(context())
        self.session.accept({**request, "success": True, "companies": COMPANIES, "sql_verified": True, "provider_base_url": "https://einvoice.impact.gr"}, context())

    def install(self):
        request = self.session.request(context(), COMPANIES[0]["issuer_vat"])
        return request, {**request, "success": True, "companies": COMPANIES, "api_key": "fixture-key", "sql_verified": True, "provider_base_url": "https://einvoice.impact.gr"}

    def test_multiple_companies_have_no_implicit_selection_or_key(self):
        self.assertEqual(len(self.session.companies), 2)
        self.assertEqual(self.session.issuer_vat, "")
        self.assertIsNone(self.session.resolve(context()))

    def test_stale_request_wrong_client_bo_or_database_is_ignored(self):
        request, response = self.install()
        for value, ctx in (({**response, "request_id": "old"}, context()),
                           ({**response, "client_code": "OTHER"}, context()),
                           ({**response, "bo_connection_id": 2}, context()),
                           (response, context(database="Other"))):
            self.assertFalse(self.session.accept(value, ctx))
        self.assertTrue(self.session.accept(response, context()))
        self.assertEqual(self.session.resolve(context()).api_key, "fixture-key")

    def test_company_switch_invalidates_key_and_old_probe_context(self):
        _, response = self.install()
        self.session.accept(response, context())
        self.session.request(context(), COMPANIES[1]["issuer_vat"])
        self.assertIsNone(self.session.resolve(context()))
        self.assertFalse(self.session.accept(response, context()))

    def test_mismatched_company_response_does_not_bind_key(self):
        _, response = self.install()
        self.session.accept({**response, "issuer_vat": COMPANIES[1]["issuer_vat"]}, context())
        self.assertIsNone(self.session.resolve(context()))

    def test_key_expiry_clear_and_cancel_drop_references(self):
        _, response = self.install()
        self.session.accept(response, context())
        with patch("app.provider_diagnostic.session.time.monotonic", return_value=self.session._expires + 1):
            self.assertIsNone(self.session.resolve(context()))
        self.session.clear()
        self.assertFalse(self.session.companies)
        self.assertFalse(self.session.pending)

    def test_pending_timeout_and_cancel_ignore_late_response(self):
        _, response = self.install()
        with patch("app.provider_diagnostic.session.time.monotonic", return_value=self.session._pending[3] + 81):
            self.assertTrue(self.session.expire_pending())
        self.assertFalse(self.session.accept(response, context()))

    def test_missing_or_untrusted_base_url_cannot_bind_credentials(self):
        for value in ("", "https://untrusted.invalid", "http://einvoiceapiuat.impact.gr"):
            _, response = self.install()
            self.session.accept({**response, "provider_base_url": value}, context())
            self.assertIsNone(self.session.resolve(context()))

    def test_uat_credentials_expose_the_actual_environment(self):
        _, response = self.install()
        self.session.accept({**response, "provider_base_url": "https://einvoiceapiuat.impact.gr/"}, context())
        self.assertEqual(self.session.resolve(context()).provider_base_url, "https://einvoiceapiuat.impact.gr")


class DiagnosticRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = Mock()
        self.manager.client_capabilities = {"CLIENT-1": {"provider_diagnostic_v1"}}
        self.manager.send_to_client, self.manager.send_to_dashboard = AsyncMock(return_value=True), AsyncMock()
        self.router = router_module.ProviderDiagnosticRequestRouter(self.manager)
        self.dashboard = object()
        self.request = ProviderContextSession().request(context())

    async def asyncTearDown(self):
        self.router.discard_dashboard(self.dashboard)

    async def test_secret_result_goes_only_to_requester_and_extra_fields_are_dropped(self):
        await self.router.request(self.dashboard, self.request)
        response = {**self.request, "type": "provider_diagnostic_context_result", "success": True,
                    "api_key": "fixture-key", "companies": COMPANIES,
                    "provider_base_url": "https://einvoiceapiuat.impact.gr",
                    "DatabaseConnection": "private", "raw_json": {"password": "private"}}
        await self.router.result("OTHER", response)
        self.manager.send_to_dashboard.assert_not_awaited()
        await self.router.result("CLIENT-1", response)
        self.manager.send_to_dashboard.assert_awaited_once()
        destination, result = self.manager.send_to_dashboard.call_args.args
        self.assertIs(destination, self.dashboard)
        self.assertEqual(result["api_key"], "fixture-key")
        self.assertEqual(result["provider_base_url"], "https://einvoiceapiuat.impact.gr")
        self.assertNotIn("private", json.dumps(result))
        self.assertFalse(self.router.pending)

    async def test_old_client_and_invalid_vat_return_correlated_failure(self):
        for request in ({**self.request, "issuer_vat": "../wrong"}, self.request):
            self.manager.client_capabilities = {}
            await self.router.request(self.dashboard, request)
            self.assertEqual(self.manager.send_to_dashboard.call_args.args[1]["request_id"], request["request_id"])
        self.manager.send_to_client.assert_not_awaited()

    async def test_timeout_disconnect_and_late_result_do_not_leak_key(self):
        await self.router.request(self.dashboard, self.request)
        self.router.discard_dashboard(self.dashboard)
        await self.router.result("CLIENT-1", {**self.request, "type": "provider_diagnostic_context_result", "api_key": "fixture-key"})
        self.manager.send_to_dashboard.assert_not_awaited()
        self.assertFalse(self.router.pending)
