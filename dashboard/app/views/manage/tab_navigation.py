"""Responsive navigation για τα tabs του Manage window."""

import logging
import math
from collections.abc import Callable

import customtkinter as ctk

from app.ui.theme import COLORS, FONTS, SPACING


LOGGER = logging.getLogger(__name__)


class ManageTabView(ctk.CTkFrame):
    """Διαχειρίζεται το navigation και το περιεχόμενο του Manage window."""

    _MIN_BUTTON_WIDTH = 124

    def __init__(
        self,
        master,
        *,
        on_tab_changed: Callable[[str], None] | None = None,
    ) -> None:
        """Αρχικοποιεί ένα responsive tab view με δημόσια CTk widgets."""

        super().__init__(
            master,
            fg_color=COLORS.surface,
            corner_radius=SPACING.card_radius,
            border_width=1,
            border_color=COLORS.border_soft,
        )

        self._on_tab_changed = on_tab_changed
        self._tabs: dict[str, ctk.CTkFrame] = {}
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._shortcuts: dict[str, str] = {}
        self._active_name: str | None = None
        self._layout_signature: tuple[int, int] | None = None
        self._layout_after_id: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.navigation = ctk.CTkFrame(
            self,
            fg_color=COLORS.background,
            corner_radius=SPACING.small_radius,
            border_width=1,
            border_color=COLORS.border_soft,
        )
        self.navigation.grid(
            row=0,
            column=0,
            padx=SPACING.inner_padding,
            pady=(SPACING.inner_padding, 0),
            sticky="ew",
        )
        self.navigation.bind("<Configure>", self._schedule_navigation_layout, add="+")

        self.content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.content.grid(
            row=1,
            column=0,
            padx=SPACING.inner_padding,
            pady=SPACING.inner_padding,
            sticky="nsew",
        )
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def add(self, name: str) -> ctk.CTkFrame:
        """Προσθέτει tab και επιστρέφει το frame του περιεχομένου του."""

        if name in self._tabs:
            raise ValueError(f"Το tab '{name}' υπάρχει ήδη.")

        position = len(self._tabs)
        shortcut = str(position + 1) if position < 9 else "0"
        tab = ctk.CTkFrame(self.content, fg_color="transparent", corner_radius=0)
        button = ctk.CTkButton(
            self.navigation,
            text=f"{shortcut}  {name}",
            height=40,
            corner_radius=SPACING.button_radius,
            border_width=1,
            font=FONTS.body_bold,
            command=lambda tab_name=name: self.set(tab_name),
        )

        self._tabs[name] = tab
        self._buttons[name] = button
        self._shortcuts[name] = shortcut
        self._style_button(name, selected=False)
        self._layout_navigation(force=True)

        if self._active_name is None:
            self.set(name)

        return tab

    def set(self, name: str) -> None:
        """Ενεργοποιεί το tab με το συγκεκριμένο όνομα."""

        if name not in self._tabs:
            raise ValueError(f"Άγνωστο tab: {name}")

        if self._active_name == name:
            return

        previous_name = self._active_name
        if previous_name is not None:
            self._tabs[previous_name].grid_remove()
            self._style_button(previous_name, selected=False)

        self._active_name = name
        self._tabs[name].grid(row=0, column=0, sticky="nsew")
        self._tabs[name].tkraise()
        self._style_button(name, selected=True)
        LOGGER.info("Επιλέχθηκε Manage tab: %s", name)

        if self._on_tab_changed is not None:
            self._on_tab_changed(name)

    def get(self) -> str:
        """Επιστρέφει το όνομα του ενεργού tab."""

        return self._active_name or ""

    def button(self, name: str) -> ctk.CTkButton:
        """Επιστρέφει το δημόσιο navigation button ενός tab."""

        if name not in self._buttons:
            raise ValueError(f"Άγνωστο tab: {name}")
        return self._buttons[name]

    def _style_button(self, name: str, *, selected: bool) -> None:
        """Εφαρμόζει το οπτικό state του navigation button."""

        button = self._buttons[name]
        if selected:
            button.configure(
                fg_color=COLORS.accent,
                hover_color=COLORS.accent_hover,
                text_color=COLORS.background,
                border_color=COLORS.accent,
            )
            return

        button.configure(
            fg_color="transparent",
            hover_color=COLORS.surface_hover,
            text_color=COLORS.text_secondary,
            border_color=COLORS.background,
        )

    def _schedule_navigation_layout(self, _event=None) -> None:
        """Προγραμματίζει μία μόνο αναδιάταξη μετά από resize."""

        if self._layout_after_id is not None:
            self.after_cancel(self._layout_after_id)
        self._layout_after_id = self.after_idle(self._layout_navigation)

    def _layout_navigation(self, *, force: bool = False) -> None:
        """Τοποθετεί τα tabs σε μία ή δύο σειρές ανάλογα με το πλάτος."""

        self._layout_after_id = None
        button_count = len(self._buttons)
        if button_count == 0:
            return

        available_width = max(self.navigation.winfo_width(), self.winfo_width(), 900)
        max_columns = max(1, int((available_width - 24) / self._MIN_BUTTON_WIDTH))
        row_count = max(1, math.ceil(button_count / max_columns))
        column_count = math.ceil(button_count / row_count)
        signature = (button_count, column_count)

        if not force and signature == self._layout_signature:
            return
        self._layout_signature = signature

        for column in range(button_count):
            self.navigation.grid_columnconfigure(column, weight=0, uniform="")

        for column in range(column_count):
            self.navigation.grid_columnconfigure(column, weight=1, uniform="manage_tabs")

        for index, button in enumerate(self._buttons.values()):
            row, column = divmod(index, column_count)
            button.grid(
                row=row,
                column=column,
                padx=SPACING.small_gap,
                pady=SPACING.small_gap,
                sticky="ew",
            )

    def destroy(self) -> None:
        """Ακυρώνει pending resize callback πριν καταστραφεί το widget."""

        if self._layout_after_id is not None:
            self.after_cancel(self._layout_after_id)
            self._layout_after_id = None
        super().destroy()
