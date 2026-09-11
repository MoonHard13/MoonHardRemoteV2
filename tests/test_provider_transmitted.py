"""Στοχευμένες δοκιμές χωρίς ζωντανή βάση, GUI ή εξωτερικές υπηρεσίες."""

import asyncio
import ast
import importlib.util
import json
import logging
import runpy
import sqlite3
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    """Φορτώνει συγκεκριμένο αρχείο ώστε τα τρία διαφορετικά app packages να μην συγκρούονται."""
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


odbc = types.ModuleType("pyodbc")
odbc.connect = Mock()
with patch.dict(sys.modules, {"pyodbc": odbc}):
    service_module = load_module("transmitted_service_test", "client/app/provider/transmitted_invoices.py")
router_module = load_module("transmitted_router_test", "server/app/websocket/transmitted_requests.py")
Filters = service_module.TransmittedInvoiceFilters
Service = service_module.TransmittedInvoicesService
Router = router_module.TransmittedRequestRouter


class FrameStub:
    """Αντικαθιστά μόνο τον μη διαθέσιμο γραφικό περιέκτη στις δοκιμές λογικής."""

    def destroy(self):
        self.destroyed = True


ctk = types.ModuleType("customtkinter")
ctk.CTkFrame = FrameStub
theme = types.ModuleType("app.ui.theme")
theme.COLORS = theme.FONTS = theme.SPACING = None
theme.apply_treeview_style = theme.primary_button_style = theme.secondary_button_style = Mock()
theme.card_style = theme.danger_button_style = Mock()
with patch.dict(sys.modules, {"customtkinter": ctk, "app.ui.theme": theme}):
    ui = load_module("transmitted_ui_test", "dashboard/app/views/manage/provider_transmitted_window.py")
with patch.dict(sys.modules, {"customtkinter": ctk, "app.ui.theme": theme,
        "app.views.manage.provider_transmitted_window": ui}):
    provider_ui = load_module("provider_tab_test", "dashboard/app/views/manage/provider_tab.py")


