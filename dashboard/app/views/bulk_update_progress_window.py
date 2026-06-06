from typing import Any

import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    card_style,
    secondary_button_style
)


class BulkUpdateProgressWindow(ctk.CTkToplevel):
    """
    Παράθυρο προόδου για το bulk update των clients.
    """

    def __init__(self, parent, on_retry_callback=None) -> None:
        """
        Δημιουργεί το παράθυρο προόδου bulk update.
        """

        super().__init__(parent)

        self.title("Bulk Update Progress")
        self.geometry("950x650")
        self.minsize(850, 500)
        self.configure(fg_color=COLORS.background)

        self.client_rows: dict[str, dict[str, Any]] = {}
        self.on_retry_callback = on_retry_callback

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()
        self.lift()
        self.focus()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του progress window.
        """

        header = ctk.CTkFrame(self, **card_style())
        header.grid(
            row=0,
            column=0,
            padx=SPACING.window_padding,
            pady=(SPACING.window_padding, SPACING.large_gap),
            sticky="ew"
        )
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="Bulk Update Progress",
            font=FONTS.title,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        self.summary_label = ctk.CTkLabel(
            header,
            text="Waiting...",
            font=FONTS.body,
            text_color=COLORS.text_secondary
        )
        self.summary_label.grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

        button_frame = ctk.CTkFrame(header, fg_color="transparent")
        button_frame.grid(row=0, column=1, rowspan=2, padx=18, pady=14, sticky="e")

        retry_button = ctk.CTkButton(
            button_frame,
            text="Retry Failed/Stuck",
            width=150,
            command=self._retry_clicked,
            fg_color=COLORS.warning,
            hover_color=COLORS.warning,
            text_color=COLORS.text_primary
        )
        retry_button.grid(row=0, column=0, padx=(0, 10), sticky="e")

        close_button = ctk.CTkButton(
            button_frame,
            text="Close",
            width=90,
            command=self.destroy,
            **secondary_button_style()
        )
        close_button.grid(row=0, column=1, sticky="e")

        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            corner_radius=SPACING.small_radius,
            fg_color=COLORS.background
        )
        self.scroll_frame.grid(
            row=1,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, SPACING.window_padding),
            sticky="nsew"
        )
        self.scroll_frame.grid_columnconfigure(0, weight=1)

    def initialize_clients(self, clients: list[dict]) -> None:
        """
        Δημιουργεί αρχικές γραμμές για όλους τους clients του bulk update.
        """

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        self.client_rows.clear()

        for row_index, client in enumerate(clients):
            self._add_client_row(row_index, client)

        self.update_states({})

    def _add_client_row(self, row_index: int, client: dict) -> None:
        """
        Προσθέτει μία γραμμή client στο progress window.
        """

        client_code = str(client.get("client_code", ""))
        display_name = client.get("display_name") or client.get("pc_name") or client_code
        pc_name = client.get("pc_name", "-")
        app_version = client.get("app_version", "-")

        row = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=COLORS.surface,
            corner_radius=SPACING.card_radius,
            border_width=1,
            border_color=COLORS.border_soft
        )
        row.grid(row=row_index, column=0, padx=4, pady=6, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        status_dot = ctk.CTkLabel(
            row,
            text="",
            width=18,
            height=18,
            corner_radius=9,
            fg_color=COLORS.text_muted
        )
        status_dot.grid(row=0, column=0, padx=(15, 10), pady=12, sticky="w")

        info_label = ctk.CTkLabel(
            row,
            text=(
                f"{display_name}\n"
                f"PC: {pc_name}  •  Current Version: {app_version}\n"
                f"Code: {client_code}"
            ),
            font=FONTS.body,
            text_color=COLORS.text_primary,
            justify="left",
            anchor="w"
        )
        info_label.grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        stage_label = ctk.CTkLabel(
            row,
            text="QUEUED",
            font=FONTS.body_bold,
            text_color=COLORS.text_secondary
        )
        stage_label.grid(row=0, column=2, padx=15, pady=12, sticky="e")

        error_label = ctk.CTkLabel(
            row,
            text="",
            font=FONTS.small,
            text_color=COLORS.danger,
            anchor="e"
        )
        error_label.grid(row=1, column=1, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

        self.client_rows[client_code] = {
            "status_dot": status_dot,
            "info_label": info_label,
            "stage_label": stage_label,
            "error_label": error_label
        }

    def update_states(self, states: dict[str, dict[str, Any]]) -> None:
        """
        Ανανεώνει την πρόοδο των clients.
        """

        summary: dict[str, int] = {}

        for state in states.values():
            stage = str(state.get("stage", "queued"))
            summary[stage] = summary.get(stage, 0) + 1

        for client_code, widgets in self.client_rows.items():
            state = states.get(client_code, {})
            stage = str(state.get("stage", "queued"))
            error = str(state.get("error", ""))

            widgets["stage_label"].configure(
                text=self._format_stage(stage),
                text_color=self._get_stage_color(stage)
            )

            widgets["status_dot"].configure(
                fg_color=self._get_stage_color(stage)
            )

            widgets["error_label"].configure(
                text=error
            )

        self.summary_label.configure(
            text=self._build_summary_text(summary)
        )

    def _format_stage(self, stage: str) -> str:
        """
        Μετατρέπει internal stage σε καθαρό label.
        """

        mapping = {
            "queued": "QUEUED",
            "checking": "CHECKING",
            "downloading": "DOWNLOADING",
            "extracting": "EXTRACTING",
            "applying": "APPLYING",
            "apply_started": "WAITING RECONNECT",
            "completed": "COMPLETED",
            "up_to_date": "UP TO DATE",
            "failed": "FAILED",
            "stuck": "STUCK / RETRYABLE"
        }

        return mapping.get(stage, stage.upper())

    def _get_stage_color(self, stage: str) -> str:
        """
        Επιστρέφει χρώμα ανάλογα με το stage.
        """

        if stage in ("completed", "up_to_date"):
            return COLORS.success

        if stage in ("failed", "stuck"):
            return COLORS.danger

        if stage in ("checking", "downloading", "extracting", "applying", "apply_started"):
            return COLORS.warning

        return COLORS.text_muted

    def _build_summary_text(self, summary: dict[str, int]) -> str:
        """
        Δημιουργεί συνοπτικό κείμενο προόδου με καθαρή τελική εικόνα.
        """

        if not summary:
            return "Waiting..."

        completed = summary.get("completed", 0)
        up_to_date = summary.get("up_to_date", 0)
        failed = summary.get("failed", 0) + summary.get("stuck", 0)

        active_stages = [
            "queued",
            "checking",
            "downloading",
            "extracting",
            "applying",
            "apply_started"
        ]

        still_waiting = sum(summary.get(stage, 0) for stage in active_stages)

        parts = [
            f"Completed: {completed}",
            f"Up to date: {up_to_date}",
            f"Failed/Stuck: {failed}",
            f"Still waiting: {still_waiting}"
        ]

        stage_parts: list[str] = []

        ordered_stages = [
            "queued",
            "checking",
            "downloading",
            "extracting",
            "applying",
            "apply_started",
            "completed",
            "up_to_date",
            "failed",
            "stuck"
        ]

        for stage in ordered_stages:
            count = summary.get(stage, 0)

            if count:
                stage_parts.append(f"{self._format_stage(stage)}: {count}")

        return "  |  ".join(parts) + "\n" + "  •  ".join(stage_parts)
    
    def _retry_clicked(self) -> None:
        """
        Ζητάει retry για failed/stuck/not completed clients.
        """

        if self.on_retry_callback:
            self.on_retry_callback()