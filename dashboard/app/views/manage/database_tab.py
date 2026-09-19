import uuid
from collections.abc import Callable
from datetime import date, datetime
from tkinter import messagebox
from typing import ClassVar

import customtkinter as ctk

from app.views.manage.backup_window import BackupManagerWindow
from app.ui.theme import (
    COLORS,
    FONTS,
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
        on_backup_request_callback: Callable[[dict], bool | None] | None = None,
    ) -> None:
        """Αρχικοποιεί το tab και το συνδέει με το κοινό BOConnection state."""

        super().__init__(parent, corner_radius=0, fg_color="transparent")
        self.client_code = client_code
        self.get_bo_values_callback = get_bo_values_callback
        self.get_selected_bo_id_callback = get_selected_bo_id_callback
        self.on_bo_selected_callback = on_bo_selected_callback
        self.on_database_request_callback = on_database_request_callback
        self.on_backup_request_callback = on_backup_request_callback
        self.backup_window: BackupManagerWindow | None = None
        self.current_request_id = ""
        self.current_action = ""
        self._progress_messages: set[str] = set()
        self.action_buttons: list[ctk.CTkButton] = []
        self._shortcut_bindings: list[tuple[str, str | None]] = []
        self._shortcut_parent = self.winfo_toplevel()
        self._layout_job: str | None = None
        self._wide_layout: bool | None = None
        self._description_labels: list[ctk.CTkLabel] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ui()
        self.bind("<Configure>", self._schedule_layout, add="+")
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        """Δημιουργεί responsive διάταξη συμβατή με το theme του dashboard."""

        header = ctk.CTkFrame(self, **card_style())
        header.grid(
            row=0,
            column=0,
            padx=16,
            pady=(12, 10),
            sticky="ew",
        )
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Database",
            font=FONTS.title,
            text_color=COLORS.text_primary,
            anchor="w",
        ).grid(row=0, column=0, padx=20, pady=(14, 0), sticky="ew")

        self.selection_badge = ctk.CTkLabel(
            header,
            text="No database",
            font=FONTS.small,
            text_color=COLORS.warning,
            fg_color=COLORS.warning_soft,
            corner_radius=8,
            height=28,
        )
        self.selection_badge.grid(row=0, column=1, padx=20, pady=(14, 0), sticky="e")

        ctk.CTkLabel(
            header,
            text="Controlled information, cleanup, maintenance and backup operations",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, padx=20, pady=(2, 10), sticky="ew")

        toolbar = ctk.CTkFrame(header, fg_color="transparent")
        toolbar.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 16), sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)

        self.bo_option = ctk.CTkOptionMenu(
            toolbar,
            values=["No BOConnections"],
            command=self._on_bo_selected,
            width=320,
            height=34,
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.bo_option.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        refresh_button = ctk.CTkButton(
            toolbar,
            text="Refresh  ·  F5",
            width=130,
            height=34,
            command=self.refresh_bo_values,
            **secondary_button_style(),
        )
        refresh_button.grid(row=0, column=1, padx=(0, 8))

        test_button = self._action_button(
            toolbar,
            text="Test connection  ·  Ctrl+T",
            command=lambda: self.request_action("test_connection"),
            width=205,
            style="primary",
        )
        test_button.configure(height=34)
        test_button.grid(row=0, column=2)

        self.workspace = ctk.CTkFrame(self, fg_color="transparent")
        self.workspace.grid(row=1, column=0, sticky="nsew")
        self.workspace.grid_rowconfigure(0, weight=1)

        self.operations = ctk.CTkScrollableFrame(
            self.workspace, fg_color="transparent", corner_radius=0)
        self.operations.grid_columnconfigure(0, weight=3)
        self.operations.grid_columnconfigure(1, weight=2)
        self.left_stack = ctk.CTkFrame(self.operations, fg_color="transparent")
        self.right_stack = ctk.CTkFrame(self.operations, fg_color="transparent")
        for stack in (self.left_stack, self.right_stack):
            stack.grid_columnconfigure(0, weight=1)

        self.info_card = self._card(
            self.left_stack,
            "Database information",
            "Read the oldest available date and row totals without changing data.",
        )
        self.info_card.grid(row=0, column=0, pady=(0, 10), sticky="ew")

        sales_button = self._action_button(
            self.info_card,
            text="SalesTrans information  ·  Ctrl+1",
            command=lambda: self.request_action("sales_trans_info"),
        )
        sales_button.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")

        mydata_button = self._action_button(
            self.info_card,
            text="MyData failed responses  ·  Ctrl+2",
            command=lambda: self.request_action("mydata_info"),
        )
        mydata_button.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="ew")

        self.history_card = self._card(
            self.left_stack,
            "Sales history",
            "Run SnProPOS_SalesTrHist using the selected cutoff date.",
        )
        self.history_card.grid(row=1, column=0, pady=(0, 10), sticky="ew")
        self.history_date_entry = self._date_field(
            self.history_card, "Cutoff date  ·  YYYYMMDD", 2, 0)
        history_button = self._action_button(
            self.history_card,
            text="Run sales history  ·  Ctrl+4",
            command=self.request_history,
        )
        history_button.grid(row=3, column=0, padx=16, pady=(2, 16), sticky="ew")

        self.backup_card = self._card(
            self.left_stack,
            "Database backup",
            "Create verified backups and manage daily, weekly or monthly schedules.",
        )
        self.backup_card.grid(row=2, column=0, pady=(0, 10), sticky="ew")
        backup_button = ctk.CTkButton(
            self.backup_card,
            text="Open Backup Manager  ·  Ctrl+7",
            command=self.open_backup_manager,
            height=36,
            **primary_button_style(),
        )
        backup_button.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")

        self.cleanup_card = self._card(
            self.right_stack,
            "MyData cleanup",
            "Delete only responses whose status is not Success within the selected range.",
        )
        self.cleanup_card.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        self.cleanup_card.grid_columnconfigure(0, weight=1)
        self.cleanup_card.grid_columnconfigure(1, weight=1)

        self.clean_from_entry = self._date_field(self.cleanup_card, "From  ·  YYYYMMDD", 2, 0)
        self.clean_to_entry = self._date_field(self.cleanup_card, "To  ·  YYYYMMDD", 2, 1)
        self.clean_to_entry.insert(0, datetime.now().astimezone().strftime("%Y%m%d"))

        self.clean_button = self._action_button(
            self.cleanup_card,
            text="Delete failed responses  ·  Ctrl+3",
            command=self.request_clean_mydata,
            style="danger",
        )
        self.clean_button.grid(
            row=4, column=0, columnspan=2, padx=16, pady=(2, 16), sticky="ew"
        )

        self.maintenance_card = self._card(
            self.right_stack,
            "Database maintenance",
            "Long-running operations. Use only outside working hours and after verifying a backup.",
            warning=True,
        )
        self.maintenance_card.grid(row=1, column=0, pady=(0, 10), sticky="ew")

        self.shrink_button = self._action_button(
            self.maintenance_card,
            text="Shrink database files  ·  Ctrl+5",
            command=self.request_shrink,
            style="danger",
        )
        self.shrink_button.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.rebuild_button = self._action_button(
            self.maintenance_card,
            text="Rebuild / Update database  ·  Ctrl+6",
            command=self.request_rebuild,
            style="danger",
        )
        self.rebuild_button.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="ew")

        ctk.CTkLabel(
            self.operations,
            text="F5 Refresh  ·  Ctrl+T Test  ·  Ctrl+1…7 Actions  ·  Ctrl+Shift+C Copy activity",
            font=FONTS.small,
            text_color=COLORS.text_muted,
            anchor="w",
        ).grid(row=2, column=0, columnspan=2, padx=8, pady=(2, 8), sticky="ew")

        self.output_card = ctk.CTkFrame(self.workspace, **card_style())
        self.output_card.grid_columnconfigure(0, weight=1)
        self.output_card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self.output_card,
            text="Activity",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=(18, 8), pady=(16, 4), sticky="w")

        activity_actions = ctk.CTkFrame(self.output_card, fg_color="transparent")
        activity_actions.grid(row=0, column=1, padx=(0, 14), pady=(12, 4), sticky="e")
        ctk.CTkButton(
            activity_actions,
            text="Copy",
            width=72,
            height=30,
            command=self.copy_output,
            **secondary_button_style(),
        ).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(
            activity_actions,
            text="Clear",
            width=72,
            height=30,
            command=self.clear_output,
            **secondary_button_style(),
        ).grid(row=0, column=1)

        self.status_label = ctk.CTkLabel(
            self.output_card,
            text="Ready",
            font=FONTS.small,
            text_color=COLORS.info,
            fg_color=COLORS.info_soft,
            corner_radius=8,
            height=28,
        )
        self.status_label.grid(row=1, column=0, columnspan=2, padx=16, pady=(2, 10), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(
            self.output_card,
            height=8,
            fg_color=COLORS.surface_light,
            progress_color=COLORS.accent,
        )
        self.progress_bar.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()

        self.output_box = ctk.CTkTextbox(
            self.output_card,
            height=240,
            fg_color=COLORS.background,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
            border_width=1,
            font=FONTS.mono_body,
            wrap="word",
        )
        self.output_box.grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 16), sticky="nsew")
        self._set_output("Select a BOConnection and choose an operation.")

        self.clean_from_entry.bind(
            "<Return>", lambda _event: self.request_clean_mydata()
        )
        self.clean_to_entry.bind("<Return>", lambda _event: self.request_clean_mydata())
        self.history_date_entry.bind("<Return>", lambda _event: self.request_history())
        self.refresh_bo_values()
        self._apply_layout()

    def _card(
        self,
        parent,
        title: str,
        description: str,
        warning: bool = False,
    ) -> ctk.CTkFrame:
        """Δημιουργεί κοινό card λειτουργιών."""

        frame = ctk.CTkFrame(parent, **card_style())
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            frame,
            text=title,
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 3), sticky="w")
        description_label = ctk.CTkLabel(
            frame,
            text=description,
            font=FONTS.small,
            text_color=COLORS.warning if warning else COLORS.text_secondary,
            justify="left",
            anchor="w",
            wraplength=420,
        )
        description_label.grid(
            row=1, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="ew")
        self._description_labels.append(description_label)
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
            height=36,
            command=command,
            **style_values,
        )
        if style == "danger":
            button.configure(
                fg_color=COLORS.danger_soft,
                hover_color=COLORS.danger,
                text_color="#FF8A8A",
                border_width=1,
                border_color=COLORS.danger,
                corner_radius=10,
                font=FONTS.body_bold,
            )
        self.action_buttons.append(button)
        return button

    def _schedule_layout(self, _event=None) -> None:
        """Συγχωνεύει τα διαδοχικά resize events πριν αλλάξει τη διάταξη."""

        if self._layout_job:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(70, self._apply_layout)

    def _apply_layout(self) -> None:
        """Τοποθετεί το Activity δίπλα ή κάτω από τις λειτουργίες."""

        self._layout_job = None
        wide = self.winfo_width() >= 1550
        self.workspace.grid_columnconfigure(0, weight=3 if wide else 1)
        self.workspace.grid_columnconfigure(1, weight=2 if wide else 0)
        self.workspace.grid_rowconfigure(0, weight=1 if wide else 3)
        self.workspace.grid_rowconfigure(1, weight=0 if wide else 2)

        self.operations.grid(
            row=0,
            column=0,
            padx=(16, 8) if wide else 16,
            pady=(0, 16 if wide else 8),
            sticky="nsew",
        )
        self.output_card.grid(
            row=0 if wide else 1,
            column=1 if wide else 0,
            padx=(8, 16) if wide else 16,
            pady=(0, 16),
            sticky="nsew",
        )

        operation_width = self.operations.winfo_width()
        if operation_width <= 100 or self._wide_layout != wide:
            available = max(self.winfo_width() - 48, 320)
            operation_width = available * 0.58 if wide else available
        paired_cards = operation_width >= 900
        self.operations.grid_columnconfigure(0, weight=3 if paired_cards else 1)
        self.operations.grid_columnconfigure(1, weight=2 if paired_cards else 0)
        self.left_stack.grid(
            row=0,
            column=0,
            padx=(4, 7) if paired_cards else 4,
            sticky="new",
        )
        self.right_stack.grid(
            row=0 if paired_cards else 1,
            column=1 if paired_cards else 0,
            padx=(7, 4) if paired_cards else 4,
            sticky="new",
        )

        wrap = int(max(260, operation_width * (0.43 if paired_cards else 0.82)))
        for label in self._description_labels:
            label.configure(wraplength=wrap)
        self._wide_layout = wide

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
        has_connection = bool(values)
        self.selection_badge.configure(
            text="Database selected" if has_connection else "No database",
            text_color=COLORS.success if has_connection else COLORS.warning,
            fg_color=COLORS.success_soft if has_connection else COLORS.warning_soft,
        )

    def _on_bo_selected(self, selected_value: str) -> None:
        """Συγχρονίζει την επιλογή βάσης με τα υπόλοιπα tabs."""

        if self.on_bo_selected_callback:
            self.on_bo_selected_callback(selected_value)
        self.selection_badge.configure(
            text="Database selected",
            text_color=COLORS.success,
            fg_color=COLORS.success_soft,
        )

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

    def open_backup_manager(self) -> None:
        """Ανοίγει ή επαναφέρει το Backup Manager πάνω από το ενεργό Manage window."""

        if self.backup_window and self.backup_window.winfo_exists():
            self.backup_window.lift()
            self.backup_window.focus_force()
            return
        owner = self.winfo_toplevel()
        self.backup_window = BackupManagerWindow(
            parent=owner,
            client_code=self.client_code,
            get_bo_values_callback=self.get_bo_values_callback,
            get_selected_bo_id_callback=self.get_selected_bo_id_callback,
            on_request_callback=self.on_backup_request_callback,
        )

    def handle_backup_result(self, payload: dict) -> None:
        """Προωθεί backup result στο ανοιχτό Backup Manager."""

        if self.backup_window and self.backup_window.winfo_exists():
            self.backup_window.handle_result(payload)

    def handle_backup_progress(self, payload: dict) -> None:
        """Προωθεί live backup progress στο ανοιχτό Backup Manager."""

        if self.backup_window and self.backup_window.winfo_exists():
            self.backup_window.handle_progress(payload)

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

        soft_color = {
            COLORS.success: COLORS.success_soft,
            COLORS.warning: COLORS.warning_soft,
            COLORS.danger: COLORS.danger_soft,
            COLORS.accent: COLORS.accent_soft,
            COLORS.info: COLORS.info_soft,
        }.get(color, COLORS.surface_light)
        self.status_label.configure(text=text, text_color=color, fg_color=soft_color)

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

    def copy_output(self) -> None:
        """Αντιγράφει την ορατή αναφορά δραστηριότητας στο clipboard."""

        text = self.output_box.get("1.0", "end-1c").strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)

    def clear_output(self) -> None:
        """Καθαρίζει μόνο την προβολή, χωρίς να επηρεάζει ενεργό αίτημα."""

        self._set_output("No activity to display.")
        if not self.current_request_id:
            self._set_status("Ready", COLORS.info)

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
            ("<Control-Key-7>", self.open_backup_manager),
            ("<Control-Shift-C>", self.copy_output),
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

        if self._layout_job:
            self.after_cancel(self._layout_job)
            self._layout_job = None
        if self.backup_window and self.backup_window.winfo_exists():
            self.backup_window.destroy()
        for key, binding_id in self._shortcut_bindings:
            if binding_id:
                self._shortcut_parent.unbind(key, binding_id)
        self._shortcut_bindings.clear()
        super().destroy()
