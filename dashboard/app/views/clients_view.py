from typing import Any

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

        self.client_rows: dict[str, dict[str, Any]] = {}
        self.empty_label: ctk.CTkLabel | None = None
        self.clients: list[dict] = []
        self.filter_text: str = ""
        self.status_filter: str = "All"
        self.group_filter: str = "All Groups"
        self.filter_after_job = None
        self.groups: list[dict] = []
        self.manage_groups_window = None
        self.manage_groups_list_frame = None
        self.last_clients_snapshot: tuple = tuple()
        self._layout_after_job = None
        self._wide_layout: bool | None = None
        self._shortcut_bindings: list[tuple[str, str | None]] = []
        self._shortcut_parent = self.winfo_toplevel()

        self.on_manage_callback = on_manage_callback
        self.on_delete_callback = on_delete_callback
        self.on_refresh_callback = on_refresh_callback
        self.on_bulk_update_callback = on_bulk_update_callback
        self.on_group_callback = on_group_callback
        self.on_create_group_callback = on_create_group_callback
        self.on_rename_group_callback = on_rename_group_callback
        self.on_delete_group_callback = on_delete_group_callback
                       
        self._build_ui()
        self.bind("<Configure>", self._schedule_layout, add="+")
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        """
        Δημιουργεί τα βασικά widgets της προβολής.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(
            row=0,
            column=0,
            padx=SPACING.card_padding,
            pady=(SPACING.card_padding, 12),
            sticky="ew"
        )
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.title_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.title_frame.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            self.title_frame,
            text="Clients",
            font=FONTS.title,
            text_color=COLORS.text_primary,
            anchor="w"
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            self.title_frame,
            text="Search, monitor and manage registered workstations",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w"
        ).grid(row=1, column=0, pady=(2, 0), sticky="w")

        self.metrics_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.metrics_frame.grid(row=0, column=1, padx=(12, 0), sticky="e")

        self.count_label = ctk.CTkLabel(
            self.metrics_frame,
            text="0 / 0 shown",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            fg_color=COLORS.surface_light,
            corner_radius=8,
            height=30
        )
        self.count_label.grid(row=0, column=0, padx=(0, 6))

        self.online_count_label = ctk.CTkLabel(
            self.metrics_frame,
            text="0 online",
            font=FONTS.small,
            text_color=COLORS.success,
            fg_color=COLORS.success_soft,
            corner_radius=8,
            height=30
        )
        self.online_count_label.grid(row=0, column=1, padx=(0, 6))

        self.connected_count_label = ctk.CTkLabel(
            self.metrics_frame,
            text="0 controllable",
            font=FONTS.small,
            text_color=COLORS.info,
            fg_color=COLORS.info_soft,
            corner_radius=8,
            height=30
        )
        self.connected_count_label.grid(row=0, column=2, padx=(0, 6))

        self.connection_status_label = ctk.CTkLabel(
            self.metrics_frame,
            text="Connecting",
            font=FONTS.small,
            text_color=COLORS.accent,
            fg_color=COLORS.accent_soft,
            corner_radius=8,
            height=30
        )
        self.connection_status_label.grid(row=0, column=3)

        self.toolbar_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS.background,
            corner_radius=SPACING.small_radius,
            border_width=1,
            border_color=COLORS.border_soft
        )
        self.toolbar_frame.grid(
            row=1,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, 10),
            sticky="ew"
        )
        self.toolbar_frame.grid_columnconfigure(0, weight=1)

        self.filters_frame = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.filters_frame.grid_columnconfigure(0, weight=1, minsize=260)

        self.search_entry = ctk.CTkEntry(
            self.filters_frame,
            placeholder_text="Search name, PC, user, code or version...",
            height=36,
            fg_color=COLORS.surface,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _event: self._schedule_filter_apply())

        self.status_option = ctk.CTkOptionMenu(
            self.filters_frame,
            values=["All", "Online", "Offline"],
            command=lambda _value: self._apply_filters(),
            width=125,
            height=36,
            dynamic_resizing=False,
            fg_color=COLORS.surface,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.status_option.set("All")
        self.status_option.grid(row=0, column=1, padx=(0, 8))

        self.group_option = ctk.CTkOptionMenu(
            self.filters_frame,
            values=["All Groups"],
            command=lambda _value: self._apply_filters(),
            width=180,
            height=36,
            dynamic_resizing=False,
            fg_color=COLORS.surface,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.group_option.set("All Groups")
        self.group_option.grid(row=0, column=2)

        self.actions_frame = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")

        self.manage_groups_button = ctk.CTkButton(
            self.actions_frame,
            text="Groups  ·  Ctrl+G",
            width=145,
            height=36,
            command=self._open_manage_groups_window,
            **secondary_button_style()
        )
        self.manage_groups_button.grid(row=0, column=0, padx=(0, 8))

        self.clear_button = ctk.CTkButton(
            self.actions_frame,
            text="Clear  ·  Ctrl+L",
            width=120,
            height=36,
            command=self._clear_filters,
            **secondary_button_style()
        )
        self.clear_button.grid(row=0, column=1, padx=(0, 8))

        self.refresh_button = ctk.CTkButton(
            self.actions_frame,
            text="Refresh  ·  F5",
            width=120,
            height=36,
            command=self.request_refresh,
            **primary_button_style()
        )
        self.refresh_button.grid(row=0, column=2, padx=(0, 8))

        self.bulk_update_button = ctk.CTkButton(
            self.actions_frame,
            text="Bulk update  ·  Ctrl+U",
            width=175,
            height=36,
            command=self.request_bulk_update,
            **primary_button_style()
        )
        self.bulk_update_button.grid(row=0, column=3)

        self._apply_layout()

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

    def _schedule_layout(self, _event=None) -> None:
        """Συγχωνεύει τα διαδοχικά resize events πριν αλλάξει τη διάταξη."""

        if self._layout_after_job:
            self.after_cancel(self._layout_after_job)
        self._layout_after_job = self.after(70, self._apply_layout)

    def _apply_layout(self) -> None:
        """Προσαρμόζει header και toolbar στο διαθέσιμο πλάτος."""

        self._layout_after_job = None
        wide = self.winfo_width() >= 1250

        self.header_frame.grid_columnconfigure(1, weight=0 if wide else 1)
        self.title_frame.grid(row=0, column=0, sticky="w")
        self.metrics_frame.grid(
            row=0 if wide else 1,
            column=1 if wide else 0,
            padx=(12, 0) if wide else 0,
            pady=0 if wide else (10, 0),
            sticky="e" if wide else "w"
        )

        self.toolbar_frame.grid_columnconfigure(0, weight=1)
        self.toolbar_frame.grid_columnconfigure(1, weight=0 if wide else 1)
        self.filters_frame.grid(
            row=0,
            column=0,
            padx=(14, 8) if wide else 14,
            pady=14,
            sticky="ew"
        )
        self.actions_frame.grid(
            row=0 if wide else 1,
            column=1 if wide else 0,
            padx=(8, 14) if wide else 14,
            pady=14 if wide else (0, 14),
            sticky="e"
        )
        detail_wrap = max(320, self.winfo_width() - 430)
        for row_data in self.client_rows.values():
            for label_name in ("identity_label", "versions_label", "meta_label"):
                label = row_data.get(label_name)
                if label and label.winfo_exists():
                    label.configure(wraplength=detail_wrap)
        self._wide_layout = wide

    def set_connection_status(self, status: str) -> None:
        """Ενημερώνει το compact badge σύνδεσης του dashboard."""

        normalized = str(status or "").strip().lower()
        if normalized == "online":
            text = "Dashboard online"
            text_color = COLORS.success
            background = COLORS.success_soft
        elif normalized in {"σύνδεση...", "connecting", "connecting..."}:
            text = "Connecting"
            text_color = COLORS.accent
            background = COLORS.accent_soft
        else:
            text = status or "Offline"
            text_color = COLORS.danger
            background = COLORS.danger_soft

        self.connection_status_label.configure(
            text=text,
            text_color=text_color,
            fg_color=background
        )

    def _bind_shortcuts(self) -> None:
        """Συνδέει τα shortcuts της αρχικής οθόνης στο κεντρικό παράθυρο."""

        shortcuts = (
            ("<Control-f>", lambda: self.search_entry.focus_set()),
            ("<Control-l>", self._clear_filters),
            ("<Control-g>", self._open_manage_groups_window),
            ("<Control-u>", self.request_bulk_update),
            ("<F5>", self.request_refresh),
        )
        for key, callback in shortcuts:
            binding_id = self._shortcut_parent.bind(
                key,
                lambda _event, action=callback: self._run_visible_shortcut(action),
                add="+"
            )
            self._shortcut_bindings.append((key, binding_id))

    def _run_visible_shortcut(self, callback) -> str | None:
        """Εκτελεί shortcut μόνο όταν η αρχική προβολή είναι ορατή."""

        if not self.winfo_exists() or not self.winfo_viewable():
            return None
        callback()
        return "break"

    def update_clients(self, clients: list[dict], force: bool = False) -> bool:
        """
        Ανανεώνει τη λίστα clients μόνο όταν αλλάξει ουσιαστικά η κατάσταση.
        Για full clients_list δεν καταστρέφει όλα τα rows, απλά συγχρονίζει hide/show/update.
        """

        new_snapshot = self._create_clients_snapshot(clients)

        if not force and new_snapshot == self.last_clients_snapshot:
            return False

        self.last_clients_snapshot = new_snapshot
        self.clients = clients
        self._apply_filters()

        return True

    def update_single_client(self, client: dict, force: bool = True) -> bool:
        """
        Ανανεώνει ή προσθέτει έναν μόνο client χωρίς να ξαναχτίζει όλη τη λίστα.

        Αν ο client είναι νέος και δεν υπάρχει ήδη στη λίστα,
        μπαίνει πρώτος ώστε να φαίνεται άμεσα στην αρχή.
        """

        if not client:
            return False

        client_code = str(client.get("client_code", "")).strip()

        if not client_code:
            return False

        updated_clients: list[dict] = []
        found = False

        for existing_client in self.clients:
            existing_code = str(existing_client.get("client_code", "")).strip()

            if existing_code == client_code:
                updated_clients.append(client)
                found = True
            else:
                updated_clients.append(existing_client)

        if not found:
            updated_clients.insert(0, client)

        self.clients = updated_clients
        self.last_clients_snapshot = self._create_clients_snapshot(self.clients)

        if client_code in self.client_rows:
            self._update_client_row_widgets(client_code, client)

        self._apply_filters()

        return True

    def _client_matches_current_filters(self, client: dict) -> bool:
        """
        Ελέγχει αν ένας client περνάει τα τρέχοντα φίλτρα της λίστας.
        """

        filter_text = self.search_entry.get().strip().lower()
        status_filter = self.status_option.get()
        group_filter = self.group_option.get()

        status = str(client.get("status", "offline")).lower()

        if status_filter == "Online" and status != "online":
            return False

        if status_filter == "Offline" and status == "online":
            return False

        group_name = str(client.get("group_name") or "Ungrouped")

        if group_filter != "All Groups" and group_name != group_filter:
            return False

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

        if filter_text and filter_text not in searchable_text:
            return False

        return True


    def _get_filtered_clients(self) -> list[dict]:
        """
        Επιστρέφει τους clients που περνάνε τα τρέχοντα φίλτρα.
        """

        return [
            client
            for client in self.clients
            if self._client_matches_current_filters(client)
        ]


    def _update_count_label(self, visible_count: int) -> None:
        """
        Ανανεώνει μόνο το counter της λίστας clients.
        """

        online_count = sum(
            1
            for client in self.clients
            if str(client.get("status", "offline")).lower() == "online"
        )
        connected_count = sum(
            1
            for client in self.clients
            if bool(client.get("ws_connected", False))
        )

        self.count_label.configure(
            text=f"{visible_count} / {len(self.clients)} shown"
        )
        self.online_count_label.configure(text=f"{online_count} online")
        self.connected_count_label.configure(text=f"{connected_count} controllable")


    def _hide_empty_label(self) -> None:
        """
        Κρύβει το μήνυμα άδειας λίστας όταν υπάρχουν ορατοί clients.
        """

        if self.empty_label and self.empty_label.winfo_exists():
            self.empty_label.destroy()

        self.empty_label = None


    def _show_empty_label_if_needed(self, visible_count: int) -> None:
        """
        Εμφανίζει μήνυμα άδειας λίστας μόνο όταν δεν υπάρχει κανένας ορατός client.
        """

        if visible_count > 0:
            self._hide_empty_label()
            return

        if self.empty_label and self.empty_label.winfo_exists():
            return

        self.empty_label = ctk.CTkLabel(
            self.scroll_frame,
            text="Δεν υπάρχουν clients με αυτά τα φίλτρα.",
            font=FONTS.body,
            text_color=COLORS.text_secondary
        )
        self.empty_label.grid(row=0, column=0, padx=15, pady=15, sticky="w")


    def _regrid_visible_client_rows(self, visible_clients: list[dict]) -> None:
        """
        Κάνει μόνο re-position στα υπάρχοντα rows χωρίς destroy/recreate.
        """

        for row_index, visible_client in enumerate(visible_clients):
            client_code = str(visible_client.get("client_code", "")).strip()
            row_data = self.client_rows.get(client_code)

            if not row_data:
                continue

            row = row_data.get("frame")

            if not row or not row.winfo_exists():
                continue

            row.grid(row=row_index, column=0, padx=4, pady=6, sticky="ew")


    def _refresh_single_client_row(self, client_code: str, client: dict) -> None:
        """
        Ανανεώνει μόνο το row ενός client.
        Δεν καταστρέφει όλη τη λίστα.
        """

        visible_clients = self._get_filtered_clients()
        visible_count = len(visible_clients)
        visible_codes = {
            str(visible_client.get("client_code", "")).strip()
            for visible_client in visible_clients
        }

        row_data = self.client_rows.get(client_code)

        if client_code not in visible_codes:
            if row_data:
                row = row_data.get("frame")

                if row and row.winfo_exists():
                    row.destroy()

                self.client_rows.pop(client_code, None)

            self._regrid_visible_client_rows(visible_clients)
            self._update_count_label(visible_count)
            self._show_empty_label_if_needed(visible_count)
            return

        self._hide_empty_label()

        if row_data:
            self._update_client_row_widgets(client_code, client)
        else:
            self._add_client_row(visible_count - 1, client)

        self._regrid_visible_client_rows(visible_clients)
        self._update_count_label(visible_count)


    def _build_client_main_text(self, client: dict) -> str:
        """
        Δημιουργεί το κείμενο πληροφοριών για ένα client row.
        """

        presentation = self._client_presentation(client)

        return (
            f"{presentation['name']}\n"
            f"{presentation['identity']}\n"
            f"{presentation['versions']}\n"
            f"{presentation['meta']}"
        )

    @staticmethod
    def _client_presentation(client: dict) -> dict[str, str]:
        """Μετατρέπει τα raw client δεδομένα σε σύντομα UI strings."""

        client_code = str(client.get("client_code") or "-")
        display_name = str(client.get("display_name") or client.get("pc_name") or "-")
        pc_name = str(client.get("pc_name") or "-")
        username = str(client.get("username") or "-")
        app_version = str(client.get("app_version") or "-")
        last_seen = str(client.get("last_seen") or "-")
        group_name = str(client.get("group_name") or "Ungrouped")
        amv_version = str(client.get("amv_version") or "-")
        bo_version = str(client.get("bo_version") or "-")
        etp_version = str(client.get("etp_version") or "-")
        aws_version = str(client.get("aws_version") or "-")

        return {
            "name": display_name,
            "group": group_name,
            "identity": f"PC  {pc_name}   ·   User  {username}",
            "versions": (
                f"MoonHard  {app_version}   ·   AMV  {amv_version}   ·   "
                f"BO  {bo_version}   ·   ETP  {etp_version}   ·   AWS  {aws_version}"
            ),
            "meta": f"Code  {client_code}   ·   Last seen  {last_seen}",
        }


    def _update_client_row_widgets(self, client_code: str, client: dict) -> None:
        """
        Ανανεώνει τα widgets ενός υπάρχοντος row.
        """

        row_data = self.client_rows.get(client_code)

        if not row_data:
            return

        status = str(client.get("status", "offline")).lower()
        ws_connected = bool(client.get("ws_connected", False))
        presentation = self._client_presentation(client)

        if status == "online" and ws_connected:
            status_color = COLORS.success
            status_background = COLORS.success_soft
            status_value = "ONLINE  ·  CONNECTED"
        elif status == "online":
            status_color = COLORS.warning
            status_background = COLORS.warning_soft
            status_value = "ONLINE  ·  NOT CONNECTED"
        else:
            status_color = COLORS.danger
            status_background = COLORS.danger_soft
            status_value = "OFFLINE"

        status_label = row_data.get("status_label")
        name_label = row_data.get("name_label")
        group_label = row_data.get("group_label")
        identity_label = row_data.get("identity_label")
        versions_label = row_data.get("versions_label")
        meta_label = row_data.get("meta_label")
        status_text = row_data.get("status_text")
        manage_button = row_data.get("manage_button")
        group_button = row_data.get("group_button")
        delete_button = row_data.get("delete_button")

        if status_label:
            status_label.configure(
                fg_color=COLORS.success if status == "online" else COLORS.danger,
                hover_color=COLORS.success if status == "online" else COLORS.danger
            )

        if name_label:
            name_label.configure(text=presentation["name"])
        if group_label:
            group_label.configure(text=presentation["group"])
        if identity_label:
            identity_label.configure(text=presentation["identity"])
        if versions_label:
            versions_label.configure(text=presentation["versions"])
        if meta_label:
            meta_label.configure(text=presentation["meta"])

        if status_text:
            status_text.configure(
                text=status_value,
                text_color=status_color,
                fg_color=status_background,
                hover_color=status_background
            )

        if manage_button:
            manage_button.configure(
                state="normal" if ws_connected else "disabled",
                command=lambda c=client: self._open_manage_callback(c)
            )

        if group_button:
            group_button.configure(
                command=lambda c=client: self._open_group_callback(c)
            )

        if delete_button:
            delete_button.configure(
                state="disabled" if ws_connected else "normal",
                command=lambda c=client: self._open_delete_callback(c)
            )

        row_data["client"] = client

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

    def _schedule_filter_apply(self) -> None:
        """
        Καθυστερεί ελάχιστα το search filtering ώστε να μην τρέχει full UI logic σε κάθε πλήκτρο.
        """

        if self.filter_after_job:
            try:
                self.after_cancel(self.filter_after_job)
            except Exception:
                pass

            self.filter_after_job = None

        self.filter_after_job = self.after(150, self._apply_filters)

    def _apply_visible_client_rows(self, visible_clients: list[dict]) -> None:
        """
        Εμφανίζει μόνο τα rows που περνάνε τα φίλτρα.
        Δεν καταστρέφει και δεν ξαναχτίζει όλη τη λίστα.
        """

        all_current_codes = {
            str(client.get("client_code", "")).strip()
            for client in self.clients
        }

        visible_codes = {
            str(client.get("client_code", "")).strip()
            for client in visible_clients
        }

        self._hide_empty_label()

        for client_code, row_data in list(self.client_rows.items()):
            row = row_data.get("frame")

            if not row or not row.winfo_exists():
                self.client_rows.pop(client_code, None)
                continue

            if client_code not in all_current_codes:
                row.destroy()
                self.client_rows.pop(client_code, None)
                continue

            if client_code not in visible_codes:
                row.grid_remove()

        for row_index, client in enumerate(visible_clients):
            client_code = str(client.get("client_code", "")).strip()

            if not client_code:
                continue

            row_data = self.client_rows.get(client_code)

            if row_data:
                self._update_client_row_widgets(client_code, client)
            else:
                self._add_client_row(row_index, client)
                row_data = self.client_rows.get(client_code)

            if not row_data:
                continue

            row = row_data.get("frame")

            if not row or not row.winfo_exists():
                continue

            row.grid(row=row_index, column=0, padx=4, pady=6, sticky="ew")

        self._update_count_label(len(visible_clients))
        self._show_empty_label_if_needed(len(visible_clients))

    def _apply_filters(self) -> None:
        """
        Εφαρμόζει search/status/group φίλτρα χωρίς να ξαναχτίζει όλα τα rows.
        """

        self.filter_after_job = None

        self.filter_text = self.search_entry.get().strip().lower()
        self.status_filter = self.status_option.get()
        selected_group = self.group_option.get()
        group_changed = selected_group != self.group_filter
        self.group_filter = selected_group

        visible_clients = self._get_filtered_clients()

        # Η αλλαγή group μεταφέρει συνήθως rows που είχαν δημιουργηθεί χαμηλά
        # στη scroll λίστα. Το καθαρό render αποτρέπει προβλήματα γεωμετρίας
        # και repaint κατά την επαναχρησιμοποίησή τους σε νέα θέση.
        if group_changed:
            self._render_clients(visible_clients)
        else:
            self._apply_visible_client_rows(visible_clients)

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

        self.empty_label = None

        self._update_count_label(len(clients))

        if not clients:
            self._show_empty_label_if_needed(0)
            return

        for row_index, client in enumerate(clients):
            self._add_client_row(row_index, client)

    def _add_client_row(self, row_index: int, client: dict) -> None:
        """
        Προσθέτει μία γραμμή client στη λίστα.
        """

        status = str(client.get("status", "offline")).lower()
        ws_connected = bool(client.get("ws_connected", False))
        presentation = self._client_presentation(client)
        client_code = str(client.get("client_code") or "-")
        detail_wrap = max(320, self.winfo_width() - 430)

        if status == "online" and ws_connected:
            status_color = COLORS.success
            status_background = COLORS.success_soft
            status_value = "ONLINE  ·  CONNECTED"
        elif status == "online":
            status_color = COLORS.warning
            status_background = COLORS.warning_soft
            status_value = "ONLINE  ·  NOT CONNECTED"
        else:
            status_color = COLORS.danger
            status_background = COLORS.danger_soft
            status_value = "OFFLINE"

        row = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=COLORS.surface,
            corner_radius=SPACING.small_radius,
            border_width=1,
            border_color=COLORS.border_soft
        )
        row.grid(row=row_index, column=0, padx=4, pady=5, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        # Χρησιμοποιείται button χωρίς ενέργεια, επειδή το CTkButton αποδίδεται
        # σταθερά μέσα στη scroll λίστα ακόμη και μετά από αλλαγή group.
        status_label = ctk.CTkButton(
            row,
            text="",
            width=8,
            height=72,
            command=None,
            fg_color=COLORS.success if status == "online" else COLORS.danger,
            hover_color=COLORS.success if status == "online" else COLORS.danger,
            border_width=0,
            corner_radius=4
        )
        status_label.grid(row=0, column=0, padx=(14, 12), pady=14, sticky="ns")

        info_frame = ctk.CTkFrame(row, fg_color="transparent")
        info_frame.grid(row=0, column=1, padx=(0, 12), pady=10, sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)

        name_label = ctk.CTkLabel(
            info_frame,
            text=presentation["name"],
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
            anchor="w"
        )
        name_label.grid(row=0, column=0, padx=(0, 8), sticky="w")

        group_label = ctk.CTkLabel(
            info_frame,
            text=presentation["group"],
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            fg_color=COLORS.surface_light,
            corner_radius=7,
            height=24
        )
        group_label.grid(row=0, column=1, sticky="w")

        identity_label = ctk.CTkLabel(
            info_frame,
            text=presentation["identity"],
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
            justify="left",
            wraplength=detail_wrap
        )
        identity_label.grid(row=1, column=0, columnspan=2, pady=(3, 0), sticky="ew")

        versions_label = ctk.CTkLabel(
            info_frame,
            text=presentation["versions"],
            font=FONTS.small,
            text_color=COLORS.text_primary,
            anchor="w",
            justify="left",
            wraplength=detail_wrap
        )
        versions_label.grid(row=2, column=0, columnspan=2, pady=(2, 0), sticky="ew")

        meta_label = ctk.CTkLabel(
            info_frame,
            text=presentation["meta"],
            font=FONTS.small,
            text_color=COLORS.text_muted,
            anchor="w",
            justify="left",
            wraplength=detail_wrap
        )
        meta_label.grid(row=3, column=0, columnspan=2, pady=(2, 0), sticky="ew")

        actions = ctk.CTkFrame(
            row,
            width=258,
            height=70,
            fg_color="transparent"
        )
        actions.grid(row=0, column=2, padx=(0, 14), pady=10, sticky="e")
        actions.grid_propagate(False)

        status_text = ctk.CTkButton(
            actions,
            text=status_value,
            width=258,
            height=28,
            command=None,
            font=FONTS.small,
            text_color=status_color,
            fg_color=status_background,
            hover_color=status_background,
            border_width=0,
            corner_radius=8
        )
        status_text.place(x=0, y=0)

        buttons_frame = ctk.CTkFrame(
            actions,
            width=258,
            height=32,
            fg_color="transparent"
        )
        buttons_frame.place(x=0, y=38)
        buttons_frame.grid_propagate(False)

        manage_button = ctk.CTkButton(
            buttons_frame,
            text="Manage",
            width=94,
            height=32,
            command=lambda c=client: self._open_manage_callback(c),
            state="normal" if ws_connected else "disabled",
            **primary_button_style()
        )
        manage_button.grid(row=0, column=0, padx=(0, 6))

        group_button = ctk.CTkButton(
            buttons_frame,
            text="Group",
            width=76,
            height=32,
            command=lambda c=client: self._open_group_callback(c),
            **secondary_button_style()
        )
        group_button.grid(row=0, column=1, padx=(0, 6))
        
        delete_button = ctk.CTkButton(
            buttons_frame,
            text="Delete",
            width=76,
            height=32,
            command=lambda c=client: self._open_delete_callback(c),
            state="disabled" if ws_connected else "normal",
            fg_color=COLORS.danger_soft,
            hover_color=COLORS.danger_hover,
            text_color="#FF8A8A",
            border_width=1,
            border_color=COLORS.danger,
            corner_radius=SPACING.button_radius,
            font=FONTS.body_bold
        )
        delete_button.grid(row=0, column=2)

        self.client_rows[str(client_code).strip()] = {
            "frame": row,
            "client": client,
            "status_label": status_label,
            "buttons_frame": buttons_frame,
            "name_label": name_label,
            "group_label": group_label,
            "identity_label": identity_label,
            "versions_label": versions_label,
            "meta_label": meta_label,
            "status_text": status_text,
            "manage_button": manage_button,
            "group_button": group_button,
            "delete_button": delete_button
        }

    def destroy(self) -> None:
        """Αφαιρεί pending jobs και global shortcuts πριν καταστραφεί η προβολή."""

        for job_name in ("filter_after_job", "_layout_after_job"):
            job_id = getattr(self, job_name, None)
            if job_id:
                try:
                    self.after_cancel(job_id)
                except Exception:
                    pass
                setattr(self, job_name, None)

        for key, binding_id in self._shortcut_bindings:
            try:
                self._shortcut_parent.unbind(key, binding_id)
            except Exception:
                pass
        self._shortcut_bindings.clear()
        super().destroy()
        
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