class FilterTests(unittest.TestCase):
    """Ελέγχει ανεξάρτητα φίλτρα, αποκλεισμούς και ασφαλή παραμετροποίηση SQL."""

    def test_mark_only(self):
        filters = Filters.from_payload({"mark": " 400001234567890 "})
        query, params = Service.build_query(filters)
        self.assertIsNone(filters.start_date)
        self.assertEqual(params, [101, "400001234567890"])
        self.assertNotIn("400001234567890", query)

    def test_all_filters_are_combined(self):
        filters = Filters.from_payload({"start_date": "20260901", "end_date": "20260910",
            "number": "000123", "mark": "444", "document_type": "note:12", "before_oid": 500, "limit": 50})
        query, params = Service.build_query(filters)
        self.assertEqual(params[0], 51)
        self.assertEqual(params[2].isoformat(), "2026-09-11T00:00:00")
        self.assertEqual(params[3:], ["000123", "444", 500, 12])
        self.assertIn(Service.INVOICE_DATE_SQL + " < ?", query)
        self.assertIn("EXISTS", query)
        self.assertIn("ORDER BY md.MyDATA_ResponseOID DESC", query)

    def test_optional_dates_and_number(self):
        for payload in ({}, {"number": "12"}, {"start_date": "2026-09-01"}, {"end_date": "20260910"}):
            with self.subTest(payload=payload):
                Service.build_query(Filters.from_payload(payload))

    def test_mydata_type_uses_distinct_mapping(self):
        query, params = Service.build_query(Filters.from_payload({"document_type": "mydata:11.1"}))
        self.assertIn("md.MyDATA_ResponseInvoiceType = ?", query)
        self.assertNotIn("pw.SalesPWNoteCode = ?", query)
        self.assertEqual(params, [101, "11.1"])

    def test_bad_values_rejected(self):
        invalid = [{"start_date": "20260230"}, {"start_date": "2026-9-1"},
            {"start_date": "20260911", "end_date": "20260910"}, {"end_date": "99991231"},
            {"number": "x" * 129}, {"mark": "x\nvalue"}, {"mark": 123},
            {"document_type": "note:0"}, {"document_type": "note:9999999999"},
            {"document_type": "note:1; DROP TABLE x"}, {"limit": True}, {"limit": 0},
            {"limit": 201}, {"limit": 1.5}, {"before_oid": -1}, {"before_oid": "1.5"}]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                Filters.from_payload(payload)

    def test_number_and_mark_are_literal_parameters(self):
        value = "' OR 1=1 --"
        query, params = Service.build_query(Filters.from_payload({"number": value, "mark": value}))
        self.assertNotIn(value, query)
        self.assertEqual(params, [101, value, value])
        self.assertNotIn(" LIKE ", query)

    def test_success_and_child_relationship(self):
        query, _ = Service.build_query(Filters.from_payload({}))
        self.assertIn("s.MyDATA_ResponseOID = md.MyDATA_ResponseOID", query)
        self.assertIn("md.MyDATA_ResponseStatusCode = N'Success'", query)
        self.assertIn("OR suc.InvoiceMARK IS NOT NULL", query)
        self.assertIn("MyDATA_ResponseProviderQRCodeLink AS DocumentURL", query)
        for statement in ("DELETE ", "UPDATE ", "INSERT ", "SendInvoice"):
            self.assertNotIn(statement, query)

    def test_older_schema_does_not_reference_optional_success_table(self):
        query, params = Service.build_query(
            Filters.from_payload({"mark": "444"}),
            include_success_table=False,
        )
        self.assertNotIn("TblSnMyDATA_ResponseSuccess", query)
        self.assertNotIn("suc.", query)
        self.assertIn("FROM dbo.TblSnMyDATA_Response AS md", query)
        self.assertIn("md.MyDATA_ResponseStatusCode = N'Success'", query)
        self.assertIn(Service.RESPONSE_MARK_SQL + " IS NOT NULL", query)
        self.assertIn(Service.RESPONSE_MARK_SQL + " = ?", query)
        self.assertEqual(params, [101, "444"])


