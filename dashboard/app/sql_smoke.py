"""Έλεγχος του πραγματικού SSMS μέσα στο συσκευασμένο Dashboard."""

import json
from pathlib import Path
import customtkinter as ctk
from app.views.manage.sql_tab import SqlTab
from app.ui.theme import COLORS


class SqlSmokeTest:
    """Ελέγχει layout, επιλογή SQL, αντίγραφα και αποτελέσματα χωρίς παραγωγική βάση."""

    @staticmethod
    def run(report_path: str):
        """Γράφει αναφορά με συνθετικά δεδομένα και προαιρετικό screenshot Windows."""
        root = tab = None
        try:
            ctk.set_appearance_mode('dark')
            root = ctk.CTk();root.geometry('1350x900');root.title('MoonHard · SSMS preview')
            root.configure(fg_color=COLORS.background)
            root.grid_columnconfigure(0,weight=1);root.grid_rowconfigure(0,weight=1)
            sent=[]
            tab=SqlTab(root,'SMOKE',sent.append);tab.grid(sticky='nsew')
            tab.set_bo_values(['ID 1 - InitialTest'],'ID 1 - InitialTest')
            root.update();tab._apply_layout();root.update()
            assert tab.splitter.winfo_height()>tab.winfo_height()*.7
            tab.sql_editor.delete('1.0','end')
            tab.sql_editor.insert('1.0',"SELECT 1 AS ID, N'Αθήνα' AS City;\nSELECT 2;")
            tab.sql_editor._textbox.tag_add('sel','1.0','1.end')
            tab.timeout_entry.delete(0, 'end');tab.timeout_entry.insert(0, '0')
            tab.execute_sql();tab.execute_sql()
            assert len(sent)==1 and sent[0]['sql_text'].endswith("AS City;")
            assert tab.busy and tab.execute_button.cget('state')=='disabled'
            rid=tab.current_sql_request_id
            tab.handle_sql_result({'client_code':'SMOKE','request_id':'OLD','success':True})
            assert tab.busy
            tab.handle_sql_result({'type':'sql_result','client_code':'SMOKE','request_id':rid,'bo_connection_id':1,
                'success':True,'elapsed_ms':25,'driver':'TEST','batches':[{'batch_index':1,'result_sets':[
                    {'columns':['ID','City','Note'],'rows':[[1,'Αθήνα','Δοκιμή'],[2,'Θεσσαλονίκη','Preview']], 'limited':False}]}]})
            root.update()
            assert not tab.busy
            assert sent[0]['timeout'] == 0
            sheet = tab.results_panel.tables[tab.results_panel.selector.get()][1]
            sheet.select_cell(0, 1);tab.results_panel.copy_selected()
            assert root.clipboard_get().strip() == 'Αθήνα'
            tab.results_panel.copy_all()
            assert 'Αθήνα' in root.clipboard_get()
            try:
                from PIL import ImageGrab
                import os
                if os.name=='nt':
                    root.lift();root.focus_force();root.update()
                    ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),
                        root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(
                            str(Path(report_path).with_suffix('.png')))
            except Exception:
                pass
            root.geometry('900x600');root.update();tab._apply_layout();root.update()
            assert int(tab.actions.grid_info()['row'])==2
            tab.execute_sql()
            tab.handle_sql_error({'client_code':'SMOKE','request_id':tab.current_sql_request_id,'message':'Test routing error'})
            assert not tab.busy and tab.stop_sql_button.cget('state')=='disabled'
            result={'success':True,'resizable_workspace':True,'selected_sql':True,'safe_request_matching':True,
                    'result_grid':True,'copy_results':True,'routing_error_recovery':True}
            code=0
        except Exception as exc:
            result={'success':False,'exception':type(exc).__name__,'message':str(exc)};code=1
        finally:
            if root:
                if tab:tab.destroy()
                for job in root.tk.call('after','info'):root.after_cancel(job)
                root.destroy()
        Path(report_path).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return code
