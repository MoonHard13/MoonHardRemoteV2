"""Πλήρη SQL αποτελέσματα, πραγματικά ODBC settings και δρομολόγηση μεγάλων πακέτων."""

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dashboard'))
from app.sql_cli import SqlCLI
from app.sql_transfer import SqlResultAssembler


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Οι δοκιμές χρησιμοποιούν συνθετικό ODBC. Το πραγματικό Windows EXE ελέγχει τη βιβλιοθήκη.
try:
    import pyodbc
except ImportError:
    pyodbc = types.ModuleType('pyodbc')
    pyodbc.connect = Mock()
    pyodbc.drivers = Mock()
    sys.modules['pyodbc'] = pyodbc

execution = load('sql_execution_test', 'client/app/sql_executor.py')
transport = load('sql_transport_test', 'client/app/sql_transport.py')
routing = load('sql_responses_test', 'server/app/websocket/sql_responses.py')


class FakeCursor:
    """Πολλαπλά αποτελέσματα και μετρητής ομαδικής ανάγνωσης."""

    def __init__(self, datasets):
        self.datasets = datasets
        self.index = 0
        self.position = 0
        self.rowcount = -1
        self.reads = []

    @property
    def description(self):
        return [(label,) for label in self.datasets[self.index][0]]

    def execute(self, sql):
        self.index = self.position = 0

    def fetchmany(self, size):
        self.reads.append(size)
        rows = self.datasets[self.index][1][self.position:self.position + size]
        self.position += len(rows)
        return rows

    def nextset(self):
        self.index += 1
        self.position = 0
        return self.index < len(self.datasets)


