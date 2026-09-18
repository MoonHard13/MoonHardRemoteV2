"""Έλεγχος του πραγματικού Overview μέσα στο Dashboard EXE."""

import json
import traceback
from pathlib import Path
import customtkinter as ctk
from app.views.client_manage_window import ClientManageWindow
from app.views.manage.overview_tab import TokenResetDialog


class OverviewSmokeTest:
    """Δοκιμάζει Manage layout και ασφαλή UI με συνθετικά δεδομένα."""

    @staticmethod
    def run(report_path):
        """Δεν συνδέεται σε Server και δεν αλλάζει πραγματικό Client."""
        root=window=None
        try:
            ctk.set_appearance_mode('dark');root=ctk.CTk();root.withdraw()
            client={'client_code':'SMOKE','display_name':'InitialTest','pc_name':'PC-01','username':'operator',
                'status':'online','ws_connected':True,'group_name':'Support','last_seen':'2026-09-18T12:00:00+00:00',
                'app_version':'1.0.3','amv_version':'13.30.000','bo_version':'13.30.001',
                'etp_version':'4.1.0.1','aws_version':'7.6.0.0','client_token':'SECRET_SMOKE'}
            renames=[]
            window=ClientManageWindow(root,client,on_rename_callback=lambda code,name:renames.append((code,name)))
            # Το Windows Toplevel εμφανίζεται ασύγχρονα. Περιμένουμε τον
            # πραγματικό βρόχο Tk και τις αρχικές αλλαγές titlebar/theme,
            # που επαναφέρουν τη γεωμετρία, πριν κάνουμε resize και μέτρηση.
            window.after(350,root.quit);root.mainloop();root.update()
            window.geometry('1350x900');window.after(150,root.quit);root.mainloop()
            tab=window.overview_tab_view;tab._apply_layout();root.update()
            assert not hasattr(window,'header_title_label') and not hasattr(window,'header_info_label')
            assert window.tabs.winfo_height()>window.winfo_height()*.9
            assert int(tab.right_stack.grid_info()['column'])==1, f'Wide layout width={tab.winfo_width()}'
            tab.copy_details();assert 'SECRET' not in root.clipboard_get()
            try:
                import os
                from PIL import ImageGrab
                if os.name=='nt':
                    window.lift();window.focus_force();root.update()
                    ImageGrab.grab(bbox=(window.winfo_rootx(),window.winfo_rooty(),
                        window.winfo_rootx()+window.winfo_width(),window.winfo_rooty()+window.winfo_height())).save(str(Path(report_path).with_suffix('.png')))
            except Exception:pass
            tab.rename_entry.delete(0,'end');tab.rename_entry.insert(0,'Αθήνα')
            window.update_client_data({**client,'amv_version':'UPDATED'})
            assert tab.rename_entry.get()=='Αθήνα' and tab.fields['amv_version'].entry.get()=='UPDATED'
            tab._save_name();tab._save_name();assert renames==[('SMOKE','Αθήνα')]
            tab.handle_rename_result({'type':'rename_client_success','client':{**client,'display_name':'Αθήνα'}})
            assert not tab.name_pending
            dialog=TokenResetDialog(window)
            assert str(dialog.transient())==str(window)
            def confirm():
                dialog.entry.insert(0,'RESET');dialog._confirm()
            window.after(150,confirm);assert dialog.get_input()=='RESET'
            window.geometry('900x600');window.after(150,root.quit);root.mainloop()
            root.update();tab._apply_layout();root.update()
            assert int(tab.right_stack.grid_info()['column'])==0
            tab.set_dashboard_online(False);assert tab.rename_button.cget('state')=='disabled'
            report={'success':True,'manage_header_removed':True,'responsive_overview':True,
                    'safe_copy':True,'draft_preserved':True,'rename_confirmed':True,'owned_confirmation':True}
            code=0
        except Exception as exc:
            report={'success':False,'exception':type(exc).__name__,'message':str(exc),'line':traceback.extract_tb(exc.__traceback__)[-1].lineno};code=1
        finally:
            if root:
                if window:window.destroy()
                for job in root.tk.call('after','info'):root.after_cancel(job)
                root.destroy()
        Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return code
