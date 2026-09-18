"""Δοκιμές Overview, απουσίας Manage header και CLI χωρίς παραγωγικές ενέργειες."""

import asyncio
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'dashboard'))
from app.overview_presenter import OverviewPresenter
from app.overview_cli import OverviewCLI


def sample(**updates):
    return {'client_code':'TEST','display_name':'InitialTest','pc_name':'PC-01','username':'operator',
            'status':'online','ws_connected':True,'group_name':'Support','last_seen':'2026-09-18T12:00:00+00:00',
            'app_version':'1.0.3','amv_version':'13.30.000','bo_version':'13.30.001',
            'etp_version':'4.1.0.1','aws_version':'7.6.0.0','client_token':'SECRET_TOKEN',
            'database_password':'SECRET_PASSWORD',**updates}


class OverviewDataTests(unittest.TestCase):
    def test_safe_metadata_and_missing_fields(self):
        raw=sample();data=OverviewPresenter.safe_data(raw)
        self.assertNotIn('SECRET',json.dumps(data));self.assertEqual(raw['client_token'],'SECRET_TOKEN')
        self.assertEqual(OverviewPresenter.safe_data({})['display_name'],'—')
        self.assertEqual(OverviewPresenter.safe_data({'pc_name':'PC'})['display_name'],'PC')
        self.assertIn('2026',OverviewPresenter.last_seen(raw['last_seen']))
        self.assertEqual(OverviewPresenter.last_seen('invalid'),'invalid')

    def test_cli_validates_name_and_requires_reset_confirmation(self):
        parser=OverviewCLI.parser()
        for name in ('','  ','bad\nname'):
            with self.assertRaises(ValueError):OverviewCLI.payload(parser.parse_args(['--client','TEST','--rename',name]))
        self.assertEqual(OverviewCLI.payload(parser.parse_args(['--client','TEST','--rename',' Αθήνα ']))['display_name'],'Αθήνα')
        with self.assertRaises(ValueError):OverviewCLI.payload(parser.parse_args(['--client','TEST','--reset-token']))
        self.assertEqual(OverviewCLI.payload(parser.parse_args(['--client','TEST','--reset-token','--confirm','RESET']))['type'],'reset_client_token')

    def test_cli_protocol_for_info_rename_and_reset(self):
        import websockets
        async def scenario(action):
            async def handler(ws):
                self.assertEqual(json.loads(await ws.recv()),{'type':'authenticate','token':'FAKE'})
                await ws.send(json.dumps({'type':'dashboard_connected'}))
                request=json.loads(await ws.recv())
                if action=='info':reply={'type':'clients_list','clients':[sample(client_code='OTHER'),sample()]}
                elif action=='rename':
                    self.assertEqual(request['display_name'],'Αθήνα')
                    await ws.send(json.dumps({'type':'rename_client_success','client':sample(client_code='OTHER')}))
                    reply={'type':'rename_client_success','client':sample(display_name='Αθήνα')}
                else:
                    self.assertEqual(request['type'],'reset_client_token')
                    reply={'type':'client_token_reset_success','client_code':'TEST','client':sample()}
                await ws.send(json.dumps(reply))
            async with websockets.serve(handler,'127.0.0.1',0) as server:
                config=SimpleNamespace(dashboard_token='FAKE',dashboard_websocket_url=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
                flags=[] if action=='info' else ['--rename','Αθήνα'] if action=='rename' else ['--reset-token','--confirm','RESET']
                args=OverviewCLI.parser().parse_args(['--client','TEST',*flags])
                result=await OverviewCLI().request(config,args)
                self.assertNotIn('SECRET',json.dumps(result))
                self.assertEqual(result.get('client_code') or result['client']['client_code'],'TEST')
        for action in ('info','rename','reset'):asyncio.run(scenario(action))


@unittest.skipUnless(importlib.util.find_spec('customtkinter') and (os.name=='nt' or os.environ.get('DISPLAY')),'Απαιτεί Tk και οθόνη.')
class OverviewUITests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk
        from app.views.manage.overview_tab import OverviewTab
        ctk.set_appearance_mode('dark')
        self.root=ctk.CTk();self.root.geometry('1350x900')
        self.root.grid_columnconfigure(0,weight=1);self.root.grid_rowconfigure(0,weight=1)
        self.renames=[];self.resets=[]
        self.tab=OverviewTab(self.root,sample(),lambda code,name:self.renames.append((code,name)),self.resets.append)
        self.tab.grid(sticky='nsew');self.root.update();self.tab._apply_layout();self.root.update()

    def tearDown(self):
        self.tab.destroy()
        for job in self.root.tk.call('after','info'):self.root.after_cancel(job)
        self.root.destroy()

    def edit_name(self,name):
        self.tab.rename_entry.delete(0,'end');self.tab.rename_entry.insert(0,name)

    def test_responsive_columns_and_readonly_copy(self):
        self.assertEqual(int(self.tab.right_stack.grid_info()['column']),1)
        self.assertGreater(self.tab.scroll.winfo_height(),self.tab.winfo_height()*.8)
        self.tab.copy_details();self.assertIn('InitialTest',self.root.clipboard_get());self.assertNotIn('SECRET',self.root.clipboard_get())
        entry=self.tab.fields['pc_name'].entry
        entry.delete(0,'end');entry.insert(0,'MODIFIED');self.assertEqual(entry.get(),'PC-01')
        self.root.geometry('900x600');self.root.update();self.tab._apply_layout();self.root.update()
        self.assertEqual(int(self.tab.right_stack.grid_info()['column']),0)
        self.assertEqual(int(self.tab.right_stack.grid_info()['row']),1)

    def test_heartbeat_preserves_draft_and_updates_versions(self):
        self.tab.rename_entry._entry.icursor(3)
        self.tab.update_client_data(sample())
        self.assertEqual(self.tab.rename_entry._entry.index('insert'),3)
        self.edit_name('Draft')
        self.tab.update_client_data(sample(amv_version='NEW',status='offline',ws_connected=False))
        self.assertEqual(self.tab.rename_entry.get(),'Draft')
        self.assertEqual(self.tab.fields['amv_version'].entry.get(),'NEW')
        self.assertEqual(self.tab.status_badge.cget('text'),'Offline')
        self.tab.revert_name();self.assertEqual(self.tab.rename_entry.get(),'InitialTest')

    def test_rename_validation_confirmation_and_new_draft(self):
        self.edit_name('  ');self.tab._save_name();self.assertFalse(self.renames)
        self.edit_name('Αθήνα');self.tab._save_name();self.tab._save_name()
        self.assertEqual(self.renames,[('TEST','Αθήνα')]);self.assertTrue(self.tab.name_pending)
        self.edit_name('Second draft')
        self.tab.handle_rename_result({'type':'rename_client_success','client':sample(display_name='Αθήνα')})
        self.assertFalse(self.tab.name_pending);self.assertEqual(self.tab.rename_entry.get(),'Second draft')
        self.assertEqual(self.tab.fields['display_name'].entry.get(),'Αθήνα')
        self.tab.revert_name();self.assertEqual(self.tab.rename_entry.get(),'Αθήνα')

    def test_failed_send_error_and_timeout_restore_buttons(self):
        self.edit_name('Changed');self.tab.on_rename_callback=lambda *args:False;self.tab._save_name()
        self.assertFalse(self.tab.name_pending)
        self.tab.on_rename_callback=lambda *args:None;self.tab._save_name()
        self.tab.handle_rename_result({'type':'rename_client_error'})
        self.assertFalse(self.tab.name_pending);self.assertEqual(self.tab.rename_entry.get(),'Changed')
        self.tab._save_name();self.tab.after_cancel(self.tab._name_job);self.tab._name_timeout()
        self.assertEqual(self.tab.rename_button.cget('state'),'normal')

    def test_token_confirmation_result_matching_and_no_secrets(self):
        with patch('app.views.manage.overview_tab.TokenResetDialog') as dialog:
            dialog.return_value.get_input.return_value=None;self.tab._reset_client_token();self.assertFalse(self.resets)
            dialog.return_value.get_input.return_value='RESET';self.tab._reset_client_token();self.tab._reset_client_token()
            self.assertEqual(self.resets,['TEST'])
            self.tab.handle_client_token_reset_result({'type':'client_token_reset_success','client_code':'OTHER'})
            self.assertEqual(self.tab.reset_token_button.cget('state'),'disabled')
            self.tab.handle_client_token_reset_result({'type':'client_token_reset_error','client_code':'TEST','message':'SECRET_TOKEN'})
            self.assertEqual(self.tab.reset_token_button.cget('state'),'normal')
            self.assertNotIn('SECRET',self.tab.security_status_label.cget('text'))

    def test_shortcut_scope_and_dashboard_disconnect(self):
        self.edit_name('Shortcut');self.tab.rename_entry.focus_force();self.root.update()
        self.tab.rename_entry._entry.event_generate('<Control-s>');self.root.update()
        self.assertEqual(len(self.renames),1)
        self.tab.set_dashboard_online(False)
        self.assertFalse(self.tab.name_pending);self.assertEqual(self.tab.status_badge.cget('text'),'Stale')
        self.assertIn('Dashboard disconnected',self.tab.fields['connection'].entry.get())
        self.assertEqual(self.tab.rename_button.cget('state'),'disabled')
        self.tab.set_dashboard_online(True);self.assertEqual(self.tab.rename_button.cget('state'),'normal')

    def test_manage_header_removed_tabs_fill_window_and_title_updates(self):
        from app.views.client_manage_window import ClientManageWindow
        window=ClientManageWindow(self.root,sample())
        try:
            window.geometry('1350x900');self.root.update()
            self.assertFalse(hasattr(window,'header_title_label'));self.assertFalse(hasattr(window,'header_info_label'))
            self.assertEqual(int(window.tabs.grid_info()['row']),0)
            self.assertGreater(window.tabs.winfo_height(),window.winfo_height()*.9)
            window.update_client_data(sample(display_name='Changed'))
            self.assertIn('Changed',window.title())
        finally:window.destroy()

    def test_dashboard_send_return_and_success_routing(self):
        from app.dashboard_app import MoonHardDashboardApp
        fake=SimpleNamespace(websocket_client=SimpleNamespace(send_message=Mock(return_value=False)))
        self.assertFalse(MoonHardDashboardApp._rename_client(fake,'TEST','Changed'))
        self.assertFalse(MoonHardDashboardApp._reset_client_token(fake,'TEST'))
        window=SimpleNamespace(winfo_exists=lambda:True,overview_tab_view=self.tab,update_client_data=Mock())
        fake.manage_windows={'TEST':window}
        self.edit_name('Changed');self.tab._save_name()
        MoonHardDashboardApp._handle_websocket_message(fake,{'type':'rename_client_success','client':sample(display_name='Changed')})
        self.assertFalse(self.tab.name_pending);window.update_client_data.assert_called_once()


if __name__=='__main__':unittest.main()