class SqlExecutionTests(unittest.TestCase):
    def setUp(self):
        self.executor = execution.SqlExecutor()

    def test_complete_rows_wide_result_multiple_sets_long_cells_and_null(self):
        text = 'Αθήνα' * 2000
        rows = [[i, text if i == 0 else '', None, *['v'] * 40] for i in range(1501)]
        cursor = FakeCursor([([f'C{i}' for i in range(43)], rows), (['Last'], [['Τέλος']])])
        result = self.executor._execute_batch(cursor, 'SELECT test', 1)
        self.assertIsNone(result['error'])
        self.assertFalse(result['limited'])
        first, second = result['result_sets']
        self.assertEqual(first['row_count'], 1501)
        self.assertEqual(first['rows'][0][1], text)
        self.assertIsNone(first['rows'][0][2])
        self.assertEqual(first['rows'][1][1], '')
        self.assertEqual(second['rows'], [['Τέλος']])
        self.assertTrue(all(size == 1000 for size in cursor.reads))

    def test_query_timeout_is_set_before_cursor_with_separate_login_limit(self):
        connection = Mock()
        cursor = FakeCursor([(['ID'], [[1]])])
        connection.cursor.side_effect = lambda: (self.assertEqual(connection.timeout, timeout), cursor)[1]
        context = Mock(__enter__=Mock(return_value=connection), __exit__=Mock(return_value=False))
        with patch.object(execution.pyodbc, 'drivers', return_value=['ODBC Driver 17 for SQL Server']), \
             patch.object(execution.pyodbc, 'connect', return_value=context) as connect:
            for timeout in (0, 120):
                with self.subTest(timeout=timeout):
                    result = self.executor.execute_sql('TEST', 'Server=TEST;Database=TEST;', 'SELECT 1', timeout)
                    self.assertTrue(result['success'])
                    self.assertEqual(connect.call_args.kwargs['timeout'], 15)
                    self.assertFalse(self.executor.active_cursors)
            for timeout in (-1, 3601, True):
                connect.reset_mock()
                with self.assertLogs(execution.logger, level='ERROR'):
                    result = self.executor.execute_sql('TEST', 'Server=TEST;Database=TEST;', 'SELECT 1', timeout)
                self.assertFalse(result['success'])
                connect.assert_not_called()

    def test_large_transfer_uses_bounded_messages_and_preserves_unicode(self):
        result = {'type': 'sql_result', 'request_id': 'TEST', 'client_code': 'TEST', 'bo_connection_id': 1,
                  'success': True, 'batches': [{'batch_index': 1, 'result_sets': [
                      {'columns': ['Value'], 'rows': [['Αθήνα' * 300000], [None], ['']]}]}]}
        assembler = SqlResultAssembler()
        packets = list(transport.SqlResultTransport.messages(result))
        self.assertGreater(len(packets), 5)
        for index, packet in enumerate(packets):
            self.assertLess(len(packet.encode('utf-8')), 300 * 1024)
            assembled = assembler.feed(json.loads(packet))
            if index < len(packets) - 1:
                self.assertIsNone(assembled)
        self.assertEqual(assembled, result)
        self.assertFalse(assembler._data)

    def test_transfer_rejects_missing_reordered_foreign_and_corrupt_packets(self):
        result = {'type': 'sql_result', 'request_id': 'TEST', 'client_code': 'TEST', 'bo_connection_id': 1, 'text': 'x' * 400000}
        packets = [json.loads(packet) for packet in transport.SqlResultTransport.messages(result)]
        assembler = SqlResultAssembler()
        with self.assertRaises(ValueError):assembler.feed(packets[1])
        self.assertIsNone(assembler.feed(packets[0]))
        with self.assertRaises(ValueError):assembler.feed({**packets[1], 'request_id': 'OTHER'})
        assembler.reset()
        with self.assertRaises(ValueError):assembler.feed({**packets[0], 'transfer': {**packets[0]['transfer'], 'data': '!'}})
        assembler.reset()
        assembler.feed(packets[0])
        with self.assertRaises(ValueError):assembler.feed(result)

    def test_server_keeps_request_and_does_not_broadcast_chunks_to_other_dashboards(self):
        async def scenario():
            dashboard = object()
            pending = {'TEST': dashboard, 'OTHER': object()}
            manager = SimpleNamespace(send_to_dashboard=AsyncMock(), broadcast_to_dashboards=AsyncMock())
            for index in range(3):
                packet = {'type': 'sql_result', 'request_id': 'TEST', 'transfer': {'index': index, 'total': 3}}
                await routing.SqlResponseRouter.forward(packet, pending, manager)
                self.assertEqual('TEST' in pending, index < 2)
                manager.send_to_dashboard.assert_awaited_with(dashboard, packet)
                manager.broadcast_to_dashboards.assert_not_awaited()
            self.assertIn('OTHER', pending)
            await routing.SqlResponseRouter.forward(packet, pending, manager)
            self.assertEqual(manager.send_to_dashboard.await_count, 3)
            manager.broadcast_to_dashboards.assert_not_awaited()
        asyncio.run(scenario())

    def test_cli_zero_waits_without_deadline_and_receives_over_one_mb(self):
        import websockets
        async def scenario():
            async def handler(ws):
                await ws.recv()
                await ws.send(json.dumps({'type': 'dashboard_connected'}))
                request = json.loads(await ws.recv())
                result = {'type': 'sql_result', 'request_id': request['request_id'], 'client_code': 'TEST',
                          'bo_connection_id': 1, 'success': True, 'batches': [{'batch_index': 1, 'result_sets': [
                              {'columns': ['ID', 'Value'], 'rows': [[i, 'Αθήνα' * 100] for i in range(1501)]}]}]}
                for packet in transport.SqlResultTransport.messages(result):
                    await ws.send(packet)
            async with websockets.serve(handler, '127.0.0.1', 0) as server:
                config = SimpleNamespace(dashboard_token='FAKE', dashboard_websocket_url=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
                args = SqlCLI.parser().parse_args(['--client', 'TEST', '--query', 'SELECT test', '--timeout', '0'])
                wait_for = asyncio.wait_for
                waits = []
                async def record_wait(awaitable, timeout):
                    waits.append(timeout)
                    return await wait_for(awaitable, timeout)
                with patch('app.sql_cli.asyncio.wait_for', side_effect=record_wait):
                    result = await SqlCLI().request(config, SqlCLI.payload(args))
                self.assertIn(None, waits)
                self.assertEqual(len(result['batches'][0]['result_sets'][0]['rows']), 1501)
        asyncio.run(scenario())


if __name__ == '__main__':
    unittest.main()
