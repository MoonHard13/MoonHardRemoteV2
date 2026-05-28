"""
Κεντρικό theme για το MoonHard Remote dashboard.
Όλα τα UI components πρέπει σταδιακά να χρησιμοποιούν αυτά τα constants.
"""

from dataclasses import dataclass
from tkinter import ttk


@dataclass(frozen=True)
class AppColors:
    """
    Χρώματα εφαρμογής.
    """

    background: str = "#071014"
    surface: str = "#0D1B20"
    surface_light: str = "#13282F"
    surface_hover: str = "#18343D"

    border: str = "#1E4650"
    border_soft: str = "#163239"

    text_primary: str = "#EAF7F8"
    text_secondary: str = "#9FB8BD"
    text_muted: str = "#6F8A90"

    accent: str = "#16C7B7"
    accent_hover: str = "#13AFA1"
    accent_soft: str = "#0F3C3A"

    success: str = "#22C55E"
    success_soft: str = "#123A25"

    warning: str = "#F59E0B"
    warning_soft: str = "#3F2A0B"

    danger: str = "#EF4444"
    danger_hover: str = "#DC2626"
    danger_soft: str = "#3B1717"

    info: str = "#38BDF8"
    info_soft: str = "#123042"


@dataclass(frozen=True)
class AppFonts:
    """
    Fonts εφαρμογής.
    """

    family: str = "Segoe UI"
    mono: str = "Consolas"

    title: tuple = ("Segoe UI", 24, "bold")
    subtitle: tuple = ("Segoe UI", 18, "bold")
    section_title: tuple = ("Segoe UI", 16, "bold")
    body: tuple = ("Segoe UI", 13)
    body_bold: tuple = ("Segoe UI", 13, "bold")
    small: tuple = ("Segoe UI", 11)
    mono_body: tuple = ("Consolas", 13)


@dataclass(frozen=True)
class AppSpacing:
    """
    Spacing / sizing εφαρμογής.
    """

    window_padding: int = 20
    card_padding: int = 16
    inner_padding: int = 10
    small_gap: int = 6
    gap: int = 10
    large_gap: int = 16

    card_radius: int = 18
    small_radius: int = 10
    button_radius: int = 10


COLORS = AppColors()
FONTS = AppFonts()
SPACING = AppSpacing()


def primary_button_style() -> dict:
    """
    Επιστρέφει style για primary buttons.
    """

    return {
        "fg_color": COLORS.accent,
        "hover_color": COLORS.accent_hover,
        "text_color": "#041010",
        "corner_radius": SPACING.button_radius,
        "font": FONTS.body_bold
    }


def secondary_button_style() -> dict:
    """
    Επιστρέφει style για secondary buttons.
    """

    return {
        "fg_color": COLORS.surface_light,
        "hover_color": COLORS.surface_hover,
        "text_color": COLORS.text_primary,
        "corner_radius": SPACING.button_radius,
        "font": FONTS.body_bold
    }


def danger_button_style() -> dict:
    """
    Επιστρέφει style για danger buttons.
    """

    return {
        "fg_color": COLORS.danger,
        "hover_color": COLORS.danger_hover,
        "text_color": "#FFFFFF",
        "corner_radius": SPACING.button_radius,
        "font": FONTS.body_bold
    }


def card_style() -> dict:
    """
    Επιστρέφει style για βασικά cards/panels.
    """

    return {
        "fg_color": COLORS.surface,
        "corner_radius": SPACING.card_radius,
        "border_width": 1,
        "border_color": COLORS.border_soft
    }


def transparent_style() -> dict:
    """
    Επιστρέφει transparent style για helper frames.
    """

    return {
        "fg_color": "transparent"
    }
    
def apply_treeview_style(style_name: str = "MoonHard.Treeview") -> str:
    """
    Εφαρμόζει κοινό dark style για ttk.Treeview.
    Επιστρέφει το style name για χρήση στο Treeview.
    """

    style = ttk.Style()

    style.theme_use("default")

    style.configure(
        style_name,
        background=COLORS.surface,
        foreground=COLORS.text_primary,
        fieldbackground=COLORS.surface,
        bordercolor=COLORS.border_soft,
        borderwidth=0,
        rowheight=28,
        font=FONTS.body
    )

    style.configure(
        f"{style_name}.Heading",
        background=COLORS.surface_light,
        foreground=COLORS.text_primary,
        relief="flat",
        font=FONTS.body_bold
    )

    style.map(
        style_name,
        background=[
            ("selected", COLORS.accent_soft)
        ],
        foreground=[
            ("selected", COLORS.text_primary)
        ]
    )

    style.map(
        f"{style_name}.Heading",
        background=[
            ("active", COLORS.surface_hover)
        ]
    )

    return style_name