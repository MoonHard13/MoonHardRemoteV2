import logging
from typing import Any
from tkinter import ttk

import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    apply_treeview_style,
    card_style,
    secondary_button_style
)


logger = logging.getLogger(__name__)


class BulkUpdateProgressWindow(ctk.CTkToplevel):
    """Παράθυρο παρακολούθησης του bulk update των clients."""

    ACTIVE_STAGES = {
        "checking",
        "waiting_download_slot",
        "downloading",
        "extracting",
        "applying",
        "apply_started"
    }
    FINISHED_STAGES = {"completed", "up_to_date"}
    PROBLEM_STAGES = {"failed", "stuck"}

    def __init__(self, parent, on_retry_callback=None) -> None:
        """Δημιουργεί το παράθυρο και συνδέει τα διαθέσιμα actions."""

        super().__init__(parent)
        self.title("Bulk Update Progress")
        self.geometry("1400x820")
        self.minsize(1050, 650)
        self.configure(fg_color=COLORS.background)

        self.on_retry_callback = on_retry_callback
        self.clients: dict[str, dict[str, Any]] = {}
        self.states: dict[str, dict[str, Any]] = {}
        self.row_snapshots: dict[str, tuple[Any, ...]] = {}
        self.filter_after_job = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.lift()
        self.focus()

    def _build_ui(self) -> None:
        """Δημιουργεί το header, τα metrics, τα φίλτρα και τον πίνακα."""

        self._build_header()
        self._build_metrics()
        self._build_filters()
        self._build_table()
        self._build_details_panel()

    def _build_header(self) -> None:
        """Δημιουργεί την περιοχή τίτλου και συνολικής προόδου."""

        header = ctk.CTkFrame(self, **card_style())
        header.grid(
            row=0,
            column=0,
            padx=SPACING.window_padding,
            pady=(SPACING.window_padding, 10),
            sticky="ew"
        )
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Bulk Update Progress",
            font=FONTS.title,
            text_color=COLORS.text_primary,
            anchor="w"
        ).grid(row=0, column=0, padx=18, pady=(14, 2), sticky="ew")

        self.summary_label = ctk.CTkLabel(
            header,
            text="Waiting for clients...",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            anchor="w"
        )
        self.summary_label.grid(row=1, column=0, padx=18, pady=(0, 8), sticky="ew")

        progress_frame = ctk.CTkFrame(header, fg_color="transparent")
        progress_frame.grid(row=2, column=0, padx=18, pady=(0, 14), sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            height=10,
            corner_radius=5,
            fg_color=COLORS.surface_light,
            progress_color=COLORS.accent
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            progress_frame,
            text="0%",
            width=55,
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="e"
        )
        self.progress_label.grid(row=0, column=1, padx=(12, 0))

        button_frame = ctk.CTkFrame(header, fg_color="transparent")
        button_frame.grid(row=0, column=1, rowspan=3, padx=18, pady=14, sticky="e")

        self.retry_button = ctk.CTkButton(
            button_frame,
            text="Retry problems  ·  Ctrl+R",
            width=205,
            height=36,
            command=self._retry_clicked,
            fg_color=COLORS.warning,
            hover_color="#D88908",
            text_color="#171006",
            corner_radius=SPACING.button_radius,
            font=FONTS.body_bold
        )
        self.retry_button.grid(row=0, column=0, padx=(0, 10))

        ctk.CTkButton(
            button_frame,
            text="Close  ·  Esc",
            width=120,
            height=36,
            command=self.destroy,
            **secondary_button_style()
        ).grid(row=0, column=1)

    def _build_metrics(self) -> None:
        """Δημιουργεί τα compact counters της διαδικασίας."""

        self.metrics_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics_frame.grid(
            row=1,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, 10),
            sticky="ew"
        )
        for column in range(5):
            self.metrics_frame.grid_columnconfigure(column, weight=1)

        metric_definitions = (
            ("total", "Total clients", COLORS.info, COLORS.info_soft),
            ("finished", "Finished", COLORS.success, COLORS.success_soft),
            ("active", "In progress", COLORS.warning, COLORS.warning_soft),
            ("queued", "Queued", COLORS.text_secondary, COLORS.surface_light),
            ("problems", "Problems", COLORS.danger, COLORS.danger_soft),
        )
        self.metric_values: dict[str, ctk.CTkLabel] = {}

        for column, (key, title, color, background) in enumerate(metric_definitions):
            card = ctk.CTkFrame(
                self.metrics_frame,
                fg_color=background,
                corner_radius=SPACING.small_radius,
                border_width=1,
                border_color=COLORS.border_soft
            )
            card.grid(
                row=0,
                column=column,
                padx=(0, 8) if column < 4 else 0,
                sticky="ew"
            )
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                card,
                text=title,
                font=FONTS.small,
                text_color=COLORS.text_secondary,
                anchor="w"
            ).grid(row=0, column=0, padx=14, pady=(9, 0), sticky="ew")

            value_label = ctk.CTkLabel(
                card,
                text="0",
                font=FONTS.subtitle,
                text_color=color,
                anchor="w"
            )
            value_label.grid(row=1, column=0, padx=14, pady=(0, 9), sticky="ew")
            self.metric_values[key] = value_label

    def _build_filters(self) -> None:
        """Δημιουργεί αναζήτηση και φίλτρο κατάστασης."""

        filter_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS.surface,
            corner_radius=SPACING.small_radius,
            border_width=1,
            border_color=COLORS.border_soft
        )
        filter_frame.grid(
            row=2,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, 10),
            sticky="ew"
        )
        filter_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            filter_frame,
            height=36,
            placeholder_text="Search client, PC, code, version or error...",
            fg_color=COLORS.surface_light,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        self.search_entry.grid(row=0, column=0, padx=(14, 8), pady=12, sticky="ew")
        self.search_entry.bind(
            "<KeyRelease>",
            lambda _event: self._schedule_filter_apply()
        )

        self.status_filter = ctk.CTkOptionMenu(
            filter_frame,
            values=[
                "All statuses",
                "In progress",
                "Queued",
                "Completed",
                "Up to date",
                "Problems"
            ],
            command=lambda _value: self._apply_filters(),
            width=165,
            height=36,
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.status_filter.set("All statuses")
        self.status_filter.grid(row=0, column=1, padx=(0, 8), pady=12)

        ctk.CTkButton(
            filter_frame,
            text="Clear  ·  Ctrl+L",
            width=135,
            height=36,
            command=self._clear_filters,
            **secondary_button_style()
        ).grid(row=0, column=2, padx=(0, 8), pady=12)

        self.filtered_count_label = ctk.CTkLabel(
            filter_frame,
            text="0 shown",
            width=90,
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="e"
        )
        self.filtered_count_label.grid(row=0, column=3, padx=(0, 14), pady=12)

    def _build_table(self) -> None:
        """Δημιουργεί τον αποδοτικό πίνακα παρακολούθησης clients."""

        table_card = ctk.CTkFrame(self, **card_style())
        table_card.grid(
            row=3,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, 10),
            sticky="nsew"
        )
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            table_card,
            text="Client update queue",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
            anchor="w"
        ).grid(row=0, column=0, padx=14, pady=(12, 8), sticky="ew")

        tree_style = apply_treeview_style("MoonHard.BulkUpdate.Treeview")
        self.client_tree = ttk.Treeview(
            table_card,
            columns=(
                "State", "Client", "PC", "Current",
                "Target", "Stage", "Retries", "Details"
            ),
            show="headings",
            style=tree_style,
            selectmode="browse"
        )
        self.client_tree.grid(row=1, column=0, sticky="nsew")
        self.client_tree.bind("<<TreeviewSelect>>", self._show_selected_details)

        y_scroll = ctk.CTkScrollbar(
            table_card,
            orientation="vertical",
            command=self.client_tree.yview
        )
        y_scroll.grid(row=1, column=1, padx=(4, 4), sticky="ns")

        x_scroll = ctk.CTkScrollbar(
            table_card,
            orientation="horizontal",
            command=self.client_tree.xview
        )
        x_scroll.grid(row=2, column=0, pady=(4, 4), sticky="ew")
        self.client_tree.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set
        )

        headings = {
            "State": "", "Client": "Client", "PC": "PC name",
            "Current": "Current", "Target": "Target", "Stage": "Stage",
            "Retries": "Retries", "Details": "Details"
        }
        for column, title in headings.items():
            self.client_tree.heading(column, text=title)

        self.client_tree.column("State", width=42, minwidth=42, anchor="center", stretch=False)
        self.client_tree.column("Client", width=245, minwidth=170)
        self.client_tree.column("PC", width=180, minwidth=130)
        self.client_tree.column("Current", width=90, minwidth=80, anchor="center", stretch=False)
        self.client_tree.column("Target", width=90, minwidth=80, anchor="center", stretch=False)
        self.client_tree.column("Stage", width=190, minwidth=150, anchor="center", stretch=False)
        self.client_tree.column("Retries", width=70, minwidth=65, anchor="center", stretch=False)
        self.client_tree.column("Details", width=360, minwidth=220)

        self.client_tree.tag_configure("finished", foreground=COLORS.success)
        self.client_tree.tag_configure("active", foreground=COLORS.warning)
        self.client_tree.tag_configure("problem", foreground="#FF7B7B")
        self.client_tree.tag_configure("queued", foreground=COLORS.text_secondary)

    def _build_details_panel(self) -> None:
        """Δημιουργεί panel λεπτομερειών για τον επιλεγμένο client."""

        details = ctk.CTkFrame(
            self,
            fg_color=COLORS.surface,
            corner_radius=SPACING.small_radius,
            border_width=1,
            border_color=COLORS.border_soft
        )
        details.grid(
            row=4,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, SPACING.window_padding),
            sticky="ew"
        )
        details.grid_columnconfigure(1, weight=1)

        self.detail_status_label = ctk.CTkLabel(
            details,
            text="SELECT A CLIENT",
            width=180,
            font=FONTS.body_bold,
            text_color=COLORS.text_secondary,
            fg_color=COLORS.surface_light,
            corner_radius=8
        )
        self.detail_status_label.grid(row=0, column=0, padx=14, pady=12, sticky="w")

        self.detail_text_label = ctk.CTkLabel(
            details,
            text="Select a row to inspect its stage, retry count and error details.",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
            justify="left",
            wraplength=900
        )
        self.detail_text_label.grid(row=0, column=1, padx=(0, 14), pady=12, sticky="ew")

    def _bind_shortcuts(self) -> None:
        """Συνδέει shortcuts για όλες τις ενέργειες του παραθύρου."""

        self.bind("<Control-f>", lambda _event: self.search_entry.focus_set())
        self.bind("<Control-l>", lambda _event: self._clear_filters())
        self.bind("<Control-r>", lambda _event: self._retry_clicked())
        self.bind("<Escape>", lambda _event: self.destroy())

    def initialize_clients(self, clients: list[dict]) -> None:
        """Αρχικοποιεί τον πίνακα χωρίς ξεχωριστό card ανά client."""

        for client_code in tuple(self.clients):
            if self.client_tree.exists(client_code):
                self.client_tree.delete(client_code)

        self.clients = {
            str(client.get("client_code", "")).strip(): client
            for client in clients
            if str(client.get("client_code", "")).strip()
        }
        self.states = {}
        self.row_snapshots.clear()

        for client_code in self.clients:
            self.client_tree.insert("", "end", iid=client_code)

        self.update_states({})
        logger.info("Bulk update UI initialized for %s clients.", len(self.clients))

    def update_states(self, states: dict[str, dict[str, Any]]) -> None:
        """Ανανεώνει μόνο τις γραμμές των clients που άλλαξαν."""

        self.states = states
        filter_may_change = False

        for client_code, client in self.clients.items():
            state = states.get(client_code, {})
            snapshot = self._build_row_snapshot(client_code, client, state)
            old_snapshot = self.row_snapshots.get(client_code)

            if old_snapshot == snapshot:
                continue

            old_stage = old_snapshot[5] if old_snapshot else None
            new_stage = snapshot[5]
            filter_may_change = filter_may_change or old_stage != new_stage
            self.row_snapshots[client_code] = snapshot
            self.client_tree.item(
                client_code,
                values=(
                    snapshot[0], snapshot[1], snapshot[2], snapshot[3],
                    snapshot[4], snapshot[8], snapshot[6], snapshot[7]
                ),
                tags=(self._get_stage_tag(new_stage),)
            )

        summary = self._calculate_summary()
        self._update_summary(summary)

        if (
            filter_may_change
            or self.status_filter.get() != "All statuses"
            or bool(self.search_entry.get().strip())
        ):
            self._apply_filters()
        else:
            self.filtered_count_label.configure(text=f"{len(self.clients)} shown")
        self._refresh_selected_details()

    def _build_row_snapshot(
        self,
        client_code: str,
        client: dict[str, Any],
        state: dict[str, Any]
    ) -> tuple[Any, ...]:
        """Δημιουργεί immutable snapshot για γρήγορο incremental update."""

        stage = str(state.get("stage", "queued"))
        error = str(state.get("error", "")).strip()
        display_name = str(
            client.get("display_name") or client.get("pc_name") or client_code
        )
        pc_name = str(client.get("pc_name") or "-")
        current_version = str(client.get("app_version") or "-")
        target_version = str(state.get("latest_version") or "-")
        retry_count = int(state.get("retry_count", 0) or 0)
        details = error or self._get_stage_detail(stage)

        return (
            "●", display_name, pc_name, current_version, target_version,
            stage, retry_count, details, self._format_stage(stage)
        )

    def _calculate_summary(self) -> dict[str, int]:
        """Υπολογίζει counters για όλους τους clients, μαζί με τους queued."""

        summary: dict[str, int] = {}
        for client_code in self.clients:
            stage = str(self.states.get(client_code, {}).get("stage", "queued"))
            summary[stage] = summary.get(stage, 0) + 1
        return summary

    def _update_summary(self, summary: dict[str, int]) -> None:
        """Ενημερώνει progress bar, summary και metric cards."""

        total = len(self.clients)
        completed = summary.get("completed", 0)
        up_to_date = summary.get("up_to_date", 0)
        finished = completed + up_to_date
        active = sum(summary.get(stage, 0) for stage in self.ACTIVE_STAGES)
        queued = summary.get("queued", 0)
        problems = sum(summary.get(stage, 0) for stage in self.PROBLEM_STAGES)
        processed = finished + problems
        progress = processed / total if total else 0

        self.metric_values["total"].configure(text=str(total))
        self.metric_values["finished"].configure(text=str(finished))
        self.metric_values["active"].configure(text=str(active))
        self.metric_values["queued"].configure(text=str(queued))
        self.metric_values["problems"].configure(text=str(problems))
        self.progress_bar.set(progress)
        self.progress_label.configure(text=f"{round(progress * 100)}%")
        self.summary_label.configure(
            text=(
                f"{processed} of {total} processed"
                f"   •   {finished} successful"
                f"   •   {active} in progress"
                f"   •   {queued} queued"
                f"   •   {problems} problems"
            )
        )
        self.retry_button.configure(
            state="normal" if problems else "disabled"
        )

    def _schedule_filter_apply(self) -> None:
        """Συγχωνεύει διαδοχικά keystrokes πριν εφαρμοστεί αναζήτηση."""

        if self.filter_after_job:
            try:
                self.after_cancel(self.filter_after_job)
            except Exception:
                pass
        self.filter_after_job = self.after(150, self._apply_filters)

    def _apply_filters(self) -> None:
        """Εμφανίζει μόνο τους clients που περνούν search και status filter."""

        self.filter_after_job = None
        search_text = self.search_entry.get().strip().lower()
        selected_filter = self.status_filter.get()
        visible_count = 0

        for client_code, client in self.clients.items():
            state = self.states.get(client_code, {})
            stage = str(state.get("stage", "queued"))
            searchable_text = " ".join(
                (
                    str(client.get("display_name", "")),
                    str(client.get("pc_name", "")),
                    str(client.get("client_code", "")),
                    str(client.get("app_version", "")),
                    str(state.get("latest_version", "")),
                    self._format_stage(stage),
                    str(state.get("error", ""))
                )
            ).lower()
            matches = (
                (not search_text or search_text in searchable_text)
                and self._stage_matches_filter(stage, selected_filter)
            )

            if matches:
                self.client_tree.reattach(client_code, "", "end")
                visible_count += 1
            else:
                self.client_tree.detach(client_code)

        self.filtered_count_label.configure(text=f"{visible_count} shown")

    def _clear_filters(self) -> None:
        """Καθαρίζει αναζήτηση και φίλτρο κατάστασης."""

        self.search_entry.delete(0, "end")
        self.status_filter.set("All statuses")
        self._apply_filters()
        logger.info("Bulk update UI filters cleared.")

    def _stage_matches_filter(self, stage: str, selected_filter: str) -> bool:
        """Ελέγχει αν ένα stage αντιστοιχεί στο επιλεγμένο UI filter."""

        if selected_filter == "In progress":
            return stage in self.ACTIVE_STAGES
        if selected_filter == "Queued":
            return stage == "queued"
        if selected_filter == "Completed":
            return stage == "completed"
        if selected_filter == "Up to date":
            return stage == "up_to_date"
        if selected_filter == "Problems":
            return stage in self.PROBLEM_STAGES
        return True

    def _show_selected_details(self, _event=None) -> None:
        """Εμφανίζει λεπτομέρειες για την επιλεγμένη γραμμή."""

        self._refresh_selected_details()

    def _refresh_selected_details(self) -> None:
        """Ανανεώνει το details panel χωρίς αλλαγή επιλογής."""

        selection = self.client_tree.selection()
        if not selection:
            return

        client_code = selection[0]
        client = self.clients.get(client_code, {})
        state = self.states.get(client_code, {})
        stage = str(state.get("stage", "queued"))
        error = str(state.get("error", "")).strip()
        retry_count = int(state.get("retry_count", 0) or 0)
        latest_version = str(state.get("latest_version") or "-")
        display_name = str(
            client.get("display_name") or client.get("pc_name") or client_code
        )

        self.detail_status_label.configure(
            text=self._format_stage(stage),
            text_color=self._get_stage_color(stage),
            fg_color=self._get_stage_background(stage)
        )
        self.detail_text_label.configure(
            text=(
                f"{display_name}  •  {client_code}  •  "
                f"Target: {latest_version}  •  Retries: {retry_count}"
                + (f"\n{error}" if error else "")
            )
        )

    def _format_stage(self, stage: str) -> str:
        """Μετατρέπει internal stage σε καθαρό UI label."""

        mapping = {
            "queued": "QUEUED",
            "checking": "CHECKING",
            "waiting_download_slot": "WAITING DOWNLOAD SLOT",
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

    def _get_stage_detail(self, stage: str) -> str:
        """Επιστρέφει σύντομη περιγραφή του τρέχοντος stage."""

        mapping = {
            "queued": "Waiting for update check",
            "checking": "Checking available version",
            "waiting_download_slot": "Waiting for an available download slot",
            "downloading": "Downloading update package",
            "extracting": "Extracting update package",
            "applying": "Applying update",
            "apply_started": "Waiting for the client to reconnect",
            "completed": "Update completed successfully",
            "up_to_date": "No update required",
            "failed": "Update failed",
            "stuck": "No response received within the allowed time"
        }
        return mapping.get(stage, "")

    def _get_stage_color(self, stage: str) -> str:
        """Επιστρέφει το κύριο χρώμα του stage."""

        if stage in self.FINISHED_STAGES:
            return COLORS.success
        if stage in self.PROBLEM_STAGES:
            return COLORS.danger
        if stage in self.ACTIVE_STAGES:
            return COLORS.warning
        return COLORS.text_secondary

    def _get_stage_background(self, stage: str) -> str:
        """Επιστρέφει το background χρώμα του stage badge."""

        if stage in self.FINISHED_STAGES:
            return COLORS.success_soft
        if stage in self.PROBLEM_STAGES:
            return COLORS.danger_soft
        if stage in self.ACTIVE_STAGES:
            return COLORS.warning_soft
        return COLORS.surface_light

    def _get_stage_tag(self, stage: str) -> str:
        """Επιστρέφει το Treeview tag που αντιστοιχεί στο stage."""

        if stage in self.FINISHED_STAGES:
            return "finished"
        if stage in self.PROBLEM_STAGES:
            return "problem"
        if stage in self.ACTIVE_STAGES:
            return "active"
        return "queued"

    def _build_summary_text(self, summary: dict[str, int]) -> str:
        """Διατηρεί συνοπτικό text format για CLI και tests."""

        completed = summary.get("completed", 0)
        up_to_date = summary.get("up_to_date", 0)
        problems = sum(summary.get(stage, 0) for stage in self.PROBLEM_STAGES)
        active = sum(summary.get(stage, 0) for stage in self.ACTIVE_STAGES)
        queued = summary.get("queued", 0)
        return (
            f"Finished: {completed + up_to_date}  |  "
            f"In progress: {active}  |  Queued: {queued}  |  "
            f"Problems: {problems}"
        )

    def _retry_clicked(self) -> None:
        """Ζητά retry για failed ή stuck clients."""

        logger.info("Manual bulk update retry requested from progress window.")
        if self.on_retry_callback:
            self.on_retry_callback()

    def destroy(self) -> None:
        """Ακυρώνει pending jobs πριν κλείσει το παράθυρο."""

        if self.filter_after_job:
            try:
                self.after_cancel(self.filter_after_job)
            except Exception:
                pass
            self.filter_after_job = None
        super().destroy()
