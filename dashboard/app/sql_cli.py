"""Εκτέλεση SQL και έλεγχος σύνδεσης από CMD με το ίδιο πρωτόκολλο του SSMS."""

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

import websockets
from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig
from app.sql_workspace import SqlFiles, SqlResultData
from app.sql_transfer import SqlResultAssembler

logger = logging.getLogger(__name__)


class SqlCLI:
    """Υποστηρίζει scripts, αρχεία, δοκιμή σύνδεσης και εξαγωγή επιστρεφόμενων αποτελεσμάτων."""

    @staticmethod
    def parser():
        """Ορίζει μία σαφή ενέργεια ανά κλήση."""
        parser = argparse.ArgumentParser(description='MoonHard SSMS: εκτέλεση SQL μέσω απομακρυσμένου Client.')
        parser.add_argument('--client', required=True)
        parser.add_argument('--bo-connection', type=int, default=1)
        actions = parser.add_mutually_exclusive_group(required=True)
        actions.add_argument('--query', help='SQL κείμενο για εκτέλεση.')
        actions.add_argument('--file', help='Διαδρομή SQL αρχείου.')
        actions.add_argument('--test-connection', action='store_true')
        parser.add_argument('--timeout', type=int, default=120, help='Query timeout, 0–3600 δευτερόλεπτα (0 = χωρίς όριο).')
        parser.add_argument('--format', choices=('json', 'csv', 'tsv'), default='json')
        parser.add_argument('--result-set', type=int, default=1, help='Result set για CSV/TSV, με αρίθμηση από 1.')
        return parser

    @staticmethod
    def payload(args):
        """Μετατρέπει τις επιλογές στο υπάρχον πρωτόκολλο, χωρίς νέα API."""
        if not 0 <= args.timeout <= 3600 or args.bo_connection < 1 or args.result_set < 1:
            raise ValueError('Ελέγξτε timeout, BOConnection ID και αριθμό result set.')
        payload = {'type': 'sql_test_connection' if args.test_connection else 'sql_execute',
                   'client_code': args.client, 'request_id': str(uuid.uuid4()),
                   'bo_connection_id': args.bo_connection, 'timeout': 15 if args.test_connection else args.timeout}
        if not args.test_connection:
            sql = SqlFiles.read(Path(args.file))[0] if args.file else args.query
            if not sql or not sql.strip():
                raise ValueError('Το SQL κείμενο είναι κενό.')
            payload['sql_text'] = sql.strip()
        return payload

    async def request(self, config, payload):
        """Περιμένει μόνο συσχετισμένη απάντηση και ζητά ακύρωση σε Ctrl+C ή λήξη αναμονής."""
        if not config.dashboard_token:
            raise ValueError('Δεν έχει οριστεί DASHBOARD_TOKEN.')
        async with websockets.connect(config.dashboard_websocket_url, open_timeout=15, close_timeout=5) as ws:
            await ws.send(json.dumps({'type': 'authenticate', 'token': config.dashboard_token}))
            async def authenticate():
                """Αγνοεί αρχικές ενημερώσεις του Dashboard."""
                while True:
                    item = json.loads(await ws.recv())
                    if item.get('type') == 'dashboard_connected':
                        return
                    if item.get('type') == 'error':
                        raise ValueError('Απέτυχε η αυθεντικοποίηση.')
            await asyncio.wait_for(authenticate(), 15)
            await ws.send(json.dumps(payload, ensure_ascii=False))
            logger.info('Αποστολή CLI SSMS. type=%s request_id=%s bo_id=%s',
                        payload['type'], payload['request_id'], payload['bo_connection_id'])
            async def receive():
                """Απορρίπτει παλιές ή ξένες απαντήσεις."""
                assembler = SqlResultAssembler()
                expected = 'sql_test_connection_result' if payload['type'] == 'sql_test_connection' else 'sql_result'
                while True:
                    item = json.loads(await ws.recv())
                    if (item.get('request_id') == payload['request_id'] and item.get('client_code') == payload['client_code']
                        and item.get('type') in (expected, 'sql_error')):
                        if item.get('type') == 'sql_error':
                            assembler.reset()
                            return item
                        result = assembler.feed(item)
                        if result is not None:
                            return result
            try:
                return await asyncio.wait_for(receive(), None if payload['timeout'] == 0 else payload['timeout'] + 30)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                if payload['type'] == 'sql_execute':
                    try:
                        await ws.send(json.dumps({'type': 'sql_cancel', 'request_id': payload['request_id'],
                                                  'client_code': payload['client_code']}))
                        logger.info('Αίτημα ακύρωσης CLI SSMS.')
                    except Exception:
                        logger.error('Αποτυχία αποστολής ακύρωσης CLI SSMS.')
                raise

    @staticmethod
    def render(result, args):
        """Παράγει JSON ή ένα επιστρεφόμενο result set με κοινή μορφοποίηση του GUI."""
        if args.format == 'json':
            return json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        datasets = SqlResultData.sets(result)
        if args.result_set > len(datasets):
            raise ValueError('Δεν βρέθηκε το ζητούμενο result set.')
        item = datasets[args.result_set - 1]
        return ('\ufeff' if args.format == 'csv' else '') + SqlResultData.delimited(
            item['columns'], item.get('rows') or [], ',' if args.format == 'csv' else '\t')

    def run(self, argv=None):
        """Χρησιμοποιεί UTF-8 output και κρατά τα logs στο stderr."""
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8', errors='replace')
        parser = self.parser()
        args = parser.parse_args(argv)
        if args.test_connection and args.format != 'json':
            parser.error('Το Test Connection επιστρέφει JSON.')
        config = DashboardConfig()
        DashboardLoggerConfig.setup_logging(config.log_dir)
        for handler in logging.getLogger().handlers:
            if type(handler) is logging.StreamHandler:
                handler.setStream(sys.stderr)
        try:
            payload = self.payload(args)
            result = asyncio.run(self.request(config, payload))
            print(self.render(result, args), end='')
            return 1 if SqlResultData.failed(result) else 0
        except KeyboardInterrupt:
            logger.info('Διακοπή CLI SSMS από χρήστη.')
            return 130
        except Exception as exc:
            logger.error('Αποτυχία CLI SSMS. exception_type=%s', type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) else 'Αποτυχία σύνδεσης, αρχείου ή λήξη αναμονής. Δεν επιβεβαιώθηκε η ολοκλήρωση του SQL.'
            print(json.dumps({'success': False, 'message': message}, ensure_ascii=False), file=sys.stderr)
            return 1


def main(argv=None):
    """Σημείο εισόδου για source και console EXE."""
    return SqlCLI().run(argv)


if __name__ == '__main__':
    raise SystemExit(main())
