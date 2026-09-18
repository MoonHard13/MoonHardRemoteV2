"""AppSettings με κάρτες, ασφαλές JSON και προσαρμοζόμενη διάταξη."""

import logging
import re
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from app.appsettings_presenter import AppSettingsPresenter as Presenter
from app.ui.theme import COLORS, FONTS, card_style, secondary_button_style

logger = logging.getLogger(__name__)


class SettingsCard(ctk.CTkFrame):
    """Κάρτα με επιλέξιμα πεδία μόνο για ανάγνωση."""

    def __init__(self, parent, title: str, caption: str):
        super().__init__(parent, **card_style())
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, font=FONTS.section_title, anchor="w").grid(
            row=0, column=0, padx=20, pady=(16, 0), sticky="ew")
        ctk.CTkLabel(self, text=caption, font=FONTS.small,
                     text_color=COLORS.text_secondary, anchor="w").grid(
            row=1, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.body.grid_columnconfigure(1, weight=1)
        self.fields = {}
        self._row = 0

    def field(self, key: str, label: str, value) -> None:
        """Προσθέτει πεδίο με οριζόντια μετακίνηση για μεγάλες τιμές."""
        ctk.CTkLabel(self.body, text=label, font=FONTS.body,
                     text_color=COLORS.text_secondary, anchor="w").grid(
            row=self._row, column=0, padx=(0, 14), pady=5, sticky="w")
        entry = ctk.CTkEntry(self.body, textvariable=tk.StringVar(value=Presenter.text(value)),
                            height=32, font=FONTS.body, fg_color=COLORS.background,
                            border_color=COLORS.border_soft, text_color=COLORS.text_primary)
        entry.grid(row=self._row, column=1, pady=5, sticky="ew")
        entry._entry.configure(state="readonly", readonlybackground=COLORS.background)
        self.fields[key] = entry
        self._row += 1

    def section(self, text: str) -> None:
        """Διαχωρίζει τις υποενότητες της ίδιας σύνδεσης."""
        ctk.CTkLabel(self.body, text=text, font=FONTS.body_bold,
                     text_color=COLORS.accent, anchor="w").grid(
            row=self._row, column=0, columnspan=2, pady=(16, 5), sticky="ew")
        self._row += 1


class AppSettingsTab(ctk.CTkFrame):
    """Παρουσιάζει τις διαθέσιμες ρυθμίσεις χωρίς αλλαγή του απομακρυσμένου αρχείου."""

    def __init__(self, parent, on_bo_connection_selected: Callable[[str], None] | None = None,
                 on_refresh_callback: Callable[[], None] | None = None) -> None:
        super().__init__(parent, corner_radius=0, fg_color="transparent")
        self.on_bo_connection_selected = on_bo_connection_selected
        self.on_refresh_callback = on_refresh_callback
        self._data = {}
        self._selected_id = None
        self._json = ""
        self._values = []
        self._layout_job = None
        self._wide = None
        self._shortcut_ids = []
        self.summary_cards = []
        self.detail_cards = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_ui()
        self.bind("<Configure>", self._schedule_layout, add="+")
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        """Δημιουργεί συμπαγή κεφαλίδα και περιεχόμενο που γεμίζει την καρτέλα."""
        header = ctk.CTkFrame(self, **card_style())
        header.grid(row=0, column=0, padx=16, pady=(12, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="AppSettings", font=FONTS.title, anchor="w").grid(
            row=0, column=0, padx=20, pady=(14, 0), sticky="w")
        self.badge = ctk.CTkLabel(header, text="Αναμονή δεδομένων", font=FONTS.small,
                                 text_color=COLORS.info, fg_color=COLORS.info_soft, corner_radius=8)
        self.badge.grid(row=0, column=1, padx=20, pady=(14, 0), sticky="e")
        self.status_label = ctk.CTkLabel(header, text="Προβολή ρυθμίσεων · Μόνο ανάγνωση",
                                        font=FONTS.small, text_color=COLORS.text_secondary, anchor="w")
        self.status_label.grid(row=1, column=0, columnspan=2, padx=20, pady=(2, 8), sticky="ew")
        self.path_entry = ctk.CTkEntry(header, height=28, font=FONTS.small,
                                      fg_color=COLORS.background, border_width=0)
        self.path_entry.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 8), sticky="ew")
        self._set_entry(self.path_entry, "Δεν έχει φορτωθεί αρχείο")
        toolbar = ctk.CTkFrame(header, fg_color="transparent")
        toolbar.grid(row=3, column=0, columnspan=2, padx=20, pady=(0, 16), sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)
        self.bo_connection_option = ctk.CTkOptionMenu(
            toolbar, values=["Δεν υπάρχουν BOConnections"], command=self._handle_bo_selected,
            width=310, height=34, fg_color=COLORS.surface_light, button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover, text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface, dropdown_hover_color=COLORS.surface_hover,
            dynamic_resizing=False, state="disabled")
        self.bo_connection_option.grid(row=0, column=0, padx=(0, 12), sticky="ew")
        self.bo_connection_option.bind("<Up>", lambda event: self._cycle_bo(-1))
        self.bo_connection_option.bind("<Down>", lambda event: self._cycle_bo(1))
        self.refresh_button = ctk.CTkButton(toolbar, text="Ανανέωση προβολής", width=155, height=34,
                                           command=self._handle_refresh, **secondary_button_style())
        self.refresh_button.grid(row=0, column=1, padx=(0, 8))
        self.copy_button = ctk.CTkButton(toolbar, text="Αντιγραφή JSON", width=135, height=34,
                                        command=self.copy_json, state="disabled", **secondary_button_style())
        self.copy_button.grid(row=0, column=2)
        self.mode = ctk.CTkSegmentedButton(self, values=["Σύνοψη", "Ασφαλές JSON"],
                                         command=self._show_mode, selected_color=COLORS.accent,
                                         selected_hover_color=COLORS.accent_hover,
                                         unselected_color=COLORS.surface_light,
                                         unselected_hover_color=COLORS.surface_hover)
        self.mode.set("Σύνοψη")
        self.mode.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="w")
        self.content = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.content.grid(row=2, column=0, padx=10, pady=(0, 12), sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.summary_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.summary_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.details_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.details_frame.grid(row=1, column=0, sticky="ew")
        self.message_label = ctk.CTkLabel(self.content, text="Αναμονή για τα AppSettings του Client…",
                                         font=FONTS.body, text_color=COLORS.text_secondary,
                                         wraplength=600, justify="left")
        self.message_label.grid(row=2, column=0, pady=32, sticky="ew")
        self.details_box = ctk.CTkTextbox(self, font=FONTS.mono_body, wrap="none",
                                         fg_color=COLORS.background, text_color=COLORS.text_primary,
                                         border_color=COLORS.border_soft, border_width=1)
        self._write_json("")
        ctk.CTkLabel(self, text="Ctrl+R Ανανέωση  ·  Ctrl+Shift+C Αντιγραφή JSON  ·  Ctrl+J Προβολή  ·  Ctrl+B Σύνδεση",
                     font=FONTS.small, text_color=COLORS.text_muted, anchor="w").grid(
            row=3, column=0, padx=20, pady=(0, 8), sticky="ew")

    @staticmethod
    def _set_entry(entry, value: str) -> None:
        """Ενημερώνει πεδίο με επιλογή και αντιγραφή χωρίς επεξεργασία."""
        entry._entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value)
        entry._entry.configure(state="readonly", readonlybackground=COLORS.background)

    def set_data(self, data: dict, selected_connection: dict | None = None) -> None:
        """Ανανεώνει τις κάρτες από το κοινό state του Manage window."""
        self._data = Presenter.safe_data(data)
        self._selected_id = (selected_connection or {}).get("ID", self._data.get("selected_bo_connection_id"))
        selected = next((item for item in self._data["bo_connections"]
                         if str(item.get("ID")) == str(self._selected_id)), {})
        self._json = Presenter.json(self._data, self._selected_id)
        self._write_json(self._json)
        self.copy_button.configure(state="normal")
        self._set_entry(self.path_entry, Presenter.text(self._data.get("file_path")))
        self.set_status("Τελευταία ανάγνωση: " + Presenter.timestamp(self._data.get("last_read_at")))
        found = self._data["file_found"]
        self.badge.configure(text="Φορτώθηκε · Μόνο ανάγνωση" if found else "Δεν βρέθηκε αρχείο",
                             text_color=COLORS.success if found else COLORS.warning,
                             fg_color=COLORS.success_soft if found else COLORS.warning_soft)
        self._clear_cards()
        if not found:
            self.set_bo_values([])
            self.message_label.configure(text="Το appsettings.production.json δεν βρέθηκε στον Client.\nΕλέγξτε τη διαδρομή και την εγκατάσταση του provider.")
            self.message_label.grid()
            return
        self.message_label.grid_remove()
        summary = self._data["appsettings_summary"]
        metrics = [("Επιτρεπόμενα hosts", summary.get("AllowedHosts")),
                   ("Μέγιστες επαναλήψεις", summary.get("MaxRetries")),
                   ("MaxWaitTimePerInvoice", summary.get("MaxWaitTimePerInvoice")),
                   ("Αρχική ημερομηνία", Presenter.date(summary.get("initialDate")))]
        for label, value in metrics:
            frame = ctk.CTkFrame(self.summary_frame, **card_style())
            frame.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(frame, text=label, font=FONTS.small, text_color=COLORS.text_secondary,
                         anchor="w").grid(row=0, column=0, padx=16, pady=(12, 2), sticky="ew")
            entry = ctk.CTkEntry(frame, height=36, font=FONTS.subtitle,
                                 fg_color=COLORS.surface, border_width=0, text_color=COLORS.text_primary)
            entry.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
            self._set_entry(entry, Presenter.text(value))
            self.summary_cards.append(frame)
        sql = SettingsCard(self.details_frame, "Σύνδεση Back Office", "Στοιχεία του επιλεγμένου BOConnection")
        self.detail_cards.append(sql)
        if selected:
            parts = Presenter.connection_parts(selected.get("DatabaseConnection", ""))
            sql.field("ID", "BOConnection ID", selected.get("ID"))
            sql.field("Server", "SQL Server", selected.get("DatabaseServer") or parts.get("server"))
            sql.field("Database", "Βάση δεδομένων", selected.get("DatabaseName") or parts.get("database"))
            sql.field("UserOID", "UserOID", selected.get("UserOID"))
            sql.field("email", "Email", selected.get("email"))
            sql.section("Προστατευμένα στοιχεία")
            for key, label, pattern in (("HasDatabaseUser", "SQL User ID", r"(?:user\s*id|uid)\s*=\s*[^;]+"),
                                        ("HasDatabasePassword", "SQL Password", r"(?:password|pwd)\s*=\s*[^;]+")):
                present = selected.get(key) or re.search(pattern, selected.get("DatabaseConnection", ""), re.IGNORECASE)
                sql.field(key, label, "***" if present else "—")
            sql.field("ClientAuth", "ClientAuth", selected.get("ClientAuth"))
            sql.field("subscriptionKey", "Subscription key", selected.get("subscriptionKey"))
            sql.section("Connection string · προστατευμένο")
            sql.field("DatabaseConnection", "Σύνδεση SQL", selected.get("DatabaseConnection"))
        else:
            sql.field("empty", "Κατάσταση", "Δεν υπάρχουν BOConnections")
        provider = SettingsCard(self.details_frame, "Συνδέσεις Provider", "Διευθύνσεις υπηρεσίας και offline λειτουργίας")
        self.detail_cards.append(provider)
        providers = self._data["provider_connections"]
        if providers:
            for index, item in enumerate(providers):
                provider.section("Provider ID " + Presenter.text(item.get("ID")))
                provider.field(f"{index}.BaseURL", "Base URL", item.get("BaseURL"))
                provider.field(f"{index}.OfflineURL", "Offline URL", item.get("OfflineURL"))
        else:
            provider.field("empty", "Κατάσταση", "Δεν υπάρχουν ProviderConnections")
        self._wide = None
        self._apply_layout()
        logger.info("Ανανέωση καρτών AppSettings. bo_count=%s provider_count=%s",
                    len(self._data["bo_connections"]), len(providers))

    def _clear_cards(self) -> None:
        """Αφαιρεί τις προηγούμενες κάρτες και τη μνήμη των πεδίων τους."""
        for frame in (self.summary_frame, self.details_frame):
            for child in frame.winfo_children():
                child.destroy()
        self.summary_cards = []
        self.detail_cards = []
        self._wide = None

    def _schedule_layout(self, event=None) -> None:
        """Συγχωνεύει τα συμβάντα μεγέθους για λιγότερες αναδιατάξεις."""
        if self._layout_job:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(60, self._apply_layout)

    def _apply_layout(self) -> None:
        """Χρησιμοποιεί δύο στήλες σε μεγάλα παράθυρα και μία σε μικρότερα."""
        self._layout_job = None
        layout = (self.winfo_width() >= 1050, self.winfo_width() >= 900)
        if layout == self._wide:
            return
        self._wide = layout
        for frame, cards, columns, maximum in ((self.summary_frame, self.summary_cards, 4 if layout[0] else 2, 4),
                                                (self.details_frame, self.detail_cards, 2 if layout[1] else 1, 2)):
            for column in range(maximum):
                frame.grid_columnconfigure(column, weight=1 if column < columns else 0,
                                           uniform="cards" if column < columns else "")
            for index, card in enumerate(cards):
                card.grid(row=index // columns, column=index % columns,
                          padx=(0 if index % columns == 0 else 6, 6 if index % columns < columns - 1 else 0),
                          pady=(0, 10), sticky="new")

    def _write_json(self, value: str) -> None:
        """Ενημερώνει το JSON χωρίς δυνατότητα επεξεργασίας."""
        self.details_box.configure(state="normal")
        self.details_box.delete("1.0", "end")
        self.details_box.insert("1.0", value)
        self.details_box.configure(state="disabled")

    def _show_mode(self, value: str) -> None:
        """Εναλλάσσει τις κάρτες με την πλήρη ασφαλή προβολή JSON."""
        if value == "Ασφαλές JSON":
            self.content.grid_remove()
            self.details_box.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="nsew")
        else:
            self.details_box.grid_remove()
            self.content.grid()
        logger.info("Αλλαγή προβολής AppSettings. mode=%s", value)

    def toggle_mode(self) -> None:
        """Εναλλάσσει την προβολή από πληκτρολόγιο."""
        value = "Ασφαλές JSON" if self.mode.get() == "Σύνοψη" else "Σύνοψη"
        self.mode.set(value)
        self._show_mode(value)

    def copy_json(self) -> None:
        """Αντιγράφει μόνο προστατευμένα δεδομένα χωρίς καταγραφή περιεχομένου."""
        if self._json:
            self.clipboard_clear()
            self.clipboard_append(self._json)
            logger.info("Αντιγραφή ασφαλούς AppSettings JSON.")

    def _handle_bo_selected(self, selected_value: str) -> None:
        """Ενημερώνει το κοινό BOConnection state από το υπάρχον callback."""
        logger.info("Αλλαγή επιλογής AppSettings BOConnection.")
        if self.on_bo_connection_selected:
            self.on_bo_connection_selected(selected_value)

    def _handle_refresh(self) -> None:
        """Ανανεώνει τα φορτωμένα στοιχεία χωρίς νέο διάβασμα αρχείου στον Client."""
        logger.info("Αίτημα ανανέωσης προβολής AppSettings.")
        if self.on_refresh_callback:
            self.on_refresh_callback()

    def _cycle_bo(self, step: int) -> str:
        """Επιτρέπει αλλαγή σύνδεσης με τα πλήκτρα πάνω και κάτω."""
        if self._values:
            index = self._values.index(self.bo_connection_option.get())
            value = self._values[(index + step) % len(self._values)]
            self.bo_connection_option.set(value)
            self._handle_bo_selected(value)
        return "break"

    def _bind_shortcuts(self) -> None:
        """Περιορίζει τις συντομεύσεις στα widgets της συγκεκριμένης καρτέλας."""
        top = self.winfo_toplevel()
        actions = {"<Control-r>": self._handle_refresh, "<Control-R>": self._handle_refresh,
                   "<Control-Shift-C>": self.copy_json, "<Control-j>": self.toggle_mode,
                   "<Control-J>": self.toggle_mode, "<Control-b>": self.bo_connection_option._canvas.focus_set,
                   "<Control-B>": self.bo_connection_option._canvas.focus_set}
        for sequence, action in actions.items():
            def handle(event, callback=action):
                """Αφήνει ανέπαφες τις συντομεύσεις άλλων καρτελών."""
                widget = top.focus_get()
                while widget is not None:
                    if widget is self:
                        callback()
                        return "break"
                    widget = getattr(widget, "master", None)
            binding = top.bind(sequence, handle, add="+")
            self._shortcut_ids.append((sequence, binding))

    def set_status(self, text: str) -> None:
        """Ενημερώνει το συνοπτικό μήνυμα κατάστασης."""
        self.status_label.configure(text=text)

    def set_text(self, text: str) -> None:
        """Καθαρίζει παλιές κάρτες όταν η φόρτωση αποτύχει ή δεν υπάρχει αποτέλεσμα."""
        self._data = {}
        self._json = ""
        self.copy_button.configure(state="disabled")
        self.set_bo_values([])
        self.badge.configure(text="Δεν υπάρχουν διαθέσιμα δεδομένα", text_color=COLORS.warning,
                             fg_color=COLORS.warning_soft)
        self._clear_cards()
        self.message_label.configure(text=text)
        self.message_label.grid()
        self._write_json("")
        logger.info("AppSettings χωρίς διαθέσιμα δεδομένα.")

    def set_bo_values(self, values: list[str], selected_value: str | None = None) -> None:
        """Διατηρεί την επιλογή και απενεργοποιεί κενές λίστες."""
        self._values = [value for value in values if value != "No BOConnections"]
        safe = self._values or ["Δεν υπάρχουν BOConnections"]
        self.bo_connection_option.configure(values=safe, state="normal" if self._values else "disabled")
        self.bo_connection_option.set(selected_value if selected_value in safe else safe[0])

    def get_selected_bo_value(self) -> str:
        """Επιστρέφει την επιλογή στο κοινό Manage window."""
        return self.bo_connection_option.get()

    def destroy(self) -> None:
        """Αφαιρεί callbacks και bindings χωρίς επιρροή στις άλλες καρτέλες."""
        if self._layout_job:
            self.after_cancel(self._layout_job)
        top = self.winfo_toplevel()
        for sequence, binding in self._shortcut_ids:
            top.unbind(sequence, binding)
        self._shortcut_ids.clear()
        super().destroy()
