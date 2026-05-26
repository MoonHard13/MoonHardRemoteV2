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
        self.provider_filtered_invoices: list[dict] = []
        self.provider_selected_invoice_ids: set[str] = set()
        self.selected_bo_connection_id: int = 1
        self.current_payways_window = None
        self.current_payways_tree = None
        self.current_payways_title_label = None
        self.current_payways_invoice_id = ""
        self.current_payways_columns: list[str] = []
        
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
        table_frame.grid_rowconfigure(1, weight=1)

        filter_frame = ctk.CTkFrame(table_frame, fg_color="transparent")
        filter_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="ew")
        filter_frame.grid_columnconfigure(1, weight=1)

        filter_label = ctk.CTkLabel(
            filter_frame,
            text="Local Filter:",
            font=("Segoe UI", 13, "bold")
        )
        filter_label.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.provider_local_filter_entry = ctk.CTkEntry(
            filter_frame,
            placeholder_text="Filter by type, name, date, number, AFM, ID..."
        )
        self.provider_local_filter_entry.grid(row=0, column=1, sticky="ew")

        self.provider_local_filter_entry.bind(
            "<KeyRelease>",
            lambda _event: self._apply_local_filter()
        )

        clear_filter_button = ctk.CTkButton(
            filter_frame,
            text="Clear",
            width=70,
            command=self._clear_local_filter
        )
        clear_filter_button.grid(row=0, column=2, padx=(8, 0), sticky="e")

        self.provider_tree = ttk.Treeview(
            table_frame,
            columns=("Select", "Type", "Name", "Date", "Number", "AFM", "ID"),
            show="headings",
            height=16
        )
        self.provider_tree.grid(row=1, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.provider_tree.yview
        )
        y_scroll.grid(row=1, column=1, sticky="ns")

        x_scroll = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.provider_tree.xview
        )
        x_scroll.grid(row=2, column=0, sticky="ew")

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
        Ζητά Provider/MyDATA errors από τον client υπολογιστή.
        """

        payload = {
            "type": "provider_get_errors",
            "request_id": str(uuid.uuid4()),
            "client_code": self.client_code,
            "bo_connection_id": self.selected_bo_connection_id,
            "start_date": self.provider_start_entry.get().strip(),
            "end_date": self.provider_end_entry.get().strip(),
            "limit": 300
        }

        self._set_status("Loading Provider/MyDATA errors...")

        if self.on_provider_request_callback:
            self.on_provider_request_callback(payload)

    def _delete_mydata(self) -> None:
        """
        Ανοίγει παράθυρο διαγραφής MyDATA όπως το MUPT.
        Ο χρήστης επιλέγει Note Type και γράφει αριθμό/list/range.
        """

        self._open_delete_mydata_window()

    def _open_delete_mydata_window(self) -> None:
        """
        Ανοίγει popup για διαγραφή MyDATA responses.
        """

        window = ctk.CTkToplevel(self)
        window.title("Delete MyDATA")
        window.geometry("560x330")
        window.minsize(540, 310)
        window.grab_set()

        window.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            window,
            text="Delete MyDATA Responses",
            font=("Segoe UI", 20, "bold")
        )
        title.grid(row=0, column=0, padx=20, pady=(18, 8), sticky="w")

        info = ctk.CTkLabel(
            window,
            text="Choose Note Type and enter number, list, or range.",
            font=("Segoe UI", 13),
            anchor="w"
        )
        info.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="w")

        form_frame = ctk.CTkFrame(window, corner_radius=14)
        form_frame.grid(row=2, column=0, padx=20, pady=(0, 15), sticky="ew")
        form_frame.grid_columnconfigure(1, weight=1)

        note_type_label = ctk.CTkLabel(
            form_frame,
            text="Note Type:",
            font=("Segoe UI", 13, "bold")
        )
        note_type_label.grid(row=0, column=0, padx=(14, 10), pady=(14, 8), sticky="w")

        self.delete_mydata_type_option = ctk.CTkOptionMenu(
            form_frame,
            values=["Loading note types..."]
        )
        self.delete_mydata_type_option.set("Loading note types...")
        self.delete_mydata_type_option.grid(row=0, column=1, padx=(0, 14), pady=(14, 8), sticky="ew")

        number_label = ctk.CTkLabel(
            form_frame,
            text="Number/List/Range:",
            font=("Segoe UI", 13, "bold")
        )
        number_label.grid(row=1, column=0, padx=(14, 10), pady=(8, 14), sticky="w")

        self.delete_mydata_number_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Examples: 123 or 123,124,125 or 100-150"
        )
        self.delete_mydata_number_entry.grid(row=1, column=1, padx=(0, 14), pady=(8, 14), sticky="ew")

        button_frame = ctk.CTkFrame(window, fg_color="transparent")
        button_frame.grid(row=3, column=0, padx=20, pady=(0, 18), sticky="ew")

        delete_button = ctk.CTkButton(
            button_frame,
            text="Delete MyDATA",
            width=140,
            command=lambda: self._execute_delete_mydata_from_window(window)
        )
        delete_button.pack(side="left")

        cancel_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            command=window.destroy
        )
        cancel_button.pack(side="left", padx=(10, 0))

        self.delete_mydata_number_entry.focus_set()

        self._request_note_types_for_mydata_delete()


    def _request_note_types_for_mydata_delete(self) -> None:
        """
        Ζητά Note Types από τον client υπολογιστή.
        """

        payload = {
            "type": "provider_get_note_types",
            "request_id": str(uuid.uuid4()),
            "client_code": self.client_code,
            "bo_connection_id": self.selected_bo_connection_id
        }

        self._set_status("Loading Note Types...")

        if self.on_provider_request_callback:
            self.on_provider_request_callback(payload)


    def handle_note_types_result(self, payload: dict) -> None:
        """
        Γεμίζει το Note Type dropdown του Delete MyDATA popup.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            self._set_status(f"Note Types load failed: {payload.get('error')}")
            return

        note_types = payload.get("note_types") or []

        if not note_types:
            self._set_status("No MyDATA note types found.")
            return

        if hasattr(self, "delete_mydata_type_option"):
            self.delete_mydata_type_option.configure(values=note_types)
            self.delete_mydata_type_option.set(note_types[0])

        self._set_status(f"Loaded {len(note_types)} Note Types.")

    def _parse_mydata_number_input(self, raw_value: str) -> list[str]:
        """
        Αναλύει αριθμό/list/range όπως το MUPT.
        Παραδείγματα:
        123
        123,124,125
        100-150
        """

        raw = raw_value.strip()

        if not raw:
            return []

        if "," in raw:
            values = [
                part.strip()
                for part in raw.split(",")
                if part.strip()
            ]

            return values

        if "-" in raw:
            parts = [
                part.strip()
                for part in raw.split("-", 1)
            ]

            if len(parts) != 2:
                return []

            if not parts[0].isdigit() or not parts[1].isdigit():
                return []

            start_no = int(parts[0])
            end_no = int(parts[1])

            if end_no < start_no:
                return []

            return [
                str(number)
                for number in range(start_no, end_no + 1)
            ]

        return [raw]


    def _execute_delete_mydata_from_window(self, window) -> None:
        """
        Στέλνει αίτημα διαγραφής MyDATA από το popup.
        """

        selected_note_type = self.delete_mydata_type_option.get().strip()
        raw_numbers = self.delete_mydata_number_entry.get().strip()

        if not selected_note_type or "|" not in selected_note_type:
            self._set_status("Select valid Note Type first.")
            return

        note_code = selected_note_type.split("|")[-1].strip()
        note_numbers = self._parse_mydata_number_input(raw_numbers)

        if not note_numbers:
            self._set_status("Enter valid number, list, or range first.")
            return

        documents = [
            {
                "note_code": note_code,
                "note_no": note_no
            }
            for note_no in note_numbers
        ]

        payload = {
            "type": "provider_delete_mydata",
            "request_id": str(uuid.uuid4()),
            "client_code": self.client_code,
            "bo_connection_id": self.selected_bo_connection_id,
            "documents": documents
        }

        self._set_status(
            f"Deleting MyDATA for NoteType {note_code}, {len(documents)} document(s)..."
        )

        window.destroy()

        if self.on_provider_request_callback:
            self.on_provider_request_callback(payload)

    def _get_loaded_invoice_type_values(self) -> list[str]:
        """
        Επιστρέφει διαθέσιμους τύπους παραστατικών από τα ήδη φορτωμένα παραστατικά.
        """

        type_values: list[str] = []

        for invoice in self.provider_invoices:
            invoice_type = str(invoice.get("InvoiceType", "")).strip()

            if invoice_type and invoice_type not in type_values:
                type_values.append(invoice_type)

        if not type_values:
            current_type = self.provider_invoice_type_entry.get().strip()

            if current_type:
                type_values.append(current_type)

        if not type_values:
            type_values.append("1.1")

        return type_values

    def _execute_delete_mydata_from_window(self, window) -> None:
        """
        Στέλνει αίτημα διαγραφής MyDATA από το popup.
        """

        note_code = self.delete_mydata_type_option.get().strip()
        note_no = self.delete_mydata_number_entry.get().strip()

        if not note_code:
            self._set_status("Select document type first.")
            return

        if not note_no:
            self._set_status("Enter invoice number first.")
            return

        payload = {
            "type": "provider_delete_mydata",
            "request_id": str(uuid.uuid4()),
            "client_code": self.client_code,
            "bo_connection_id": self.selected_bo_connection_id,
            "documents": [
                {
                    "note_code": note_code,
                    "note_no": note_no
                }
            ]
        }

        self._set_status(
            f"Deleting MyDATA responses for type {note_code}, number {note_no}..."
        )

        window.destroy()

        if self.on_provider_request_callback:
            self.on_provider_request_callback(payload)

    def _get_selected_documents_for_mydata_delete(self) -> list[dict]:
        """
        Επιστρέφει τα επιλεγμένα παραστατικά για MyDATA delete.
        Χρησιμοποιεί:
        InvoiceType -> SalesPWNoteCode
        aa          -> SalesPWNoteNo
        """

        selected_documents: list[dict] = []

        for invoice in self.provider_invoices:
            invoice_id = str(invoice.get("InvoiceId", "")).strip()

            if invoice_id not in self.provider_selected_invoice_ids:
                continue

            note_code = str(invoice.get("InvoiceType", "")).strip()
            note_no = str(invoice.get("aa", "")).strip()

            if note_code and note_no:
                selected_documents.append(
                    {
                        "invoice_id": invoice_id,
                        "note_code": note_code,
                        "note_no": note_no
                    }
                )

        return selected_documents

    def _show_payways(self) -> None:
        """
        Ζητά τρόπους πληρωμής για το επιλεγμένο παραστατικό.
        """

        selected_invoice_id = self._get_single_selected_invoice_id()

        if not selected_invoice_id:
            self._set_status("Select exactly one invoice first.")
            return

        self._request_payways_for_invoice(selected_invoice_id)

    def populate_invoices(self, invoices: list[dict]) -> None:
        """
        Γεμίζει τον πίνακα με παραστατικά.
        """

        self.provider_invoices = invoices
        self._apply_local_filter()

    def _render_invoices(self, invoices: list[dict]) -> None:
        """
        Κάνει render τα παραστατικά στον πίνακα.
        """

        for item in self.provider_tree.get_children():
            self.provider_tree.delete(item)

        for invoice in invoices:
            invoice_id = str(invoice.get("InvoiceId", ""))

            selected_symbol = "☑" if invoice_id in self.provider_selected_invoice_ids else "☐"

            self.provider_tree.insert(
                "",
                "end",
                values=(
                    selected_symbol,
                    invoice.get("InvoiceType", ""),
                    invoice.get("DocumentName", ""),
                    invoice.get("IssueDate", ""),
                    invoice.get("aa", ""),
                    invoice.get("CustAFM", ""),
                    invoice_id
                )
            )

        self.provider_count_label.configure(
            text=f"Count: {len(invoices)} / {len(self.provider_invoices)}"
        )


    def _apply_local_filter(self) -> None:
        """
        Φιλτράρει τοπικά τα ήδη φορτωμένα παραστατικά.
        """

        filter_text = ""

        if hasattr(self, "provider_local_filter_entry"):
            filter_text = self.provider_local_filter_entry.get().strip().lower()

        if not filter_text:
            self.provider_filtered_invoices = list(self.provider_invoices)
            self._render_invoices(self.provider_filtered_invoices)
            self._set_status(f"Loaded {len(self.provider_invoices)} invoices.")
            return

        filtered: list[dict] = []

        for invoice in self.provider_invoices:
            searchable_text = " ".join(
                [
                    str(invoice.get("InvoiceType", "")),
                    str(invoice.get("DocumentName", "")),
                    str(invoice.get("IssueDate", "")),
                    str(invoice.get("aa", "")),
                    str(invoice.get("CustAFM", "")),
                    str(invoice.get("InvoiceId", ""))
                ]
            ).lower()

            if filter_text in searchable_text:
                filtered.append(invoice)

        self.provider_filtered_invoices = filtered
        self._render_invoices(filtered)

        self._set_status(
            f"Local filter: {len(filtered)} of {len(self.provider_invoices)} invoices."
        )


    def _clear_local_filter(self) -> None:
        """
        Καθαρίζει το τοπικό φίλτρο.
        """

        if hasattr(self, "provider_local_filter_entry"):
            self.provider_local_filter_entry.delete(0, "end")

        self._apply_local_filter()

    def clear_invoices(self) -> None:
        """
        Καθαρίζει τον πίνακα παραστατικών.
        """

        self.provider_invoices.clear()
        self.provider_filtered_invoices.clear()
        self.provider_selected_invoice_ids.clear()

        if hasattr(self, "provider_local_filter_entry"):
            self.provider_local_filter_entry.delete(0, "end")

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
        Μετά την αποστολή παραστατικών κάνει αυτόματο refresh του πίνακα.
        Έτσι εμφανίζονται μόνο όσα παραστατικά έχουν μείνει προς αποστολή.
        """

        if payload.get("client_code") != self.client_code:
            return

        total = payload.get("total", 0)
        success_count = payload.get("success_count", 0)
        fail_count = payload.get("fail_count", 0)
        error = payload.get("error")

        self.provider_selected_invoice_ids.clear()

        if error:
            self._set_status(
                f"Send finished with errors. Total: {total}, OK: {success_count}, Failed: {fail_count}. Refreshing..."
            )
        else:
            self._set_status(
                f"Send finished. Total: {total}, OK: {success_count}, Failed: {fail_count}. Refreshing..."
            )

        self._search_invoices()
        
    def handle_errors_result(self, payload: dict) -> None:
        """
        Εμφανίζει Provider/MyDATA errors σε popup table.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            self._set_status(f"Errors load failed: {payload.get('error')}")
            return

        errors = payload.get("errors") or []
        self._set_status(f"Loaded {len(errors)} Provider/MyDATA error row(s).")
        self._open_errors_window(errors)
        
    def _open_payways_window(
        self,
        invoice_id: str,
        payways: list[dict]
    ) -> None:
        """
        Ανοίγει παράθυρο με τους τρόπους πληρωμής του παραστατικού.
        Περιλαμβάνει κουμπί διαγραφής και right-click delete.
        """

        window = ctk.CTkToplevel(self)

        self.current_payways_window = window
        self.current_payways_invoice_id = invoice_id

        window.title(f"Payways - Invoice {invoice_id}")
        window.geometry("1000x560")
        window.minsize(850, 460)

        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(2, weight=1)

        title = ctk.CTkLabel(
            window,
            text=f"Payways for Invoice {invoice_id} ({len(payways)})",
            font=("Segoe UI", 20, "bold")
        )

        self.current_payways_title_label = title

        title.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        actions_frame = ctk.CTkFrame(window, corner_radius=12)
        actions_frame.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="ew")

        table_frame = ctk.CTkFrame(window, corner_radius=12)
        table_frame.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        if payways:
            columns = list(payways[0].keys())
        else:
            columns = ["Message"]

        tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=16
        )

        self.current_payways_tree = tree
        self.current_payways_columns = columns

        tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=tree.yview
        )
        y_scroll.grid(row=0, column=1, sticky="ns")

        x_scroll = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=tree.xview
        )
        x_scroll.grid(row=1, column=0, sticky="ew")

        tree.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set
        )

        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=170, minwidth=100, stretch=True)

        if payways:
            for payway in payways:
                tree.insert(
                    "",
                    "end",
                    values=[payway.get(column, "") for column in columns]
                )
        else:
            tree.insert("", "end", values=["No payways found."])

        delete_button = ctk.CTkButton(
            actions_frame,
            text="Delete Selected Payway",
            width=190,
            command=lambda: self._delete_selected_payway_from_tree(
                tree=tree,
                columns=columns,
                invoice_id=invoice_id
            )
        )
        delete_button.pack(side="left", padx=10, pady=10)

        copy_button = ctk.CTkButton(
            actions_frame,
            text="Copy All",
            width=100,
            command=lambda: self._copy_tree_all_rows(tree)
        )
        copy_button.pack(side="left", padx=5, pady=10)

        tree.bind("<Control-c>", lambda _event: self._copy_tree_selected_rows(tree))
        tree.bind(
            "<Button-3>",
            lambda event: self._show_payways_context_menu(
                event=event,
                tree=tree,
                columns=columns,
                invoice_id=invoice_id
            )
        )

    def _refresh_payways_window(
        self,
        invoice_id: str,
        payways: list[dict]
    ) -> None:
        """
        Ανανεώνει το υπάρχον Payways popup χωρίς να ανοίξει νέο παράθυρο.
        """

        tree = self.current_payways_tree

        if tree is None:
            self._open_payways_window(
                invoice_id=invoice_id,
                payways=payways
            )
            return

        if payways:
            columns = list(payways[0].keys())
        else:
            columns = ["Message"]

        self.current_payways_columns = columns

        tree.delete(*tree.get_children())
        tree.configure(columns=columns)

        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=170, minwidth=100, stretch=True)

        if payways:
            for payway in payways:
                tree.insert(
                    "",
                    "end",
                    values=[payway.get(column, "") for column in columns]
                )
        else:
            tree.insert("", "end", values=["No payways found."])

        if self.current_payways_title_label:
            self.current_payways_title_label.configure(
                text=f"Payways for Invoice {invoice_id} ({len(payways)})"
            )

    def _show_payways_context_menu(
        self,
        event,
        tree: ttk.Treeview,
        columns: list[str],
        invoice_id: str
    ) -> None:
        """
        Εμφανίζει right-click menu για Payways.
        """

        context_menu = __import__("tkinter").Menu(self, tearoff=0)

        context_menu.add_command(
            label="Delete selected payway",
            command=lambda: self._delete_selected_payway_from_tree(
                tree=tree,
                columns=columns,
                invoice_id=invoice_id
            )
        )

        context_menu.add_separator()

        context_menu.add_command(
            label="Copy selected rows",
            command=lambda: self._copy_tree_selected_rows(tree)
        )

        context_menu.add_command(
            label="Copy all rows",
            command=lambda: self._copy_tree_all_rows(tree)
        )

        context_menu.tk_popup(event.x_root, event.y_root)
        context_menu.grab_release()


    def _delete_selected_payway_from_tree(
        self,
        tree: ttk.Treeview,
        columns: list[str],
        invoice_id: str
    ) -> None:
        """
        Δημιουργεί request διαγραφής για τον επιλεγμένο τρόπο πληρωμής.
        Το backend delete θα συνδεθεί μετά.
        """

        selected_items = tree.selection()

        if len(selected_items) != 1:
            self._set_status("Select exactly one payway first.")
            return

        if "SalesPayWayOID" not in columns:
            self._set_status("SalesPayWayOID column was not found.")
            return

        selected_item = selected_items[0]
        values = list(tree.item(selected_item, "values"))

        oid_index = columns.index("SalesPayWayOID")
        sales_payway_oid = str(values[oid_index]).strip()

        if not sales_payway_oid:
            self._set_status("Selected payway has empty SalesPayWayOID.")
            return

        payload = {
            "type": "provider_delete_payway",
            "request_id": str(uuid.uuid4()),
            "client_code": self.client_code,
            "bo_connection_id": self.selected_bo_connection_id,
            "invoice_id": invoice_id,
            "sales_payway_oid": sales_payway_oid
        }

        self._set_status(f"Deleting payway {sales_payway_oid}...")

        if self.on_provider_request_callback:
            self.on_provider_request_callback(payload)

    def handle_delete_payway_result(self, payload: dict) -> None:
        """
        Μετά τη διαγραφή τρόπου πληρωμής ανανεώνει το ίδιο Payways popup.
        """

        if payload.get("client_code") != self.client_code:
            return

        invoice_id = payload.get("invoice_id", "")
        sales_payway_oid = payload.get("sales_payway_oid", "")

        if not payload.get("success"):
            self._set_status(
                f"Payway delete failed: {payload.get('error')}"
            )
            return

        deleted_main_rows = payload.get("deleted_main_rows", 0)
        deleted_history_rows = payload.get("deleted_history_rows", 0)

        self._set_status(
            f"Deleted payway {sales_payway_oid}. Main rows: {deleted_main_rows}, history rows: {deleted_history_rows}. Refreshing..."
        )

        self._request_payways_for_invoice(invoice_id)

    def handle_delete_mydata_result(self, payload: dict) -> None:
            
        def _copy_tree_selected_rows(self, tree: ttk.Treeview) -> None:
            """
            Αντιγράφει τις επιλεγμένες γραμμές ενός Treeview.
            """

            selected_items = tree.selection()

            if not selected_items:
                return

            lines: list[str] = []

            for item in selected_items:
                values = tree.item(item, "values")
                lines.append("\t".join(str(value) for value in values))

            copied_text = "\n".join(lines)

            self.clipboard_clear()
            self.clipboard_append(copied_text)


    def _copy_tree_all_rows(self, tree: ttk.Treeview) -> None:
        """
        Αντιγράφει όλες τις γραμμές ενός Treeview.
        """

        lines: list[str] = []

        for item in tree.get_children():
            values = tree.item(item, "values")
            lines.append("\t".join(str(value) for value in values))

        copied_text = "\n".join(lines)

        self.clipboard_clear()
        self.clipboard_append(copied_text)


    def _show_tree_copy_menu(self, event, tree: ttk.Treeview) -> None:
        """
        Εμφανίζει context menu για αντιγραφή γραμμών.
        """

        context_menu = __import__("tkinter").Menu(self, tearoff=0)
        context_menu.add_command(
            label="Copy selected rows",
            command=lambda: self._copy_tree_selected_rows(tree)
        )
        context_menu.add_command(
            label="Copy all rows",
            command=lambda: self._copy_tree_all_rows(tree)
        )

        context_menu.tk_popup(event.x_root, event.y_root)
        context_menu.grab_release()
        
    def _get_single_selected_invoice_id(self) -> str:
        """
        Επιστρέφει το μοναδικό επιλεγμένο InvoiceId.
        Αν δεν υπάρχει ακριβώς ένα επιλεγμένο παραστατικό, επιστρέφει κενό.
        """

        if len(self.provider_selected_invoice_ids) != 1:
            return ""

        return next(iter(self.provider_selected_invoice_ids))
    
    def handle_payways_result(self, payload: dict) -> None:
        """
        Εμφανίζει ή ανανεώνει τους τρόπους πληρωμής στο ίδιο popup.
        """

        if payload.get("client_code") != self.client_code:
            return

        invoice_id = payload.get("invoice_id", "")

        if not payload.get("success"):
            self._set_status(f"Payways load failed: {payload.get('error')}")
            return

        payways = payload.get("payways") or []

        self._set_status(
            f"Loaded {len(payways)} payway row(s) for invoice {invoice_id}."
        )

        if (
            self.current_payways_window
            and self.current_payways_window.winfo_exists()
            and self.current_payways_tree
            and self.current_payways_invoice_id == invoice_id
        ):
            self._refresh_payways_window(
                invoice_id=invoice_id,
                payways=payways
            )
            return

        self._open_payways_window(
            invoice_id=invoice_id,
            payways=payways
        )


    def _request_payways_for_invoice(self, invoice_id: str) -> None:
        """
        ???? ???? ???? ??????? ???????? ??? ???????????? InvoiceId.
        """

        clean_invoice_id = str(invoice_id).strip()

        if not clean_invoice_id:
            self._set_status("InvoiceId is empty.")
            return

        payload = {
            "type": "provider_get_payways",
            "request_id": str(uuid.uuid4()),
            "client_code": self.client_code,
            "bo_connection_id": self.selected_bo_connection_id,
            "invoice_id": clean_invoice_id
        }

        self._set_status(f"Loading payways for invoice {clean_invoice_id}...")

        if self.on_provider_request_callback:
            self.on_provider_request_callback(payload)
