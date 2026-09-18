"""Έλεγχος πραγματικού Overview CLI EXE με προσωρινό δοκιμαστικό Server."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
import websockets


class OverviewCLISmoke:
    """Ελέγχει read, rename και reset αποκλειστικά σε συνθετικό Client."""

    @staticmethod
    async def run(exe,folder):
        result=subprocess.run([exe,'--help'],cwd=folder,capture_output=True,timeout=30)
        assert result.returncode==0 and 'Overview' in result.stdout.decode('utf-8')
        async def handler(ws):
            assert json.loads(await ws.recv())=={'type':'authenticate','token':'FAKE'}
            await ws.send(json.dumps({'type':'dashboard_connected'}))
            request=json.loads(await ws.recv())
            client={'client_code':'SMOKE','display_name':'Αθήνα','pc_name':'PC-01','client_token':'SECRET'}
            if request['type']=='refresh_clients':reply={'type':'clients_list','clients':[client]}
            elif request['type']=='rename_client':
                assert request['display_name']=='Αθήνα'
                reply={'type':'rename_client_success','client':client}
            else:
                assert request['type']=='reset_client_token'
                reply={'type':'client_token_reset_success','client_code':'SMOKE','client':client}
            await ws.send(json.dumps(reply,ensure_ascii=False))
        async with websockets.serve(handler,'127.0.0.1',0) as server:
            env={**os.environ,'DASHBOARD_TOKEN':'FAKE','DASHBOARD_WEBSOCKET_URL':f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}',
                 'MOONHARD_DASHBOARD_DATA_DIR':str(Path(folder)/'logs')}
            for flags in ([],['--rename','Αθήνα'],['--reset-token','--confirm','RESET']):
                process=await asyncio.create_subprocess_exec(exe,'--client','SMOKE',*flags,cwd=folder,env=env,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                try:stdout,stderr=await asyncio.wait_for(process.communicate(),45)
                except asyncio.TimeoutError:process.kill();await process.wait();raise
                assert process.returncode==0,stderr.decode('utf-8',errors='replace')
                data=json.loads(stdout.decode('utf-8'))
                assert 'SECRET' not in json.dumps(data)
                assert data.get('client_code')=='SMOKE' or data['client']['client_code']=='SMOKE'
        print('Overview CLI EXE: OK')


if __name__=='__main__':asyncio.run(OverviewCLISmoke.run(sys.argv[1],sys.argv[2]))
