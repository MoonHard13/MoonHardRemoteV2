"""Έλεγχος της καρτέλας AppSettings μέσα στο συσκευασμένο Dashboard."""

import json
from pathlib import Path

import customtkinter as ctk

from app.views.manage.appsettings_tab import AppSettingsTab


class AppSettingsSmokeTest:
    """Ελέγχει πραγματικό UI και προστασία τιμών χωρίς σύνδεση σε πελάτη."""

    @staticmethod
    def sample() -> dict:
        """Παρέχει τεχνητές ρυθμίσεις αποκλειστικά για δοκιμές και προεπισκόπηση."""
        return {'file_found': True,
                'file_path': r'C:\Program Files (x86)\Sunsoft Ltd\ExternalTaxProvider\External.Tax.Provider\appsettings.production.json',
                'last_read_at': '2026-09-18T12:30:00+03:00', 'selected_bo_connection_id': 1,
                'appsettings_summary': {'AllowedHosts': '*', 'MaxRetries': 10,
                                        'MaxWaitTimePerInvoice': 15, 'initialDate': 20240101},
                'bo_connections': [{'ID': 1, 'DatabaseConnection': 'Server=TEST-PC;Database=InitialTest;User ID=PRIVATE_USER;Password=PRIVATE_PASS',
                                    'UserOID': 1, 'email': 'support@example.com', 'ClientAuth': 'PRIVATE_AUTH',
                                    'subscriptionKey': 'PRIVATE_KEY', 'HasDatabaseUser': True, 'HasDatabasePassword': True}],
                'provider_connections': [{'ID': 1, 'BaseURL': 'https://provider.example.com/api',
                                          'OfflineURL': 'http://localhost:5000'}]}

    @classmethod
    def run(cls, report_path: str) -> int:
        """Γράφει αναφορά και ελέγχει διαστάσεις, αντιγραφή, κενές καταστάσεις και αλλαγή προβολής."""
        root = None
        tab = None
        try:
            root = ctk.CTk()
            root.title('MoonHard · AppSettings preview')
            root.geometry('1350x900')
            root.grid_columnconfigure(0, weight=1)
            root.grid_rowconfigure(0, weight=1)
            tab = AppSettingsTab(root)
            tab.grid(sticky='nsew')
            tab.set_bo_values(['ID 1 - InitialTest'], 'ID 1 - InitialTest')
            tab.set_data(cls.sample(), {'ID': 1})
            root.update()
            tab._apply_layout()
            root.update()
            assert tab.content.winfo_height() > tab.winfo_height() * .6
            assert tab.detail_cards[0].fields['Database'].get() == 'InitialTest'
            assert tab.detail_cards[0].fields['Database']._entry.cget('state') == 'readonly'
            tab.copy_json()
            assert 'PRIVATE' not in root.clipboard_get()
            tab.toggle_mode()
            root.update()
            assert tab.details_box.winfo_ismapped()
            tab.toggle_mode()
            root.geometry('800x700')
            root.update()
            tab._apply_layout()
            assert int(tab.detail_cards[1].grid_info()['column']) == 0
            tab.set_data({'file_found': False, 'file_path': r'C:\Missing.json'})
            assert tab.bo_connection_option.cget('state') == 'disabled'
            result = {'success': True, 'readonly_fields': True, 'safe_json': True,
                      'responsive_layout': True, 'empty_state': True}
            code = 0
        except Exception as exc:
            result = {'success': False, 'exception': type(exc).__name__, 'message': str(exc)}
            code = 1
        finally:
            if root:
                if tab:
                    tab.destroy()
                for job in root.tk.call('after', 'info'):
                    root.after_cancel(job)
                root.destroy()
        Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return code
