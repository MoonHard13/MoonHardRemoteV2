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

    def __init__(
        self,
        parent,
        on_manage_callback=None,
        on_delete_callback=None,
        on_refresh_callback=None,
        on_bulk_update_callback=None,
        on_group_callback=None,
        on_create_group_callback=None,
        on_rename_group_callback=None,
        on_delete_group_callback=None
    ) -> None:
        """
        Δημιουργεί το UI της λίστας clients.
        """

        super().__init__(parent, **card_style())

        self.client_rows: dict[str, ctk.CTkFrame] = {}
        self.clients: list[dict] = []
        self.filter_text: str = ""
        self.status_filter: str = "All"
        self.groups: list[dict] = []
        self.group_filter: str = "All Groups"
        self.manage_groups_window = None
        self.manage_groups_list_frame = None
        self.last_clients_snapshot: tuple = tuple()
        self.on_manage_callback = on_manage_callback
        self.on_delete_callback = on_delete_callback 
        self.on_refresh_callback = on_refresh_callback
        self.on_bulk_update_callback = on_bulk_update_callback
        self.on_group_callback = on_group_callback
        self.on_create_group_callback = on_create_group_callback
        self.on_rename_group_callback = on_rename_group_callback
        self.on_delete_group_callback = on_delete_group_callback
                       
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
        filter_frame.grid_columnconfigure(0, weight=0, minsize=420)
        filter_frame.grid_columnconfigure(1, weight=0)
        filter_frame.grid_columnconfigure(2, weight=0)
        filter_frame.grid_columnconfigure(3, weight=1)
        filter_frame.grid_columnconfigure(4, weight=0)
        filter_frame.grid_columnconfigure(5, weight=0)
        filter_frame.grid_columnconfigure(6, weight=0)
        filter_frame.grid_columnconfigure(7, weight=0)

        self.search_entry = ctk.CTkEntry(
            filter_frame,
            placeholder_text="Search by name, PC, user, code...",
            width=420,
            fg_color=COLORS.surface_light,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 10), pady=(0, 8), sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _event: self._apply_filters())

        self.status_option = ctk.CTkOptionMenu(
            filter_frame,
            values=["All", "Online", "Offline"],
            command=lambda _value: self._apply_filters(),
            width=120,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.status_option.set("All")
        self.status_option.grid(row=0, column=1, padx=(0, 10), pady=(0, 8), sticky="e")

        self.group_option = ctk.CTkOptionMenu(
            filter_frame,
            values=["All Groups"],
            command=lambda _value: self._apply_filters(),
            width=180,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.group_option.set("All Groups")
        self.group_option.grid(row=0, column=2, padx=(0, 0), pady=(0, 8), sticky="e")

        self.manage_groups_button = ctk.CTkButton(
            filter_frame,
            text="Manage Groups",
            width=130,
            command=self._open_manage_groups_window,
            **secondary_button_style()
        )
        self.manage_groups_button.grid(row=0, column=4, padx=(0, 10), sticky="e")

        clear_button = ctk.CTkButton(
            filter_frame,
            text="Clear",
            width=80,
            command=self._clear_filters,
            **secondary_button_style()
        )
        clear_button.grid(row=0, column=5, padx=(0, 10), sticky="w")

        self.refresh_button = ctk.CTkButton(
            filter_frame,
            text="Refresh",
            width=90,
            command=self.request_refresh,
            **primary_button_style()
        )
        self.refresh_button.grid(row=0, column=6, padx=(0, 10), sticky="w")

        self.bulk_update_button = ctk.CTkButton(
            filter_frame,
            text="Bulk Update",
            width=120,
            command=self.request_bulk_update,
            **primary_button_style()
        )
        self.bulk_update_button.grid(row=0, column=7, padx=(0, 0), sticky="w")

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

    def update_groups(self, groups: list[dict]) -> None:
        """
        Ανανεώνει τη λίστα των διαθέσιμων groups στο dropdown.
        """

        self.groups = groups or []

        group_names = [
            str(group.get("name", "")).strip()
            for group in self.groups
            if str(group.get("name", "")).strip()
        ]

        unique_group_names = sorted(set(group_names), key=str.lower)
        values = ["All Groups"] + unique_group_names

        current_value = self.group_option.get()

        self.group_option.configure(values=values)

        if current_value in values:
            self.group_option.set(current_value)
        else:
            self.group_option.set("All Groups")

        self._apply_filters()

        if (
            self.manage_groups_window
            and self.manage_groups_window.winfo_exists()
            and self.manage_groups_list_frame
        ):
            self._render_manage_groups_list()

    def _open_manage_groups_window(self) -> None:
        """
        Ανοίγει παράθυρο διαχείρισης client groups.
        """

        if self.manage_groups_window and self.manage_groups_window.winfo_exists():
            self.manage_groups_window.lift()
            self.manage_groups_window.focus_force()
            return

        self.manage_groups_window = ctk.CTkToplevel(self)
        self.manage_groups_window.title("Manage Client Groups")
        self.manage_groups_window.geometry("650x500")
        self.manage_groups_window.minsize(550, 400)
        self.manage_groups_window.configure(fg_color=COLORS.background)
        
        self.manage_groups_window.grid_columnconfigure(0, weight=1)
        self.manage_groups_window.grid_rowconfigure(1, weight=1)

        self.manage_groups_window.transient(self.winfo_toplevel())
        self.manage_groups_window.lift()
        self.manage_groups_window.focus_force()
        self.manage_groups_window.attributes("-topmost", True)
        self.manage_groups_window.after(
            300,
            lambda: self.manage_groups_window.attributes("-topmost", False)
        )

        header_frame = ctk.CTkFrame(
            self.manage_groups_window,
            **card_style()
        )
        header_frame.grid(
            row=0,
            column=0,
            padx=SPACING.window_padding,
            pady=(SPACING.window_padding, 10),
            sticky="ew"
        )
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header_frame,
            text="Manage Groups",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, padx=SPACING.card_padding, pady=SPACING.card_padding, sticky="w")

        create_button = ctk.CTkButton(
            header_frame,
            text="Create Group",
            width=130,
            command=self._create_group_dialog,
            **primary_button_style()
        )
        create_button.grid(row=0, column=1, padx=SPACING.card_padding, pady=SPACING.card_padding, sticky="e")

        self.manage_groups_list_frame = ctk.CTkScrollableFrame(
            self.manage_groups_window,
            corner_radius=SPACING.small_radius,
            fg_color=COLORS.surface
        )
        self.manage_groups_list_frame.grid(
            row=1,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, SPACING.window_padding),
            sticky="nsew"
        )
        self.manage_groups_list_frame.grid_columnconfigure(0, weight=1)

        self._render_manage_groups_list()

    def _render_manage_groups_list(self) -> None:
        """
        Κάνει render τη λίστα groups μέσα στο Manage Groups window.
        """

        if not self.manage_groups_list_frame:
            return

        for widget in self.manage_groups_list_frame.winfo_children():
            widget.destroy()

        if not self.groups:
            empty_label = ctk.CTkLabel(
                self.manage_groups_list_frame,
                text="No groups found.",
                font=FONTS.body,
                text_color=COLORS.text_secondary
            )
            empty_label.grid(row=0, column=0, padx=15, pady=15, sticky="w")
            return

        for row_index, group in enumerate(self.groups):
            self._add_group_row(row_index, group)

    def _add_group_row(self, row_index: int, group: dict) -> None:
        """
        Προσθέτει μία γραμμή group στο Manage Groups window.
        """

        group_name = str(group.get("name", ""))
        is_default = bool(group.get("is_default", False))

        clients_count = sum(
            1
            for client in self.clients
            if str(client.get("group_id", "")) == str(group.get("id", ""))
        )

        row = ctk.CTkFrame(
            self.manage_groups_list_frame,
            fg_color=COLORS.background,
            corner_radius=SPACING.card_radius,
            border_width=1,
            border_color=COLORS.border_soft
        )
        row.grid(row=row_index, column=0, padx=8, pady=6, sticky="ew")

        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=0)
        row.grid_columnconfigure(2, weight=0)

        info_text = f"{group_name}\nClients: {clients_count}"

        if is_default:
            info_text += "  •  Default group"

        info_label = ctk.CTkLabel(
            row,
            text=info_text,
            font=FONTS.body,
            text_color=COLORS.text_primary,
            justify="left",
            anchor="w"
        )
        info_label.grid(
            row=0,
            column=0,
            padx=15,
            pady=12,
            sticky="ew"
        )

        rename_button = ctk.CTkButton(
            row,
            text="Rename",
            width=100,
            command=lambda g=group: self._rename_group_dialog(g),
            state="disabled" if is_default else "normal",
            **secondary_button_style()
        )
        rename_button.grid(
            row=0,
            column=1,
            padx=(0, 8),
            pady=12,
            sticky="e"
        )

        delete_button = ctk.CTkButton(
            row,
            text="Delete",
            width=90,
            command=lambda g=group: self._delete_group_dialog(g),
            state="disabled" if is_default else "normal",
            fg_color=COLORS.danger,
            hover_color=COLORS.danger_hover,
            text_color=COLORS.text_primary
        )
        delete_button.grid(
            row=0,
            column=2,
            padx=(0, 15),
            pady=12,
            sticky="e"
        )

    def _create_group_dialog(self) -> None:
        """
        Ανοίγει custom popup για δημιουργία νέου group.
        """

        create_window = ctk.CTkToplevel(self.manage_groups_window or self)
        create_window.title("Create Group")
        create_window.geometry("420x220")
        create_window.resizable(False, False)
        create_window.configure(fg_color=COLORS.background)

        create_window.transient(self.manage_groups_window or self.winfo_toplevel())
        create_window.lift()
        create_window.focus_force()
        create_window.attributes("-topmost", True)
        create_window.after(
            300,
            lambda: create_window.attributes("-topmost", False)
        )

        create_window.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            create_window,
            text="Create New Group",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title_label.grid(
            row=0,
            column=0,
            padx=20,
            pady=(20, 8),
            sticky="w"
        )

        name_entry = ctk.CTkEntry(
            create_window,
            placeholder_text="Group name...",
            width=360,
            fg_color=COLORS.surface_light,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        name_entry.grid(
            row=1,
            column=0,
            padx=20,
            pady=(0, 18),
            sticky="ew"
        )
        name_entry.focus_set()

        buttons_frame = ctk.CTkFrame(create_window, fg_color="transparent")
        buttons_frame.grid(
            row=2,
            column=0,
            padx=20,
            pady=(0, 20),
            sticky="e"
        )

        cancel_button = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            width=90,
            command=create_window.destroy,
            **secondary_button_style()
        )
        cancel_button.grid(row=0, column=0, padx=(0, 10))

        def submit_create_group() -> None:
            group_name = name_entry.get().strip()

            if not group_name:
                return

            print(f"Creating group from UI: {group_name}")

            if self.on_create_group_callback:
                self.on_create_group_callback(group_name)

            create_window.destroy()

        save_button = ctk.CTkButton(
            buttons_frame,
            text="Create",
            width=90,
            command=submit_create_group,
            **primary_button_style()
        )
        save_button.grid(row=0, column=1)

        create_window.bind("<Return>", lambda _event: submit_create_group())
        create_window.bind("<Escape>", lambda _event: create_window.destroy())

    def _rename_group_dialog(self, group: dict) -> None:
        """
        Ζητάει νέο όνομα για group.
        """

        group_name = str(group.get("name", ""))

        dialog = ctk.CTkInputDialog(
            text=f"Enter new name for group:\n\n{group_name}",
            title="Rename Group"
        )

        new_name = dialog.get_input()

        if new_name is None:
            return

        clean_new_name = new_name.strip()

        if not clean_new_name:
            return

        if self.on_rename_group_callback:
            self.on_rename_group_callback(group, clean_new_name)

    def _delete_group_dialog(self, group: dict) -> None:
        """
        Ζητάει επιβεβαίωση για διαγραφή group.
        Οι clients θα μεταφερθούν στο Ungrouped από τον server.
        """

        group_name = str(group.get("name", ""))
        clients_count = sum(
            1
            for client in self.clients
            if str(client.get("group_id", "")) == str(group.get("id", ""))
        )

        confirm = ctk.CTkInputDialog(
            text=(
                f"Type DELETE to delete this group:\n\n"
                f"{group_name}\n\n"
                f"Clients in this group: {clients_count}\n\n"
                f"Clients will be moved to Ungrouped."
            ),
            title="Delete Group"
        )

        answer = confirm.get_input()

        if answer != "DELETE":
            return

        if self.on_delete_group_callback:
            self.on_delete_group_callback(group)

    def force_refresh(self) -> None:
        """
        Κάνει χειροκίνητο refresh της λίστας clients.
        """

        self._apply_filters()

    def request_refresh(self) -> None:
        """
        Ζητάει φρέσκια λίστα clients από τον server και κάνει τοπικό redraw.
        """

        if self.on_refresh_callback:
            self.on_refresh_callback()

        self.force_refresh()

    def request_bulk_update(self) -> None:
        """
        Ζητάει από το dashboard να ξεκινήσει bulk update για online/connected clients.
        """

        if self.on_bulk_update_callback:
            self.on_bulk_update_callback(self.clients)

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
                    str(client.get("ws_connected", "")),
                    str(client.get("app_version", "")),
                    str(client.get("amv_version", "")),
                    str(client.get("bo_version", "")),
                    str(client.get("etp_version", "")),
                    str(client.get("aws_version", "")),
                    str(client.get("group_id", "")),
                    str(client.get("group_name", "")),
                )
            )

        return tuple(sorted(snapshot_items))

    def _apply_filters(self) -> None:
        """
        Εφαρμόζει search και status filter στους clients.
        """

        self.filter_text = self.search_entry.get().strip().lower()
        self.status_filter = self.status_option.get()
        self.group_filter = self.group_option.get()

        filtered_clients: list[dict] = []

        for client in self.clients:
            status = str(client.get("status", "offline")).lower()

            if self.status_filter == "Online" and status != "online":
                continue

            if self.status_filter == "Offline" and status == "online":
                continue

            group_name = str(client.get("group_name") or "Ungrouped")

            if self.group_filter != "All Groups" and group_name != self.group_filter:
                continue

            searchable_text = " ".join(
                [
                    str(client.get("display_name", "")),
                    str(client.get("pc_name", "")),
                    str(client.get("username", "")),
                    str(client.get("client_code", "")),
                    str(client.get("app_version", "")),
                    str(client.get("amv_version", "")),
                    str(client.get("bo_version", "")),
                    str(client.get("etp_version", "")),
                    str(client.get("aws_version", "")),
                    str(client.get("group_name", ""))
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
        self.group_option.set("All Groups")
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
        ws_connected = bool(client.get("ws_connected", False))
        controllable_text = "CONNECTED" if ws_connected else "NOT CONNECTED"
        
        client_code = client.get("client_code", "-")
        display_name = client.get("display_name") or client.get("pc_name") or "-"
        pc_name = client.get("pc_name", "-")
        username = client.get("username", "-")
        app_version = client.get("app_version", "-")
        last_seen = client.get("last_seen", "-")
        group_name = client.get("group_name") or "Ungrouped"
        amv_version = client.get("amv_version") or "-"
        bo_version = client.get("bo_version") or "-"
        etp_version = client.get("etp_version") or "-"
        aws_version = client.get("aws_version") or "-"

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
            f"PC: {pc_name}  •  User: {username}  •  MoonHard: {app_version}\n"
            f"AMV: {amv_version}  •  BO: {bo_version}  •  ETP: {etp_version}  •  AWS: {aws_version}\n"
            f"Group: {group_name}  •  Code: {client_code}\n"
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
            text=f"{status.upper()} / {controllable_text}",
            font=FONTS.body_bold,
            text_color=status_color
        )
        status_text.grid(row=0, column=2, padx=15, pady=12, sticky="e")

        manage_button = ctk.CTkButton(
            row,
            text="Manage",
            width=100,
            command=lambda c=client: self._open_manage_callback(c),
            state="normal" if ws_connected else "disabled",
            **primary_button_style()
        )
        manage_button.grid(row=0, column=3, padx=(0, 8), pady=12, sticky="e")

        group_button = ctk.CTkButton(
            row,
            text="Group",
            width=80,
            command=lambda c=client: self._open_group_callback(c),
            **secondary_button_style()
        )
        group_button.grid(row=0, column=4, padx=(0, 8), pady=12, sticky="e")
        
        delete_button = ctk.CTkButton(
            row,
            text="Delete",
            width=80,
            command=lambda c=client: self._open_delete_callback(c),
            state="disabled" if ws_connected else "normal",
            fg_color=COLORS.danger,
            hover_color=COLORS.danger_hover,
            text_color=COLORS.text_primary
        )
        delete_button.grid(row=0, column=5, padx=(0, 15), pady=12, sticky="e")
        
    def _open_manage_callback(self, client: dict) -> None:
        """
        Ενημερώνει το dashboard ότι ο χρήστης θέλει να διαχειριστεί συγκεκριμένο client.
        """

        if self.on_manage_callback:
            self.on_manage_callback(client)

    def _open_group_callback(self, client: dict) -> None:
        """
        Ανοίγει dropdown επιλογής group για τον client.
        Τα groups έρχονται από το Manage Groups / server.
        """

        client_code = client.get("client_code", "-")
        display_name = client.get("display_name") or client.get("pc_name") or client_code
        current_group = client.get("group_name") or "Ungrouped"

        group_names = [
            str(group.get("name", "")).strip()
            for group in self.groups
            if str(group.get("name", "")).strip()
        ]

        group_names = sorted(set(group_names), key=str.lower)

        if not group_names:
            group_names = ["Ungrouped"]

        if current_group not in group_names:
            group_names.insert(0, current_group)

        group_window = ctk.CTkToplevel(self)
        group_window.title("Change Client Group")
        group_window.geometry("420x220")
        group_window.resizable(False, False)
        group_window.configure(fg_color=COLORS.background)

        group_window.transient(self.winfo_toplevel())
        group_window.lift()
        group_window.focus_force()
        group_window.attributes("-topmost", True)
        group_window.after(
            300,
            lambda: group_window.attributes("-topmost", False)
        )

        group_window.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            group_window,
            text="Change Client Group",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title_label.grid(
            row=0,
            column=0,
            padx=20,
            pady=(20, 8),
            sticky="w"
        )

        client_label = ctk.CTkLabel(
            group_window,
            text=f"{display_name}\n{client_code}",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            justify="left",
            anchor="w"
        )
        client_label.grid(
            row=1,
            column=0,
            padx=20,
            pady=(0, 12),
            sticky="ew"
        )

        selected_group = ctk.StringVar(value=current_group)

        group_option = ctk.CTkOptionMenu(
            group_window,
            values=group_names,
            variable=selected_group,
            width=360,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        group_option.grid(
            row=2,
            column=0,
            padx=20,
            pady=(0, 18),
            sticky="ew"
        )

        buttons_frame = ctk.CTkFrame(group_window, fg_color="transparent")
        buttons_frame.grid(
            row=3,
            column=0,
            padx=20,
            pady=(0, 20),
            sticky="e"
        )

        cancel_button = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            width=90,
            command=group_window.destroy,
            **secondary_button_style()
        )
        cancel_button.grid(row=0, column=0, padx=(0, 10))

        def apply_group_change() -> None:
            new_group_name = selected_group.get().strip()

            if not new_group_name:
                return

            if self.on_group_callback:
                self.on_group_callback(client, new_group_name)

            group_window.destroy()

        save_button = ctk.CTkButton(
            buttons_frame,
            text="Save",
            width=90,
            command=apply_group_change,
            **primary_button_style()
        )
        save_button.grid(row=0, column=1)
            
    def _open_delete_callback(self, client: dict) -> None:
        """
        Ζητάει επιβεβαίωση και ενημερώνει το dashboard ότι ο χρήστης θέλει διαγραφή client.
        """

        client_code = client.get("client_code", "-")
        display_name = client.get("display_name") or client.get("pc_name") or client_code

        confirm = ctk.CTkInputDialog(
            text=(
                f"Type DELETE to remove this client from dashboard and database:\n\n"
                f"{display_name}\n{client_code}"
            ),
            title="Confirm Client Delete"
        )

        answer = confirm.get_input()

        if answer != "DELETE":
            return

        if self.on_delete_callback:
            self.on_delete_callback(client)