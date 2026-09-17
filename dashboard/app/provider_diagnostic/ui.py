import json
import logging
from collections.abc import Callable
from tkinter import Menu, filedialog, ttk

import customtkinter as ctk

from app.provider_diagnostic.diagnostics import APIDiagnosticStore
from app.provider_diagnostic.service import ProviderDiagnosticService
from app.provider_diagnostic.sections import SECTIONS
from app.provider_diagnostic.tasks import BackgroundTask
from app.provider_diagnostic.session import ProviderContextSession
from app.provider_diagnostic.models import ProviderEndpoint
from app.provider_diagnostic.documents_view import DocumentsView
from app.ui.theme import COLORS, FONTS, apply_treeview_style, card_style, secondary_button_style


logger = logging.getLogger(__name__)


class ProviderDiagnosticTab(ctk.CTkFrame):
    """Μη μπλοκαρισμένο diagnostic module μέσα στο υπάρχον Manage window."""

    SECTIONS = SECTIONS
    COLUMNS = ("Timestamp", "Endpoint", "Operation", "Duration ms", "HTTP Status",
               "Records", "Result", "Error Category", "Message")

    def __init__(self, parent, service: ProviderDiagnosticService,
                 is_active: Callable[[], bool],
                 session: ProviderContextSession | None = None,
                 request_context: Callable[[dict], object] | None = None) -> None:
        super().__init__(parent, fg_color="transparent")
        self.service = service
        self.session = session or ProviderContextSession()
        self._request_context = request_context
        self._company_labels = {}
        self._last_ready = False
        self._is_active = is_active
        self._task = BackgroundTask()
        self._closed = False
        self._scope = None
        self._context = None
        self._job = None
        self._bindings = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_ui()
        self._bind_shortcuts()
        self.refresh_context()
        self._job = self.after(100, self._poll)

    def _build_ui(self) -> None:
        toolbar = ctk.CTkFrame(self, **card_style())
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        toolbar.grid_columnconfigure(0, weight=1)
        self.section = ctk.CTkOptionMenu(toolbar, values=list(self.SECTIONS),
                                         command=self._show_section, width=200)
        self.section.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkButton(toolbar, text="Εταιρείες · F5", command=self.load_companies,
                      width=120, **secondary_button_style()).grid(row=0, column=1, padx=5)
        self.probe_button = ctk.CTkButton(toolbar, text="Έλεγχος Provider · Ctrl+Enter",
                                          command=self.probe, width=220, **secondary_button_style())
        self.probe_button.grid(row=0, column=2, padx=5)
        self.cancel_button = ctk.CTkButton(toolbar, text="Ακύρωση · Esc", command=self.cancel,
                                           width=120, state="disabled", **secondary_button_style())
        self.cancel_button.grid(row=0, column=3, padx=10)
        self.status = ctk.CTkLabel(self, text="", anchor="w", font=FONTS.small,
                                   text_color=COLORS.text_secondary, wraplength=750)
        self.status.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        self.overview = ctk.CTkScrollableFrame(self, fg_color=COLORS.surface)
        self.overview.grid_columnconfigure(0, weight=1)
        company_bar = ctk.CTkFrame(self.overview, fg_color="transparent")
        company_bar.grid(row=0, column=0, padx=16, pady=10, sticky="ew")
        company_bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(company_bar, text="Εταιρεία / ΑΦΜ · Alt+A").grid(row=0, column=0, padx=(0, 10))
        self.company = ctk.CTkComboBox(company_bar, values=["Ανακτήστε εταιρείες με F5"],
                                     state="disabled", command=self._select_company, width=440)
        self.company.grid(row=0, column=1, sticky="ew")
        self.company.bind("<Return>", lambda _: self._select_company(self.company.get()))
        self.context_text = ctk.CTkLabel(self.overview, text="", anchor="w", justify="left",
                                         font=FONTS.body, wraplength=740)
        self.context_text.grid(row=1, column=0, padx=16, pady=16, sticky="ew")
        self.last_request = ctk.CTkLabel(self.overview, text="Δεν έχει γίνει Provider API call.",
                                         anchor="w", justify="left", font=FONTS.body)
        self.last_request.grid(row=2, column=0, padx=16, pady=8, sticky="ew")
        self.document_totals = ctk.CTkLabel(self.overview, text="Δεν έχουν ανακτηθεί παραστατικά για το επιλεγμένο διάστημα.",
                     justify="left", anchor="w", font=FONTS.body, text_color=COLORS.text_secondary,
                     wraplength=740)
        self.document_totals.grid(row=3, column=0, padx=16, pady=16, sticky="ew")
        self.documents_view = DocumentsView(self, self.load_documents, lambda text: self.status.configure(text=text))
        self.planned = ctk.CTkFrame(self, **card_style())
        self.planned.grid_columnconfigure(0, weight=1)
        self.planned_text = ctk.CTkLabel(self.planned, text="", font=FONTS.body,
                                         justify="left", wraplength=740)
        self.planned_text.grid(row=0, column=0, padx=24, pady=40, sticky="nw")
        self.api_view = ctk.CTkFrame(self, fg_color="transparent")
        self.api_view.grid_columnconfigure(0, weight=1)
        self.api_view.grid_rowconfigure(1, weight=1)
        filters = ctk.CTkFrame(self.api_view, fg_color="transparent")
        filters.grid(row=0, column=0, sticky="ew", pady=8)
        filters.grid_columnconfigure(1, weight=1)
        self.outcome = ctk.CTkOptionMenu(filters, values=["All", "Success", "Errors"],
                                         width=100, command=lambda _: self.refresh_diagnostics())
        self.outcome.grid(row=0, column=0, padx=4)
        self.endpoint = ctk.CTkEntry(filters, placeholder_text="Endpoint · Ctrl+F")
        self.endpoint.grid(row=0, column=1, sticky="ew", padx=4)
        self.http_status = ctk.CTkEntry(filters, placeholder_text="HTTP Status", width=105)
        self.http_status.grid(row=0, column=2, padx=4)
        for entry in (self.endpoint, self.http_status):
            entry.bind("<KeyRelease>", lambda _: self.refresh_diagnostics())
        for column, text, action in ((3, "Copy · Ctrl+C", self.copy_selected),
                                     (4, "Export · Ctrl+E", self.export)):
            ctk.CTkButton(filters, text=text, command=action, width=120,
                          **secondary_button_style()).grid(row=0, column=column, padx=4)
        table = ctk.CTkFrame(self.api_view, fg_color="transparent")
        table.grid(row=1, column=0, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=self.COLUMNS, show="headings",
                                 style=apply_treeview_style(), selectmode="extended")
        self.tree.grid(row=0, column=0, sticky="nsew")
        for column in self.COLUMNS:
            self.tree.heading(column, text=column, command=lambda c=column: self._sort(c))
            self.tree.column(column, width=150 if column != "Endpoint" else 350, minwidth=80, stretch=True)
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._sort_reverse: dict[str, bool] = {}
        self.menu = Menu(self.tree, tearoff=False)
        self.menu.add_command(label="Αντιγραφή διαγνωστικών", command=self.copy_selected)
        self.menu.add_command(label="Εξαγωγή ορατών διαγνωστικών", command=self.export)
        self.tree.bind("<Button-3>", self._context_menu)
        self._show_section("Overview")

    def _show_section(self, section: str) -> None:
        self.section.set(section)
        for frame in (self.overview, self.api_view, self.documents_view, self.planned):
            frame.grid_remove()
        frame = self.overview if section == "Overview" else self.api_view if section == "API Diagnostics" else self.documents_view if section == "Documents" else self.planned
        if frame is self.planned:
            phase = self.SECTIONS[section]
            text = (f"{section}\n\nΠρογραμματισμένη υλοποίηση: Phase {phase}.\n"
                    "Η λειτουργία δεν έχει υλοποιηθεί ακόμη.") if phase else (
                        "QR Tools\n\nΑπαιτείται πλήρες endpoint/schema από S1Ecos\n"
                        "για το RequestGroupQRDetails. Δεν εκτελείται guessed request.")
            self.planned_text.configure(text=text)
        frame.grid(row=2, column=0, padx=8, pady=8, sticky="nsew")

    def refresh_context(self) -> None:
        if self._closed:
            return
        context = self.service.snapshot()
        scope = (*self.session.scope(context), self.session.issuer_vat, self.session.provider_base_url, self.session.generation)
        if self._scope is not None and scope != self._scope:
            self._task.cancel()
            self._clear_documents()
            if scope[:4] != self._scope[:4]:
                self.session.clear()
                context = self.service.snapshot()
                scope = (*self.session.scope(context), self.session.issuer_vat, self.session.provider_base_url, self.session.generation)
                self._update_company_options()
            # Το προηγούμενο worker κρατά το προηγούμενο store, ποτέ το νέο customer dataset.
            self.service.diagnostics.close()
            self.service.diagnostics = APIDiagnosticStore()
        if not context.client_connected:
            self._task.cancel()
            self._clear_documents()
            self.session.clear()
            self._update_company_options()
            context = self.service.snapshot()
            scope = (*self.session.scope(context), self.session.issuer_vat, self.session.provider_base_url, self.session.generation)
        self._scope, self._context = scope, context
        self._last_ready = context.provider_ready
        erp = "Client συνδεδεμένος · SQL σύνδεση δεν έχει ελεγχθεί" if context.client_connected else "Client εκτός σύνδεσης · SQL σύνδεση δεν έχει ελεγχθεί"
        if self.session.sql_verified:
            erp = "Επιτυχής ανάγνωση TblSnCompany στην επιλεγμένη βάση"
        provider = "Έτοιμος για χειροκίνητο έλεγχο" if context.provider_ready else self.session.message
        environment = ProviderEndpoint.environment(self.session.provider_base_url) if self.session.provider_base_url else "Μη διαθέσιμο"
        self.context_text.configure(text=(f"Πελάτης/εγκατάσταση: {context.display_name}\n"
            f"Client: {context.client_code}\nBOConnection: {context.bo_connection_id or 'Μη διαθέσιμο'}\n"
            f"Server: {context.database_server or 'Μη διαθέσιμο'}\nDatabase: {context.database_name or 'Μη διαθέσιμο'}\n"
            f"ΑΦΜ εκδότη: {context.issuer_vat or self.session.issuer_vat or 'Επιλέξτε εταιρεία'}\n"
            f"Περιβάλλον: {environment}\nProvider URL (ρυθμίσεις): {self.session.provider_base_url or 'Μη διαθέσιμο'}\n"
            f"GetDocuments URL: {ProviderEndpoint.documents_origin(self.session.provider_base_url) if self.session.provider_base_url else 'Μη διαθέσιμο'}\n"
            f"ERP: {erp}\nProvider: {provider}"))
        self.probe_button.configure(state="normal" if context.provider_ready and not self._task.busy else "disabled")
        self.documents_view.load_button.configure(state="normal" if context.provider_ready and not self._task.busy else "disabled")
        self.documents_view.scope.configure(text=f"{context.display_name} · BOConnection {context.bo_connection_id} · "
            f"ΑΦΜ: {context.issuer_vat or self.session.issuer_vat or 'Επιλέξτε εταιρεία'} · {environment}")
        self.status.configure(text="Phase 2 · Πραγματικά εξερχόμενα παραστατικά και API Diagnostics")
        self.refresh_diagnostics()
        logger.info("Ενημέρωση context Provider Diagnostic Center.")

    def _update_company_options(self) -> None:
        self._company_labels = {
            f"{row['issuer_vat'][2:]} · {row['company_name'] or 'Εταιρεία'}": row["issuer_vat"]
            for row in self.session.companies
        }
        values = list(self._company_labels) or ["Ανακτήστε εταιρείες με F5"]
        self.company.configure(values=values, state="readonly" if self._company_labels else "disabled")
        selected = next((label for label, vat in self._company_labels.items()
                         if vat == self.session.issuer_vat), "Επιλέξτε εταιρεία / ΑΦΜ")
        self.company.set(selected if self._company_labels else values[0])

    def load_companies(self) -> None:
        self._request_provider_context("")

    def _select_company(self, label) -> None:
        vat = self._company_labels.get(label)
        if vat:
            self._request_provider_context(vat)

    def _request_provider_context(self, issuer_vat) -> None:
        if self._closed or not self._request_context:
            return
        self._task.cancel()
        try:
            payload = self.session.request(self.service.context.snapshot(), issuer_vat)
            sent = self._request_context(payload)
            if sent is False:
                self.session.cancel("Δεν είναι διαθέσιμη η σύνδεση Dashboard–server.")
        except ValueError as exc:
            self.session.cancel(str(exc))
        self._update_company_options()
        self.refresh_context()
        self.status.configure(text=self.session.message)
        self.cancel_button.configure(state="normal" if self.session.pending or self._task.busy else "disabled")
        logger.info("Αίτημα ανάκτησης εταιρειών/Provider context.")

    def handle_context_result(self, payload) -> None:
        if self._closed or not self.session.accept(payload, self.service.context.snapshot()):
            return
        self._update_company_options()
        self.refresh_context()
        if len(self.session.companies) == 1 and not self.session.issuer_vat and self.session.context_valid:
            self._select_company(next(iter(self._company_labels)))
        else:
            self.status.configure(text=self.session.message + (
                f" Παραλείφθηκαν εγγραφές χωρίς ΑΦΜ 9 ψηφίων: {self.session.invalid_afm_count}."
                if self.session.invalid_afm_count else ""))
            self.cancel_button.configure(state="normal" if self._task.busy else "disabled")
        logger.info("Επεξεργασία Provider context ολοκληρώθηκε.")

    def _focus_company(self) -> None:
        self._show_section("Overview")
        self.company.focus_set()

    def _focus_section(self) -> None:
        self.section.focus_set()

    def probe(self) -> None:
        self.refresh_context()
        if not self._context.provider_ready or self._task.busy:
            return
        context = self._context
        diagnostics = self.service.diagnostics
        if self._task.start(lambda cancel: self.service.probe(context, cancel, diagnostics)):
            self._running_kind = "probe"
            self._running_scope = self._scope
            self.status.configure(text="Ανάγνωση πρώτης σελίδας σημερινών παραστατικών…")
            self.probe_button.configure(state="disabled")
            self.cancel_button.configure(state="normal")
            logger.info("Έναρξη χειροκίνητου Provider diagnostic request.")

    def _clear_documents(self):
        self.documents_view.clear()
        self.document_totals.configure(text="Δεν έχουν ανακτηθεί παραστατικά για το επιλεγμένο διάστημα.")

    def load_documents(self):
        self.refresh_context()
        self._show_section("Documents")
        if not self._context.provider_ready or self._task.busy:
            return
        context, diagnostics = self._context, self.service.diagnostics
        start, end = self.documents_view.date_from.get().strip(), self.documents_view.date_to.get().strip()
        if self._task.start(lambda cancel: self.service.documents(context, start, end, cancel,
                self._task.report_progress, diagnostics)):
            self._clear_documents()
            self._running_kind, self._running_scope = "documents", self._scope
            self.status.configure(text="Ανάκτηση παραστατικών…")
            self.probe_button.configure(state="disabled")
            self.documents_view.load_button.configure(state="disabled")
            self.cancel_button.configure(state="normal")

    def _install_documents(self, dataset):
        self.documents_view.set_dataset(dataset)
        summary = dataset.summary()
        self.document_totals.configure(text=(f"Διάστημα: {dataset.date_from}–{dataset.date_to}\n"
            f"Παραστατικά: {summary['records']} · Σελίδες API: {summary['pages']}\n"
            f"Συνολική αξία: {summary['total_amount']} · ΦΠΑ: {summary['total_vat']}\n"
            f"Με MARK: {summary['with_mark']} · Χωρίς MARK: {summary['without_mark']}\n"
            f"Τύποι: {', '.join(f'{name}: {count}' for name, count in sorted(summary['invoice_types'].items())) or 'Δεν υπάρχουν'}\n"
            f"Χωρίς διαθέσιμη αξία: {summary['missing_amounts']} · Χωρίς διαθέσιμο ΦΠΑ: {summary['missing_vat']}\n"
            f"Ανακτήθηκαν από API: {summary['fetched_records']} · Εκτός διαστήματος: {dataset.excluded_by_date}\n"
            f"Τελευταία ανάκτηση: {dataset.loaded_at}\n{dataset.warning}"))

    def cancel(self) -> None:
        if self.session.pending:
            self.session.cancel()
            self.refresh_context()
            self.status.configure(text=self.session.message)
            self.cancel_button.configure(state="disabled")
        if self._task.busy:
            self._task.cancel()
            self.status.configure(text="Ζητήθηκε ακύρωση· το ενεργό socket έχει πεπερασμένο timeout.")
            logger.info("Ζητήθηκε ακύρωση Provider diagnostic request.")

    def _poll(self) -> None:
        if self._closed:
            return
        if self.session.expire_pending():
            self.refresh_context()
            self.status.configure(text=self.session.message)
            self.cancel_button.configure(state="disabled")
        if self._last_ready and not self.service.snapshot().provider_ready:
            self.refresh_context()
        progress = self._task.poll_progress()
        if isinstance(progress, dict) and not self._task.cancel_event.is_set() and getattr(self, "_running_scope", None) == self._scope:
            self.status.configure(text=f"Ανάκτηση: {progress['pages']} σελίδες · {progress['records']} στο διάστημα · "
                f"{progress.get('fetched_records', progress['records'])} από API…")
        result = self._task.poll()
        if result is not None:
            value, error = result
            if getattr(self, "_running_scope", None) == self._scope:
                if error:
                    self.status.configure(text=error.message)
                elif getattr(self, "_running_kind", "probe") == "documents":
                    self._install_documents(value)
                    self.status.configure(text=value.status_text)
                else:
                    self.status.configure(text=f"Έλεγχος ολοκληρώθηκε. Records πρώτης σελίδας: {value['records']}")
            self.probe_button.configure(state="normal" if self._context.provider_ready else "disabled")
            self.documents_view.load_button.configure(state="normal" if self._context.provider_ready else "disabled")
            self.cancel_button.configure(state="disabled")
            self.refresh_diagnostics()
        self._job = self.after(100, self._poll)

    def refresh_diagnostics(self) -> None:
        rows = self.service.diagnostics.entries(self.outcome.get(), self.endpoint.get().strip(), self.http_status.get().strip())
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for row in rows:
            self.tree.insert("", "end", values=(row.timestamp.isoformat(timespec="seconds"), row.endpoint,
                row.operation, row.duration_ms, row.http_status if row.http_status is not None else "-",
                row.records, "Success" if row.success else "Failure", row.error_category, row.error_message))
        all_rows = self.service.diagnostics.entries()
        latest_success = next((row for row in reversed(all_rows) if row.success), None)
        last = all_rows[-1] if all_rows else None
        self.last_request.configure(text=(f"Τελευταία επιτυχία: {latest_success.timestamp.isoformat(timespec='seconds') if latest_success else 'Δεν υπάρχει'}\n"
            f"Διάρκεια τελευταίου attempt: {last.duration_ms if last else '-'} ms\n"
            f"Τελευταίο HTTP status: {last.http_status if last else '-'}"))

    def _sort(self, column: str) -> None:
        numeric = column in ("Duration ms", "HTTP Status", "Records")
        def key(iid):
            value = self.tree.set(iid, column)
            return int(value) if numeric and value.isdigit() else -1 if numeric else value.casefold()
        reverse = self._sort_reverse.get(column, False)
        for position, iid in enumerate(sorted(self.tree.get_children(), key=key, reverse=reverse)):
            self.tree.move(iid, "", position)
        self._sort_reverse[column] = not reverse

    def _context_menu(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            try:
                self.menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.menu.grab_release()

    def copy_selected(self) -> None:
        if self.section.get() == "Documents":
            self.documents_view.copy_selected()
            return
        lines = ["\t".join(str(value) for value in self.tree.item(iid, "values")) for iid in self.tree.selection()]
        if lines:
            self.clipboard_clear()
            self.clipboard_append("\n".join(lines))
            logger.info("Αντιγραφή επιλεγμένων API diagnostics.")

    def export(self) -> None:
        if self.section.get() == "Documents":
            self.documents_view.export()
            return
        path = filedialog.asksaveasfilename(parent=self.winfo_toplevel(), defaultextension=".json",
            initialfile="provider-api-diagnostics.json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            rows = [dict(zip(self.COLUMNS, self.tree.item(iid, "values"))) for iid in self.tree.get_children()]
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(rows, stream, ensure_ascii=False, indent=2)
            self.status.configure(text=f"Εξαγωγή ολοκληρώθηκε. Εγγραφές: {len(rows)}")
            logger.info("Εξαγωγή API diagnostics ολοκληρώθηκε. count=%s", len(rows))
        except OSError:
            self.status.configure(text="Δεν ήταν δυνατή η αποθήκευση. Ελέγξτε δικαιώματα και διαθέσιμο χώρο.")
            logger.warning("Αποτυχία αποθήκευσης API diagnostics.")

    def _search(self) -> None:
        if self.section.get() == "Documents":
            self.documents_view.filters["number"].focus_set()
            return
        self._show_section("API Diagnostics")
        self.endpoint.focus_set()

    def _bind_shortcuts(self) -> None:
        top = self.winfo_toplevel()
        for sequence, operation in (("<F5>", self.load_companies), ("<Alt-a>", self._focus_company),
                ("<Alt-s>", self._focus_section), ("<Control-Return>", self.probe),
                ("<Escape>", self.cancel), ("<Control-f>", self._search),
                ("<Control-c>", self.copy_selected), ("<Control-e>", self.export)):
            def handler(event, action=operation):
                if self._is_active() and event.widget.winfo_toplevel() == top:
                    if event.keysym.lower() == "c" and event.widget not in (self.tree, self.documents_view.tree):
                        return None
                    action()
                    return "break"
                return None
            self._bindings.append((sequence, top.bind(sequence, handler, add="+")))
        for sequence, action in (("<Control-l>", self.load_documents),
                ("<Alt-d>", lambda: self._show_section("Documents")),
                ("<Alt-Key-1>", lambda: self._focus_document_date("date_from")),
                ("<Alt-Key-2>", lambda: self._focus_document_date("date_to")),
                ("<Control-o>", self.documents_view.open_url),
                ("<Control-r>", self.documents_view.reset_filters),
                ("<Control-Shift-C>", self.documents_view.copy_details)):
            def document_handler(event, operation=action, shortcut=sequence):
                if self._is_active() and event.widget.winfo_toplevel() == top and (
                        shortcut.startswith("<Alt-") or shortcut == "<Control-l>" or self.section.get() == "Documents"):
                    operation()
                    return "break"
            self._bindings.append((sequence, top.bind(sequence, document_handler, add="+")))

    def _focus_document_date(self, name):
        self._show_section("Documents")
        getattr(self.documents_view, name).focus_set()

    def destroy(self) -> None:
        self._closed = True
        self._task.close()
        self.session.clear()
        self.service.close()
        if self._job is not None:
            self.after_cancel(self._job)
        top = self.winfo_toplevel()
        for sequence, binding in self._bindings:
            if binding:
                top.unbind(sequence, binding)
        super().destroy()
