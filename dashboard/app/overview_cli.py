"""CLI για ασφαλή Overview metadata, rename και το υπάρχον token reset."""

import argparse
import asyncio
import json
import logging
import sys
import websockets
from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig
from app.overview_presenter import OverviewPresenter

logger = logging.getLogger(__name__)


class OverviewCLI:
    """Χρησιμοποιεί τις υπάρχουσες ρυθμίσεις και αιτήματα, χωρίς νέα Server API."""

    @staticmethod
    def parser():
        """Το reset απαιτεί την ίδια ρητή επιβεβαίωση με το GUI."""
        parser = argparse.ArgumentParser(description='MoonHard Overview: στοιχεία και διαχείριση Client.')
        parser.add_argument('--client', required=True)
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument('--rename', metavar='NAME')
        actions.add_argument('--reset-token', action='store_true')
        parser.add_argument('--confirm', choices=['RESET'])
        return parser

    @staticmethod
    def payload(args):
        """Επικυρώνει την ενέργεια πριν δημιουργηθεί σύνδεση."""
        if args.reset_token:
            if args.confirm != 'RESET':
                raise ValueError('Το reset απαιτεί --confirm RESET.')
            return {'type': 'reset_client_token', 'client_code': args.client}
        if args.confirm:
            raise ValueError('Το --confirm αφορά μόνο --reset-token.')
        if args.rename is not None:
            return {'type': 'rename_client', 'client_code': args.client,
                    'display_name': OverviewPresenter.validate_name(args.rename)}
        return {'type': 'refresh_clients'}

    async def request(self, config, args):
        """Περιμένει αποτέλεσμα από την ίδια αυθεντικοποιημένη σύνδεση."""
        request = self.payload(args)
        if not config.dashboard_token:
            raise ValueError('Δεν έχει οριστεί DASHBOARD_TOKEN.')
        async with websockets.connect(config.dashboard_websocket_url, open_timeout=15, close_timeout=5) as ws:
            await ws.send(json.dumps({'type': 'authenticate', 'token': config.dashboard_token}))
            async def authenticate():
                while True:
                    item = json.loads(await ws.recv())
                    if item.get('type') == 'dashboard_connected':return
                    if item.get('type') == 'error':raise ValueError('Απέτυχε η αυθεντικοποίηση.')
            await asyncio.wait_for(authenticate(), 15)
            await ws.send(json.dumps(request, ensure_ascii=False))
            logger.info('Αίτημα Overview CLI. type=%s client_code=%s',request['type'],args.client)
            async def receive():
                while True:
                    item = json.loads(await ws.recv());kind = item.get('type')
                    if request['type'] == 'refresh_clients' and kind == 'clients_list':
                        client = next((client for client in item.get('clients', []) if client.get('client_code') == args.client),None)
                        if client is None:raise ValueError('Δεν βρέθηκε ο Client.')
                        return OverviewPresenter.safe_data(client)
                    if request['type'] == 'rename_client' and kind == 'rename_client_success':
                        client = item.get('client') or {}
                        if client.get('client_code') == args.client:
                            return {'success': True, 'client': OverviewPresenter.safe_data(client)}
                    if request['type'] == 'rename_client' and kind == 'rename_client_error':
                        raise ValueError('Αποτυχία αλλαγής ονόματος.')
                    if request['type'] == 'reset_client_token' and item.get('client_code') == args.client:
                        if kind == 'client_token_reset_success':return {'success': True, 'client_code': args.client, 'reconnect_required': True}
                        if kind == 'client_token_reset_error':raise ValueError('Αποτυχία reset token.')
            return await asyncio.wait_for(receive(), 30)

    def run(self, argv=None):
        """Γράφει UTF-8 JSON και κρατά logs στο stderr χωρίς μυστικά."""
        for stream in (sys.stdout,sys.stderr):
            if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
        args = self.parser().parse_args(argv)
        config = DashboardConfig();DashboardLoggerConfig.setup_logging(config.log_dir)
        for handler in logging.getLogger().handlers:
            if type(handler) is logging.StreamHandler:handler.setStream(sys.stderr)
        try:
            print(json.dumps(asyncio.run(self.request(config,args)),ensure_ascii=False,indent=2))
            return 0
        except KeyboardInterrupt:
            logger.info('Διακοπή Overview CLI από χρήστη.');return 130
        except Exception as exc:
            logger.error('Αποτυχία Overview CLI. exception_type=%s',type(exc).__name__)
            print(json.dumps({'success':False,'message':str(exc) if isinstance(exc,ValueError) else
                  'Αποτυχία σύνδεσης ή λήξη αναμονής. Η ενέργεια δεν επιβεβαιώθηκε.'},ensure_ascii=False),file=sys.stderr)
            return 1


def main(argv=None):
    """Σημείο εισόδου source και console EXE."""
    return OverviewCLI().run(argv)


if __name__ == '__main__':raise SystemExit(main())
