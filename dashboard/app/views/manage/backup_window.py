import uuid
from collections.abc import Callable
from tkinter import TclError, messagebox
from typing import Any, ClassVar

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


class BackupDestinationForm(ctk.CTkFrame):
    """Επαναχρησιμοποιήσιμη φόρμα προορισμού και retention backup."""

    DESTINATION_LABELS: ClassVar[dict[str, str]] = {
        "Local folder": "local",
        "UNC network share": "unc",
        "Cloud via rclone": "cloud",
    }
    RETENTION_LABELS: ClassVar[dict[str, str]] = {
        "Replace previous backup": "replace",
        "Keep all backups": "keep_all",
        "Keep last N backups": "keep_last",
    }

    def __init__(self, parent) -> None:
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.compression_var = ctk.BooleanVar(value=True)
        self.copy_only_var = ctk.BooleanVar(value=True)
        self._build()

    def _build(self) -> None:
        self.destination_type = self._option(
            "Destination type",
            list(self.DESTINATION_LABELS),
            row=0,
            column=0,
            command=lambda _value: self._refresh_states(),
        )
        self.retention_mode = self._option(
            "Retention",
            list(self.RETENTION_LABELS),
            row=0,
            column=1,
            command=lambda _value: self._refresh_states(),
        )
        self.destination_path = self._entry(
            "Backup folder (SQL Server-visible path)", row=2, column=0, columnspan=2
        )
        self.destination_path.insert(0, r"C:\MoonHardBackups")
        self.staging_path = self._entry(
            "Cloud staging folder (SQL Server and client-visible)",
            row=4,
            column=0,
            columnspan=2,
        )
        self.staging_path.insert(0, r"C:\ProgramData\MoonHardRemoteV2\backups\staging")
        self.cloud_remote = self._entry(
            "rclone destination (example: mega:MoonHardBackups)",
            row=6,
            column=0,
            columnspan=2,
        )
        self.retention_count = self._entry("Number of backups to keep", row=8, column=0)
        self.retention_count.insert(0, "7")

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=8, column=1, padx=8, pady=(0, 10), sticky="nsew")
        ctk.CTkCheckBox(
            options,
            text="Compression",
            variable=self.compression_var,
            fg_color=COLORS.accent,
            hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            font=FONTS.body,
        ).pack(anchor="w", pady=(17, 5))
        ctk.CTkCheckBox(
            options,
            text="COPY_ONLY",
            variable=self.copy_only_var,
            fg_color=COLORS.accent,
            hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            font=FONTS.body,
        ).pack(anchor="w", pady=5)
        self._refresh_states()

    def _entry(
        self, label: str, row: int, column: int, columnspan: int = 1
    ) -> ctk.CTkEntry:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            padx=8,
            pady=(0, 10),
            sticky="ew",
        )
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame,
            text=label,
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        ).grid(row=0, column=0, pady=(0, 4), sticky="w")
        entry = ctk.CTkEntry(
            frame,
            fg_color=COLORS.surface_light,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
        )
        entry.grid(row=1, column=0, sticky="ew")
        return entry

    def _option(
        self,
        label: str,
        values: list[str],
        row: int,
        column: int,
        command: Callable[[str], None],
    ) -> ctk.CTkOptionMenu:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=column, padx=8, pady=(0, 10), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame,
            text=label,
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        ).grid(row=0, column=0, pady=(0, 4), sticky="w")
        option = ctk.CTkOptionMenu(
            frame,
            values=values,
            command=command,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        option.grid(row=1, column=0, sticky="ew")
        return option

    def _refresh_states(self) -> None:
        destination = self.DESTINATION_LABELS.get(self.destination_type.get(), "local")
        cloud_state = "normal" if destination == "cloud" else "disabled"
        disk_state = "disabled" if destination == "cloud" else "normal"
        self.destination_path.configure(state=disk_state)
        self.staging_path.configure(state=cloud_state)
        self.cloud_remote.configure(state=cloud_state)
        retention = self.RETENTION_LABELS.get(self.retention_mode.get(), "keep_last")
        self.retention_count.configure(
            state="normal" if retention == "keep_last" else "disabled"
        )

    def get_settings(self) -> dict[str, Any]:
        """Συλλέγει τις τιμές της φόρμας στο αυστηρό protocol schema."""

        try:
            retention_count = int(self.retention_count.get().strip() or "7")
        except ValueError as exc:
            raise ValueError("Retention count must be a whole number.") from exc
        if not 1 <= retention_count <= 365:
            raise ValueError("Retention count must be between 1 and 365.")
        destination_type = self.DESTINATION_LABELS[self.destination_type.get()]
        settings = {
            "destination_type": destination_type,
            "destination_path": self.destination_path.get().strip(),
            "staging_path": self.staging_path.get().strip(),
            "cloud_remote": self.cloud_remote.get().strip(),
            "retention_mode": self.RETENTION_LABELS[self.retention_mode.get()],
            "retention_count": retention_count,
            "compression": bool(self.compression_var.get()),
            "copy_only": bool(self.copy_only_var.get()),
        }
        required_path = (
            settings["staging_path"]
            if destination_type == "cloud"
            else settings["destination_path"]
        )
        if not required_path:
            raise ValueError("A backup or staging folder is required.")
        if destination_type == "cloud" and not settings["cloud_remote"]:
            raise ValueError("An rclone cloud destination is required.")
        return settings

    def set_settings(self, settings: dict[str, Any]) -> None:
        """Φορτώνει υπάρχουσες ρυθμίσεις schedule στη φόρμα."""

        destination_value = next(
            (
                label
                for label, value in self.DESTINATION_LABELS.items()
                if value == settings.get("destination_type")
            ),
            "Local folder",
        )
        retention_value = next(
            (
                label
                for label, value in self.RETENTION_LABELS.items()
                if value == settings.get("retention_mode")
            ),
            "Keep last N backups",
        )
        self.destination_type.set(destination_value)
        self.retention_mode.set(retention_value)
        for entry, key, default in (
            (self.destination_path, "destination_path", r"C:\MoonHardBackups"),
            (
                self.staging_path,
                "staging_path",
                r"C:\ProgramData\MoonHardRemoteV2\backups\staging",
            ),
            (self.cloud_remote, "cloud_remote", ""),
            (self.retention_count, "retention_count", "7"),
        ):
            entry.configure(state="normal")
            entry.delete(0, "end")
            entry.insert(0, str(settings.get(key, default)))
        self.compression_var.set(bool(settings.get("compression", True)))
        self.copy_only_var.set(bool(settings.get("copy_only", True)))
        self._refresh_states()


class BackupManagerWindow(ctk.CTkToplevel):
    """Παράθυρο manual backup, schedules, cloud remotes και ιστορικού."""

    WEEKDAYS: ClassVar[list[str]] = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    FREQUENCIES: ClassVar[dict[str, str]] = {
        "Daily": "daily",
        "Weekly": "weekly",
        "Monthly": "monthly",
    }

    def __init__(
        self,
        parent,
        client_code: str,
        get_bo_values_callback: Callable[[], list[str]],
        get_selected_bo_id_callback: Callable[[], int],
        on_request_callback: Callable[[dict[str, Any]], bool | None] | None,
    ) -> None:
        super().__init__(parent)
        self.client_code = client_code
        self.get_bo_values_callback = get_bo_values_callback
        self.get_selected_bo_id_callback = get_selected_bo_id_callback
        self.on_request_callback = on_request_callback
        self.pending: dict[str, str] = {}
        self.acknowledged_requests: set[str] = set()
        self.ack_timeout_jobs: dict[str, str] = {}
        self.schedules: dict[str, dict[str, Any]] = {}
        self.schedule_labels: dict[str, str] = {}
        self.selected_schedule_id = ""

        self.title("Database Backup & Scheduling")
        self.geometry("1080x790")
        self.minsize(960, 700)
        # Κανονικό ανεξάρτητο παράθυρο ώστε τα Windows να εμφανίζουν
        # minimize/maximize και να επιτρέπεται πλήρης αλλαγή μεγέθους.
        self.resizable(True, True)
        self.configure(fg_color=COLORS.background)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._close_window)
        self.after(100, self._bring_to_front)
        self.after(200, self.refresh_data)

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, **card_style())
        header.grid(
            row=0,
            column=0,
            padx=SPACING.window_padding,
            pady=SPACING.window_padding,
            sticky="ew",
        )
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text="Database Backup & Scheduling",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, columnspan=4, padx=18, pady=(14, 6), sticky="w")
        ctk.CTkLabel(
            header,
            text="BOConnection:",
            font=FONTS.body_bold,
            text_color=COLORS.text_primary,
        ).grid(row=1, column=0, padx=(18, 8), pady=(0, 14), sticky="w")
        values = self.get_bo_values_callback() or ["No BOConnections"]
        selected_id = self.get_selected_bo_id_callback()
        selected = next(
            (value for value in values if value.startswith(f"ID {selected_id} ")),
            values[0],
        )
        self.bo_option = ctk.CTkOptionMenu(
            header,
            values=values,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
            width=300,
        )
        self.bo_option.grid(row=1, column=1, padx=(0, 10), pady=(0, 14), sticky="w")
        self.bo_option.set(selected)
        ctk.CTkButton(
            header,
            text="Refresh  [Ctrl+R]",
            command=self.refresh_data,
            width=130,
            **secondary_button_style(),
        ).grid(row=1, column=2, padx=6, pady=(0, 14))
        self.status_label = ctk.CTkLabel(
            header,
            text="Ready",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
        )
        self.status_label.grid(row=1, column=3, padx=(10, 18), pady=(0, 14), sticky="e")

        self.tabs = ctk.CTkTabview(
            self,
            fg_color=COLORS.surface,
            segmented_button_fg_color=COLORS.surface_light,
            segmented_button_selected_color=COLORS.accent,
            segmented_button_selected_hover_color=COLORS.accent_hover,
            segmented_button_unselected_color=COLORS.surface_light,
            segmented_button_unselected_hover_color=COLORS.surface_hover,
            text_color=COLORS.text_primary,
        )
        self.tabs.grid(
            row=1,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, SPACING.window_padding),
            sticky="nsew",
        )
        self.now_tab = self.tabs.add("Backup Now")
        self.schedule_tab = self.tabs.add("Schedules")
        self.history_tab = self.tabs.add("History")
        for tab in (self.now_tab, self.schedule_tab, self.history_tab):
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)
        self._build_now_tab()
        self._build_schedule_tab()
        self._build_history_tab()

    def _build_now_tab(self) -> None:
        content = ctk.CTkScrollableFrame(self.now_tab, fg_color="transparent")
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        card = ctk.CTkFrame(content, **card_style())
        card.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text="Create verified full backup",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")
        ctk.CTkLabel(
            card,
            text=(
                "SQL Server writes the .bak file. Cloud mode verifies it locally before upload. "
                "The last valid backup is preserved until replacement succeeds."
            ),
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            wraplength=920,
            justify="left",
        ).grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")
        self.manual_form = BackupDestinationForm(card)
        self.manual_form.grid(row=2, column=0, padx=8, pady=4, sticky="ew")
        ctk.CTkButton(
            card,
            text="Start Backup  [Ctrl+B]",
            command=self.run_manual_backup,
            height=38,
            **primary_button_style(),
        ).grid(row=3, column=0, padx=16, pady=(4, 16), sticky="ew")

        activity = ctk.CTkFrame(content, **card_style())
        activity.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        activity.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            activity,
            text="Backup Activity",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")
        self.progress_bar = ctk.CTkProgressBar(
            activity,
            height=9,
            fg_color=COLORS.surface_light,
            progress_color=COLORS.accent,
        )
        self.progress_bar.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress_bar.set(0)
        self.activity_box = ctk.CTkTextbox(
            activity,
            height=145,
            fg_color=COLORS.background,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
            border_width=1,
            font=FONTS.mono_body,
            wrap="word",
        )
        self.activity_box.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        self._set_activity("Ready. Configure a destination and start the backup.")

    def _build_schedule_tab(self) -> None:
        content = ctk.CTkScrollableFrame(self.schedule_tab, fg_color="transparent")
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)

        select_card = ctk.CTkFrame(content, **card_style())
        select_card.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        select_card.grid_columnconfigure(0, weight=1)
        self.schedule_option = ctk.CTkOptionMenu(
            select_card,
            values=["New schedule"],
            command=self._select_schedule,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.schedule_option.grid(row=0, column=0, padx=16, pady=14, sticky="ew")
        ctk.CTkButton(
            select_card,
            text="New",
            command=self.new_schedule,
            width=90,
            **secondary_button_style(),
        ).grid(row=0, column=1, padx=(0, 8), pady=14)
        ctk.CTkButton(
            select_card,
            text="Run selected",
            command=self.run_selected_schedule,
            width=125,
            **secondary_button_style(),
        ).grid(row=0, column=2, padx=(0, 8), pady=14)
        ctk.CTkButton(
            select_card,
            text="Delete",
            command=self.delete_selected_schedule,
            width=90,
            **danger_button_style(),
        ).grid(row=0, column=3, padx=(0, 16), pady=14)

        editor = ctk.CTkFrame(content, **card_style())
        editor.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        editor.grid_columnconfigure(0, weight=1)
        editor.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            editor,
            text="Schedule settings",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 6), sticky="w")
        self.schedule_name = self._editor_entry(editor, "Name", 1, 0)
        self.schedule_time = self._editor_entry(editor, "Time (HH:MM)", 1, 1)
        self.schedule_time.insert(0, "02:00")
        self.frequency_option = self._editor_option(
            editor,
            "Frequency",
            list(self.FREQUENCIES),
            3,
            0,
            lambda _value: self._refresh_schedule_states(),
        )
        self.weekday_option = self._editor_option(
            editor, "Weekday", self.WEEKDAYS, 3, 1, lambda _value: None
        )
        self.day_of_month = self._editor_entry(editor, "Day of month (1-31)", 5, 0)
        self.day_of_month.insert(0, "1")
        enabled_frame = ctk.CTkFrame(editor, fg_color="transparent")
        enabled_frame.grid(row=5, column=1, padx=16, pady=(0, 10), sticky="ew")
        self.enabled_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            enabled_frame,
            text="Schedule enabled",
            variable=self.enabled_var,
            fg_color=COLORS.accent,
            hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            font=FONTS.body,
        ).pack(anchor="w", pady=(20, 8))
        self.schedule_form = BackupDestinationForm(editor)
        self.schedule_form.grid(
            row=7, column=0, columnspan=2, padx=8, pady=(2, 4), sticky="ew"
        )
        ctk.CTkButton(
            editor,
            text="Save Schedule  [Ctrl+S]",
            command=self.save_schedule,
            height=38,
            **primary_button_style(),
        ).grid(row=8, column=0, columnspan=2, padx=16, pady=(4, 16), sticky="ew")
        self._refresh_schedule_states()

    def _build_history_tab(self) -> None:
        card = ctk.CTkFrame(self.history_tab, **card_style())
        card.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(
            card,
            text="Backup History",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")
        ctk.CTkButton(
            card,
            text="Retry Pending Cloud Uploads",
            command=self.retry_pending,
            width=240,
            **secondary_button_style(),
        ).grid(row=0, column=1, padx=16, pady=(14, 6), sticky="e")
        self.cloud_hint = ctk.CTkLabel(
            card,
            text="Configured cloud remotes: not loaded",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        )
        self.cloud_hint.grid(
            row=1, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="w"
        )
        self.history_box = ctk.CTkTextbox(
            card,
            fg_color=COLORS.background,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
            border_width=1,
            font=FONTS.mono_body,
            wrap="word",
        )
        self.history_box.grid(
            row=2, column=0, columnspan=2, padx=16, pady=(0, 16), sticky="nsew"
        )
        self._set_history("No backup history loaded.")

    def _editor_entry(self, parent, label: str, row: int, column: int) -> ctk.CTkEntry:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=column, padx=16, pady=(0, 10), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame, text=label, font=FONTS.small, text_color=COLORS.text_secondary
        ).grid(row=0, column=0, pady=(0, 4), sticky="w")
        entry = ctk.CTkEntry(
            frame,
            fg_color=COLORS.surface_light,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
        )
        entry.grid(row=1, column=0, sticky="ew")
        return entry

    def _editor_option(
        self,
        parent,
        label: str,
        values: list[str],
        row: int,
        column: int,
        command: Callable[[str], None],
    ) -> ctk.CTkOptionMenu:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=column, padx=16, pady=(0, 10), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame, text=label, font=FONTS.small, text_color=COLORS.text_secondary
        ).grid(row=0, column=0, pady=(0, 4), sticky="w")
        option = ctk.CTkOptionMenu(
            frame,
            values=values,
            command=command,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        option.grid(row=1, column=0, sticky="ew")
        return option

    def refresh_data(self) -> None:
        self._request("list", parameters={})
        self._request("list_cloud_remotes", parameters={})

    def run_manual_backup(self) -> None:
        try:
            settings = self.manual_form.get_settings()
            bo_connection_id = self._selected_bo_id()
        except ValueError as exc:
            self._set_status(str(exc), COLORS.danger)
            return
        if not messagebox.askyesno(
            "Confirm Database Backup",
            "A full verified backup will be created.\n\n"
            f"Database: {self.bo_option.get()}\n"
            f"Destination: {settings['cloud_remote'] if settings['destination_type'] == 'cloud' else settings['destination_path']}\n"
            f"Retention: {settings['retention_mode']}\n\nContinue?",
            parent=self,
        ):
            return
        self.tabs.set("Backup Now")
        self.progress_bar.set(0)
        self._set_activity("Backup request sent to the remote client...")
        self._request(
            "run",
            bo_connection_id=bo_connection_id,
            parameters={"settings": settings},
        )

    def save_schedule(self) -> None:
        try:
            schedule = self._schedule_payload()
        except ValueError as exc:
            self._set_status(str(exc), COLORS.danger)
            return
        self._request("save_schedule", parameters={"schedule": schedule})

    def delete_selected_schedule(self) -> None:
        if not self.selected_schedule_id:
            self._set_status("Select a saved schedule first.", COLORS.warning)
            return
        if not messagebox.askyesno(
            "Delete Backup Schedule",
            "Delete the selected schedule? Existing backup files will not be removed.",
            parent=self,
        ):
            return
        self._request(
            "delete_schedule",
            parameters={"schedule_id": self.selected_schedule_id},
        )

    def run_selected_schedule(self) -> None:
        if not self.selected_schedule_id:
            self._set_status("Select a saved schedule first.", COLORS.warning)
            return
        if not messagebox.askyesno(
            "Run Backup Schedule Now",
            "Run the selected schedule immediately without changing its next automatic run?",
            parent=self,
        ):
            return
        self.tabs.set("Backup Now")
        self.progress_bar.set(0)
        self._set_activity("Scheduled configuration started manually...")
        self._request(
            "run_schedule",
            parameters={"schedule_id": self.selected_schedule_id},
            bo_connection_id=int(
                self.schedules[self.selected_schedule_id].get("bo_connection_id", 1)
            ),
        )

    def retry_pending(self) -> None:
        self.tabs.set("Backup Now")
        self.progress_bar.set(0)
        self._set_activity("Retrying verified cloud staging files...")
        self._request("retry_pending", parameters={})

    def new_schedule(self) -> None:
        self.selected_schedule_id = ""
        self.schedule_option.set("New schedule")
        self.schedule_name.delete(0, "end")
        self.schedule_time.delete(0, "end")
        self.schedule_time.insert(0, "02:00")
        self.frequency_option.set("Daily")
        self.weekday_option.set("Monday")
        self.day_of_month.configure(state="normal")
        self.day_of_month.delete(0, "end")
        self.day_of_month.insert(0, "1")
        self.enabled_var.set(True)
        self.schedule_form.set_settings({})
        self._refresh_schedule_states()

    def _schedule_payload(self) -> dict[str, Any]:
        name = self.schedule_name.get().strip()
        if not name:
            raise ValueError("Schedule name is required.")
        run_time = self.schedule_time.get().strip()
        if len(run_time) != 5 or run_time[2] != ":":
            raise ValueError("Schedule time must use HH:MM.")
        try:
            hour, minute = (int(part) for part in run_time.split(":"))
            day_of_month = int(self.day_of_month.get().strip() or "1")
        except ValueError as exc:
            raise ValueError("Schedule time/day contains an invalid number.") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Schedule time must be a valid 24-hour time.")
        if not 1 <= day_of_month <= 31:
            raise ValueError("Day of month must be between 1 and 31.")
        return {
            "schedule_id": self.selected_schedule_id,
            "name": name,
            "bo_connection_id": self._selected_bo_id(),
            "frequency": self.FREQUENCIES[self.frequency_option.get()],
            "time": run_time,
            "weekday": self.WEEKDAYS.index(self.weekday_option.get()),
            "day_of_month": day_of_month,
            "enabled": bool(self.enabled_var.get()),
            "settings": self.schedule_form.get_settings(),
        }

    def _select_schedule(self, label: str) -> None:
        schedule_id = self.schedule_labels.get(label, "")
        if not schedule_id:
            self.new_schedule()
            return
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            return
        self.selected_schedule_id = schedule_id
        self._replace_entry(self.schedule_name, schedule.get("name", ""))
        self._replace_entry(self.schedule_time, schedule.get("time", "02:00"))
        frequency_label = next(
            (
                label_name
                for label_name, value in self.FREQUENCIES.items()
                if value == schedule.get("frequency")
            ),
            "Daily",
        )
        self.frequency_option.set(frequency_label)
        weekday = int(schedule.get("weekday", 0))
        self.weekday_option.set(self.WEEKDAYS[max(0, min(weekday, 6))])
        self.day_of_month.configure(state="normal")
        self._replace_entry(self.day_of_month, schedule.get("day_of_month", 1))
        self.enabled_var.set(bool(schedule.get("enabled", True)))
        self.schedule_form.set_settings(schedule.get("settings", {}))
        self._select_bo_id(int(schedule.get("bo_connection_id", 1)))
        self._refresh_schedule_states()

    def _refresh_schedule_states(self) -> None:
        frequency = self.FREQUENCIES.get(self.frequency_option.get(), "daily")
        self.weekday_option.configure(
            state="normal" if frequency == "weekly" else "disabled"
        )
        self.day_of_month.configure(
            state="normal" if frequency == "monthly" else "disabled"
        )

    def _request(
        self,
        operation: str,
        parameters: dict[str, Any],
        bo_connection_id: int | None = None,
    ) -> None:
        if not self.on_request_callback:
            self._set_status("Backup request channel is unavailable.", COLORS.danger)
            return
        request_id = str(uuid.uuid4())
        self.pending[request_id] = operation
        self._set_status(f"Running: {operation}...", COLORS.accent)
        sent = self.on_request_callback(
            {
                "type": "backup_request",
                "request_id": request_id,
                "client_code": self.client_code,
                "bo_connection_id": bo_connection_id or self._selected_bo_id(default=1),
                "operation": operation,
                "parameters": parameters,
            }
        )
        if sent is False:
            self._clear_pending_request(request_id)
            self._set_status("Dashboard WebSocket is not connected.", COLORS.danger)
            return
        self.ack_timeout_jobs[request_id] = self.after(
            15000,
            lambda current_request_id=request_id: self._handle_ack_timeout(
                current_request_id
            ),
        )

    def handle_progress(self, payload: dict[str, Any]) -> None:
        if payload.get("client_code") != self.client_code:
            return
        request_id = str(payload.get("request_id") or "")
        if request_id not in self.pending:
            return
        self._acknowledge_request(request_id)
        percent = payload.get("percent")
        if isinstance(percent, (int, float)) and not isinstance(percent, bool):
            self.progress_bar.set(max(0.0, min(float(percent) / 100.0, 1.0)))
        message = str(payload.get("message") or "").strip()
        stage = str(payload.get("stage") or "backup").replace("_", " ").title()
        if message:
            self._append_activity(f"\n[{stage}] {message}")
            self._set_status(message, COLORS.accent)

    def handle_result(self, payload: dict[str, Any]) -> None:
        if payload.get("client_code") != self.client_code:
            return
        request_id = str(payload.get("request_id") or "")
        operation = self.pending.get(request_id)
        if not operation:
            return
        self._clear_pending_request(request_id)
        if operation == "list":
            self._load_snapshot(payload)
        elif operation == "list_cloud_remotes":
            remotes = payload.get("cloud_remotes") or []
            text = ", ".join(str(item) for item in remotes) if remotes else "none"
            self.cloud_hint.configure(text=f"Configured cloud remotes: {text}")
        elif operation in {"save_schedule", "delete_schedule"}:
            if payload.get("success"):
                self._set_status(
                    str(payload.get("message") or "Completed."), COLORS.success
                )
                self.new_schedule()
                self._request("list", parameters={})
            else:
                self._show_error(payload)
        else:
            self._show_backup_result(payload)
            self._request("list", parameters={})

    def _load_snapshot(self, payload: dict[str, Any]) -> None:
        if not payload.get("success"):
            self._show_error(payload)
            return
        schedules = payload.get("schedules") or []
        self.schedules = {
            str(item.get("schedule_id")): item
            for item in schedules
            if isinstance(item, dict) and item.get("schedule_id")
        }
        self.schedule_labels = {}
        labels = ["New schedule"]
        for schedule_id, schedule in self.schedules.items():
            state = "Enabled" if schedule.get("enabled") else "Disabled"
            label = (
                f"{schedule.get('name', 'Unnamed')} | {state} | "
                f"Next: {schedule.get('next_run_at') or '-'}"
            )
            self.schedule_labels[label] = schedule_id
            labels.append(label)
        self.schedule_option.configure(values=labels)
        if self.selected_schedule_id not in self.schedules:
            self.selected_schedule_id = ""
            self.schedule_option.set("New schedule")
        self._render_history(payload.get("history") or [])
        self._set_status("Backup data refreshed.", COLORS.success)

    def _show_backup_result(self, payload: dict[str, Any]) -> None:
        success = bool(payload.get("success"))
        status = str(payload.get("status") or ("completed" if success else "failed"))
        lines = [
            f"Status: {status}",
            f"Message: {payload.get('message') or '-'}",
            f"Database: {payload.get('database_name') or '-'}",
            f"File: {payload.get('file_path') or payload.get('remote_file_path') or payload.get('staging_file_path') or '-'}",
            f"Verified: {payload.get('verified', False)}",
            f"Size: {self._format_size(payload.get('size_bytes'))}",
            f"Elapsed: {payload.get('elapsed_ms', '-')} ms",
        ]
        if payload.get("retention_deleted"):
            lines.append(
                f"Retention deleted: {len(payload['retention_deleted'])} file(s)"
            )
        if payload.get("warnings"):
            lines.extend(f"Warning: {item}" for item in payload["warnings"])
        if payload.get("error"):
            lines.append(f"Error: {payload['error']}")
        self._set_activity("\n".join(lines))
        if success:
            self.progress_bar.set(1)
            self._set_status("Backup operation completed.", COLORS.success)
        elif status == "upload_failed" and payload.get("verified"):
            self._set_status(
                "Backup verified; cloud upload is pending retry.", COLORS.warning
            )
        else:
            self._set_status("Backup operation failed.", COLORS.danger)

    def _show_error(self, payload: dict[str, Any]) -> None:
        error = str(payload.get("error") or "Unknown backup error.")
        self._set_status(error, COLORS.danger)
        self._set_activity(f"Backup operation failed.\n\n{error}")

    def _render_history(self, history: list[dict[str, Any]]) -> None:
        if not history:
            self._set_history("No backups have been recorded on this client.")
            return
        blocks = []
        for item in history[:200]:
            destination = (
                item.get("remote_file_path")
                or item.get("file_path")
                or item.get("staging_file_path")
                or "-"
            )
            blocks.append(
                "\n".join(
                    [
                        f"{item.get('started_at', '-')} | {str(item.get('status', '-')).upper()}",
                        f"Database: {item.get('database_name') or '-'} | Source: {item.get('source') or '-'}",
                        f"Destination: {destination}",
                        f"Size: {self._format_size(item.get('size_bytes'))} | Verified: {item.get('verified', False)}",
                        f"Message: {item.get('message') or item.get('error') or '-'}",
                    ]
                )
            )
        self._set_history("\n\n".join(blocks))

    def _selected_bo_id(self, default: int | None = None) -> int:
        try:
            return int(self.bo_option.get().split()[1])
        except (IndexError, TypeError, ValueError) as exc:
            if default is not None:
                return default
            raise ValueError("Select a valid BOConnection.") from exc

    def _select_bo_id(self, bo_connection_id: int) -> None:
        values = self.get_bo_values_callback() or []
        selected = next(
            (value for value in values if value.startswith(f"ID {bo_connection_id} ")),
            None,
        )
        if selected:
            self.bo_option.set(selected)

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.configure(text=str(text)[:160], text_color=color)

    def _set_activity(self, text: str) -> None:
        self.activity_box.configure(state="normal")
        self.activity_box.delete("1.0", "end")
        self.activity_box.insert("1.0", text)
        self.activity_box.configure(state="disabled")

    def _append_activity(self, text: str) -> None:
        self.activity_box.configure(state="normal")
        self.activity_box.insert("end", text)
        self.activity_box.see("end")
        self.activity_box.configure(state="disabled")

    def _set_history(self, text: str) -> None:
        self.history_box.configure(state="normal")
        self.history_box.delete("1.0", "end")
        self.history_box.insert("1.0", text)
        self.history_box.configure(state="disabled")

    @staticmethod
    def _replace_entry(entry: ctk.CTkEntry, value: Any) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, str(value))

    @staticmethod
    def _format_size(value: Any) -> str:
        try:
            size = int(value)
        except (TypeError, ValueError):
            return "-"
        return f"{size / (1024 * 1024):,.2f} MB"

    def _bring_to_front(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(250, lambda: self.attributes("-topmost", False))
        except TclError:
            return

    def _acknowledge_request(self, request_id: str) -> None:
        """Ακυρώνει το σύντομο watchdog μόλις απαντήσει ο remote client."""

        self.acknowledged_requests.add(request_id)
        job = self.ack_timeout_jobs.pop(request_id, None)
        if job:
            try:
                self.after_cancel(job)
            except TclError:
                pass

    def _clear_pending_request(self, request_id: str) -> str | None:
        """Καθαρίζει pending state και τυχόν acknowledgement timer."""

        operation = self.pending.pop(request_id, None)
        self.acknowledged_requests.discard(request_id)
        job = self.ack_timeout_jobs.pop(request_id, None)
        if job:
            try:
                self.after_cancel(job)
            except TclError:
                pass
        return operation

    def _handle_ack_timeout(self, request_id: str) -> None:
        """Δείχνει σαφές μήνυμα όταν server/client δεν γνωρίζει το backup protocol."""

        self.ack_timeout_jobs.pop(request_id, None)
        if request_id not in self.pending or request_id in self.acknowledged_requests:
            return
        operation = self._clear_pending_request(request_id)
        message = (
            "The remote client did not acknowledge the backup request within 15 seconds.\n\n"
            "Update/restart the MoonHard Remote Client and confirm that the updated "
            "server is deployed, then try again. No backup start was confirmed."
        )
        self._set_status("Remote client did not acknowledge the request.", COLORS.danger)
        if operation in {"run", "run_schedule", "retry_pending"}:
            self._set_activity(message)

    def _close_window(self) -> None:
        """Ακυρώνει UI timers πριν κλείσει το Backup Manager."""

        for request_id in list(self.pending):
            self._clear_pending_request(request_id)
        self.destroy()

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-b>", lambda _event: self.run_manual_backup())
        self.bind("<Control-s>", lambda _event: self.save_schedule())
        self.bind("<Control-r>", lambda _event: self.refresh_data())
        self.bind("<Escape>", lambda _event: self._close_window())
