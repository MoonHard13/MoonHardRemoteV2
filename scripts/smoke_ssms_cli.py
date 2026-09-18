"""Έλεγχος console SSMS EXE με συνθετικό τοπικό SQL πρωτόκολλο."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
import websockets
import importlib.util

spec = importlib.util.spec_from_file_location('ssms_smoke_transport', Path(__file__).resolve().parents[1] / 'client/app/sql_transport.py')
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


async def run(exe, folder):
    """Ελέγχει τη συσκευασία χωρίς παραγωγικές συνδέσεις ή SQL queries."""
    help_result=subprocess.run([exe,'--help'],cwd=folder,capture_output=True,timeout=30)
    assert help_result.returncode==0 and 'SSMS' in help_result.stdout.decode('utf-8')
    async def handler(ws):
        """Εξυπηρετεί μόνο τη δοκιμαστική εκτέλεση."""
        assert json.loads(await ws.recv())=={'type':'authenticate','token':'FAKE_SMOKE'}
        await ws.send(json.dumps({'type':'dashboard_connected'}))
        request=json.loads(await ws.recv())
        assert request['type']=='sql_execute' and request['sql_text']=='SELECT 1'
        assert request['timeout'] == 0
        result = {'type':'sql_result','request_id':request['request_id'],'client_code':'SMOKE',
            'bo_connection_id':1,'success':True,'elapsed_ms':1,'batches':[{'batch_index':1,'result_sets':[
                {'columns':['ID','City'],'rows':[[i,'Αθήνα' * 100] for i in range(1501)]}]}]}
        for packet in module.SqlResultTransport.messages(result):
            await ws.send(packet)
    async with websockets.serve(handler,'127.0.0.1',0) as server:
        env={**os.environ,'DASHBOARD_TOKEN':'FAKE_SMOKE',
             'DASHBOARD_WEBSOCKET_URL':f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}",
             'MOONHARD_DASHBOARD_DATA_DIR':str(Path(folder)/'logs')}
        process=await asyncio.create_subprocess_exec(exe,'--client','SMOKE','--query','SELECT 1','--format','csv','--timeout','0',
            cwd=folder,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:stdout,stderr=await asyncio.wait_for(process.communicate(),45)
        except asyncio.TimeoutError:
            process.kill();await process.wait();raise
        assert process.returncode==0,stderr.decode('utf-8',errors='replace')
        assert stdout.startswith(b'\xef\xbb\xbf')
        text=stdout.decode('utf-8-sig')
        assert 'ID,City' in text and 'Αθήνα' in text and '1500,' in text
        assert len(text.splitlines()) == 1502
    print('SSMS CLI EXE: OK')


if __name__=='__main__':asyncio.run(run(sys.argv[1],sys.argv[2]))
