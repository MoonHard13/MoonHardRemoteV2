import tkinter as tk
import uuid
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    card_style,
    primary_button_style,
    secondary_button_style,
    danger_button_style,
    apply_treeview_style
)


class ProcessesTab(ctk.CTkFrame):
    """
    Tab για προβολή running processes του client.
    """

    def __init__(
        self,
        parent,
        client_code: str,
        on_processes_request_callback: Callable[[dict], None] | None = None,
        on_process_action_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το Processes tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client_code = client_code
        self.on_processes_request_callback = on_processes_request_callback
        self.on_process_action_callback = on_process_action_callback
        self.processes: list[dict] = []
        self.auto_refresh_enabled = False
        self.auto_refresh_job = None
        self.sort_column = "MemoryMB"
        self.sort_reverse = True

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του Processes tab.
        """

        top_frame = ctk.CTkFrame(self, **card_style())
        top_frame.grid(
            row=0,
            column=0,
            padx=SPACING.card_padding,
            pady=SPACING.card_padding,
            sticky="ew"
        )
        top_frame.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="Task Manager / Processes",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(
            row=0,
            column=0,
            padx=SPACING.card_padding,
            pady=(14, 4),
            sticky="w"
        )

        self.status_label = ctk.CTkLabel(
            top_frame,
            text="Ready",
            font=FONTS.body,
            text_color=COLORS.text_secondary
        )
        self.status_label.grid(
            row=1,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, 14),
            sticky="w"
        )

        self.search_entry = ctk.CTkEntry(
            top_frame,
            placeholder_text="Filter by process name, PID, memory, path...",
            fg_color=COLORS.surface_light,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        self.search_entry.grid(
            row=0,
            column=1,
            padx=(0, 10),
            pady=(14, 4),
            sticky="ew"
        )
        self.search_entry.bind("<KeyRelease>", lambda _event: self._render_processes())

        self.quick_filter_option = ctk.CTkOptionMenu(
            top_frame,
            values=["All", "High Memory", "Has Path"],
            command=lambda _value: self._render_processes(),
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.quick_filter_option.set("All")
        self.quick_filter_option.grid(
            row=1,
            column=1,
            padx=(0, 10),
            pady=(0, 14),
            sticky="w"
        )

        refresh_button = ctk.CTkButton(
            top_frame,
            text="Refresh Processes",
            width=160,
            command=self.request_processes,
            **primary_button_style()
        )
        refresh_button.grid(
            row=0,
            column=2,
            padx=(0, SPACING.card_padding),
            pady=(14, 4)
        )

        clear_button = ctk.CTkButton(
            top_frame,
            text="Clear",
            width=80,
            command=self._clear_filter,
            **secondary_button_style()
        )
        clear_button.grid(
            row=1,
            column=2,
            padx=(0, SPACING.card_padding),
            pady=(0, 14)
        )

        self.auto_refresh_checkbox = ctk.CTkCheckBox(
            top_frame,
            text="Auto Refresh",
            command=self._toggle_auto_refresh,
            fg_color=COLORS.accent,
            hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary
        )
        self.auto_refresh_checkbox.grid(
            row=2,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, 14),
            sticky="w"
        )

        self.refresh_interval_option = ctk.CTkOptionMenu(
            top_frame,
            values=["5s", "10s", "30s"],
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.refresh_interval_option.set("10s")
        self.refresh_interval_option.grid(
            row=2,
            column=1,
            padx=(0, 10),
            pady=(0, 14),
            sticky="w"
        )

        kill_button = ctk.CTkButton(
            top_frame,
            text="Kill Selected",
            width=130,
            command=self.kill_selected_process,
            **danger_button_style()
        )
        kill_button.grid(
            row=1,
            column=1,
            padx=(150, 10),
            pady=(0, 14),
            sticky="w"
        )

        table_frame = ctk.CTkFrame(self, **card_style())
        table_frame.grid(
            row=1,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, SPACING.card_padding),
            sticky="nsew"
        )
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        tree_container = tk.Frame(
            table_frame,
            bg=COLORS.background,
            highlightthickness=0,
            bd=0
        )
        tree_container.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        tree_style = apply_treeview_style("MoonHard.Processes.Treeview")

        self.tree = ttk.Treeview(
            tree_container,
            columns=("Name", "PID", "CpuTime", "MemoryMB", "Threads", "Handles", "Path"),
            show="headings",
            height=16,
            style=tree_style
        )

        vertical_scrollbar = tk.Scrollbar(
            tree_container,
            orient="vertical",
            command=self.tree.yview,
            width=18,
            bg="#D1D5DB",
            activebackground="#16C7B7",
            troughcolor="#13282F",
            relief="flat",
            bd=0
        )

        horizontal_scrollbar = tk.Scrollbar(
            tree_container,
            orient="horizontal",
            command=self.tree.xview,
            width=18,
            bg="#D1D5DB",
            activebackground="#16C7B7",
            troughcolor="#13282F",
            relief="flat",
            bd=0
        )

        self.tree.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set
        )

        vertical_scrollbar.pack(side="right", fill="y")
        horizontal_scrollbar.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        headings = {
            "Name": "Process Name",
            "PID": "PID",
            "CpuTime": "CPU Time",
            "MemoryMB": "Memory MB",
            "Threads": "Threads",
            "Handles": "Handles",
            "Path": "Path"
        }

        widths = {
            "Name": 220,
            "PID": 90,
            "CpuTime": 120,
            "MemoryMB": 130,
            "Threads": 100,
            "Handles": 100,
            "Path": 600
        }

        for column, heading in headings.items():
            self.tree.heading(
                column,
                text=heading,
                command=lambda selected_column=column: self._sort_by_column(
                    selected_column
                )
            )
            self.tree.column(
                column,
                width=widths[column],
                minwidth=80,
                stretch=False
            )

        self.tree.bind("<Button-3>", self._show_process_context_menu)
        self.tree.bind("<Double-1>", self._open_selected_process_details)

    def request_processes(self) -> None:
        """
        Στέλνει request για ανάγνωση processes από τον client.
        """

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text="Loading processes...",
            text_color=COLORS.accent
        )

        if self.on_processes_request_callback:
            self.on_processes_request_callback(
                {
                    "type": "processes_get",
                    "request_id": request_id,
                    "client_code": self.client_code
                }
            )

    def handle_processes_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα processes.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            self.status_label.configure(
                text=f"Failed: {payload.get('error')}",
                text_color=COLORS.danger
            )
            return

        self.processes = payload.get("processes") or []

        self.status_label.configure(
            text=f"Loaded {len(self.processes)} processes.",
            text_color=COLORS.success
        )

        self._render_processes()

    def _render_processes(self) -> None:
        """
        Κάνει render τη λίστα processes με τοπικό φίλτρο.
        """

        filter_text = self.search_entry.get().strip().lower()
        quick_filter = self.quick_filter_option.get()

        self.tree.delete(*self.tree.get_children())

        shown_count = 0

        filtered_processes = []
        for process in self.processes:
            searchable_text = " ".join(
                [
                    str(process.get("name", "")),
                    str(process.get("pid", "")),
                    str(process.get("cpu_time", "")),
                    str(process.get("memory_mb", "")),
                    str(process.get("threads", "")),
                    str(process.get("handles", "")),
                    str(process.get("path", ""))
                ]
            ).lower()

            if filter_text and filter_text not in searchable_text:
                continue

            memory_mb = self._safe_float(process.get("memory_mb", 0))

            if quick_filter == "High Memory" and memory_mb < 300:
                continue

            if quick_filter == "Has Path" and not process.get("path"):
                continue

            filtered_processes.append(process)

        self.status_label.configure(
            text=f"Showing {shown_count} / {len(self.processes)} processes."
        )

        filtered_processes = self._sort_processes(filtered_processes)

        for process in filtered_processes:
            self.tree.insert(
                "",
                "end",
                values=(
                    process.get("name", ""),
                    process.get("pid", ""),
                    process.get("cpu_time", ""),
                    process.get("memory_mb", ""),
                    process.get("threads", ""),
                    process.get("handles", ""),
                    process.get("path", "")
                )
            )

        shown_count = len(filtered_processes)

    def _show_process_context_menu(self, event) -> None:
        """
        Εμφανίζει δεξί κλικ menu για process copy actions.
        """

        row_id = self.tree.identify_row(event.y)

        if row_id:
            self.tree.selection_set(row_id)

        selected_values = self._get_selected_process_values()

        if not selected_values:
            return

        menu = tk.Menu(
            self,
            tearoff=0,
            bg="#13282F",
            fg="#EAF7F7",
            activebackground="#16C7B7",
            activeforeground="#031316"
        )

        menu.add_command(
            label="Kill Process",
            command=self.kill_selected_process
        )
        menu.add_separator()
        menu.add_command(
            label="Copy Process Name",
            command=lambda: self._copy_selected_value(0, "process name")
        )
        menu.add_command(
            label="Copy PID",
            command=lambda: self._copy_selected_value(1, "PID")
        )
        menu.add_command(
            label="Copy Path",
            command=lambda: self._copy_selected_value(6, "path")
        )

        menu.tk_popup(event.x_root, event.y_root)

    def _open_selected_process_details(self, _event=None) -> None:
        """
        Ανοίγει popup με λεπτομέρειες για το επιλεγμένο process.
        """

        values = self._get_selected_process_values()

        if not values:
            self.status_label.configure(
                text="Select a process first.",
                text_color=COLORS.danger
            )
            return

        process_data = {
            "Process Name": values[0] if len(values) > 0 else "",
            "PID": values[1] if len(values) > 1 else "",
            "CPU Time": values[2] if len(values) > 2 else "",
            "Memory MB": values[3] if len(values) > 3 else "",
            "Threads": values[4] if len(values) > 4 else "",
            "Handles": values[5] if len(values) > 5 else "",
            "Path": values[6] if len(values) > 6 else ""
        }

        popup = ctk.CTkToplevel(self)
        popup.title("Process Details")
        popup.geometry("720x430")
        popup.minsize(620, 360)
        popup.configure(fg_color=COLORS.background)
        popup.grab_set()

        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            popup,
            text=f"Process Details — {process_data['Process Name']}",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(
            row=0,
            column=0,
            padx=20,
            pady=(20, 10),
            sticky="w"
        )

        details_frame = ctk.CTkFrame(
            popup,
            **card_style()
        )
        details_frame.grid(
            row=1,
            column=0,
            padx=20,
            pady=(0, 16),
            sticky="nsew"
        )
        details_frame.grid_columnconfigure(1, weight=1)

        for row_index, (label, value) in enumerate(process_data.items()):
            label_widget = ctk.CTkLabel(
                details_frame,
                text=f"{label}:",
                font=FONTS.body,
                text_color=COLORS.text_secondary
            )
            label_widget.grid(
                row=row_index,
                column=0,
                padx=(16, 12),
                pady=8,
                sticky="nw"
            )

            value_widget = ctk.CTkLabel(
                details_frame,
                text=str(value),
                font=FONTS.body,
                text_color=COLORS.text_primary,
                wraplength=500,
                justify="left"
            )
            value_widget.grid(
                row=row_index,
                column=1,
                padx=(0, 16),
                pady=8,
                sticky="w"
            )

        button_frame = ctk.CTkFrame(popup, fg_color="transparent")
        button_frame.grid(
            row=2,
            column=0,
            padx=20,
            pady=(0, 20),
            sticky="e"
        )

        copy_path_button = ctk.CTkButton(
            button_frame,
            text="Copy Path",
            width=110,
            command=lambda: self._copy_text_from_popup(
                popup,
                process_data.get("Path", ""),
                "path"
            ),
            **secondary_button_style()
        )
        copy_path_button.grid(row=0, column=0, padx=(0, 10))

        close_button = ctk.CTkButton(
            button_frame,
            text="Close",
            width=100,
            command=popup.destroy,
            **primary_button_style()
        )
        close_button.grid(row=0, column=1)

    def _get_selected_process_values(self) -> tuple:
        """
        Επιστρέφει τα values της επιλεγμένης γραμμής.
        """

        selected_items = self.tree.selection()

        if not selected_items:
            return tuple()

        values = self.tree.item(selected_items[0], "values")

        if not values:
            return tuple()

        return values

    def _get_selected_process_info(self) -> dict:
        """
        Επιστρέφει βασικά στοιχεία του επιλεγμένου process.
        """

        values = self._get_selected_process_values()

        if not values:
            return {}

        return {
            "process_name": str(values[0]),
            "pid": str(values[1])
        }

    def _copy_selected_value(self, value_index: int, label: str) -> None:
        """
        Αντιγράφει συγκεκριμένη τιμή από την επιλεγμένη γραμμή.
        """

        values = self._get_selected_process_values()

        if not values or len(values) <= value_index:
            return

        value = str(values[value_index])

        self.clipboard_clear()
        self.clipboard_append(value)

        self.status_label.configure(
            text=f"Copied {label}: {value}",
            text_color=COLORS.success
        )

    def _clear_filter(self) -> None:
        """
        Καθαρίζει τα φίλτρα.
        """

        self.search_entry.delete(0, "end")
        self.quick_filter_option.set("All")
        self._render_processes()

    def _safe_float(self, value) -> float:
        """
        Μετατρέπει τιμή σε float με ασφάλεια.
        """

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
        
    def kill_selected_process(self) -> None:
        """
        Ζητάει επιβεβαίωση και στέλνει kill request για το επιλεγμένο process.
        """

        process_info = self._get_selected_process_info()

        if not process_info:
            self.status_label.configure(
                text="Select a process first.",
                text_color=COLORS.danger
            )
            return

        process_name = process_info.get("process_name", "")
        pid = process_info.get("pid", "")

        critical_processes = {
            "system",
            "registry",
            "wininit",
            "winlogon",
            "csrss",
            "lsass",
            "services",
            "smss",
            "dwm",
            "svchost"
        }

        if process_name.strip().lower() in critical_processes:
            self.status_label.configure(
                text=f"Blocked critical process: {process_name}",
                text_color=COLORS.danger
            )
            return

        self._open_kill_confirmation_popup(process_name, pid)

    def _open_kill_confirmation_popup(self, process_name: str, pid: str) -> None:
        """
        Ανοίγει popup επιβεβαίωσης πριν τον τερματισμό process.
        """

        popup = ctk.CTkToplevel(self)
        popup.title("Confirm Process Kill")
        popup.geometry("460x220")
        popup.resizable(False, False)
        popup.configure(fg_color=COLORS.background)
        popup.grab_set()

        popup.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            popup,
            text="Kill selected process?",
            font=FONTS.subtitle,
            text_color=COLORS.danger
        )
        title.grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        message = ctk.CTkLabel(
            popup,
            text=(
                f"Process: {process_name}\n"
                f"PID: {pid}\n\n"
                "This action will force-close the process."
            ),
            font=FONTS.body,
            text_color=COLORS.text_primary,
            justify="left"
        )
        message.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        button_frame = ctk.CTkFrame(popup, fg_color="transparent")
        button_frame.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="e")

        cancel_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            command=popup.destroy,
            **secondary_button_style()
        )
        cancel_button.grid(row=0, column=0, padx=(0, 10))

        kill_button = ctk.CTkButton(
            button_frame,
            text="Kill",
            width=100,
            command=lambda: self._send_kill_process_request(popup, process_name, pid),
            **danger_button_style()
        )
        kill_button.grid(row=0, column=1)

    def _send_kill_process_request(
        self,
        popup: ctk.CTkToplevel,
        process_name: str,
        pid: str
    ) -> None:
        """
        Στέλνει kill request για process.
        """

        popup.destroy()

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text=f"Killing process: {process_name} ({pid})...",
            text_color=COLORS.accent
        )

        if self.on_process_action_callback:
            self.on_process_action_callback(
                {
                    "type": "process_kill",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "pid": pid,
                    "process_name": process_name
                }
            )
            
    def handle_process_kill_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα kill process.
        """

        if payload.get("client_code") != self.client_code:
            return

        process_name = payload.get("process_name", "")
        pid = payload.get("pid", "")

        if not payload.get("success"):
            self.status_label.configure(
                text=f"Kill failed for {process_name} ({pid}): {payload.get('error')}",
                text_color=COLORS.danger
            )
            return

        self.status_label.configure(
            text=f"Killed process: {process_name} ({pid}). Refreshing processes...",
            text_color=COLORS.success
        )

        self.request_processes()
        
    def _copy_text_from_popup(
        self,
        popup: ctk.CTkToplevel,
        text: str,
        label: str
    ) -> None:
        """
        Αντιγράφει κείμενο από popup.
        """

        if not text:
            return

        popup.clipboard_clear()
        popup.clipboard_append(text)

        self.status_label.configure(
            text=f"Copied {label}.",
            text_color=COLORS.success
        )
        
    def _toggle_auto_refresh(self) -> None:
        """
        Ενεργοποιεί ή απενεργοποιεί το auto refresh των processes.
        """

        self.auto_refresh_enabled = bool(self.auto_refresh_checkbox.get())

        if self.auto_refresh_enabled:
            self.status_label.configure(
                text="Auto refresh enabled.",
                text_color=COLORS.success
            )
            self.request_processes()
            self._schedule_auto_refresh()
        else:
            self._cancel_auto_refresh()
            self.status_label.configure(
                text="Auto refresh disabled.",
                text_color=COLORS.text_secondary
            )

    def _schedule_auto_refresh(self) -> None:
        """
        Προγραμματίζει το επόμενο auto refresh.
        """

        if not self.auto_refresh_enabled:
            return

        self._cancel_auto_refresh()

        interval_ms = self._get_refresh_interval_ms()

        self.auto_refresh_job = self.after(
            interval_ms,
            self._run_auto_refresh
        )

    def _run_auto_refresh(self) -> None:
        """
        Εκτελεί auto refresh και προγραμματίζει το επόμενο.
        """

        if not self.auto_refresh_enabled:
            return

        self.request_processes()
        self._schedule_auto_refresh()

    def _cancel_auto_refresh(self) -> None:
        """
        Ακυρώνει το υπάρχον auto refresh job.
        """

        if self.auto_refresh_job:
            try:
                self.after_cancel(self.auto_refresh_job)
            except Exception:
                pass

            self.auto_refresh_job = None

    def _get_refresh_interval_ms(self) -> int:
        """
        Επιστρέφει το interval του auto refresh σε milliseconds.
        """

        selected_interval = self.refresh_interval_option.get()

        interval_map = {
            "5s": 5000,
            "10s": 10000,
            "30s": 30000
        }

        return interval_map.get(selected_interval, 10000)
    
    def destroy(self) -> None:
        """
        Καθαρίζει το auto refresh job πριν καταστραφεί το tab.
        """

        self._cancel_auto_refresh()
        super().destroy()
        
    def _sort_by_column(self, column: str) -> None:
        """
        Αλλάζει το sorting column και κάνει render ξανά.
        """

        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = column in {
                "PID",
                "CpuTime",
                "MemoryMB",
                "Threads",
                "Handles"
            }

        self._render_processes()

    def _sort_processes(self, processes: list[dict]) -> list[dict]:
        """
        Ταξινομεί τα processes με βάση την επιλεγμένη στήλη.
        """

        key_map = {
            "Name": "name",
            "PID": "pid",
            "CpuTime": "cpu_time",
            "MemoryMB": "memory_mb",
            "Threads": "threads",
            "Handles": "handles",
            "Path": "path"
        }

        process_key = key_map.get(self.sort_column, "memory_mb")

        numeric_keys = {
            "pid",
            "cpu_time",
            "memory_mb",
            "threads",
            "handles"
        }

        if process_key in numeric_keys:
            return sorted(
                processes,
                key=lambda process: self._safe_float(process.get(process_key, 0)),
                reverse=self.sort_reverse
            )

        return sorted(
            processes,
            key=lambda process: str(process.get(process_key, "")).lower(),
            reverse=self.sort_reverse
        )