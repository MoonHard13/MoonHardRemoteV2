"""Δοκιμές σύγκρισης και ανάγνωσης ERP χωρίς πραγματική βάση ή credentials."""

import asyncio
import importlib.util
import importlib
import json
import sys
import types
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dashboard'))
from app.provider_diagnostic.documents import DocumentDataset
from app.provider_diagnostic.erp_data import ERPDataset, ERPLoader, ERPPageBridge
from app.provider_diagnostic.reconciliation import ReconciliationEngine
from app.provider_diagnostic.models import DiagnosticContext
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

odbc = types.ModuleType('pyodbc')
odbc.connect = Mock()
with patch.dict(sys.modules, {'pyodbc': odbc}):
    context_reader = load_module('recon_context_fixture', 'client/app/provider/diagnostic_context.py')
    with patch.dict(sys.modules, {'app.provider.diagnostic_context': context_reader}):
        reader_module = load_module('recon_reader_fixture', 'client/app/provider/reconciliation_reader.py')
base_router = load_module('recon_base_router_fixture', 'server/app/websocket/transmitted_requests.py')
with patch.dict(sys.modules, {'app.websocket.transmitted_requests': base_router}):
    router_module = load_module('recon_router_fixture', 'server/app/websocket/provider_diagnostic_requests.py')
Reader = reader_module.ReconciliationReader


def row(**values):
    return dict(series='Α', number='1', invoiceType='11.1', dateIssued='2026-09-17T00:00:00',
        mark='123', uid='ABC', totalAmount='12.40', totalVatAmount='2.40', counterPartyVAT='012345678', **values)


def changed(**values):
    return {**row(), **values}


def ctx():
    return DiagnosticContext('CLIENT-1', 'Εταιρεία', 1, 'SQL', 'DB', True, issuer_vat='EL012345678')


class EngineTests(unittest.TestCase):
    def compare(self, erp=(), provider=(), **options):
        dataset = DocumentDataset(tuple(provider), '20260917', '20260917', 1, 'now', **options)
        source = ERPDataset(tuple(erp), '20260917', '20260917', 'EL012345678', True, False)
        return ReconciliationEngine.compare(source, dataset, Event())

    def test_mark_and_uid_match_normalizes_number_vat_and_date(self):
        result = self.compare([row()], [changed(number='0001', counterPartyVAT='EL012345678', dateIssued='2026-09-17T23:59:59')])
        self.assertEqual(result.records[0]['status'], 'matched')
        self.assertEqual(result.records[0]['match_basis'], 'mark+uid')

    def test_amount_difference_uses_decimal_cents(self):
        result = self.compare([changed(totalAmount='12.41')], [row()])
        self.assertEqual(result.records[0]['differences']['totalAmount']['delta'], '0.01')
        self.assertEqual(result.records[0]['status'], 'differences')

    def test_missing_pos_amount_is_unknown_not_zero_or_difference(self):
        result = self.compare([changed(totalAmount=None, totalVatAmount=None)], [row()])
        self.assertEqual(result.records[0]['status'], 'matched_missing_fields')
        self.assertEqual(result.records[0]['differences'], {})
        self.assertIn('totalAmount', result.records[0]['unavailable_fields'])

    def test_uid_case_does_not_create_difference(self):
        self.assertEqual(self.compare([changed(uid='abc')], [row()]).records[0]['status'], 'matched')

    def test_shared_mark_conflicting_uid_is_visible_difference(self):
        result = self.compare([changed(uid='DIFFERENT')], [row()])
        self.assertIn('uid', result.records[0]['differences'])

    def test_mark_and_uid_pointing_to_different_rows_are_ambiguous(self):
        result = self.compare([row()], [changed(uid='OTHER'), changed(mark='456')])
        self.assertTrue(all(r['status'] == 'ambiguous' for r in result.records))

    def test_duplicate_mark_never_produces_definitive_pair(self):
        result = self.compare([row(), changed(number='2')], [row()])
        self.assertTrue(all(r['status'] == 'ambiguous' for r in result.records))

    def test_duplicate_provider_uid_is_ambiguous(self):
        result = self.compare([row()], [row(), changed(mark='456')])
        self.assertTrue(all(r['status'] == 'ambiguous' for r in result.records))

    def test_fallback_requires_all_identity_fields(self):
        result = self.compare([changed(mark='', uid='')], [changed(mark='', uid='')])
        self.assertEqual(result.records[0]['match_basis'], 'series_number_type_date')
        result = self.compare([changed(mark='', uid='', invoiceType='')], [changed(mark='', uid='')])
        self.assertEqual([r['status'] for r in result.records], ['erp_only', 'provider_only'])

    def test_fallback_does_not_override_conflicting_mark(self):
        result = self.compare([changed(mark='456', uid='')], [changed(uid='')])
        self.assertEqual([r['status'] for r in result.records], ['erp_only', 'provider_only'])

    def test_erp_only_requires_verified_provider_completion(self):
        for options, expected in [({}, True), ({'termination':'short_page_404'}, False),
                ({'complete':False, 'termination':'next_page_404'}, False), ({'invalid_date_count':1}, False)]:
            with self.subTest(options=options):
                result = self.compare([row()], [], **options)
                self.assertEqual(result.records[0]['confirmed'], expected)

    def test_provider_only_requires_full_erp_coverage(self):
        self.assertFalse(self.compare([], [row()]).records[0]['confirmed'])
        e = ERPDataset((), '20260917', '20260917', 'EL012345678', True, True)
        p = DocumentDataset((row(),), '20260917', '20260917', 1, 'now')
        self.assertTrue(ReconciliationEngine.compare(e, p, Event()).records[0]['confirmed'])

    def test_scope_mismatch_and_cancel_fail(self):
        e = ERPDataset((row(),), '20260916', '20260917', 'EL012345678', True, True)
        p = DocumentDataset((row(),), '20260917', '20260917', 1, 'now')
        with self.assertRaises(ProviderAPIError):
            ReconciliationEngine.compare(e, p, Event())
        cancel = Event(); cancel.set()
        with self.assertRaises(ProviderAPIError) as error:
            ReconciliationEngine.compare(replace(e, date_from='20260917'), p, cancel)
        self.assertEqual(error.exception.category, ErrorCategory.CANCELLED)

    def test_filters_summary_preserve_inferred_flag(self):
        result = self.compare([row()], [], termination='short_page_404')
        self.assertEqual(len(result.filtered(status='erp_only', number='1')), 1)
        self.assertEqual(result.filtered(status='matched'), [])
        self.assertTrue(result.summary()['completion_inferred'])
        self.assertEqual(result.summary()['confirmed_erp_only'], 0)


