import logging
import uuid
import webbrowser
from tkinter import ttk
from urllib.parse import urlsplit

import customtkinter as ctk

from app.ui.theme import COLORS, FONTS, apply_treeview_style, primary_button_style, secondary_button_style


logger = logging.getLogger(__name__)


class DocumentLink:
    """Ελέγχει συνδέσμους προβολής πριν δοθούν στον browser ή στο πρόχειρο."""

    @staticmethod
    def validate(value: str) -> str:
        """Επιτρέπει μόνο πλήρη HTTP/HTTPS URL χωρίς ενσωματωμένα διαπιστευτήρια."""
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise ValueError("Δεν υπάρχει διαθέσιμο URL προβολής για αυτό το παραστατικό.")
        if any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value:
            raise ValueError("Το αποθηκευμένο URL δεν είναι έγκυρο.")
        try:
            parts = urlsplit(value)
            if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
                raise ValueError
            if parts.username is not None or parts.password is not None:
                raise ValueError
            if parts.port is not None and not 1 <= parts.port <= 65535:
                raise ValueError
        except ValueError:
            raise ValueError("Το αποθηκευμένο URL δεν είναι έγκυρο HTTP/HTTPS URL.") from None
        return value


class TransmittedInvoicesView(ctk.CTkFrame):
    """Ενσωματωμένη προβολή Provider με προσωρινά αποτελέσματα ανά BOConnection."""

    COLUMNS = (
        ("InvoiceDate", "Ημερομηνία", 100), ("DocumentType", "Τύπος παραστατικού", 200),
        ("Series", "Σειρά", 75), ("Number", "Αριθμός", 100), ("MARK", "MARK", 165),
        ("ResponseDate", "Ημ/νία απάντησης", 150), ("State", "Κατάσταση", 145),
        ("DocumentURL", "URL παραστατικού", 360),
    )

    def __init__(self, parent, client_code: str, bo_connection_id: int, send_callback, back_callback) -> None:
        """Δεσμεύει τη βάση κατά το άνοιγμα για να μην αναμειγνύονται αποτελέσματα."""
        super().__init__(parent, corner_radius=0, fg_color=COLORS.background)
        self.client_code, self.bo_connection_id = client_code, bo_connection_id
        self.send_callback = send_callback
        self.back_callback = back_callback
        self._shortcut_bindings = []
        self._shortcut_parent = self.winfo_toplevel()
        self._initial_load_after_id = None
        self.rows: dict[str, dict] = {}
        self.type_values = {"Όλοι οι τύποι": ""}
        self.pending: dict[str, tuple[str, object]] = {}
        self.next_before_oid = None
        self.active_filters = {}
        self.busy = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_ui()
        self._bind_shortcuts()
        self._initial_load_after_id = self.after(100, self._load_types)

    def _build_ui(self) -> None:
        """Χρησιμοποιεί το υπάρχον θέμα και προσθέτει μόνο τα νέα χειριστήρια."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=18, pady=(12, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text=f"Διαβιβασμένα παραστατικά · BOConnection {self.bo_connection_id}",
                     font=FONTS.subtitle, text_color=COLORS.text_primary).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="← Provider", width=120, command=self.back_callback,
                      **secondary_button_style()).grid(row=0, column=1, padx=(12, 0), sticky="e")
        form = ctk.CTkFrame(self, fg_color=COLORS.surface)
        form.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")
        for column in (1, 3, 5):
            form.grid_columnconfigure(column, weight=1)
        self.entries = {}
        fields = (("start_date", "Από", "YYYYMMDD", 0, 0),
                  ("end_date", "Έως", "YYYYMMDD", 0, 2),
                  ("number", "Αριθμός", "Ακριβής αριθμός", 1, 0),
                  ("mark", "MARK", "Ακριβές MARK", 1, 2))
        for key, label, placeholder, row, column in fields:
            ctk.CTkLabel(form, text=label, font=FONTS.body_bold).grid(row=row, column=column, padx=(12, 8), pady=8, sticky="w")
            entry = ctk.CTkEntry(form, placeholder_text=placeholder, fg_color=COLORS.surface_light,
                               border_color=COLORS.border, text_color=COLORS.text_primary)
            entry.grid(row=row, column=column + 1, padx=(0, 12), pady=8, sticky="ew")
            self.entries[key] = entry
        ctk.CTkLabel(form, text="Τύπος", font=FONTS.body_bold).grid(row=0, column=4, padx=8, pady=8)
        self.type_option = ctk.CTkOptionMenu(form, values=list(self.type_values), width=220,
            fg_color=COLORS.surface_light, button_color=COLORS.accent, text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface, dropdown_hover_color=COLORS.surface_hover)
        self.type_option.grid(row=0, column=5, padx=(0, 12), pady=8, sticky="ew")
        buttons = ctk.CTkFrame(form, fg_color="transparent")
        buttons.grid(row=1, column=4, columnspan=2, padx=12, pady=8, sticky="e")
        self.search_button = ctk.CTkButton(buttons, text="Αναζήτηση", width=105, command=self.search, **primary_button_style())
        self.search_button.pack(side="left", padx=4)
        self.clear_button = ctk.CTkButton(buttons, text="Καθαρισμός", width=105, command=self.clear, **secondary_button_style())
        self.clear_button.pack(side="left", padx=4)
        ctk.CTkLabel(form, text="Ημερομηνίες YYYYMMDD (π.χ. 20260901), με συμπερίληψη της ημέρας Έως. Κενό πεδίο = χωρίς φίλτρο.",
            font=FONTS.small, text_color=COLORS.text_secondary).grid(row=2, column=0, columnspan=6, padx=12, pady=(0, 8), sticky="w")
        table = ctk.CTkFrame(self, fg_color=COLORS.surface)
        table.grid(row=2, column=0, padx=18, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=[c[0] for c in self.COLUMNS], show="headings", selectmode="browse",
                                style=apply_treeview_style("MoonHard.Transmitted.Treeview"))
        for name, title, width in self.COLUMNS:
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, minwidth=60, stretch=name == "DocumentType")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vertical_scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=self._tree_scrolled, xscrollcommand=horizontal.set)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self.tree.bind("<Double-1>", self._double_click)
        self.tree.bind("<Return>", lambda event: self._shortcut(self.open_url))
        self.url_text = ctk.StringVar(value="")
        self.url_entry = ctk.CTkEntry(self, textvariable=self.url_text, state="readonly", fg_color=COLORS.surface_light)
        self.url_entry.grid(row=3, column=0, padx=18, pady=8, sticky="ew")
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, padx=18, pady=(0, 8), sticky="ew")
        self.open_button = ctk.CTkButton(actions, text="Άνοιγμα URL", width=135, state="disabled", command=self.open_url, **primary_button_style())
        self.open_button.pack(side="left")
        self.copy_button = ctk.CTkButton(actions, text="Αντιγραφή URL", width=140, state="disabled", command=self.copy_url, **secondary_button_style())
        self.copy_button.pack(side="left", padx=8)
        self.status = ctk.CTkLabel(self, text="Συμπληρώστε τα επιθυμητά φίλτρα και πατήστε Αναζήτηση.",
                                  font=FONTS.body, anchor="w", wraplength=870, text_color=COLORS.text_secondary)
        self.status.grid(row=5, column=0, padx=18, pady=(0, 14), sticky="ew")

    def _bind_shortcuts(self) -> None:
        """Ενεργοποιεί τις συντομεύσεις μόνο όταν η ενσωματωμένη προβολή είναι ορατή."""
        for key, callback in (("<Control-f>", self.search), ("<F5>", self.search),
                              ("<Control-l>", self.clear), ("<Control-o>", self.open_url),
                              ("<Control-Shift-C>", self.copy_url), ("<Escape>", self.back_callback)):
            binding_id = self._shortcut_parent.bind(
                key, lambda event, action=callback: self._visible_shortcut(action), add="+")
            self._shortcut_bindings.append((key, binding_id))
        for entry in self.entries.values():
            entry.bind("<Return>", lambda event: self._shortcut(self.search))

    @staticmethod
    def _shortcut(action):
        """Αποτρέπει δεύτερο χειρισμό του ίδιου συμβάντος."""
        action()
        return "break"

    def _visible_shortcut(self, action):
        """Δεν δεσμεύει πλήκτρα άλλων tabs ή της βασικής προβολής Provider."""
        if self.winfo_viewable():
            return self._shortcut(action)
        return None

    def _send(self, kind: str, fields: dict) -> None:
        """Συσχετίζει κάθε αίτημα με χρονικό όριο και τη συγκεκριμένη βάση."""
        request_id = str(uuid.uuid4())
        timer = self.after(85000, lambda: self._timeout(request_id))
        self.pending[request_id] = (kind, timer)
        payload = {**fields, "type": kind, "request_id": request_id, "client_code": self.client_code,
                   "bo_connection_id": self.bo_connection_id}
        try:
            if not self.send_callback:
                raise RuntimeError
            self.send_callback(payload)
        except Exception:
            self.after_cancel(timer)
            self.pending.pop(request_id, None)
            self._set_busy(False)
            self.status.configure(text="Αποτυχία αποστολής. Ελέγξτε τη σύνδεση του dashboard.")

    def _load_types(self) -> None:
        """Φορτώνει τους τύπους χωρίς να εκτελεί αναζήτηση παραστατικών."""
        self._initial_load_after_id = None
        self._send("provider_transmitted_types", {})

    def _timeout(self, request_id: str) -> None:
        """Επαναφέρει τα κουμπιά αν λείπει απάντηση ή χρησιμοποιείται παλιός server."""
        pending = self.pending.pop(request_id, None)
        if pending and pending[0] == "provider_transmitted_search":
            self._set_busy(False)
        if pending:
            self.status.configure(text="Δεν ελήφθη απάντηση. Ελέγξτε σύνδεση και ενημέρωση server/client.")

    def search(self) -> None:
        """Ξεκινά νέα αναζήτηση και εμφανίζει τα αποτελέσματα σε μία συνεχή λίστα."""
        if self.busy:
            return
        self.active_filters = {key: entry.get().strip() for key, entry in self.entries.items()}
        self.active_filters["document_type"] = self.type_values.get(self.type_option.get(), "")
        self._clear_rows()
        self._fetch_batch(None)

    def _fetch_batch(self, before_oid) -> None:
        """Ζητά την επόμενη ασφαλή παρτίδα και την προσθέτει στην ίδια λίστα."""
        self._set_busy(True)
        self.status.configure(text="Αναζήτηση διαβιβασμένων..." if not self.rows
                              else f"Φόρτωση περισσότερων... ({len(self.rows)} ήδη εμφανίζονται)")
        self._send("provider_transmitted_search", {**self.active_filters, "limit": 100,
                   "before_oid": before_oid})

    def handle_result(self, payload: dict) -> None:
        """Αγνοεί παλιές απαντήσεις και δεδομένα άλλου client ή BOConnection."""
        if payload.get("client_code") != self.client_code or payload.get("bo_connection_id") != self.bo_connection_id:
            return
        request_id = payload.get("request_id")
        pending = self.pending.get(request_id)
        if not pending or payload.get("type") != f"{pending[0]}_result":
            return
        self.pending.pop(request_id)
        self.after_cancel(pending[1])
        if pending[0] == "provider_transmitted_types":
            if payload.get("success"):
                self.type_values = {"Όλοι οι τύποι": ""}
                for item in payload.get("document_types", []):
                    self.type_values[item["label"]] = item["value"]
                self.type_option.configure(values=list(self.type_values))
            else:
                self.status.configure(text=payload.get("error") or "Δεν φορτώθηκαν οι τύποι.")
            return
        if not payload.get("success"):
            self._set_busy(False)
            self.status.configure(text=payload.get("error") or "Η αναζήτηση απέτυχε.")
            return
        for invoice in payload.get("invoices", []):
            iid = str(invoice["ResponseOID"])
            if iid in self.rows:
                continue
            self.rows[iid] = invoice
            cancelled = invoice.get("CancellationMARK") or invoice.get("CancellationDate")
            display = {**invoice, "State": "Με ακύρωση" if cancelled else "Διαβιβασμένο"}
            try:
                DocumentLink.validate(invoice.get("DocumentURL", ""))
                display["DocumentURL"] = invoice["DocumentURL"]
            except ValueError:
                display["DocumentURL"] = "Μη έγκυρο URL" if invoice.get("DocumentURL") else "Δεν υπάρχει URL"
            self.tree.insert("", "end", iid=iid, values=[display.get(c[0], "") for c in self.COLUMNS])
        self.next_before_oid = payload.get("next_before_oid") if payload.get("has_more") else None
        self._set_busy(False)
        if not self.rows:
            message = "Δεν βρέθηκαν διαβιβασμένα με αυτά τα φίλτρα."
        elif self.next_before_oid is not None:
            message = f"Εμφανίζονται {len(self.rows)} εγγραφές. Κυλήστε προς τα κάτω για περισσότερες."
        else:
            message = f"Βρέθηκαν συνολικά {len(self.rows)} εγγραφές."
        self.status.configure(text=message)
        logger.info("Εμφάνιση διαβιβασμένων. count=%s", len(self.rows))

    def _tree_scrolled(self, first, last) -> None:
        """Συνεχίζει την ίδια λίστα όταν ο χρήστης φτάσει κοντά στο τέλος της."""
        self.vertical_scrollbar.set(first, last)
        try:
            near_bottom = float(last) >= 0.98
        except (TypeError, ValueError):
            return
        if near_bottom:
            self._load_more()

    def _load_more(self) -> None:
        """Φορτώνει την επόμενη παρτίδα χωρίς αλλαγή σελίδας ή απώλεια επιλογής."""
        if self.busy or self.next_before_oid is None:
            return
        cursor = self.next_before_oid
        self.next_before_oid = None
        self._fetch_batch(cursor)

    def _set_busy(self, busy: bool) -> None:
        """Αποτρέπει παράλληλες αναζητήσεις και αλλαγές φίλτρων κατά την αναμονή."""
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.search_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.type_option.configure(state=state)
        for entry in self.entries.values():
            entry.configure(state=state)

    def _clear_rows(self) -> None:
        """Αφαιρεί την προηγούμενη επιλογή, ώστε να μην ανοίξει παλιός σύνδεσμος."""
        self.rows.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.next_before_oid = None
        self.url_text.set("")
        self.open_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")

    def clear(self) -> None:
        """Μηδενίζει όλα τα φίλτρα και τα προσωρινά αποτελέσματα."""
        if self.busy:
            return
        for entry in self.entries.values():
            entry.delete(0, "end")
        self.type_option.set("Όλοι οι τύποι")
        self.active_filters = {}
        self._clear_rows()
        self._set_busy(False)
        self.status.configure(text="Τα φίλτρα καθαρίστηκαν.")
        self.entries["mark"].focus_set()
        logger.info("Καθαρισμός φίλτρων διαβιβασμένων.")

    def _selected_url(self) -> str:
        """Επιστρέφει μόνο έγκυρο URL από την τρέχουσα επιλογή."""
        selection = self.tree.selection()
        if not selection or selection[0] not in self.rows:
            raise ValueError("Επιλέξτε ένα παραστατικό.")
        return DocumentLink.validate(self.rows[selection[0]].get("DocumentURL", ""))

    def _selection_changed(self, event=None) -> None:
        """Ενεργοποιεί τις ενέργειες μόνο για διαθέσιμο και έγκυρο σύνδεσμο."""
        try:
            url = self._selected_url()
        except ValueError as exc:
            self.url_text.set("")
            self.open_button.configure(state="disabled")
            self.copy_button.configure(state="disabled")
            if self.tree.selection():
                self.status.configure(text=str(exc))
            return
        self.url_text.set(url)
        self.open_button.configure(state="normal")
        self.copy_button.configure(state="normal")

    def _double_click(self, event) -> str:
        """Ανοίγει μόνο τη γραμμή κάτω από τον δείκτη, όχι την προηγούμενη επιλογή."""
        if self.tree.identify_region(event.x, event.y) == "cell":
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.selection_set(iid)
                self.open_url()
        return "break"

    def open_url(self) -> None:
        """Ανοίγει το URL στον browser του υπολογιστή του τεχνικού."""
        try:
            url = self._selected_url()
            if not webbrowser.open(url, new=2):
                raise ValueError("Δεν άνοιξε ο browser. Χρησιμοποιήστε Αντιγραφή URL.")
            logger.info("Άνοιγμα συνδέσμου διαβιβασμένου στον browser.")
            self.status.configure(text="Ο σύνδεσμος δόθηκε στον browser.")
        except Exception as exc:
            self.status.configure(text=str(exc) if isinstance(exc, ValueError) else "Αποτυχία ανοίγματος browser.")

    def copy_url(self) -> None:
        """Αντιγράφει τον επιλεγμένο σύνδεσμο χωρίς καταγραφή του στα logs."""
        try:
            url = self._selected_url()
            self.clipboard_clear()
            self.clipboard_append(url)
            self.status.configure(text="Το URL αντιγράφηκε.")
            logger.info("Αντιγραφή συνδέσμου διαβιβασμένου.")
        except Exception as exc:
            self.status.configure(text=str(exc) if isinstance(exc, ValueError) else "Αποτυχία αντιγραφής URL.")

    def destroy(self) -> None:
        """Ακυρώνει χρονόμετρα και αποδεσμεύει αποτελέσματα και συντομεύσεις."""
        if self._initial_load_after_id is not None:
            self.after_cancel(self._initial_load_after_id)
        for key, binding_id in self._shortcut_bindings:
            self._shortcut_parent.unbind(key, binding_id)
        self._shortcut_bindings.clear()
        for _, timer in self.pending.values():
            self.after_cancel(timer)
        self.pending.clear()
        self.rows.clear()
        super().destroy()
