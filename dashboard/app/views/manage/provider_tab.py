import uuid
from datetime import datetime, timedelta
from typing import Callable

import customtkinter as ctk
from tkinter import ttk


class ProviderTab(ctk.CTkFrame):
    """
    Provider/MUPT tab για remote διαχείριση παραστατικών.
    Δεν αποθηκεύει δεδομένα MUPT στον server ή στη Supabase.
    """

    def __init__(
        self,
        parent,
        client_code: str,
        get_bo_values_callback: Callable[[], list[str]] | None = None,
        get_selected_bo_id_callback: Callable[[], int] | None = None,
        on_provider_request_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το Provider tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client_code = client_code
        self.get_bo_values_callback = get_bo_values_callback
        self.get_selected_bo_id_callback = get_selected_bo_id_callback
        self.on_provider_request_callback = on_provider_request_callback

        self.provider_invoices: list[dict] = []
        self.provider_selected_invoice_ids: set[str] = set()
        self.selected_bo_connection_id: int = 1

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το βασικό UI του Provider/MUPT tab.
        """

        top_frame = ctk.CTkFrame(self, corner_radius=16)
        top_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)
        top_frame.grid_columnconfigure(3, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="Universal Provider Tool",
            font=("Segoe UI", 20, "bold")
        )
        title.grid(row=0, column=0, columnspan=6, padx=18, pady=(18, 8), sticky="w")

        bo_label = ctk.CTkLabel(
            top_frame,
            text="BOConnection:",
            font=("Segoe UI", 13, "bold")
        )
        bo_label.grid(row=1, column=0, padx=(18, 8), pady=6, sticky="w")

        self.provider_bo_option = ctk.CTkOptionMenu(
            top_frame,
            values=["ID 1"],
            command=self._on_provider_bo_selected
        )
        self.provider_bo_option.set("ID 1")
        self.provider_bo_option.grid(row=1, column=1, padx=(0, 12), pady=6, sticky="w")

        api_label = ctk.CTkLabel(
            top_frame,
            text="API URL:",
            font=("Segoe UI", 13, "bold")
        )
        api_label.grid(row=2, column=0, padx=(18, 8), pady=6, sticky="w")

        self.provider_api_url_entry = ctk.CTkEntry(
            top_frame,
            placeholder_text="Provider API URL with invoiceid placeholder"
        )
        self.provider_api_url_entry.grid(row=2, column=1, columnspan=5, padx=(0, 18), pady=6, sticky="ew")
        self.provider_api_url_entry.insert(
            0,
            "http://localhost/External.Tax.Provider/api/TaxProvider/SendInvoice/1/0/1/1/0?id=invoiceid&userId=3"
        )

        start_label = ctk.CTkLabel(
            top_frame,
            text="Date From:",
            font=("Segoe UI", 13, "bold")
        )
        start_label.grid(row=3, column=0, padx=(18, 8), pady=6, sticky="w")

        self.provider_start_entry = ctk.CTkEntry(top_frame, width=120)
        self.provider_start_entry.grid(row=3, column=1, padx=(0, 12), pady=6, sticky="w")
        self.provider_start_entry.insert(0, self._today_yyyymmdd())

        end_label = ctk.CTkLabel(
            top_frame,
            text="Date To:",
            font=("Segoe UI", 13, "bold")
        )
        end_label.grid(row=3, column=2, padx=(8, 8), pady=6, sticky="w")

        self.provider_end_entry = ctk.CTkEntry(top_frame, width=120)
        self.provider_end_entry.grid(row=3, column=3, padx=(0, 12), pady=6, sticky="w")
        self.provider_end_entry.insert(0, self._tomorrow_yyyymmdd())

        today_button = ctk.CTkButton(
            top_frame,
            text="Today",
            width=80,
            command=self._preset_today
        )
        today_button.grid(row=3, column=4, padx=(0, 8), pady=6)

        month_button = ctk.CTkButton(
            top_frame,
            text="This Month",
            width=100,
            command=self._preset_month
        )
        month_button.grid(row=3, column=5, padx=(0, 18), pady=6)

        afm_label = ctk.CTkLabel(
            top_frame,
            text="AFM:",
            font=("Segoe UI", 13, "bold")
        )
        afm_label.grid(row=4, column=0, padx=(18, 8), pady=(6, 18), sticky="w")

        self.provider_afm_entry = ctk.CTkEntry(
            top_frame,
            width=160,
            placeholder_text="e.g. 123456789"
        )
        self.provider_afm_entry.grid(row=4, column=1, padx=(0, 12), pady=(6, 18), sticky="w")

        type_label = ctk.CTkLabel(
            top_frame,
            text="Invoice Type:",
            font=("Segoe UI", 13, "bold")
        )
        type_label.grid(row=4, column=2, padx=(8, 8), pady=(6, 18), sticky="w")

        self.provider_invoice_type_entry = ctk.CTkEntry(
            top_frame,
            width=160,
            placeholder_text="e.g. 1.1"
        )
        self.provider_invoice_type_entry.grid(row=4, column=3, padx=(0, 12), pady=(6, 18), sticky="w")

        search_button = ctk.CTkButton(
            top_frame,
            text="Search",
            width=100,
            command=self._search_invoices
        )
        search_button.grid(row=4, column=4, padx=(0, 8), pady=(6, 18))

        self.provider_count_label = ctk.CTkLabel(
            top_frame,
            text="Count: 0",
            font=("Segoe UI", 13, "bold")
        )
        self.provider_count_label.grid(row=4, column=5, padx=(0, 18), pady=(6, 18), sticky="e")

        self._build_invoice_table()
        self._build_actions()

    def _build_invoice_table(self) -> None:
        """
        Δημιουργεί τον πίνακα παραστατικών.
        """

        table_frame = ctk.CTkFrame(self, corner_radius=16)
        table_frame.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        self.provider_tree = ttk.Treeview(
            table_frame,
            columns=("Select", "Type", "Name", "Date", "Number", "AFM", "ID"),
            show="headings",
            height=16
        )
        self.provider_tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.provider_tree.yview
        )
        y_scroll.grid(row=0, column=1, sticky="ns")

        x_scroll = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.provider_tree.xview
        )
        x_scroll.grid(row=1, column=0, sticky="ew")

        self.provider_tree.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set
        )

        headings = {
            "Select": "Select",
            "Type": "Type",
            "Name": "Name",
            "Date": "Date",
            "Number": "Number",
            "AFM": "AFM",
            "ID": "ID"
        }

        for column, text in headings.items():
            self.provider_tree.heading(column, text=text)

        self.provider_tree.column("Select", width=80, anchor="center", stretch=False)
        self.provider_tree.column("Type", width=100)
        self.provider_tree.column("Name", width=260)
        self.provider_tree.column("Date", width=110)
        self.provider_tree.column("Number", width=120)
        self.provider_tree.column("AFM", width=140)
        self.provider_tree.column("ID", width=220)

        self.provider_tree.bind("<Button-1>", self._toggle_invoice_selection)

    def _build_actions(self) -> None:
        """
        Δημιουργεί τα action buttons του Provider tab.
        """

        actions_frame = ctk.CTkFrame(self, corner_radius=16)
        actions_frame.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="ew")

        send_selected_button = ctk.CTkButton(
            actions_frame,
            text="Send Selected",
            width=130,
            command=self._send_selected
        )
        send_selected_button.pack(side="left", padx=(12, 6), pady=12)

        send_all_button = ctk.CTkButton(
            actions_frame,
            text="Send All",
            width=110,
            command=self._send_all
        )
        send_all_button.pack(side="left", padx=6, pady=12)

        errors_button = ctk.CTkButton(
            actions_frame,
            text="Show Errors",
            width=120,
            command=self._show_errors
        )
        errors_button.pack(side="left", padx=6, pady=12)

        mydata_button = ctk.CTkButton(
            actions_frame,
            text="Delete MyDATA",
            width=130,
            command=self._delete_mydata
        )
        mydata_button.pack(side="left", padx=6, pady=12)

        payways_button = ctk.CTkButton(
            actions_frame,
            text="Payways",
            width=110,
            command=self._show_payways
        )
        payways_button.pack(side="left", padx=6, pady=12)

        self.provider_status_label = ctk.CTkLabel(
            actions_frame,
            text="Ready",
            anchor="w"
        )
        self.provider_status_label.pack(side="right", padx=12, pady=12)

    def update_bo_values(self, bo_values: list[str], selected_value: str = "ID 1") -> None:
        """
        Ενημερώνει το BOConnection dropdown από τα AppSettings.
        """

        if bo_values:
            self.provider_bo_option.configure(values=bo_values)

            if selected_value in bo_values:
                self.provider_bo_option.set(selected_value)
            else:
                self.provider_bo_option.set(bo_values[0])

            connection_id = self._extract_bo_id_from_option(self.provider_bo_option.get())

            if connection_id is not None:
                self.selected_bo_connection_id = connection_id

        else:
            self.provider_bo_option.configure(values=["No BOConnections"])
            self.provider_bo_option.set("No BOConnections")

    def _on_provider_bo_selected(self, selected_value: str) -> None:
        """
        Επιλέγει BOConnection ID για Provider actions.
        """

        connection_id = self._extract_bo_id_from_option(selected_value)

        if connection_id is not None:
            self.selected_bo_connection_id = connection_id

    def _search_invoices(self) -> None:
        """
        Προσωρινό Search handler.
        Το backend θα μπει στο επόμενο βήμα.
        """

        payload = {
            "type": "provider_search_invoices",
            "request_id": str(uuid.uuid4()),
            "client_code": self.client_code,
            "bo_connection_id": self.selected_bo_connection_id,
            "start_date": self.provider_start_entry.get().strip(),
            "end_date": self.provider_end_entry.get().strip(),
            "afm": self.provider_afm_entry.get().strip(),
            "invoice_type": self.provider_invoice_type_entry.get().strip()
        }

        self._set_status("Searching invoices...")

        if self.on_provider_request_callback:
            # Δεν θα αποθηκευτεί τίποτα στον server. Θα γίνει μόνο WebSocket forwarding στο επόμενο βήμα.
            self.on_provider_request_callback(payload)

    def _send_selected(self) -> None:
        """
        Στέλνει τα επιλεγμένα παραστατικά μέσω του client PC.
        """

        selected_ids = sorted(self.provider_selected_invoice_ids)

        if not selected_ids:
            self._set_status("No selected invoices.")
            return

        self._send_invoice_ids(selected_ids)

    def _send_all(self) -> None:
        """
        Στέλνει όλα τα φορτωμένα παραστατικά μέσω του client PC.
        """

        invoice_ids: list[str] = []

        for invoice in self.provider_invoices:
            invoice_id = str(invoice.get("InvoiceId", "")).strip()

            if invoice_id:
                invoice_ids.append(invoice_id)

        if not invoice_ids:
            self._set_status("No invoices loaded.")
            return

        self._send_invoice_ids(invoice_ids)

    def _show_errors(self) -> None:
        """
        Προσωρινό handler για εμφάνιση σφαλμάτων.
        """

        self._set_status("Errors backend is not connected yet.")

    def _delete_mydata(self) -> None:
        """
        Προσωρινό handler για MyDATA cleanup.
        """

        self._set_status("MyDATA cleanup backend is not connected yet.")

    def _show_payways(self) -> None:
        """
        Προσωρινό handler για τρόπους πληρωμής.
        """

        self._set_status("Payways backend is not connected yet.")

    def populate_invoices(self, invoices: list[dict]) -> None:
        """
        Γεμίζει τον πίνακα με παραστατικά.
        """

        self.clear_invoices()
        self.provider_invoices = invoices

        for invoice in invoices:
            invoice_id = str(invoice.get("InvoiceId", ""))

            self.provider_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    invoice.get("InvoiceType", ""),
                    invoice.get("DocumentName", ""),
                    invoice.get("IssueDate", ""),
                    invoice.get("aa", ""),
                    invoice.get("CustAFM", ""),
                    invoice_id
                )
            )

        self.provider_count_label.configure(text=f"Count: {len(invoices)}")
        self._set_status(f"Loaded {len(invoices)} invoices.")

    def clear_invoices(self) -> None:
        """
        Καθαρίζει τον πίνακα παραστατικών.
        """

        self.provider_invoices.clear()
        self.provider_selected_invoice_ids.clear()

        for item in self.provider_tree.get_children():
            self.provider_tree.delete(item)

        self.provider_count_label.configure(text="Count: 0")

    def _toggle_invoice_selection(self, event) -> None:
        """
        Επιτρέπει επιλογή/αποεπιλογή παραστατικού από την πρώτη στήλη.
        """

        region = self.provider_tree.identify_region(event.x, event.y)

        if region != "cell":
            return

        row_id = self.provider_tree.identify_row(event.y)
        column = self.provider_tree.identify_column(event.x)

        if not row_id or column != "#1":
            return

        values = list(self.provider_tree.item(row_id, "values"))
        invoice_id = str(values[6])

        if invoice_id in self.provider_selected_invoice_ids:
            self.provider_selected_invoice_ids.remove(invoice_id)
            values[0] = "☐"
        else:
            self.provider_selected_invoice_ids.add(invoice_id)
            values[0] = "☑"

        self.provider_tree.item(row_id, values=values)

    def _set_status(self, text: str) -> None:
        """
        Ενημερώνει το status του Provider tab.
        """

        self.provider_status_label.configure(text=text)

    def _extract_bo_id_from_option(self, selected_value: str) -> int | None:
        """
        Εξάγει το BOConnection ID από κείμενο τύπου 'ID 1 - DatabaseName'.
        """

        try:
            parts = selected_value.split()
            return int(parts[1])
        except Exception:
            return None

    def _today_yyyymmdd(self) -> str:
        """
        Επιστρέφει σημερινή ημερομηνία σε YYYYMMDD.
        """

        return datetime.today().strftime("%Y%m%d")

    def _tomorrow_yyyymmdd(self) -> str:
        """
        Επιστρέφει αυριανή ημερομηνία σε YYYYMMDD.
        """

        return (datetime.today() + timedelta(days=1)).strftime("%Y%m%d")

    def _month_start_yyyymmdd(self) -> str:
        """
        Επιστρέφει πρώτη ημέρα του μήνα σε YYYYMMDD.
        """

        today = datetime.today()
        return today.replace(day=1).strftime("%Y%m%d")

    def _preset_today(self) -> None:
        """
        Βάζει εύρος ημερομηνιών για σήμερα.
        """

        self.provider_start_entry.delete(0, "end")
        self.provider_start_entry.insert(0, self._today_yyyymmdd())

        self.provider_end_entry.delete(0, "end")
        self.provider_end_entry.insert(0, self._tomorrow_yyyymmdd())

    def _preset_month(self) -> None:
        """
        Βάζει εύρος ημερομηνιών για τον τρέχοντα μήνα.
        """

        self.provider_start_entry.delete(0, "end")
        self.provider_start_entry.insert(0, self._month_start_yyyymmdd())

        self.provider_end_entry.delete(0, "end")
        self.provider_end_entry.insert(0, self._tomorrow_yyyymmdd())
        
    def handle_search_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα αναζήτησης παραστατικών Provider/MUPT.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            self.clear_invoices()
            self._set_status(f"Search failed: {payload.get('error')}")
            return

        invoices = payload.get("invoices") or []
        table = payload.get("table") or "-"

        self.populate_invoices(invoices)
        self._set_status(f"Loaded {len(invoices)} invoices from {table}.")
        
    def _send_invoice_ids(self, invoice_ids: list[str]) -> None:
        """
        Δημιουργεί Provider send request.
        Ο server θα κάνει μόνο forwarding προς τον client.
        """

        api_url = self.provider_api_url_entry.get().strip()

        if not api_url:
            self._set_status("Provider API URL is empty.")
            return

        if "invoiceid" not in api_url.lower():
            self._set_status("API URL must contain invoiceid.")
            return

        payload = {
            "type": "provider_send_invoices",
            "request_id": str(uuid.uuid4()),
            "client_code": self.client_code,
            "bo_connection_id": self.selected_bo_connection_id,
            "api_url": api_url,
            "invoice_ids": invoice_ids,
            "timeout": 60,
            "max_workers": 6
        }

        self._set_status(f"Sending {len(invoice_ids)} invoice(s)...")

        if self.on_provider_request_callback:
            self.on_provider_request_callback(payload)
            
    def handle_send_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα αποστολής παραστατικών.
        """

        if payload.get("client_code") != self.client_code:
            return

        total = payload.get("total", 0)
        success_count = payload.get("success_count", 0)
        fail_count = payload.get("fail_count", 0)
        elapsed_ms = payload.get("elapsed_ms")
        error = payload.get("error")

        if error:
            self._set_status(
                f"Send completed with errors. Total: {total}, OK: {success_count}, Failed: {fail_count}"
            )
        else:
            self._set_status(
                f"Send completed. Total: {total}, OK: {success_count}, Failed: {fail_count}, Time: {elapsed_ms} ms"
            )