class ERPLoaderTests(unittest.TestCase):
    def wire_row(self, oid=10, source='pos', **values):
        return {**row(), 'page_oid':oid, 'document_id':f'{source}:{oid}', 'issuer_vat':ctx().issuer_vat,
            'source':source, 'issue_date_verified':True, **values}

    def page(self, records=(), more=False, cursor=None):
        return {'records':list(records), 'has_more':more, 'next_before_oid':cursor,
            'coverage_complete':False, 'warnings':['Περιορισμένη κάλυψη ERP']}

    def load(self, fetch, cancel=None):
        return ERPLoader.load(fetch, ctx(), '20260917', '20260917', cancel or Event())

    def test_keyset_pages_then_second_source_no_duplicate_payment_rows(self):
        fetch = Mock(side_effect=[self.page([self.wire_row(10)], True, 10),
            self.page([self.wire_row(8)]), self.page([self.wire_row(7, 'sales')])])
        dataset = self.load(fetch)
        self.assertEqual([r['document_id'] for r in dataset.records], ['pos:10','pos:8','sales:7'])
        self.assertEqual([call.args[3:5] for call in fetch.call_args_list], [('pos',None),('pos',10),('sales',None)])
        self.assertFalse(dataset.coverage_complete)
        self.assertEqual(len(dataset.warnings), 1)

    def test_rejects_wrong_company_source_date_and_oid(self):
        bad = [{'issuer_vat':'EL999999999'}, {'source':'sales'}, {'dateIssued':'2026-09-16'},
            {'page_oid':True}, {'document_id':'pos:9'}, {'dateIssued':None}]
        for values in bad:
            with self.subTest(values=values), self.assertRaises(ProviderAPIError):
                self.load(Mock(return_value=self.page([self.wire_row(**values)])))

    def test_non_decreasing_cursor_and_duplicate_ids_fail(self):
        for records in ([self.wire_row(10),self.wire_row(10)], [self.wire_row(8),self.wire_row(10)]):
            with self.assertRaises(ProviderAPIError):
                self.load(Mock(return_value=self.page(records)))
        with self.assertRaises(ProviderAPIError):
            self.load(Mock(return_value=self.page([self.wire_row()], True, 9)))

    def test_limits_cancel_and_invalid_range(self):
        fetch = Mock(return_value=self.page())
        with patch.object(ERPLoader, 'MAX_PAGES', 1), self.assertRaises(ProviderAPIError) as error:
            self.load(fetch)
        self.assertEqual(error.exception.category, ErrorCategory.DATA_LIMIT)
        fetch.reset_mock()
        cancel = Event(); cancel.set()
        with self.assertRaises(ProviderAPIError): self.load(fetch, cancel)
        fetch.assert_not_called()
        with self.assertRaises(ProviderAPIError):
            ERPLoader.load(fetch, ctx(), '20260918', '20260917', Event())

    def test_malformed_pages_are_not_empty_success(self):
        for page in ({'records':{}, 'has_more':False}, self.page([], True, 10),
                {**self.page(), 'warnings':['x'*501]}, {**self.page(), 'has_more':1}):
            with self.subTest(page=page), self.assertRaises(ProviderAPIError): self.load(Mock(return_value=page))


