"""Δοκιμή πραγματικού console EXE με προσωρινό τοπικό WebSocket."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import websockets


async def run(exe: str, working_directory: str) -> None:
    """Ελέγχει τη λειτουργία χωρίς παραγωγικό token ή παραγωγικό server."""
    help_result = subprocess.run([exe, '--help'], cwd=working_directory, capture_output=True, timeout=30)
    assert help_result.returncode == 0
    assert 'AppSettings' in help_result.stdout.decode('utf-8')

    async def handler(ws):
        """Εξυπηρετεί μόνο το ελεγχόμενο αίτημα της δοκιμής."""
        auth = json.loads(await ws.recv())
        assert auth == {'type': 'authenticate', 'token': 'SMOKE_FAKE_TOKEN'}
        await ws.send(json.dumps({'type': 'dashboard_connected'}))
        request = json.loads(await ws.recv())
        assert request == {'type': 'get_client_appsettings', 'client_code': 'SMOKE_TEST'}
        await ws.send(json.dumps({'type': 'client_appsettings_result', 'client_code': 'SMOKE_TEST', 'success': True,
                                 'appsettings': {'file_found': True, 'selected_bo_connection_id': 1,
                                     'bo_connections': [{'ID': 1, 'DatabaseConnection': 'Server=TEST;Database=InitialTest;Password=PRIVATE_PASS',
                                                         'subscriptionKey': 'PRIVATE_KEY'}]}}))

    async with websockets.serve(handler, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        env = {**os.environ, 'DASHBOARD_TOKEN': 'SMOKE_FAKE_TOKEN',
               'DASHBOARD_WEBSOCKET_URL': f'ws://127.0.0.1:{port}',
               'MOONHARD_DASHBOARD_DATA_DIR': str(Path(working_directory) / 'logs')}
        process = await asyncio.create_subprocess_exec(exe, '--client', 'SMOKE_TEST', '--bo-connection', '1',
                   cwd=working_directory, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 45)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise
        assert process.returncode == 0, stderr.decode('utf-8', errors='replace')
        text = stdout.decode('utf-8')
        assert 'PRIVATE' not in text
        result = json.loads(text)
        assert result['bo_connections'][0]['ID'] == 1
        assert 'InitialTest' in result['bo_connections'][0]['DatabaseConnection']
    print('AppSettings CLI EXE: OK')


if __name__ == '__main__':
    asyncio.run(run(sys.argv[1], sys.argv[2]))