class DocumentFallbackTests(unittest.TestCase):
    """Εκτελεί τις εκφράσεις fallback σε τοπικά δεδομένα με κενά πεδία απόκρισης."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("""CREATE TABLE responses (
            MyDATA_ResponseOID INTEGER, MyDATA_ResponseSalesTransPosHdr INTEGER,
            MyDATA_ResponseInvoiceDate TEXT, MyDATA_ResponseInvoiceNumber TEXT,
            MyDATA_ResponseInvoiceSeries TEXT)""")
        self.db.execute("""CREATE TABLE pos (
            SalesPWPosHdr INTEGER, SalesPWDate TEXT, SalesPWNoteNo INTEGER, SalesPWNoteRow TEXT)""")
        self.db.executemany("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", [
            (1, 101, None, None, None),
            (2, 102, None, '  ', ' '),
            (3, 103, '2026-09-02 09:00:00', '00045', 'Δ'),
            (4, 104, None, None, None),
            (5, 105, None, None, None)])
        self.db.executemany("INSERT INTO pos VALUES (?, ?, ?, ?)", [
            (101, '2026-09-01 10:00:00', 123, 'Α'),
            (102, '2026-09-01 23:59:00', 124, 'Β'),
            (103, '2026-08-01 09:00:00', 99, 'Γ'),
            (105, '2026-09-02 00:00:00', 125, 'Α')])

    def query(self, where="", params=()):
        """Προσαρμόζει μόνο το πρόθεμα Unicode literal N για τη μηχανή SQLite."""
        query = f"""SELECT md.MyDATA_ResponseOID, {Service.INVOICE_DATE_SQL},
            {Service.NUMBER_SQL}, {Service.SERIES_SQL}
            FROM responses md LEFT JOIN pos doc
              ON doc.SalesPWPosHdr = md.MyDATA_ResponseSalesTransPosHdr
            {where} ORDER BY md.MyDATA_ResponseOID"""
        return self.db.execute(query.replace("N''", "''"), params).fetchall()

    def test_date_search_includes_empty_response_date_and_whole_end_day(self):
        filters = Filters.from_payload({"start_date": "20260901", "end_date": "20260901"})
        rows = self.query(f"WHERE {Service.INVOICE_DATE_SQL} >= ? AND {Service.INVOICE_DATE_SQL} < ?",
            (filters.start_date.isoformat(sep=" "), filters.end_exclusive.isoformat(sep=" ")))
        self.assertEqual([row[0] for row in rows], [1, 2])
        self.assertEqual(rows[0][1:], ('2026-09-01 10:00:00', '123', 'Α'))
        self.assertEqual(rows[1][2:], ('124', 'Β'))

    def test_number_search_matches_displayed_pos_number(self):
        rows = self.query(f"WHERE {Service.NUMBER_SQL} = ?", ('123',))
        self.assertEqual([row[0] for row in rows], [1])

    def test_present_response_metadata_keeps_leading_zeroes(self):
        row = self.query("WHERE md.MyDATA_ResponseOID = ?", (3,))[0]
        self.assertEqual(row[1:], ('2026-09-02 09:00:00', '00045', 'Δ'))

    def test_missing_document_is_not_given_a_fabricated_date(self):
        row = self.query("WHERE md.MyDATA_ResponseOID = ?", (4,))[0]
        self.assertEqual(row[1:], (None, None, None))

    def test_production_select_and_filters_use_the_same_expressions(self):
        query, _ = Service.build_query(Filters.from_payload({"start_date": "20260901", "number": "123"}))
        self.assertGreaterEqual(query.count(Service.INVOICE_DATE_SQL), 2)
        self.assertGreaterEqual(query.count(Service.NUMBER_SQL), 2)
        self.assertIn("pw.SalesPWDate, pw.SalesPWNoteRow, pw.SalesPWNoteNo", query)
        self.assertIn("LEFT JOIN dbo.TblSnNoteType", query)


class ServiceTests(unittest.TestCase):
    """Ελέγχει το όριο ανάκτησης, χρόνους αναμονής και αποφυγή διαρροών στα logs."""

    def setUp(self):
        odbc.connect.reset_mock()
        self.connection, self.cursor = Mock(), Mock()
        odbc.connect.return_value.__enter__ = Mock(return_value=self.connection)
        odbc.connect.return_value.__exit__ = Mock(return_value=False)
        self.connection.cursor.return_value = self.cursor
        self.cursor.description = [(c,) for c in ("ResponseOID", "DocumentURL", "Number", "MARK")]
        self.provider = Mock()
        self.provider._to_odbc_connection_string.return_value = "local-secret-connection"
        self.provider._table_exists.return_value = True
        self.service = Service(self.provider)

    def test_fetch_extra_row_for_next_page(self):
        self.cursor.fetchmany.return_value = [(30, "https://example.invalid/1", "001", "44"),
            (20, None, "002", "45"), (10, "https://example.invalid/3", "003", "46")]
        result = self.service.search("local", {"limit": 2})
        self.assertTrue(result["success"])
        self.assertTrue(result["has_more"])
        self.assertEqual(result["next_before_oid"], 20)
        self.assertEqual(len(result["invoices"]), 2)
        self.assertEqual(result["invoices"][1]["DocumentURL"], "")
        self.assertEqual(self.connection.timeout, 30)
        self.cursor.fetchmany.assert_called_once_with(3)
        self.cursor.fetchall.assert_not_called()

    def test_empty_page(self):
        self.cursor.fetchmany.return_value = []
        result = self.service.search("local", {"mark": "0"})
        self.assertTrue(result["success"])
        self.assertFalse(result["has_more"])
        self.assertIsNone(result["next_before_oid"])

    def test_search_uses_response_only_query_when_success_table_is_missing(self):
        self.provider._table_exists.return_value = False
        self.cursor.fetchmany.return_value = []
        result = self.service.search("local", {"mark": "444"})
        self.assertTrue(result["success"])
        self.provider._table_exists.assert_called_once_with(
            self.cursor,
            "TblSnMyDATA_ResponseSuccess",
        )
        query, params = self.cursor.execute.call_args.args
        self.assertNotIn("TblSnMyDATA_ResponseSuccess", query)
        self.assertNotIn("suc.", query)
        self.assertIn(Service.RESPONSE_MARK_SQL, query)
        self.assertEqual(params, [101, "444"])

    def test_large_page_stays_within_websocket_budget(self):
        self.cursor.fetchmany.return_value = [(i, "https://example.invalid/" + "α" * 3900, "1", "4")
                                             for i in range(201, 0, -1)]
        result = self.service.search("local", {"limit": 200})
        self.assertTrue(result["success"])
        self.assertTrue(result["has_more"])
        self.assertLess(len(result["invoices"]), 200)
        self.assertLess(len(json.dumps(result, ensure_ascii=False).encode("utf-8")), 530000)
        self.assertEqual(result["next_before_oid"], result["invoices"][-1]["ResponseOID"])

    def test_validation_happens_before_database_connect(self):
        result = self.service.search("local", {"start_date": "bad"})
        self.assertFalse(result["success"])
        odbc.connect.assert_not_called()

    def test_oversized_url_is_never_truncated_into_a_different_url(self):
        self.cursor.fetchmany.return_value = [(1, "https://example.invalid/" + "x" * 4096, "1", "4")]
        result = self.service.search("local", {})
        self.assertEqual(result["invoices"][0]["DocumentURL"], "")
        self.assertTrue(result["invoices"][0]["URLNote"])

    def test_database_error_does_not_expose_connection(self):
        self.cursor.execute.side_effect = RuntimeError("local-secret-connection")
        with self.assertLogs(service_module.logger, level="ERROR") as logs:
            result = self.service.search("local", {})
        self.assertFalse(result["success"])
        self.assertNotIn("local-secret", str(result) + str(logs.output))

    def test_error_detail_redacts_sql_credentials(self):
        detail = Service._safe_error_detail(
            RuntimeError(
                "Invalid object; UID=operator;PWD=super-secret;Password=second-secret"
            )
        )
        self.assertIn("Invalid object", detail)
        self.assertNotIn("operator", detail)
        self.assertNotIn("super-secret", detail)
        self.assertNotIn("second-secret", detail)

    def test_types_have_unambiguous_values(self):
        self.cursor.fetchmany.side_effect = [[(1, "Απόδειξη")], [("11.1",), ("bad value",)]]
        result = self.service.get_document_types("local")
        self.assertEqual([t["value"] for t in result["document_types"]], ["note:1", "mydata:11.1"])


class RouterTests(unittest.IsolatedAsyncioTestCase):
    """Ελέγχει πραγματικές ασύγχρονες μεθόδους του router με απομονωμένες συνδέσεις."""

    async def asyncSetUp(self):
        self.manager = types.SimpleNamespace(send_to_dashboard=AsyncMock(), send_to_client=AsyncMock(return_value=True))
        self.router = Router(self.manager)
        self.dashboard = object()
        self.payload = {"type": "provider_transmitted_search", "request_id": str(uuid4()),
                        "client_code": "CLIENT-1", "bo_connection_id": 2, "mark": "444"}

    async def asyncTearDown(self):
        self.router.discard_dashboard(self.dashboard)

    async def test_round_trip_only_to_requesting_dashboard(self):
        await self.router.request(self.dashboard, self.payload)
        result = {**self.payload, "type": "provider_transmitted_search_result", "success": True,
                  "invoices": [{"DocumentURL": "https://example.invalid/private"}]}
        await self.router.result("CLIENT-1", result)
        self.manager.send_to_dashboard.assert_awaited_once_with(self.dashboard, result)
        self.assertFalse(self.router.pending)

    async def test_spoofed_client_or_wrong_bo_cannot_consume_request(self):
        await self.router.request(self.dashboard, self.payload)
        result = {**self.payload, "type": "provider_transmitted_search_result"}
        await self.router.result("OTHER", result)
        await self.router.result("CLIENT-1", {**result, "bo_connection_id": 3})
        await self.router.result("CLIENT-1", {**result, "type": "provider_transmitted_types_result"})
        self.manager.send_to_dashboard.assert_not_awaited()
        self.assertIn(self.payload["request_id"], self.router.pending)

    async def test_unsolicited_or_late_result_is_discarded(self):
        await self.router.result("CLIENT-1", {**self.payload, "type": "provider_transmitted_search_result"})
        self.manager.send_to_dashboard.assert_not_awaited()

    async def test_offline_client_cleans_pending(self):
        self.manager.send_to_client.return_value = False
        await self.router.request(self.dashboard, self.payload)
        self.assertFalse(self.router.pending)
        self.assertFalse(self.manager.send_to_dashboard.call_args.args[1]["success"])

    async def test_timeout_and_disconnect_cleanup(self):
        await self.router.request(self.dashboard, self.payload)
        await self.router._expire(self.payload["request_id"])
        self.assertFalse(self.router.pending)
        self.assertFalse(self.manager.send_to_dashboard.call_args.args[1]["success"])
        await self.router.request(self.dashboard, self.payload)
        self.router.discard_dashboard(self.dashboard)
        self.assertFalse(self.router.pending)

    async def test_invalid_and_duplicate_request(self):
        await self.router.request(self.dashboard, {**self.payload, "request_id": "not-a-uuid"})
        self.manager.send_to_client.assert_not_awaited()
        await self.router.request(self.dashboard, self.payload)
        await self.router.request(self.dashboard, self.payload)
        self.manager.send_to_client.assert_awaited_once()

    async def test_unexpected_fields_are_not_forwarded(self):
        await self.router.request(self.dashboard, {**self.payload, "password": "secret"})
        self.assertNotIn("password", self.manager.send_to_client.call_args.args[1])


class WindowLogicTests(unittest.TestCase):
    """Ελέγχει τη λογική του παραθύρου χωρίς να ισχυρίζεται οπτική δοκιμή Tk."""

    def make_window(self):
        window = object.__new__(ui.TransmittedInvoicesView)
        window.client_code, window.bo_connection_id = "CLIENT-1", 2
        window.pending, window.rows, window.entries = {}, {}, {}
        window.type_values = {"Όλοι οι τύποι": ""}
        window.next_before_oid = None
        window.busy, window.active_filters = False, {"mark": "444"}
        window._initial_load_after_id = None
        window._shortcut_bindings = []
        window._shortcut_parent = Mock()
        for name in ("tree", "status", "url_text", "open_button", "copy_button", "search_button",
                     "clear_button", "type_option", "vertical_scrollbar", "after_cancel"):
            setattr(window, name, Mock())
        window.tree.get_children.return_value = []
        return window

    def test_link_validation(self):
        good = "https://example.invalid/view?id=123&signature=abc%2Bdef"
        self.assertEqual(ui.DocumentLink.validate(good), good)
        for url in ("", "file:///C:/data", "javascript:alert(1)", "//example.com", "https://a:b@example.com/",
                    "https://example.com:99999/", "https://example.com/\n", "https://example.com\\path"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ui.DocumentLink.validate(url)

    def test_stale_or_wrong_context_results_ignored(self):
        window = self.make_window()
        window.pending["r"] = ("provider_transmitted_search", "timer")
        result = {"request_id": "r", "type": "provider_transmitted_search_result",
                  "client_code": "CLIENT-1", "bo_connection_id": 2, "success": True, "invoices": []}
        for changed in ({"client_code": "OTHER"}, {"bo_connection_id": 3}, {"request_id": "old"},
                        {"type": "provider_transmitted_types_result"}):
            window.handle_result({**result, **changed})
        window.after_cancel.assert_not_called()
        window.handle_result(result)
        self.assertNotIn("r", window.pending)
        window.after_cancel.assert_called_once_with("timer")

    def test_error_reenables_search(self):
        window = self.make_window()
        window.busy = True
        window.pending["r"] = ("provider_transmitted_search", "timer")
        window.handle_result({"request_id": "r", "type": "provider_transmitted_search_result",
            "client_code": "CLIENT-1", "bo_connection_id": 2, "success": False, "error": "offline"})
        self.assertFalse(window.busy)
        window.search_button.configure.assert_called_with(state="normal")

    def test_selected_url_opens_on_dashboard_only(self):
        window = self.make_window()
        window.rows = {"1": {"DocumentURL": "https://example.invalid/document"}}
        window.tree.selection.return_value = ("1",)
        with patch.object(ui.webbrowser, "open", return_value=True) as browser:
            window.open_url()
        browser.assert_called_once_with("https://example.invalid/document", new=2)

    def test_missing_url_disables_actions(self):
        window = self.make_window()
        window.rows = {"1": {"DocumentURL": ""}}
        window.tree.selection.return_value = ("1",)
        window._selection_changed()
        window.open_button.configure.assert_called_with(state="disabled")

    def test_load_more_preserves_filters_and_appends_to_same_list(self):
        window = self.make_window()
        window.next_before_oid = 101
        window._fetch_batch = Mock()
        window._load_more()
        window._fetch_batch.assert_called_once_with(101)
        self.assertIsNone(window.next_before_oid)

    def test_scroll_at_bottom_loads_more(self):
        window = self.make_window()
        window.next_before_oid = 101
        window._load_more = Mock()
        window._tree_scrolled("0.70", "0.99")
        window.vertical_scrollbar.set.assert_called_once_with("0.70", "0.99")
        window._load_more.assert_called_once()

    def test_multiple_batches_remain_in_one_list(self):
        window = self.make_window()
        base = {"type": "provider_transmitted_search_result", "client_code": "CLIENT-1",
                "bo_connection_id": 2, "success": True}
        window.pending["r1"] = ("provider_transmitted_search", "timer-1")
        window.handle_result({**base, "request_id": "r1", "has_more": True, "next_before_oid": 50,
                              "invoices": [{"ResponseOID": 100, "DocumentURL": ""}]})
        window.pending["r2"] = ("provider_transmitted_search", "timer-2")
        window.handle_result({**base, "request_id": "r2", "has_more": False,
                              "invoices": [{"ResponseOID": 50, "DocumentURL": ""}]})
        self.assertEqual(set(window.rows), {"100", "50"})
        self.assertEqual(window.tree.insert.call_count, 2)

    def test_destroy_cancels_pending(self):
        window = self.make_window()
        window.pending["r"] = ("provider_transmitted_search", "timer")
        window.rows["1"] = {"DocumentURL": "private"}
        window.destroy()
        self.assertFalse(window.pending)
        self.assertFalse(window.rows)
        self.assertTrue(window.destroyed)

    def test_table_shows_actual_url_instead_of_availability_label(self):
        window = self.make_window()
        window.pending["r"] = ("provider_transmitted_search", "timer")
        url = "https://example.invalid/invoice?id=123"
        window.handle_result({"request_id": "r", "type": "provider_transmitted_search_result",
            "client_code": "CLIENT-1", "bo_connection_id": 2, "success": True,
            "invoices": [{"ResponseOID": 1, "DocumentURL": url, "Series": "Α", "Number": "123"}]})
        values = window.tree.insert.call_args.kwargs["values"]
        self.assertEqual(values[2:4], ["Α", "123"])
        self.assertEqual(values[-1], url)
        self.assertNotIn("Διαθέσιμο", values)

    def test_hidden_view_does_not_capture_shortcuts(self):
        window = self.make_window()
        window.winfo_viewable = Mock(return_value=False)
        action = Mock()
        self.assertIsNone(window._visible_shortcut(action))
        action.assert_not_called()
        window.winfo_viewable.return_value = True
        self.assertEqual(window._visible_shortcut(action), "break")
        action.assert_called_once()

    def test_destroy_removes_only_its_own_shortcuts_and_initial_load(self):
        window = self.make_window()
        window._initial_load_after_id = "initial"
        window._shortcut_bindings = [("<Escape>", "binding-1")]
        window.destroy()
        window.after_cancel.assert_called_once_with("initial")
        window._shortcut_parent.unbind.assert_called_once_with("<Escape>", "binding-1")


class ProviderNavigationTests(unittest.TestCase):
    """Ελέγχει την εναλλαγή ενσωματωμένων προβολών και τη διατήρηση της επιλεγμένης βάσης."""

    def setUp(self):
        self.provider = object.__new__(provider_ui.ProviderTab)
        self.provider.main_content = Mock()
        self.provider.transmitted_view = None
        self.provider.client_code = "CLIENT-1"
        self.provider.selected_bo_connection_id = 2
        self.provider.on_provider_request_callback = Mock()

    def test_open_back_and_reopen_reuses_embedded_view(self):
        view = Mock()
        view.bo_connection_id = 2
        view.winfo_exists.return_value = True
        view.entries = {"mark": Mock()}
        with patch.object(provider_ui, "TransmittedInvoicesView", return_value=view) as factory:
            self.provider._open_transmitted()
            self.provider.main_content.grid_remove.assert_called_once()
            view.grid.assert_called_once_with(row=0, column=0, sticky="nsew")
            self.provider._show_main_provider()
            view.grid_remove.assert_called_once()
            self.provider.main_content.grid.assert_called_once_with()
            self.provider._open_transmitted()
            factory.assert_called_once()
            view.destroy.assert_not_called()

    def test_changed_bo_replaces_view(self):
        old = Mock(bo_connection_id=1)
        old.winfo_exists.return_value = True
        self.provider.transmitted_view = old
        new = Mock()
        new.entries = {"mark": Mock()}
        with patch.object(provider_ui, "TransmittedInvoicesView", return_value=new) as factory:
            self.provider._open_transmitted()
            old.destroy.assert_called_once()
            self.assertEqual(factory.call_args.args[2], 2)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    """Εκτελεί τις πραγματικές μεθόδους του agent με αντικατάσταση μόνο των εξωτερικών εξαρτήσεων."""

    async def test_handler_uses_selected_bo_and_keeps_mark(self):
        source = ast.parse((ROOT / "client/app/client_agent.py").read_text(encoding="utf-8-sig"))
        original = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "MoonHardClientAgent")
        names = {"_handle_provider_transmitted", "_get_bo_connection_by_id"}
        methods = [n for n in original.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
        module = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name="Agent", bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[]))
        namespace = {"asyncio": asyncio, "json": json, "logger": logging.getLogger("test-agent"), "TransmittedInvoicesService": Service}
        exec(compile(module, "client_agent.py", "exec"), namespace)
        agent = namespace["Agent"]()
        agent.identity = {"client_code": "CLIENT-1"}
        agent.appsettings_reader = Mock()
        agent.appsettings_reader.read_appsettings_production.return_value = {"bo_connections": [
            {"ID": 1, "DatabaseConnection": "first"}, {"ID": 2, "DatabaseConnection": "second"}]}
        agent.transmitted_invoices_service = Mock()
        agent.transmitted_invoices_service.search.return_value = {"success": True, "invoices": []}
        websocket = types.SimpleNamespace(send=AsyncMock())
        payload = {"type": "provider_transmitted_search", "request_id": "r", "bo_connection_id": 2, "mark": "444"}
        await agent._handle_provider_transmitted(websocket, payload)
        agent.transmitted_invoices_service.search.assert_called_once_with("second", payload)
        reply = json.loads(websocket.send.call_args.args[0])
        self.assertEqual(reply["bo_connection_id"], 2)
        self.assertEqual(reply["type"], "provider_transmitted_search_result")


class CLITests(unittest.IsolatedAsyncioTestCase):
    """Ελέγχει αυθεντικοποίηση, διαβίβαση MARK και το πραγματικό σημείο εισόδου CMD."""

    def setUp(self):
        self.config_module = types.ModuleType("app.config")
        self.config_module.DashboardConfig = Mock()
        self.logging_module = types.ModuleType("app.logger_config")
        self.logging_module.DashboardLoggerConfig = Mock()
        self.socket_module = types.ModuleType("websockets")
        self.socket_module.connect = Mock()
        self.stubs = {"app.config": self.config_module, "app.logger_config": self.logging_module,
            "app.views.manage.provider_transmitted_window": ui, "websockets": self.socket_module}
        with patch.dict(sys.modules, self.stubs):
            self.cli = load_module("transmitted_cli_test", "dashboard/app/provider_transmitted_cli.py")

    async def test_authenticated_mark_search(self):
        messages = []

        class Socket:
            """Τοπικός απομονωμένος διάλογος WebSocket."""
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def send(self, message): messages.append(json.loads(message))
            async def recv(self): return json.dumps({"type": "dashboard_connected"})
            async def __aiter__(self):
                yield json.dumps({"type": "clients_list", "clients": []})
                yield json.dumps({**messages[-1], "type": "provider_transmitted_search_result", "success": True})

        self.socket_module.connect.return_value = Socket()
        args = self.cli.TransmittedInvoicesCLI.parser().parse_args(["--client", "CLIENT-1", "--mark", "444"])
        config = types.SimpleNamespace(dashboard_token="test-token", dashboard_websocket_url="ws://127.0.0.1/test")
        result = await self.cli.TransmittedInvoicesCLI().request(config, args)
        self.assertTrue(result["success"])
        self.assertEqual(messages[0]["type"], "authenticate")
        self.assertEqual(messages[1]["mark"], "444")
        self.assertEqual(messages[1]["start_date"], "")
        self.assertNotIn("token", messages[1])

    async def test_failed_auth_does_not_send_search(self):
        sent = []

        class Socket:
            """Προσομοιώνει απόρριψη αυθεντικοποίησης."""
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def send(self, message): sent.append(json.loads(message))
            async def recv(self): return json.dumps({"type": "error"})

        self.socket_module.connect.return_value = Socket()
        args = self.cli.TransmittedInvoicesCLI.parser().parse_args(["--client", "CLIENT-1"])
        config = types.SimpleNamespace(dashboard_token="test-token", dashboard_websocket_url="ws://127.0.0.1/test")
        with self.assertRaises(ValueError):
            await self.cli.TransmittedInvoicesCLI().request(config, args)
        self.assertEqual(len(sent), 1)

    async def test_executable_entry_dispatches_cli_before_gui(self):
        app_module = types.ModuleType("app.dashboard_app")
        app_module.MoonHardDashboardApp = Mock()
        cli_module = types.ModuleType("app.provider_transmitted_cli")
        cli_module.main = Mock(return_value=0)
        with patch.dict(sys.modules, {**self.stubs, "app.dashboard_app": app_module,
                                     "app.provider_transmitted_cli": cli_module}), \
             patch.object(sys, "argv", ["main.py", "--provider-transmitted", "--client", "CLIENT-1"]):
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(ROOT / "dashboard/app/main.py"), run_name="__main__")
        self.assertEqual(stopped.exception.code, 0)
        cli_module.main.assert_called_once_with(["--client", "CLIENT-1"])
        app_module.MoonHardDashboardApp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
