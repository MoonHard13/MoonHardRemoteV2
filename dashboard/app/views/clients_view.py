import customtkinter as ctk


class ClientsView(ctk.CTkFrame):
    """
    Προβολή λίστας clients στο dashboard.
    """

    def __init__(self, parent, on_manage_callback=None) -> None:
        """
        Δημιουργεί το UI της λίστας clients.
        """

        super().__init__(parent, corner_radius=18)

        self.client_rows: dict[str, ctk.CTkFrame] = {}
        self.on_manage_callback = on_manage_callback
        
        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί τα βασικά widgets της προβολής.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            self,
            text="Connected Clients",
            font=("Segoe UI", 22, "bold")
        )
        title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            corner_radius=14
        )
        self.scroll_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

    def update_clients(self, clients: list[dict]) -> None:
        """
        Ανανεώνει τη λίστα clients στο GUI.
        """

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        self.client_rows.clear()

        if not clients:
            empty_label = ctk.CTkLabel(
                self.scroll_frame,
                text="Δεν υπάρχουν clients ακόμα.",
                font=("Segoe UI", 15)
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
        status_color = "#22C55E" if status == "online" else "#EF4444"

        client_code = client.get("client_code", "-")
        display_name = client.get("display_name") or client.get("pc_name") or "-"
        pc_name = client.get("pc_name", "-")
        username = client.get("username", "-")
        app_version = client.get("app_version", "-")
        last_seen = client.get("last_seen", "-")

        row = ctk.CTkFrame(
            self.scroll_frame,
            corner_radius=14
        )
        row.grid(row=row_index, column=0, padx=5, pady=7, sticky="ew")
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
            f"PC: {pc_name} | User: {username} | Version: {app_version}\n"
            f"Code: {client_code}\n"
            f"Last seen: {last_seen}"
        )

        info_label = ctk.CTkLabel(
            row,
            text=main_text,
            font=("Segoe UI", 14),
            justify="left",
            anchor="w"
        )
        info_label.grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        status_text = ctk.CTkLabel(
            row,
            text=status.upper(),
            font=("Segoe UI", 13, "bold")
        )
        status_text.grid(row=0, column=2, padx=15, pady=12, sticky="e")

        manage_button = ctk.CTkButton(
            row,
            text="Manage",
            width=100,
            command=lambda c=client: self._open_manage_callback(c)
        )
        manage_button.grid(row=0, column=3, padx=(0, 15), pady=12, sticky="e")

        def save_name() -> None:
            """
            Στέλνει το νέο όνομα στο callback του dashboard.
            """

            new_name = name_entry.get().strip()

            if not new_name:
                error_label.configure(text="Το όνομα δεν μπορεί να είναι κενό.")
                return

            if self.on_rename_callback:
                self.on_rename_callback(client_code, new_name)

            dialog.destroy()

        buttons_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons_frame.pack(padx=20, pady=(5, 15), fill="x")

        cancel_button = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            width=100,
            command=dialog.destroy
        )
        cancel_button.pack(side="right", padx=(8, 0))

        save_button = ctk.CTkButton(
            buttons_frame,
            text="Save",
            width=100,
            command=save_name
        )
        save_button.pack(side="right")

        dialog.bind("<Return>", lambda _event: save_name())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        
    def _open_manage_callback(self, client: dict) -> None:
        """
        Ενημερώνει το dashboard ότι ο χρήστης θέλει να διαχειριστεί συγκεκριμένο client.
        """

        if self.on_manage_callback:
            self.on_manage_callback(client)