class BridgeTests(unittest.TestCase):
    def test_request_correlates_and_rejects_other_scopes(self):
        bridge = ERPPageBridge(None)
        def send(request):
            reply = {**request, 'type':request['type']+'_result', 'success':True, 'records':[]}
            for changes in ({'client_code':'OTHER'}, {'bo_connection_id':2}, {'issuer_vat':'EL999999999'},
                    {'date_from':'20260916'}, {'source':'sales'}, {'request_id':str(uuid4())}):
                self.assertFalse(bridge.accept({**reply, **changes}))
            self.assertTrue(bridge.accept(reply))
            return True
        bridge.send = send
        result = bridge.request(ctx(), '20260917', '20260917', 'pos', None, Event())
        self.assertTrue(result['success'])
        self.assertEqual(bridge.pending, {})
        self.assertFalse(bridge.accept(result))

    def test_send_failure_is_sanitized_and_clears_pending(self):
        bridge=ERPPageBridge(Mock(side_effect=RuntimeError("password=private-fixture")))
        with self.assertRaises(ProviderAPIError) as error:
            bridge.request(ctx(),'20260917','20260917','pos',None,Event())
        self.assertEqual(error.exception.category,ErrorCategory.ERP_CONNECTION)
        self.assertNotIn('private-fixture',str(error.exception))
        self.assertEqual(bridge.pending,{})

    def test_capability_failure_is_received_with_no_scope_fields(self):
        bridge = ERPPageBridge(None)
        def send(request):
            bridge.accept({'type':request['type']+'_result','request_id':request['request_id'],
                'client_code':request['client_code'],'bo_connection_id':1,'success':False})
            return True
        bridge.send = send
        with self.assertRaises(ProviderAPIError) as error:
            bridge.request(ctx(), '20260917','20260917','pos',None,Event())
        self.assertEqual(error.exception.category, ErrorCategory.ERP_READ)

    def test_cancel_timeout_and_close_clear_pending(self):
        for mode, category in [('cancel',ErrorCategory.CANCELLED), ('timeout',ErrorCategory.ERP_TIMEOUT), ('close',ErrorCategory.ERP_READ)]:
            cancel = Event()
            bridge = ERPPageBridge(lambda p:True)
            bridge.TIMEOUT = 0
            if mode == 'cancel': cancel.set()
            if mode == 'close':
                bridge.TIMEOUT = 1
                bridge.send = lambda p:bridge.close()
            with self.subTest(mode=mode), self.assertRaises(ProviderAPIError) as error:
                bridge.request(ctx(),'20260917','20260917','pos',None,cancel)
            self.assertEqual(error.exception.category, category)
            self.assertEqual(bridge.pending, {})


