import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    card_style,
    primary_button_style,
    secondary_button_style
)


class ClientsView(ctk.CTkFrame):
    """
    Προβολή λίστας clients στο dashboard.
    """

    def __init__(self, parent, on_manage_callback=None) -> None:
        """
        Δημιουργεί το UI της λίστας clients.
        """

        super().__init__(parent, **card_style())

        self.client_rows: dict[str, ctk.CTkFrame] = {}
        self.clients: list[dict] = []
        self.filter_text: str = ""
        self.status_filter: str = "All"
        self.last_clients_snapshot: tuple = tuple()
        self.on_manage_callback = on_manage_callback
        
        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί τα βασικά widgets της προβολής.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=SPACING.card_padding, pady=(SPACING.card_padding, 8), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header_frame,
            text="Connected Clients",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, sticky="w")

        self.count_label = ctk.CTkLabel(
            header_frame,
            text="0 clients",
            font=FONTS.body_bold,
            text_color=COLORS.text_secondary
        )
        self.count_label.grid(row=0, column=1, sticky="e")

        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.grid(row=1, column=0, padx=SPACING.card_padding, pady=(0, 10), sticky="ew")
        filter_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            filter_frame,
            placeholder_text="Search by name, PC, user, code...",
            fg_color=COLORS.surface_light,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _event: self._apply_filters())

        self.status_option = ctk.CTkOptionMenu(
            filter_frame,
            values=["All", "Online", "Offline"],
            command=lambda _value: self._apply_filters(),
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.status_option.set("All")
        self.status_option.grid(row=0, column=1, padx=(0, 10))

        clear_button = ctk.CTkButton(
            filter_frame,
            text="Clear",
            width=80,
            command=self._clear_filters,
            **secondary_button_style()
        )
        clear_button.grid(row=0, column=2, padx=(0, 10))

        self.refresh_button = ctk.CTkButton(
            filter_frame,
            text="Refresh",
            width=90,
            command=self.force_refresh,
            **primary_button_style()
        )
        self.refresh_button.grid(row=0, column=3)

        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            corner_radius=SPACING.small_radius,
            fg_color=COLORS.background
        )
        self.scroll_frame.grid(
            row=2,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, SPACING.card_padding),
            sticky="nsew"
        )
        self.scroll_frame.grid_columnconfigure(0, weight=1)

    def update_clients(self, clients: list[dict], force: bool = False) -> bool:
        """
        Ανανεώνει τη λίστα clients μόνο όταν αλλάξει ουσιαστικά η κατάσταση.
        """

        new_snapshot = self._create_clients_snapshot(clients)

        if not force and new_snapshot == self.last_clients_snapshot:
            return False

        self.last_clients_snapshot = new_snapshot
        self.clients = clients
        self._apply_filters()

        return True

    def force_refresh(self) -> None:
        """
        Κάνει χειροκίνητο refresh της λίστας clients.
        """

        self._apply_filters()

    def _create_clients_snapshot(self, clients: list[dict]) -> tuple:
        """
        Δημιουργεί σταθερό snapshot ώστε να αποφεύγονται άσκοπα redraws.
        Δεν περιλαμβάνει το last_seen, γιατί αλλάζει συχνά από heartbeat.
        """

        snapshot_items: list[tuple] = []

        for client in clients:
            snapshot_items.append(
                (
                    str(client.get("client_code", "")),
                    str(client.get("display_name", "")),
                    str(client.get("pc_name", "")),
                    str(client.get("username", "")),
                    str(client.get("status", "")),
                    str(client.get("app_version", "")),
                )
            )

        return tuple(sorted(snapshot_items))

    def _apply_filters(self) -> None:
        """
        Εφαρμόζει search και status filter στους clients.
        """

        self.filter_text = self.search_entry.get().strip().lower()
        self.status_filter = self.status_option.get()

        filtered_clients: list[dict] = []

        for client in self.clients:
            status = str(client.get("status", "offline")).lower()

            if self.status_filter == "Online" and status != "online":
                continue

            if self.status_filter == "Offline" and status == "online":
                continue

            searchable_text = " ".join(
                [
                    str(client.get("display_name", "")),
                    str(client.get("pc_name", "")),
                    str(client.get("username", "")),
                    str(client.get("client_code", "")),
                    str(client.get("app_version", ""))
                ]
            ).lower()

            if self.filter_text and self.filter_text not in searchable_text:
                continue

            filtered_clients.append(client)

        self._render_clients(filtered_clients)


    def _clear_filters(self) -> None:
        """
        Καθαρίζει search και status filter.
        """

        self.search_entry.delete(0, "end")
        self.status_option.set("All")
        self._apply_filters()


    def _render_clients(self, clients: list[dict]) -> None:
        """
        Κάνει render τους filtered clients.
        """

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        self.client_rows.clear()

        online_count = sum(
            1
            for client in self.clients
            if str(client.get("status", "offline")).lower() == "online"
        )

        self.count_label.configure(
            text=f"{len(clients)} shown / {len(self.clients)} total · {online_count} online"
        )

        if not clients:
            empty_label = ctk.CTkLabel(
                self.scroll_frame,
                text="Δεν υπάρχουν clients με αυτά τα φίλτρα.",
                font=FONTS.body,
                text_color=COLORS.text_secondary
            )
            empty_label.grid(row=0, column=0, padx=15, pady=15, sticky="w")
            return

        for row_index, client in enumerate(clients):
            self._add_client_row(row_index, client)

    def _add_client_row(self, row_index: int, client: dict) -> None:
        """
        Προσθέτει μία γραμμή client στη λίστα.
        """

        status = str(client.get("status", "offline")).lower()
        status_color = COLORS.success if status == "online" else COLORS.danger

        client_code = client.get("client_code", "-")
        display_name = client.get("display_name") or client.get("pc_name") or "-"
        pc_name = client.get("pc_name", "-")
        username = client.get("username", "-")
        app_version = client.get("app_version", "-")
        last_seen = client.get("last_seen", "-")

        row = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=COLORS.surface,
            corner_radius=SPACING.card_radius,
            border_width=1,
            border_color=COLORS.border_soft
        )
        row.grid(row=row_index, column=0, padx=4, pady=6, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        status_label = ctk.CTkLabel(
            row,
            text="",
            width=18,
            height=18,
            corner_radius=9,
            fg_color=status_color
        )
        status_label.grid(row=0, column=0, padx=(15, 10), pady=12, sticky="w")

        main_text = (
            f"{display_name}\n"
            f"PC: {pc_name}  •  User: {username}  •  Version: {app_version}\n"
            f"Code: {client_code}\n"
            f"Last seen: {last_seen}"
        )

        info_label = ctk.CTkLabel(
            row,
            text=main_text,
            font=FONTS.body,
            text_color=COLORS.text_primary,
            justify="left",
            anchor="w"
        )
        info_label.grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        status_text = ctk.CTkLabel(
            row,
            text=status.upper(),
            font=FONTS.body_bold,
            text_color=status_color
        )
        status_text.grid(row=0, column=2, padx=15, pady=12, sticky="e")

        manage_button = ctk.CTkButton(
            row,
            text="Manage",
            width=100,
            command=lambda c=client: self._open_manage_callback(c),
            **primary_button_style()
        )
        manage_button.grid(row=0, column=3, padx=(0, 15), pady=12, sticky="e")
        
    def _open_manage_callback(self, client: dict) -> None:
        """
        Ενημερώνει το dashboard ότι ο χρήστης θέλει να διαχειριστεί συγκεκριμένο client.
        """

        if self.on_manage_callback:
            self.on_manage_callback(client)
            