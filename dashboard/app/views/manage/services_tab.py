import uuid
import tkinter as tk
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


class ServicesTab(ctk.CTkFrame):
    """
    Tab για προβολή Windows services του client.
    """

    def __init__(
        self,
        parent,
        client_code: str,
        on_services_request_callback: Callable[[dict], None] | None = None,
        on_service_action_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το Services tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client_code = client_code
        self.on_services_request_callback = on_services_request_callback
        self.on_service_action_callback = on_service_action_callback
        self.services: list[dict] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του Services tab.
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
            text="Windows Services",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, padx=SPACING.card_padding, pady=(14, 4), sticky="w")

        self.status_label = ctk.CTkLabel(
            top_frame,
            text="Ready",
            font=FONTS.body,
            text_color=COLORS.text_secondary
        )
        self.status_label.grid(row=1, column=0, padx=SPACING.card_padding, pady=(0, 14), sticky="w")

        self.search_entry = ctk.CTkEntry(
            top_frame,
            placeholder_text="Filter by name, display name, status, start type...",
            fg_color=COLORS.surface_light,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        self.search_entry.grid(row=0, column=1, padx=(0, 10), pady=(14, 4), sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _event: self._render_services())

        self.quick_filter_option = ctk.CTkOptionMenu(
            top_frame,
            values=["All", "Running", "Stopped", "Automatic", "Manual"],
            command=lambda _value: self._render_services(),
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
            column=0,
            padx=SPACING.card_padding,
            pady=(0, 14),
            sticky="w"
        )

        refresh_button = ctk.CTkButton(
            top_frame,
            text="Refresh Services",
            width=150,
            command=self.request_services,
            **primary_button_style()
        )
        refresh_button.grid(row=0, column=2, padx=(0, SPACING.card_padding), pady=(14, 4))

        clear_button = ctk.CTkButton(
            top_frame,
            text="Clear",
            width=80,
            command=self._clear_filter,
            **secondary_button_style()
        )
        clear_button.grid(row=1, column=2, padx=(0, SPACING.card_padding), pady=(0, 14))

        start_button = ctk.CTkButton(
            top_frame,
            text="Start Selected",
            width=130,
            command=self.start_selected_service,
            **primary_button_style()
        )
        start_button.grid(
            row=1,
            column=1,
            padx=(0, 165),
            pady=(0, 14),
            sticky="e"
        )

        stop_button = ctk.CTkButton(
            top_frame,
            text="Stop Selected",
            width=130,
            command=self.stop_selected_service,
            **danger_button_style()
        )
        stop_button.grid(
            row=1,
            column=1,
            padx=(0, 310),
            pady=(0, 14),
            sticky="e"
        )
        
        restart_button = ctk.CTkButton(
            top_frame,
            text="Restart Selected",
            width=150,
            command=self.restart_selected_service,
            **danger_button_style()
        )
        restart_button.grid(
            row=1,
            column=1,
            padx=(0, 10),
            pady=(0, 14),
            sticky="e"
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

        tree_style = apply_treeview_style("MoonHard.Services.Treeview")

        self.tree = ttk.Treeview(
            tree_container,
            columns=("Name", "DisplayName", "Status", "StartType"),
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
        self.tree.bind("<Button-3>", self._show_service_context_menu)
        
        headings = {
            "Name": "Name",
            "DisplayName": "Display Name",
            "Status": "Status",
            "StartType": "Start Type"
        }

        widths = {
            "Name": 220,
            "DisplayName": 420,
            "Status": 120,
            "StartType": 140
        }

        for column, heading in headings.items():
            self.tree.heading(column, text=heading)
            self.tree.column(
                column,
                width=widths[column],
                minwidth=100,
                stretch=False
            )

    def request_services(self) -> None:
        """
        Στέλνει request για ανάγνωση Windows services από τον client.
        """

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text="Loading services...",
            text_color=COLORS.accent
        )

        if self.on_services_request_callback:
            self.on_services_request_callback(
                {
                    "type": "services_get",
                    "request_id": request_id,
                    "client_code": self.client_code
                }
            )

    def _get_selected_service_name(self) -> str:
        """
        Επιστρέφει το service name της επιλεγμένης γραμμής.
        """

        selected_items = self.tree.selection()

        if not selected_items:
            return ""

        values = self.tree.item(selected_items[0], "values")

        if not values:
            return ""

        return str(values[0])

    def _show_service_context_menu(self, event) -> None:
        """
        Εμφανίζει δεξί κλικ menu για service actions.
        """

        row_id = self.tree.identify_row(event.y)

        if row_id:
            self.tree.selection_set(row_id)

        service_name = self._get_selected_service_name()

        if not service_name:
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
            label="Start Service",
            command=self.start_selected_service
        )
        menu.add_command(
            label="Stop Service",
            command=self.stop_selected_service
        )
        menu.add_command(
            label="Restart Service",
            command=self.restart_selected_service
        )
        menu.add_separator()
        menu.add_command(
            label="Copy Service Name",
            command=self._copy_selected_service_name
        )

        menu.tk_popup(event.x_root, event.y_root)

    def _copy_selected_service_name(self) -> None:
        """
        Αντιγράφει το service name της επιλεγμένης γραμμής.
        """

        service_name = self._get_selected_service_name()

        if not service_name:
            return

        self.clipboard_clear()
        self.clipboard_append(service_name)

        self.status_label.configure(
            text=f"Copied service name: {service_name}",
            text_color=COLORS.success
        )

    def restart_selected_service(self) -> None:
        """
        Στέλνει restart request για το επιλεγμένο service.
        """

        service_name = self._get_selected_service_name()

        if not service_name:
            self.status_label.configure(
                text="Select a service first.",
                text_color=COLORS.danger
            )
            return

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text=f"Restarting service: {service_name}...",
            text_color=COLORS.accent
        )

        if self.on_service_action_callback:
            self.on_service_action_callback(
                {
                    "type": "service_restart",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "service_name": service_name
                }
            )

    def start_selected_service(self) -> None:
        """
        Στέλνει start request για το επιλεγμένο service.
        """

        service_name = self._get_selected_service_name()

        if not service_name:
            self.status_label.configure(
                text="Select a service first.",
                text_color=COLORS.danger
            )
            return

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text=f"Starting service: {service_name}...",
            text_color=COLORS.accent
        )

        if self.on_service_action_callback:
            self.on_service_action_callback(
                {
                    "type": "service_start",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "service_name": service_name
                }
            )

    def stop_selected_service(self) -> None:
        """
        Στέλνει stop request για το επιλεγμένο service.
        """

        service_name = self._get_selected_service_name()

        if not service_name:
            self.status_label.configure(
                text="Select a service first.",
                text_color=COLORS.danger
            )
            return

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text=f"Stopping service: {service_name}...",
            text_color=COLORS.accent
        )

        if self.on_service_action_callback:
            self.on_service_action_callback(
                {
                    "type": "service_stop",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "service_name": service_name
                }
            )

    def handle_service_action_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα start/stop/restart service.
        """

        if payload.get("client_code") != self.client_code:
            return

        service_name = payload.get("service_name", "")
        message_type = payload.get("type", "")

        action_name = (
            message_type
            .replace("service_", "")
            .replace("_result", "")
            .capitalize()
        )

        if not payload.get("success"):
            self.status_label.configure(
                text=f"{action_name} failed for {service_name}: {payload.get('error')}",
                text_color=COLORS.danger
            )
            return

        self.status_label.configure(
            text=f"{action_name} completed: {service_name}. Refreshing services...",
            text_color=COLORS.success
        )

        self.request_services()

    def handle_service_restart_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα restart service.
        """

        self.handle_service_action_result(payload)

    def handle_services_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα υπηρεσιών.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            self.status_label.configure(
                text=f"Failed: {payload.get('error')}",
                text_color=COLORS.danger
            )
            return

        self.services = payload.get("services") or []

        self.status_label.configure(
            text=f"Loaded {len(self.services)} services.",
            text_color=COLORS.success
        )

        self._render_services()

    def _render_services(self) -> None:
        """
        Κάνει render τη λίστα services με τοπικό φίλτρο.
        """

        filter_text = self.search_entry.get().strip().lower()
        quick_filter = self.quick_filter_option.get()

        self.tree.delete(*self.tree.get_children())

        shown_count = 0

        for service in self.services:
            searchable_text = " ".join(
                [
                    str(service.get("name", "")),
                    str(service.get("display_name", "")),
                    str(service.get("status", "")),
                    str(service.get("start_type", ""))
                ]
            ).lower()

            if filter_text and filter_text not in searchable_text:
                continue

            status = str(service.get("status", "")).lower()
            start_type = str(service.get("start_type", "")).lower()

            if quick_filter == "Running" and status != "running":
                continue

            if quick_filter == "Stopped" and status != "stopped":
                continue

            if quick_filter == "Automatic" and start_type != "auto":
                continue

            if quick_filter == "Manual" and start_type != "manual":
                continue

            self.tree.insert(
                "",
                "end",
                values=(
                    service.get("name", ""),
                    service.get("display_name", ""),
                    service.get("status", ""),
                    service.get("start_type", "")
                )
            )
            shown_count += 1

        self.status_label.configure(
            text=f"Showing {shown_count} / {len(self.services)} services."
        )

    def _clear_filter(self) -> None:
        """
        Καθαρίζει τα φίλτρα.
        """

        self.search_entry.delete(0, "end")
        self.quick_filter_option.set("All")
        self._render_services()