class SQLReaderTests(unittest.TestCase):
    def schema(self, success=True):
        schema = {name:set() for name in Reader.TABLES}
        schema['VSnVSalesPayWay'] = set('salespaywayoid salespwposhdr salespwnotecode salespwnoterow salespwnoteno salespwdate companyoid'.split())
        schema['TblSnSNoteHdr'] = set('snotehdroid snotehdrprndate snotehdrsr snotehdrno snotehdrvpaytotal snotehdrvfpatotal snotehdrcustafm companyoid'.split())
        schema['TblSnCompany'] = {'companyoid','companyafm'}
        schema['TblSnMyDATA_Response'] = set('mydata_responseoid mydata_responsesalestransposhdr mydata_responseinvoicemark mydata_responseinvoiceuid mydata_responseinvoicetype mydata_responseinvoiceseries mydata_responseinvoicenumber'.split())
        if success:
            schema['TblSnMyDATA_ResponseSuccess'] = set('mydata_responseoid mydata_responsesuccessoid mydata_responsesuccessinvoicemark snotehdroid'.split())
        return schema

    def query(self, source='pos', schema=None, single=True, before=None):
        return Reader.build_query(schema or self.schema(), source, datetime(2026,9,17),datetime(2026,9,18),
            'EL012345678',single,before)

    def test_pos_groups_payment_methods_without_using_payment_value_as_total(self):
        query, params, warnings = self.query(before=42)
        self.assertIn('GROUP BY base.SalesPWPosHdr', query)
        self.assertIn('AND doc.page_oid < ?', query)
        self.assertNotIn('SalesPWValue', query)
        self.assertIn('CAST(NULL AS decimal(19,4)) AS totalAmount', query)
        self.assertEqual(params[-1], 42)
        self.assertEqual(query.count('?'), len(params))
        self.assertTrue(warnings)

    def test_sales_new_schema_success_link_and_optional_amounts(self):
        query, params, warnings = self.query('sales')
        self.assertIn('ref.SNoteHdrOID = doc.link_oid',query)
        self.assertIn('base.[SNoteHdrVPayTotal]',query)
        self.assertIn('base.[SNoteHdrVFpaTotal]',query)
        self.assertEqual(query.count('?'),len(params))
        self.assertEqual(warnings,[])

    def test_old_schema_does_not_reference_absent_success_table_or_columns(self):
        schema=self.schema(False)
        schema['TblSnMyDATA_Response'].add('snotehdroid')
        schema['TblSnSNoteHdr'].remove('snotehdrvfpatotal')
        query,params,_=self.query('sales',schema)
        self.assertNotIn('dbo.TblSnMyDATA_ResponseSuccess',query)
        self.assertIn('NULL AS totalVatAmount',query)
        self.assertEqual(query.count('?'),len(params))

    def test_no_response_table_preserves_untransmitted_documents(self):
        schema=self.schema(False); schema['TblSnMyDATA_Response']=set()
        query,_,warnings=self.query(schema=schema)
        self.assertIn('SELECT CAST(NULL AS nvarchar(500)) AS mark',query)
        self.assertNotIn('dbo.TblSnMyDATA_Response AS md',query)
        self.assertTrue(any('σύνδεση' in warning for warning in warnings))

    def test_multiple_afms_are_parameterized_and_require_relation(self):
        query,params,_=self.query(single=False)
        self.assertIn('c.CompanyOID = base.CompanyOID',query)
        self.assertNotIn('012345678',query)
        self.assertEqual(params[1:4],['012345678','EL012345678','GR012345678'])
        self.assertEqual(query.count('?'),len(params))
        schema=self.schema(); schema['VSnVSalesPayWay'].remove('companyoid')
        with self.assertRaises(ValueError): self.query(schema=schema,single=False)

    def test_validation_rejects_injection_and_end_overflow_before_connect(self):
        payload=dict(issuer_vat='EL012345678',date_from='20260917',date_to='20260917',source='pos',bo_connection_id=1)
        start,end,_,_=Reader.validate(payload)
        self.assertEqual((start.hour,end.day,end.hour),(0,18,0))
        reader=Reader(Mock(),Mock())
        odbc.connect.reset_mock()
        for values in ({'source':'pos; DROP TABLE'}, {'issuer_vat':'012345678'}, {'before_oid':True},
                {'date_from':'20260230'}, {'date_from':'20260918'}, {'date_to':'99991231'}, {'bo_connection_id':0}):
            with self.subTest(values=values): self.assertFalse(reader.read({**payload,**values})['success'])
        odbc.connect.assert_not_called()

    def test_read_exact_bo_closes_resources_and_never_sends_credentials(self):
        settings,provider,connection,cursor=Mock(),Mock(),Mock(),Mock()
        settings.read_appsettings_production.return_value={'bo_connections':[{'ID':2,'DatabaseConnection':'WRONG'},
            {'ID':1,'DatabaseConnection':'RIGHT','subscriptionKey':'PRIVATE'}]}
        provider._to_odbc_connection_string.return_value='ODBC'
        odbc.connect.return_value=connection; odbc.connect.side_effect=None
        connection.cursor.return_value=cursor
        cursor.fetchmany.side_effect=[[('012345678',)], [(10,'pos:10','Α','1','2026-09-17T00:00:00',None,None,'','123','ABC','11.1','200',1)]]
        cursor.description=[(name,) for name in ('page_oid','document_id','series','number','dateIssued','totalAmount','totalVatAmount','counterPartyVAT','mark','uid','invoiceType','response_status','issue_date_verified')]
        reader=Reader(settings,provider)
        with patch.object(reader,'metadata',return_value=self.schema()):
            result=reader.read(dict(issuer_vat='EL012345678',date_from='20260917',date_to='20260917',source='pos',bo_connection_id=1))
        self.assertTrue(result['success'])
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['records'][0]['issuer_vat'],'EL012345678')
        self.assertNotIn('PRIVATE',json.dumps(result))
        provider._to_odbc_connection_string.assert_called_once_with('RIGHT')
        connection.close.assert_called_once(); cursor.close.assert_called_once()


class RouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager=Mock(); self.manager.send_to_dashboard=AsyncMock(); self.manager.send_to_client=AsyncMock(return_value=True)
        self.manager.client_capabilities={'CLIENT-1':['provider_reconciliation_v1']}
        self.router=router_module.ProviderDiagnosticRequestRouter(self.manager)
        self.dashboard=object()
        self.request=dict(type='provider_diagnostic_erp_page',request_id=str(uuid4()),client_code='CLIENT-1',
            bo_connection_id=1,issuer_vat='EL012345678',date_from='20260917',date_to='20260917',source='pos',before_oid=None)

    async def asyncTearDown(self): self.router.discard_dashboard(self.dashboard)

    async def test_old_client_error_has_correct_erp_result_type(self):
        self.manager.client_capabilities={'CLIENT-1':['provider_diagnostic_v1']}
        await self.router.request(self.dashboard,self.request)
        result=self.manager.send_to_dashboard.call_args.args[1]
        self.assertEqual(result['type'],'provider_diagnostic_erp_page_result')
        self.assertFalse(result['success']); self.manager.send_to_client.assert_not_called()

    async def test_private_key_and_raw_settings_not_forwarded_with_erp(self):
        await self.router.request(self.dashboard,{**self.request,'api_key':'PRIVATE'})
        forwarded=self.manager.send_to_client.call_args.args[1]
        self.assertNotIn('api_key',forwarded)
        reply={**self.request,'type':'provider_diagnostic_erp_page_result','success':True,'records':[],
            'api_key':'PRIVATE','appsettings':{'password':'PRIVATE'}}
        await self.router.result('OTHER',reply)
        self.manager.send_to_dashboard.assert_not_called()
        await self.router.result('CLIENT-1',reply)
        result=self.manager.send_to_dashboard.call_args.args[1]
        self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertIs(self.manager.send_to_dashboard.call_args.args[0],self.dashboard)
        self.assertEqual(self.router.pending,{})



class ReconciliationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture=types.ModuleType('customtkinter'); fixture.CTkFrame=type('FrameFixture',(),{})
        with patch.dict(sys.modules, {'customtkinter':fixture}):
            cls.ui=importlib.import_module('app.provider_diagnostic.ui')
            cls.view_module=importlib.import_module('app.provider_diagnostic.reconciliation_view')

    def tab(self):
        tab=self.ui.ProviderDiagnosticTab.__new__(self.ui.ProviderDiagnosticTab)
        tab._closed=False; tab._last_ready=False
        tab._scope=tab._running_scope=('CLIENT',1,'EL012345678')
        tab._running_kind='reconciliation'; tab._context=types.SimpleNamespace(provider_ready=True)
        tab.session=Mock(); tab.session.expire_pending.return_value=False
        tab._task=Mock(); tab._task.poll_progress.return_value=None
        for name in ('status','probe_button','cancel_button','reconciliation_view','documents_view','refresh_diagnostics','after'):
            setattr(tab,name,Mock())
        return tab

    def test_reconciliation_installs_only_matching_scope_and_not_document_table(self):
        for stale in (False,True):
            tab=self.tab()
            if stale: tab._running_scope=('OTHER',2)
            dataset=types.SimpleNamespace(erp_records=42,provider_records=49)
            tab._task.poll.return_value=(dataset,None)
            tab._poll()
            if stale: tab.reconciliation_view.set_dataset.assert_not_called()
            else: tab.reconciliation_view.set_dataset.assert_called_once_with(dataset)
            tab.documents_view.set_dataset.assert_not_called()

    def test_copy_export_search_route_to_reconciliation(self):
        tab=self.tab(); tab.section=Mock(); tab.section.get.return_value='Reconciliation'
        tab.reconciliation_view.filters={"number":Mock()}
        tab.copy_selected(); tab.export(); tab._search()
        tab.reconciliation_view.copy_selected.assert_called_once()
        tab.reconciliation_view.export.assert_called_once()
        tab.reconciliation_view.filters["number"].focus_set.assert_called_once()
        tab.documents_view.copy_selected.assert_not_called()

    def test_classification_filter_and_coverage_warning_are_visible(self):
        view=self.view_module.ReconciliationView.__new__(self.view_module.ReconciliationView)
        view.filters={name:Mock() for name in ('series','number','invoice_type','mark')}
        for entry in view.filters.values(): entry.get.return_value=''
        view.status_filter=Mock(); view.status_filter.get.return_value='Μόνο ERP'
        view._filter_job=None; view._sort_reverse={}; view._render=Mock(); view.count=Mock()
        e=ERPDataset((row(),),'20260917','20260917','EL012345678',True,False,('Περιορισμένη κάλυψη ERP',))
        p=DocumentDataset((),'20260917','20260917',1,'now',termination='short_page_404',last_page_records=49)
        view.dataset=ReconciliationEngine.compare(e,p,Event())
        view.apply_filters()
        self.assertEqual(len(view._rows),1)
        text=view.count.configure.call_args.kwargs['text']
        self.assertIn('49/100',text); self.assertIn('Περιορισμένη κάλυψη ERP',text)
        self.assertFalse(view._rows[0]['confirmed'])


class ReconciliationCLITests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        dotenv=types.ModuleType('dotenv'); dotenv.load_dotenv=Mock()
        with patch.dict(sys.modules,{'dotenv':dotenv}):
            cls.cli=importlib.import_module('app.provider_diagnostic.cli')

    async def test_full_context_provider_erp_exchange_and_safe_export(self):
        class Socket:
            def __init__(self):
                self.queue=asyncio.Queue(); self.requests=[]
                self.queue.put_nowait({'type':'dashboard_connected'})
            async def send(self,raw):
                request=json.loads(raw); self.requests.append(request)
                if request['type']=='get_client_appsettings':
                    self.queue.put_nowait({'type':'clients_list','clients':[{'client_code':'CLIENT-1','ws_connected':True}]})
                    self.queue.put_nowait({'type':'client_appsettings_result','client_code':'CLIENT-1','success':True,
                        'appsettings':{'bo_connections':[{'ID':1,'DatabaseName':'DB'}]}})
                elif request['type']=='provider_diagnostic_context':
                    reply={**request,'type':request['type']+'_result','success':True,'sql_verified':True,
                        'companies':[{'issuer_vat':'EL012345678','company_name':'Εταιρεία'}],
                        'provider_base_url':'https://einvoice.impact.gr'}
                    if request['issuer_vat']: reply['api_key']='private-recon-fixture'
                    self.queue.put_nowait(reply)
                elif request['type']=='provider_diagnostic_erp_page':
                    records=[] if request['source']=='sales' else [{**row(),'page_oid':10,'document_id':'pos:10',
                        'issuer_vat':'EL012345678','source':'pos','issue_date_verified':True}]
                    self.queue.put_nowait({**request,'type':request['type']+'_result','success':True,'records':records,
                        'has_more':False,'next_before_oid':None,'coverage_complete':False,'warnings':['POS: ελλιπή ποσά']})
            async def recv(self): return json.dumps(await self.queue.get())
            def __aiter__(self): return self
            async def __anext__(self): return await self.recv()
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
        socket=Socket()
        config=types.SimpleNamespace(dashboard_token='fixture-token',dashboard_websocket_url='wss://fixture.invalid')
        provider=DocumentDataset((row(),changed(mark='999',uid='ZZZ',number='2')),'20260917','20260917',1,'now',
            termination='short_page_404',last_page_records=2)
        options={'date_from':'20260917','date_to':'20260917','reconcile':True,'filters':{'status':'provider_only'}}
        with patch.object(self.cli.websockets,'connect',return_value=socket), \
                patch.object(self.cli.ProviderDiagnosticService,'documents',return_value=provider):
            result=await asyncio.wait_for(self.cli.ProviderDiagnosticCLI().context(config,'CLIENT-1',1,documents=options),5)
        self.assertTrue(result['success']); self.assertEqual(result['operation'],'reconciliation')
        self.assertEqual(result['summary']['erp_records'],1); self.assertEqual(result['summary']['provider_records'],2)
        self.assertEqual(result['visible_records'],1); self.assertFalse(result['documents'][0]['confirmed'])
        self.assertFalse(result['completion_verified']); self.assertNotIn('private-recon-fixture',json.dumps(result))
        erp_requests=[r for r in socket.requests if r['type']=='provider_diagnostic_erp_page']
        self.assertEqual([r['source'] for r in erp_requests],['pos','sales'])
        self.assertTrue(all(r['issuer_vat']=='EL012345678' for r in erp_requests))

    def test_cli_options_are_mutually_exclusive_and_filters_match_gui(self):
        args=self.cli.ProviderDiagnosticCLI.parser().parse_args(['--client','CLIENT-1','--reconcile',
            '--date-from','20260916','--date-to','20260917','--reconciliation-status','differences'])
        self.assertTrue(args.reconcile); self.assertEqual(args.reconciliation_status,'differences')
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            self.cli.ProviderDiagnosticCLI.parser().parse_args(['--client','CLIENT-1','--reconcile','--documents'])


