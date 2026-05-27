from typing import Callable

import customtkinter as ctk


class AppSettingsTab(ctk.CTkFrame):
    """
    AppSettings tab για προβολή appsettings.production.json και επιλογή BOConnection.
    """

    def __init__(
        self,
        parent,
        on_bo_connection_selected: Callable[[str], None] | None = None,
        on_refresh_callback: Callable[[], None] | None = None
    ) -> None:
        """
        Δημιουργεί το AppSettings tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.on_bo_connection_selected = on_bo_connection_selected
        self.on_refresh_callback = on_refresh_callback

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()


    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του AppSettings tab.
        """

        top_frame = ctk.CTkFrame(self, corner_radius=16)
        top_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="AppSettings Production JSON",
            font=("Segoe UI", 20, "bold")
        )
        title.grid(row=0, column=0, columnspan=3, padx=18, pady=(18, 8), sticky="w")

        self.status_label = ctk.CTkLabel(
            top_frame,
            text="Waiting for appsettings data...",
            font=("Segoe UI", 13),
            anchor="w"
        )
        self.status_label.grid(row=1, column=0, columnspan=3, padx=18, pady=(0, 10), sticky="ew")

        bo_label = ctk.CTkLabel(
            top_frame,
            text="BO Connection ID:",
            font=("Segoe UI", 14, "bold")
        )
        bo_label.grid(row=2, column=0, padx=(18, 10), pady=(5, 18), sticky="w")

        self.bo_connection_option = ctk.CTkOptionMenu(
            top_frame,
            values=["ID 1"],
            command=self._handle_bo_selected
        )
        self.bo_connection_option.set("ID 1")
        self.bo_connection_option.grid(row=2, column=1, padx=(0, 10), pady=(5, 18), sticky="w")

        refresh_button = ctk.CTkButton(
            top_frame,
            text="Refresh Display",
            width=130,
            command=self._handle_refresh
        )
        refresh_button.grid(row=2, column=2, padx=(0, 18), pady=(5, 18), sticky="e")

        self.details_box = ctk.CTkTextbox(
            self,
            font=("Consolas", 13),
            wrap="word"
        )
        self.details_box.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")
        self.details_box.configure(state="disabled")


    def _handle_bo_selected(self, selected_value: str) -> None:
        """
        Ενημερώνει το parent όταν αλλάζει BOConnection επιλογή.
        """

        if self.on_bo_connection_selected:
            self.on_bo_connection_selected(selected_value)


    def _handle_refresh(self) -> None:
        """
        Ζητά από το parent να κάνει refresh την τρέχουσα προβολή.
        """

        if self.on_refresh_callback:
            self.on_refresh_callback()


    def set_status(self, text: str) -> None:
        """
        Ενημερώνει το status label.
        """

        self.status_label.configure(text=text)


    def set_text(self, text: str) -> None:
        """
        Ενημερώνει το details textbox.
        """

        self.details_box.configure(state="normal")
        self.details_box.delete("1.0", "end")
        self.details_box.insert("end", text)
        self.details_box.configure(state="disabled")


    def set_bo_values(
        self,
        values: list[str],
        selected_value: str | None = None
    ) -> None:
        """
        Ενημερώνει τις επιλογές BOConnection.
        """

        safe_values = values if values else ["No BOConnections"]

        self.bo_connection_option.configure(values=safe_values)

        if selected_value and selected_value in safe_values:
            self.bo_connection_option.set(selected_value)
        else:
            self.bo_connection_option.set(safe_values[0])


    def get_selected_bo_value(self) -> str:
        """
        Επιστρέφει την τρέχουσα επιλογή BOConnection.
        """

        return self.bo_connection_option.get()