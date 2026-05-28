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
        on_services_request_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το Services tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client_code = client_code
        self.on_services_request_callback = on_services_request_callback
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
        Καθαρίζει το φίλτρο.
        """

        self.search_entry.delete(0, "end")
        self._render_services()