class AdditionalMatchingTests(unittest.TestCase):
    def test_no_identifiers_cannot_prove_absence_in_nonempty_provider(self):
        e=ERPDataset((changed(mark='',uid='',invoiceType=''),),'20260917','20260917','EL012345678',True,False)
        p=DocumentDataset((row(),),'20260917','20260917',1,'now')
        result=ReconciliationEngine.compare(e,p,Event())
        self.assertEqual(result.records[0]['status'],'erp_only')
        self.assertFalse(result.records[0]['confirmed'])

    def test_large_duplicate_groups_have_bounded_candidate_preview(self):
        e=ERPDataset(tuple(changed(mark='',uid='') for _ in range(1000)),'20260917','20260917','EL012345678',True,True)
        p=DocumentDataset(tuple(changed(mark='',uid='') for _ in range(1000)),'20260917','20260917',1,'now')
        result=ReconciliationEngine.compare(e,p,Event())
        self.assertEqual(len(result.records),2000)
        self.assertTrue(all(r['status']=='ambiguous' for r in result.records))
        self.assertTrue(all(len(r['candidate_provider_indexes'])<=20 for r in result.records))
        self.assertTrue(all(not r['confirmed'] for r in result.records))


class IssueDateTests(unittest.TestCase):
    def test_unverified_payment_date_is_not_compared_as_issue_date_or_used_for_absence(self):
        erp=changed(issue_date_verified=False, dateIssued='2026-09-17T00:00:00')
        p=changed(dateIssued='2026-09-16T23:59:59')
        differences, unavailable=ReconciliationEngine.differences(erp,p)
        self.assertNotIn('dateIssued',differences)
        self.assertIn('dateIssued',unavailable)
        self.assertIsNone(ReconciliationEngine.identity(erp))
        source=ERPDataset((erp,),'20260917','20260917','EL012345678',True,False)
        provider=DocumentDataset((),'20260917','20260917',1,'now')
        result=ReconciliationEngine.compare(source,provider,Event())
        self.assertFalse(result.records[0]['confirmed'])

    def test_pos_query_filters_the_effective_invoice_date_after_response_join(self):
        fixture=SQLReaderTests()
        schema=fixture.schema()
        schema['TblSnMyDATA_Response'].add('mydata_responseinvoicedate')
        query,params,_=fixture.query(schema=schema,before=100)
        self.assertIn('COALESCE(TRY_CONVERT(datetime2, response.invoice_date), doc.dateIssued)',query)
        self.assertIn('MAX(base.SalesPWDate) AS dateIssued',query)
        self.assertNotIn('GROUP BY base.SalesPWDate',query)
        self.assertNotIn('WHERE base.SalesPWDate',query)
        self.assertIn('MyDATA_ResponseInvoiceDate',query)
        self.assertEqual(query.count('?'),len(params))


