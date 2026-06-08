import uuid
from typing import Callable

import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    card_style,
    primary_button_style,
    secondary_button_style
)


class SenarioProsorinonTab(ctk.CTkFrame):
    """
    Tab για έλεγχο Σεναρίου Προσωρινών Αποδείξεων.
    """

    def __init__(
        self,
        parent,
        client_code: str,
        get_bo_values_callback: Callable[[], list[str]],
        get_selected_bo_id_callback: Callable[[], int],
        on_senario_request_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το Senario Prosorinon tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client_code = client_code
        self.get_bo_values_callback = get_bo_values_callback
        self.get_selected_bo_id_callback = get_selected_bo_id_callback
        self.on_senario_request_callback = on_senario_request_callback
        self.latest_payload: dict = {}

        self.selected_result_index: int | None = None
        self.result_buttons: list[ctk.CTkButton] = []

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του tab.
        """

        top_frame = ctk.CTkFrame(self, **card_style())
        top_frame.grid(
            row=0,
            column=0,
            columnspan=2,
            padx=SPACING.card_padding,
            pady=SPACING.card_padding,
            sticky="ew"
        )
        top_frame.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="Senario Prosorinon",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, padx=18, pady=(16, 4), sticky="w")

        self.status_label = ctk.CTkLabel(
            top_frame,
            text="Ready",
            font=FONTS.body,
            text_color=COLORS.text_secondary
        )
        self.status_label.grid(row=1, column=0, columnspan=4, padx=18, pady=(0, 16), sticky="w")

        self.bo_option = ctk.CTkOptionMenu(
            top_frame,
            values=["No BOConnections"],
            width=260
        )
        self.bo_option.grid(row=0, column=1, padx=(10, 10), pady=(16, 4), sticky="e")

        refresh_bo_button = ctk.CTkButton(
            top_frame,
            text="Refresh BO",
            width=110,
            command=self.refresh_bo_values,
            **secondary_button_style()
        )
        refresh_bo_button.grid(row=0, column=2, padx=(0, 10), pady=(16, 4), sticky="e")

        run_button = ctk.CTkButton(
            top_frame,
            text="Run Checks",
            width=130,
            command=self.request_run_checks,
            **primary_button_style()
        )
        run_button.grid(row=0, column=3, padx=(0, 10), pady=(16, 4), sticky="e")

        clear_button = ctk.CTkButton(
            top_frame,
            text="Clear",
            width=90,
            command=self.clear_results,
            **secondary_button_style()
        )
        clear_button.grid(row=0, column=4, padx=(0, 18), pady=(16, 4), sticky="e")

        summary_frame = ctk.CTkFrame(self, **card_style())
        summary_frame.grid(
            row=1,
            column=0,
            padx=(SPACING.card_padding, 8),
            pady=(0, SPACING.card_padding),
            sticky="nsew"
        )
        summary_frame.grid_columnconfigure(0, weight=1)
        summary_frame.grid_rowconfigure(2, weight=1)

        summary_title = ctk.CTkLabel(
            summary_frame,
            text="Results",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        summary_title.grid(row=0, column=0, padx=14, pady=(14, 4), sticky="w")

        self.summary_label = ctk.CTkLabel(
            summary_frame,
            text="Total: - | Success: - | Problems: -",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            justify="left"
        )
        self.summary_label.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")

        self.results_scroll = ctk.CTkScrollableFrame(
            summary_frame,
            fg_color=COLORS.background,
            corner_radius=SPACING.small_radius
        )
        self.results_scroll.grid(row=2, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self.results_scroll.grid_columnconfigure(0, weight=1)

        details_frame = ctk.CTkFrame(self, **card_style())
        details_frame.grid(
            row=1,
            column=1,
            padx=(8, SPACING.card_padding),
            pady=(0, SPACING.card_padding),
            sticky="nsew"
        )
        details_frame.grid_columnconfigure(0, weight=1)
        details_frame.grid_rowconfigure(1, weight=1)

        self.detail_title_label = ctk.CTkLabel(
            details_frame,
            text="Details",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        self.detail_title_label.grid(row=0, column=0, padx=14, pady=(14, 6), sticky="w")

        self.details_textbox = ctk.CTkTextbox(
            details_frame,
            fg_color=COLORS.background,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
            border_width=1,
            font=FONTS.mono_body,
            wrap="word"
        )
        self.details_textbox.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")

        self.refresh_bo_values()
        self._set_details_text(
            "Press 'Run Checks' to execute Senario Prosorinon checks on the selected BOConnection."
        )

    def refresh_bo_values(self) -> None:
        """
        Ανανεώνει τις διαθέσιμες BOConnections.
        """

        values = self.get_bo_values_callback() if self.get_bo_values_callback else []

        if not values:
            values = ["No BOConnections"]

        self.bo_option.configure(values=values)

        current_selected_id = self.get_selected_bo_id_callback() if self.get_selected_bo_id_callback else 1
        selected_text = ""

        for value in values:
            if value.startswith(f"ID {current_selected_id} "):
                selected_text = value
                break

        self.bo_option.set(selected_text or values[0])

    def request_run_checks(self) -> None:
        """
        Στέλνει request για εκτέλεση των ελέγχων.
        """

        bo_connection_id = self._extract_bo_id_from_option(self.bo_option.get())

        if bo_connection_id is None:
            self.status_label.configure(
                text="No valid BOConnection selected.",
                text_color=COLORS.danger
            )
            return

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text=f"Running checks on BOConnection ID {bo_connection_id}...",
            text_color=COLORS.accent
        )

        self.summary_label.configure(
            text="Total: - | Success: - | Problems: -"
        )

        self._clear_result_buttons()
        self._set_details_text("Running checks. Please wait...")

        if self.on_senario_request_callback:
            self.on_senario_request_callback(
                {
                    "type": "senario_prosorinon_run",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "bo_connection_id": bo_connection_id,
                    "timeout": 90
                }
            )

    def handle_result(self, payload: dict) -> None:
        """
        Εμφανίζει τα αποτελέσματα των ελέγχων.
        """

        self.latest_payload = payload

        if not payload.get("success"):
            error = str(payload.get("error", "Unknown error."))

            self.status_label.configure(
                text="Checks failed.",
                text_color=COLORS.danger
            )

            self.summary_label.configure(
                text="Total: 0 | Success: 0 | Problems: 0"
            )

            self._clear_result_buttons()
            self._set_details_text(f"ERROR:\n{error}")
            return

        total = int(payload.get("total", 0))
        success_count = int(payload.get("success_count", 0))
        problem_count = int(payload.get("problem_count", 0))
        database_name = payload.get("database_name", "-")
        results = payload.get("results") or []

        self.status_label.configure(
            text=f"Completed on database: {database_name}",
            text_color=COLORS.success if problem_count == 0 else COLORS.warning
        )

        self.summary_label.configure(
            text=f"Total: {total} | Success: {success_count} | Problems: {problem_count}"
        )

        self._populate_results(results)

        if results:
            self._select_result(0)
        else:
            self._set_details_text("No results returned.")

    def clear_results(self) -> None:
        """
        Καθαρίζει τα αποτελέσματα.
        """

        self.latest_payload = {}
        self.status_label.configure(text="Ready", text_color=COLORS.text_secondary)
        self.summary_label.configure(text="Total: - | Success: - | Problems: -")
        self._clear_result_buttons()
        self._set_details_text(
            "Press 'Run Checks' to execute Senario Prosorinon checks on the selected BOConnection."
        )

    def _populate_results(self, results: list[dict]) -> None:
        """
        Γεμίζει τη λίστα αποτελεσμάτων.
        """

        self._clear_result_buttons()

        for index, result in enumerate(results):
            success = bool(result.get("success"))
            title = str(result.get("title", "-"))

            prefix = "✅" if success else "❌"

            button = ctk.CTkButton(
                self.results_scroll,
                text=f"{prefix} {title}",
                anchor="w",
                height=38,
                fg_color=COLORS.surface_light,
                hover_color=COLORS.surface_hover,
                text_color=COLORS.text_primary,
                command=lambda i=index: self._select_result(i)
            )
            button.grid(row=index, column=0, padx=6, pady=4, sticky="ew")

            self.result_buttons.append(button)

    def _select_result(self, index: int) -> None:
        """
        Επιλέγει αποτέλεσμα και δείχνει λεπτομέρειες.
        """

        results = self.latest_payload.get("results") or []

        if index < 0 or index >= len(results):
            return

        self.selected_result_index = index
        result = results[index]

        success = bool(result.get("success"))
        title = str(result.get("title", "-"))
        message = str(result.get("message", ""))

        self.detail_title_label.configure(
            text=("✅ " if success else "❌ ") + title,
            text_color=COLORS.success if success else COLORS.danger
        )

        self._set_details_text(message)

    def _clear_result_buttons(self) -> None:
        """
        Καθαρίζει τα result buttons.
        """

        for button in self.result_buttons:
            button.destroy()

        self.result_buttons.clear()
        self.selected_result_index = None

    def _set_details_text(self, text: str) -> None:
        """
        Γράφει κείμενο στο details textbox.
        """

        self.details_textbox.configure(state="normal")
        self.details_textbox.delete("1.0", "end")
        self.details_textbox.insert("1.0", text)
        self.details_textbox.configure(state="disabled")

    def _extract_bo_id_from_option(self, selected_value: str) -> int | None:
        """
        Εξάγει BOConnection ID από επιλογή τύπου 'ID 1 - Database'.
        """

        try:
            parts = selected_value.split()
            return int(parts[1])
        except Exception:
            return None