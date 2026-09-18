"""Δοκιμή του συσκευασμένου SQL Client με συνθετικό ODBC, χωρίς σύνδεση σε βάση."""

import base64
import json
from pathlib import Path
from unittest.mock import patch

from app.sql_executor import SqlExecutor
from app.sql_transport import SqlResultTransport


class SqlClientSmokeTest:
    """Ελέγχει ότι το πραγματικό EXE περιέχει τη διόρθωση αποτελεσμάτων και timeout."""

    @staticmethod
    def run(report_path):
        """Γράφει αναφορά χωρίς δεδομένα, connection strings ή παραγωγικά credentials."""
        try:
            rows = [[str(i), 'Αθήνα' + ('x' * 10000 if i == 0 else ''), *['v'] * 40] for i in range(1201)]

            class Cursor:
                description = [(f'C{i}',) for i in range(42)]
                rowcount = -1

                def execute(self, sql):
                    self.position = 0

                def fetchmany(self, size):
                    result = rows[self.position:self.position + size]
                    self.position += len(result)
                    return result

                def nextset(self):
                    return False

            class Connection:
                timeout = None

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def cursor(self):
                    return Cursor()

            connection = Connection()
            executor = SqlExecutor()
            with patch('app.sql_executor.pyodbc.drivers', return_value=['ODBC Driver 17 for SQL Server']), \
                 patch('app.sql_executor.pyodbc.connect', return_value=connection):
                result = executor.execute_sql('SMOKE', 'Server=TEST;Database=TEST;', 'SELECT test', 0)
                assert result['success'] and connection.timeout == 0
            dataset = result['batches'][0]['result_sets'][0]
            assert len(dataset['rows']) == 1201 and len(dataset['rows'][0][1]) > 10000
            assert not dataset['limited'] and executor._serialize_value(None) is None
            envelope = {'type': 'sql_result', 'client_code': 'SMOKE', 'request_id': 'SMOKE', 'bo_connection_id': 1, **result}
            packets = [json.loads(packet) for packet in SqlResultTransport.messages(envelope)]
            assert len(packets) > 1
            raw = b''.join(base64.b64decode(packet['transfer']['data']) for packet in packets)
            assert json.loads(raw) == envelope
            report = {'success': True, 'complete_rows': 1201, 'complete_cells': True,
                      'unlimited_query_timeout': True, 'chunked_transfer': True}
            code = 0
        except Exception as exc:
            report = {'success': False, 'exception': type(exc).__name__}
            code = 1
        Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
        return code