class SQLFallbackAndDiagnosticsTests(unittest.TestCase):
    def test_missing_date_field_is_text_null_for_try_convert(self):
        fixture = SQLReaderTests()
        schema = fixture.schema()
        self.assertNotIn('mydata_responseinvoicedate', schema['TblSnMyDATA_Response'])
        query, _, _ = fixture.query(schema=schema)
        self.assertIn('CAST(NULL AS nvarchar(500)) AS invoice_date', query)
        self.assertNotRegex(query, r'(?<!\))\bNULL AS invoice_date')

    def test_missing_mark_field_does_not_promote_success_mark_to_int(self):
        fixture = SQLReaderTests()
        schema = fixture.schema()
        schema['TblSnMyDATA_Response'].remove('mydata_responseinvoicemark')
        query, _, _ = fixture.query(schema=schema)
        self.assertIn("COALESCE(CAST(NULL AS nvarchar(500)), NULLIF(LTRIM(RTRIM(suc.mark)), N''))", query)
        self.assertNotIn('COALESCE(NULL,', query)

    def test_no_response_relation_keeps_all_text_nulls_typed(self):
        fixture = SQLReaderTests()
        schema = fixture.schema(False)
        schema['TblSnMyDATA_Response'] = set()
        for source in ('pos', 'sales'):
            query, params, _ = fixture.query(source=source, schema=schema)
            for name in ('mark', 'uid', 'invoiceType', 'invoice_date', 'response_status'):
                self.assertIn(f'CAST(NULL AS nvarchar(500)) AS {name}', query)
            self.assertEqual(query.count('?'), len(params))

    def test_diagnostics_extract_codes_without_exception_text(self):
        error = RuntimeError('42000', '[SQL Server]password=private-fixture; SQL text (529) (SQLExecDirectW)')
        self.assertEqual(Reader.sql_error_details(error), ('42000', 529, 'unsupported_conversion'))
        error = RuntimeError('42S22', "Invalid column name 'private-fixture' (207)")
        self.assertEqual(Reader.sql_error_details(error), ('42S22', 207, 'invalid_column'))
        self.assertEqual(Reader.sql_error_details(RuntimeError('07002', 'private-fixture')), ('07002', '-', 'parameter_count'))
        self.assertEqual(Reader.sql_error_details(RuntimeError('password=private-fixture', 'server=private-fixture (1433)')),
            ('-', '-', 'unknown'))

    def test_failed_execute_logs_scope_stage_and_safe_codes_and_closes_resources(self):
        class ProgrammingError(Exception):
            pass
        settings, provider, connection, cursor = Mock(), Mock(), Mock(), Mock()
        settings.read_appsettings_production.return_value = {'bo_connections': [{'ID': 1, 'DatabaseConnection': 'PRIVATE'}]}
        provider._to_odbc_connection_string.return_value = 'ODBC'
        odbc.connect.side_effect = None
        odbc.connect.return_value = connection
        connection.cursor.return_value = cursor
        cursor.fetchmany.return_value = [('012345678',)]
        cursor.execute.side_effect = [None, ProgrammingError('42000', 'password=private-fixture (529) (SQLExecDirectW)')]
        reader = Reader(settings, provider)
        with patch.object(reader, 'metadata', return_value=SQLReaderTests().schema()), \
                self.assertLogs(reader_module.logger, level='WARNING') as logs:
            result = reader.read(dict(issuer_vat='EL012345678', date_from='20260917', date_to='20260917', source='pos', bo_connection_id=1))
        self.assertFalse(result['success'])
        message = ' '.join(logs.output)
        for expected in ('exception_type=ProgrammingError', 'source=pos', 'stage=erp_query', 'sqlstate=42000', 'native_code=529'):
            self.assertIn(expected, message)
        self.assertNotIn('private-fixture', message + json.dumps(result))
        self.assertNotIn('012345678', message)
        connection.close.assert_called_once()
        cursor.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
