import uuid
from collections.abc import Callable
from datetime import date, datetime
from tkinter import messagebox
from typing import ClassVar

import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    card_style,
    danger_button_style,
    primary_button_style,
    secondary_button_style,
)


class DatabaseTab(ctk.CTkFrame):
    """UI για τις προκαθορισμένες λειτουργίες ελέγχου και συντήρησης βάσης."""

    ACTION_TITLES: ClassVar[dict[str, str]] = {
        "test_connection": "Connection Test",
        "sales_trans_info": "SalesTrans Information",
        "mydata_info": "MyData Information",
        "clean_mydata": "MyData Cleanup",
        "history": "Sales History",
        "shrink": "Database Shrink",
        "rebuild": "Database Rebuild / Update",
    }

    def __init__(
        self,
        parent,
        client_code: str,
        get_bo_values_callback: Callable[[], list[str]],
        get_selected_bo_id_callback: Callable[[], int],
        on_bo_selected_callback: Callable[[str], None] | None = None,
        on_database_request_callback: Callable[[dict], None] | None = None,
    ) -> None:
        """Αρχικοποιεί το tab και το συνδέει με το κοινό BOConnection state."""

        super().__init__(parent, corner_radius=0, fg_color="transparent")
        self.client_code = client_code
        self.get_bo_values_callback = get_bo_values_callback
        self.get_selected_bo_id_callback = get_selected_bo_id_callback
        self.on_bo_selected_callback = on_bo_selected_callback
        self.on_database_request_callback = on_database_request_callback
        self.current_request_id = ""
        self.current_action = ""
        self._progress_messages: set[str] = set()
        self.action_buttons: list[ctk.CTkButton] = []
        self._shortcut_bindings: list[tuple[str, str | None]] = []
        self._shortcut_parent = self.winfo_toplevel()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        """Δημιουργεί responsive διάταξη συμβατή με το theme του dashboard."""

        content = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
        )
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        header = ctk.CTkFrame(content, **card_style())
        header.grid(
            row=0,
            column=0,
            columnspan=2,
            padx=SPACING.card_padding,
            pady=(SPACING.card_padding, SPACING.inner_padding),
            sticky="ew",
        )
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Database Maintenance",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, columnspan=4, padx=18, pady=(16, 4), sticky="w")

        ctk.CTkLabel(
            header,
            text="BOConnection:",
            font=FONTS.body_bold,
            text_color=COLORS.text_primary,
        ).grid(row=1, column=0, padx=(18, 10), pady=(6, 16), sticky="w")

        self.bo_option = ctk.CTkOptionMenu(
            header,
            values=["No BOConnections"],
            command=self._on_bo_selected,
            width=260,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.bo_option.grid(row=1, column=1, padx=(0, 10), pady=(6, 16), sticky="w")

        refresh_button = ctk.CTkButton(
            header,
            text="Refresh BO  [F5]",
            width=125,
            command=self.refresh_bo_values,
            **secondary_button_style(),
        )
        refresh_button.grid(row=1, column=2, padx=(0, 10), pady=(6, 16))

        test_button = self._action_button(
            header,
            text="Test Connection  [Ctrl+T]",
            command=lambda: self.request_action("test_connection"),
            width=185,
            style="primary",
        )
        test_button.grid(row=1, column=3, padx=(0, 18), pady=(6, 16))

        info_card = self._card(content, row=1, column=0, title="Database Information")
        ctk.CTkLabel(
            info_card,
            text="Read the oldest date and row totals without changing data.",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            justify="left",
            wraplength=390,
        ).grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="w")

        sales_button = self._action_button(
            info_card,
            text="SalesTrans Info  [Ctrl+1]",
            command=lambda: self.request_action("sales_trans_info"),
        )
        sales_button.grid(row=2, column=0, padx=(16, 6), pady=(0, 16), sticky="ew")

        mydata_button = self._action_button(
            info_card,
            text="MyData Info  [Ctrl+2]",
            command=lambda: self.request_action("mydata_info"),
        )
        mydata_button.grid(row=2, column=1, padx=(6, 16), pady=(0, 16), sticky="ew")

        cleanup_card = self._card(content, row=1, column=1, title="MyData Cleanup")
        cleanup_card.grid_columnconfigure(0, weight=1)
        cleanup_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            cleanup_card,
            text="Deletes only responses whose status is not Success within the selected range.",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            justify="left",
            wraplength=390,
        ).grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="w")

        self.clean_from_entry = self._date_field(cleanup_card, "From (YYYYMMDD)", 2, 0)
        self.clean_to_entry = self._date_field(cleanup_card, "To (YYYYMMDD)", 2, 1)
        self.clean_to_entry.insert(0, datetime.now().astimezone().strftime("%Y%m%d"))

        clean_button = self._action_button(
            cleanup_card,
            text="Clean Responses  [Ctrl+3]",
            command=self.request_clean_mydata,
            style="danger",
        )
        clean_button.grid(
            row=4, column=0, columnspan=2, padx=16, pady=(2, 16), sticky="ew"
        )

        history_card = self._card(content, row=2, column=0, title="Sales History")
        history_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            history_card,
            text="Runs SnProPOS_SalesTrHist for the selected cutoff date.",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            justify="left",
            wraplength=390,
        ).grid(row=1, column=0, padx=16, pady=(0, 10), sticky="w")

        self.history_date_entry = self._date_field(
            history_card,
            "Date (YYYYMMDD)",
            2,
            0,
        )
        history_button = self._action_button(
            history_card,
            text="Run History  [Ctrl+4]",
            command=self.request_history,
        )
        history_button.grid(row=4, column=0, padx=16, pady=(2, 16), sticky="ew")

        maintenance_card = self._card(
            content, row=2, column=1, title="Database Maintenance"
        )
        ctk.CTkLabel(
            maintenance_card,
            text=(
                "Run these operations only during non-working hours. "
                "Rebuild may require significant time."
            ),
            font=FONTS.body,
            text_color=COLORS.warning,
            justify="left",
            wraplength=390,
        ).grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 14), sticky="w")

        shrink_button = self._action_button(
            maintenance_card,
            text="Shrink Database  [Ctrl+5]",
            command=self.request_shrink,
            style="danger",
        )
        shrink_button.grid(row=2, column=0, padx=(16, 6), pady=(0, 16), sticky="ew")

        rebuild_button = self._action_button(
            maintenance_card,
            text="Rebuild / Update  [Ctrl+6]",
            command=self.request_rebuild,
            style="danger",
        )
        rebuild_button.grid(row=2, column=1, padx=(6, 16), pady=(0, 16), sticky="ew")

        output_card = ctk.CTkFrame(content, **card_style())
        output_card.grid(
            row=3,
            column=0,
            columnspan=2,
            padx=SPACING.card_padding,
            pady=(0, SPACING.card_padding),
            sticky="nsew",
        )
        output_card.grid_columnconfigure(0, weight=1)
        output_card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            output_card,
            text="Activity",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")

        self.status_label = ctk.CTkLabel(
            output_card,
            text="Ready",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
        )
        self.status_label.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(
            output_card,
            height=8,
            fg_color=COLORS.surface_light,
            progress_color=COLORS.accent,
        )
        self.progress_bar.grid(row=2, column=0, padx=16, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()

        self.output_box = ctk.CTkTextbox(
            output_card,
            height=150,
            fg_color=COLORS.background,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
            border_width=1,
            font=FONTS.mono_body,
            wrap="word",
        )
        self.output_box.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")
        self._set_output("Select a BOConnection and choose an operation.")

        self.clean_from_entry.bind(
            "<Return>", lambda _event: self.request_clean_mydata()
        )
        self.clean_to_entry.bind("<Return>", lambda _event: self.request_clean_mydata())
        self.history_date_entry.bind("<Return>", lambda _event: self.request_history())
        self.refresh_bo_values()

    def _card(self, parent, row: int, column: int, title: str) -> ctk.CTkFrame:
        """Δημιουργεί κοινό card λειτουργιών."""

        frame = ctk.CTkFrame(parent, **card_style())
        frame.grid(
            row=row,
            column=column,
            padx=(
                SPACING.card_padding if column == 0 else 6,
                6 if column == 0 else SPACING.card_padding,
            ),
            pady=(0, SPACING.inner_padding),
            sticky="nsew",
        )
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            frame,
            text=title,
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 5), sticky="w")
        return frame

    def _date_field(
        self,
        parent,
        label: str,
        row: int,
        column: int,
    ) -> ctk.CTkEntry:
        """Δημιουργεί label και input ημερομηνίας σε κοινή μορφή."""

        field = ctk.CTkFrame(parent, fg_color="transparent")
        field.grid(row=row, column=column, padx=16, pady=(0, 10), sticky="ew")
        field.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            field,
            text=label,
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        ).grid(row=0, column=0, pady=(0, 4), sticky="w")
        entry = ctk.CTkEntry(
            field,
            fg_color=COLORS.surface_light,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
        )
        entry.grid(row=1, column=0, sticky="ew")
        return entry

    def _action_button(
        self,
        parent,
        text: str,
        command: Callable[[], None],
        width: int = 150,
        style: str = "secondary",
    ) -> ctk.CTkButton:
        """Δημιουργεί button που συμμετέχει στο κοινό busy state."""

        style_values = {
            "primary": primary_button_style,
            "danger": danger_button_style,
            "secondary": secondary_button_style,
        }[style]()
        button = ctk.CTkButton(
            parent,
            text=text,
            width=width,
            command=command,
            **style_values,
        )
        self.action_buttons.append(button)
        return button

    def refresh_bo_values(self) -> None:
        """Ανανεώνει τις BOConnections και κρατά την κοινή επιλογή του Manage window."""

        values = self.get_bo_values_callback() if self.get_bo_values_callback else []
        safe_values = values or ["No BOConnections"]
        selected_id = (
            self.get_selected_bo_id_callback()
            if self.get_selected_bo_id_callback
            else 1
        )
        selected_value = next(
            (value for value in safe_values if value.startswith(f"ID {selected_id} ")),
            safe_values[0],
        )
        self.bo_option.configure(values=safe_values)
        self.bo_option.set(selected_value)

    def _on_bo_selected(self, selected_value: str) -> None:
        """Συγχρονίζει την επιλογή βάσης με τα υπόλοιπα tabs."""

        if self.on_bo_selected_callback:
            self.on_bo_selected_callback(selected_value)

    @staticmethod
    def _extract_bo_id(selected_value: str) -> int | None:
        """Εξάγει ID από τιμή τύπου 'ID 1 - DatabaseName'."""

        try:
            return int(selected_value.split()[1])
        except (IndexError, TypeError, ValueError):
            return None

    def request_action(
        self,
        action: str,
        parameters: dict[str, str] | None = None,
    ) -> None:
        """Στέλνει μία database action εφόσον υπάρχει έγκυρη βάση και δεν εκτελείται άλλη."""

        if self.current_request_id:
            self._set_status(
                "Another database action is already running.", COLORS.warning
            )
            return

        bo_connection_id = self._extract_bo_id(self.bo_option.get())
        if bo_connection_id is None:
            self._set_status("No valid BOConnection selected.", COLORS.danger)
            return

        request_id = str(uuid.uuid4())
        self.current_request_id = request_id
        self.current_action = action
        self._progress_messages.clear()
        self._set_busy(True)
        title = self.ACTION_TITLES.get(action, action)
        self._set_status(f"Running {title}...", COLORS.accent)
        if action == "rebuild":
            self.progress_bar.set(0)
            self.progress_bar.grid()
        else:
            self.progress_bar.grid_remove()
        self._set_output(
            f"Action: {title}\n"
            f"BOConnection ID: {bo_connection_id}\n"
            "Status: Waiting for the remote client..."
        )

        if not self.on_database_request_callback:
            self.current_request_id = ""
            self.current_action = ""
            self._set_busy(False)
            self._set_status("Database request channel is unavailable.", COLORS.danger)
            return

        self.on_database_request_callback(
            {
                "type": "database_action",
                "request_id": request_id,
                "client_code": self.client_code,
                "bo_connection_id": bo_connection_id,
                "action": action,
                "parameters": parameters or {},
            }
        )

    def handle_progress(self, payload: dict) -> None:
        """Εμφανίζει live τα SQL μηνύματα και την πρόοδο του ενεργού rebuild."""

        if payload.get("client_code") != self.client_code:
            return
        if payload.get("request_id") != self.current_request_id:
            return
        if payload.get("action") != self.current_action or self.current_action != "rebuild":
            return

        message = str(payload.get("message") or "").strip()
        if not message or message in self._progress_messages:
            return

        self._progress_messages.add(message)
        current_table = payload.get("current_table")
        total_tables = payload.get("total_tables")

        if (
            type(current_table) is int
            and type(total_tables) is int
            and total_tables > 0
        ):
            self.progress_bar.set(min(current_table / total_tables, 1.0))
            self._set_status(
                f"Rebuild running: table {current_table} of {total_tables}",
                COLORS.accent,
            )
        else:
            self._set_status("Rebuild running...", COLORS.accent)

        self._append_output(f"\n- {message}")

    def request_clean_mydata(self) -> None:
        """Επιβεβαιώνει και ζητά καθαρισμό μη επιτυχημένων MyData responses."""

        start_date = self.clean_from_entry.get().strip()
        end_date = self.clean_to_entry.get().strip()
        if not self._valid_date(start_date) or not self._valid_date(end_date):
            self._set_status(
                "Both cleanup dates must be valid YYYYMMDD values.", COLORS.danger
            )
            return
        if start_date > end_date:
            self._set_status(
                "The From date cannot be after the To date.", COLORS.danger
            )
            return
        if not self._confirm(
            "Confirm MyData Cleanup",
            "This will permanently delete non-Success MyData responses.\n\n"
            f"Database: {self.bo_option.get()}\nRange: {start_date} - {end_date}\n\nContinue?",
        ):
            return
        self.request_action(
            "clean_mydata",
            {"start_date": start_date, "end_date": end_date},
        )

    def request_history(self) -> None:
        """Επιβεβαιώνει και ζητά μεταφορά SalesTrans στο ιστορικό."""

        history_date = self.history_date_entry.get().strip()
        if not self._valid_date(history_date):
            self._set_status(
                "History date must be a valid YYYYMMDD value.", COLORS.danger
            )
            return
        if not self._confirm(
            "Confirm Sales History",
            "SnProPOS_SalesTrHist will run on the selected database.\n\n"
            f"Database: {self.bo_option.get()}\nDate: {history_date}\n\nContinue?",
        ):
            return
        self.request_action("history", {"history_date": history_date})

    def request_shrink(self) -> None:
        """Επιβεβαιώνει και ζητά shrink της επιλεγμένης βάσης."""

        if self._confirm(
            "Confirm Database Shrink",
            "Run this operation only outside working hours and after verifying a backup.\n\n"
            f"Database: {self.bo_option.get()}\n"
            "Targets: data file 5000 MB, log file 1000 MB.\n\nContinue?",
        ):
            self.request_action("shrink")

    def request_rebuild(self) -> None:
        """Επιβεβαιώνει και ζητά εκτέλεση της spsnrebuildupdate."""

        if self._confirm(
            "Confirm Database Rebuild",
            "spsnrebuildupdate may run for a long time. Use only outside working hours "
            "and after verifying a backup.\n\n"
            f"Database: {self.bo_option.get()}\n\nContinue?",
        ):
            self.request_action("rebuild")

    def handle_result(self, payload: dict) -> None:
        """Εμφανίζει μόνο το αποτέλεσμα της τρέχουσας ενέργειας του συγκεκριμένου client."""

        if payload.get("client_code") != self.client_code:
            return
        if payload.get("request_id") != self.current_request_id:
            return
        if payload.get("action") != self.current_action:
            return

        action = self.current_action
        self.current_request_id = ""
        self.current_action = ""
        self._set_busy(False)

        if not payload.get("success"):
            self.progress_bar.grid_remove()
            self._set_status("Database action failed.", COLORS.danger)
            self._set_output(
                f"Action: {self.ACTION_TITLES.get(action, action)}\n"
                f"Error: {payload.get('error') or 'Unknown error.'}"
            )
            return

        self._set_status(
            f"Completed on database: {payload.get('database_name') or '-'}",
            COLORS.success,
        )
        if action == "rebuild":
            self.progress_bar.set(1)
        else:
            self.progress_bar.grid_remove()
        self._set_output(self._format_result(payload))

        if action == "mydata_info":
            first_date = str(payload.get("first_date") or "")[:10].replace("-", "")
            if self._valid_date(first_date):
                self.clean_from_entry.delete(0, "end")
                self.clean_from_entry.insert(0, first_date)

    def _format_result(self, payload: dict) -> str:
        """Μετατρέπει το αποτέλεσμα της ενέργειας σε ευανάγνωστη αναφορά."""

        action = str(payload.get("action") or "")
        lines = [
            f"Action: {self.ACTION_TITLES.get(action, action)}",
            f"Database: {payload.get('database_name') or '-'}",
            f"Elapsed: {payload.get('elapsed_ms')} ms",
            f"Message: {payload.get('message') or 'Completed.'}",
        ]

        fields_by_action = {
            "test_connection": (
                ("Server", "server_name"),
                ("Login", "login_name"),
                ("Driver", "driver"),
            ),
            "sales_trans_info": (
                ("First date", "first_date"),
                ("Total rows", "total_rows"),
            ),
            "mydata_info": (
                ("First failed date", "first_date"),
                ("Failed rows", "failed_rows"),
            ),
            "clean_mydata": (
                ("From", "start_date"),
                ("To", "end_date"),
                ("Deleted rows", "deleted_rows"),
            ),
            "history": (
                ("History date", "history_date"),
                ("Completion message detected", "completion_detected"),
            ),
            "shrink": (
                ("Data file", "data_file"),
                ("Data target", "data_target_mb"),
                ("Log file", "log_file"),
                ("Log target", "log_target_mb"),
            ),
        }
        for label, key in fields_by_action.get(action, ()):
            value = payload.get(key)
            suffix = " MB" if key in {"data_target_mb", "log_target_mb"} else ""
            lines.append(
                f"{label}: {value if value not in (None, '') else '-'}{suffix}"
            )

        sql_messages = payload.get("sql_messages") or []
        if sql_messages:
            lines.extend(("", "SQL messages:"))
            lines.extend(f"- {message}" for message in sql_messages)
        return "\n".join(lines)

    def _set_busy(self, busy: bool) -> None:
        """Απενεργοποιεί όλες τις ενέργειες όσο εκτελείται εργασία βάσης."""

        state = "disabled" if busy else "normal"
        for button in self.action_buttons:
            button.configure(state=state)
        self.bo_option.configure(state=state)

    def _set_status(self, text: str, color: str) -> None:
        """Ενημερώνει τη γραμμή κατάστασης."""

        self.status_label.configure(text=text, text_color=color)

    def _set_output(self, text: str) -> None:
        """Ενημερώνει το read-only πλαίσιο αποτελεσμάτων."""

        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.insert("1.0", text)
        self.output_box.configure(state="disabled")

    def _append_output(self, text: str) -> None:
        """Προσθέτει live μήνυμα και μετακινεί την προβολή στην τελευταία γραμμή."""

        self.output_box.configure(state="normal")
        self.output_box.insert("end", text)
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    @staticmethod
    def _valid_date(value: str) -> bool:
        """Ελέγχει πραγματική ημερομηνία σε αυστηρή μορφή YYYYMMDD."""

        try:
            parsed = date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:8]}")
            return parsed.strftime("%Y%m%d") == value
        except (TypeError, ValueError):
            return False

    def _confirm(self, title: str, message: str) -> bool:
        """Ζητά ρητή επιβεβαίωση πριν από λειτουργία που αλλάζει δεδομένα."""

        owner = self.winfo_toplevel()
        result = messagebox.askyesno(
            title,
            message,
            icon="warning",
            parent=owner,
        )
        owner.after_idle(owner.focus_force)
        return bool(result)

    def _bind_shortcuts(self) -> None:
        """Συνδέει keyboard shortcuts που ενεργοποιούνται μόνο όταν φαίνεται το tab."""

        shortcuts = (
            ("<F5>", self.refresh_bo_values),
            ("<Control-t>", lambda: self.request_action("test_connection")),
            ("<Control-Key-1>", lambda: self.request_action("sales_trans_info")),
            ("<Control-Key-2>", lambda: self.request_action("mydata_info")),
            ("<Control-Key-3>", self.request_clean_mydata),
            ("<Control-Key-4>", self.request_history),
            ("<Control-Key-5>", self.request_shrink),
            ("<Control-Key-6>", self.request_rebuild),
        )
        for key, callback in shortcuts:
            binding_id = self._shortcut_parent.bind(
                key,
                lambda _event, action=callback: self._visible_shortcut(action),
                add="+",
            )
            self._shortcut_bindings.append((key, binding_id))

    def _visible_shortcut(self, callback: Callable[[], None]) -> str | None:
        """Εκτελεί shortcut μόνο όταν το Database tab είναι ορατό."""

        if self.winfo_viewable():
            callback()
            return "break"
        return None

    def destroy(self) -> None:
        """Αφαιρεί τα global bindings όταν κλείνει το Manage window."""

        for key, binding_id in self._shortcut_bindings:
            if binding_id:
                self._shortcut_parent.unbind(key, binding_id)
        self._shortcut_bindings.clear()
        super().destroy()
