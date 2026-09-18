"""Προβολή remote Terminal με ενιαίο prompt και μόνιμη συνεδρία shell."""

import logging
import time
import uuid
from typing import Callable, Any

import customtkinter as ctk

from app.ui.theme import COLORS, FONTS, SPACING, secondary_button_style
from app.views.manage.inline_terminal import InlineTerminal


logger = logging.getLogger(__name__)


class TerminalTab(ctk.CTkFrame):
    """Συντονίζει toolbar, προστατευμένο terminal και το πρωτόκολλο συνεδριών."""

    def __init__(self, parent, client_code: str,
                 on_terminal_command_callback: Callable[[dict], None] | None = None,
                 on_terminal_autocomplete_callback: Callable[[dict], None] | None = None,
                 client_label: str = "") -> None:
        super().__init__(parent, corner_radius=0, fg_color="transparent")
        self.client_code = client_code
        self.client_label = client_label or client_code
        self.on_terminal_command_callback = on_terminal_command_callback
        self.on_terminal_autocomplete_callback = on_terminal_autocomplete_callback
        self.current_directory = ""
        self.session_id = ""
        self.request_id = ""
        self.ready = False
        self.running = False
        self.opening = False
        self.last_autocomplete_request_id = ""
        self.autocomplete_source = ""
        self.autocomplete_matches = []
        self.autocomplete_index = 0
        self.command_history = []
        self.history_index = None
        self.history_draft = ""
        self.timer = None
        self.started = 0.0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_ui()
        self.bind("<Map>", self._ensure_session, add="+")

    def _build_ui(self) -> None:
        """Δημιουργεί συμπαγή toolbar, επεκτεινόμενο transcript και γραμμή κατάστασης."""
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Remote Terminal", font=FONTS.subtitle).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text=self.client_label, font=FONTS.small,
                     text_color=COLORS.text_secondary).grid(row=1, column=0, sticky="w")
        self.connection_label = ctk.CTkLabel(header, text="● Not connected", text_color=COLORS.text_muted)
        self.connection_label.grid(row=0, column=1, rowspan=2, sticky="e")
        toolbar = ctk.CTkFrame(self, fg_color=COLORS.surface_light, corner_radius=10)
        toolbar.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")
        toolbar.grid_columnconfigure(1, weight=1)
        self.shell_option = ctk.CTkOptionMenu(toolbar, values=["cmd", "powershell"], width=132,
            command=self._change_shell, fg_color=COLORS.surface, button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover, dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover)
        self.shell_option.grid(row=0, column=0, padx=8, pady=8)
        self.directory_label = ctk.CTkLabel(toolbar, text="Working directory pending", anchor="w",
                                          font=FONTS.small, text_color=COLORS.text_secondary)
        self.directory_label.grid(row=0, column=1, padx=8, sticky="ew")
        for column, (label, action) in enumerate((("Clear", self.clear_terminal), ("Copy", self.copy_all),
                                                 ("Stop", self.stop_command), ("Reconnect", self.reconnect)), 2):
            button = ctk.CTkButton(toolbar, text=label, width=72, height=30,
                                  command=action, **secondary_button_style())
            button.grid(row=0, column=column, padx=(0, 6), pady=8)
            if label == "Stop":
                self.stop_button = button
                button.configure(state="disabled")
        self.auto_scroll = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(toolbar, text="Auto-scroll", variable=self.auto_scroll, width=108,
                       command=self._toggle_scroll, font=FONTS.small).grid(row=1, column=0, padx=8, pady=(0, 8))
        ctk.CTkLabel(toolbar, text="Enter: execute  •  ↑ ↓: history  •  Tab: complete  •  Ctrl+L: clear",
                     font=FONTS.small, text_color=COLORS.text_muted).grid(row=1, column=1, columnspan=5, sticky="w")
        self.output_box = InlineTerminal(self, font=(FONTS.mono, 14), wrap="none",
            fg_color="#050A0C", text_color=COLORS.text_primary,
            border_color=COLORS.border, border_width=1, corner_radius=10)
        self.output_box.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="nsew")
        status = ctk.CTkFrame(self, fg_color="transparent")
        status.grid(row=3, column=0, padx=16, pady=(0, 12), sticky="ew")
        status.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(status, text="Open the tab to connect", font=FONTS.small,
                                       text_color=COLORS.text_secondary)
        self.status_label.grid(row=0, column=0, sticky="w")
        self.details_label = ctk.CTkLabel(status, text="", font=FONTS.small, text_color=COLORS.text_muted)
        self.details_label.grid(row=0, column=1, sticky="e")
        text = self.output_box.text
        bindings = {"<Return>": self.send_terminal_command, "<KP_Enter>": self.send_terminal_command,
                    "<Up>": self._show_previous_command, "<Down>": self._show_next_command,
                    "<Tab>": self._request_terminal_autocomplete, "<Control-l>": self.clear_terminal,
                    "<Control-L>": self.clear_terminal, "<Control-c>": self._control_c,
                    "<Control-C>": self._control_c, "<Control-Shift-a>": self.copy_all,
                    "<Control-Shift-A>": self.copy_all, "<Control-Shift-r>": self.reconnect,
                    "<Control-Shift-R>": self.reconnect, "<Control-Shift-s>": self._cycle_shell,
                    "<Control-Shift-S>": self._cycle_shell, "<Control-Shift-l>": self._toggle_scroll_shortcut,
                    "<Control-Shift-L>": self._toggle_scroll_shortcut}
        for sequence, action in bindings.items():
            text.bind(sequence, action)
        self.output_box.append("MoonHard Remote • Persistent CMD / PowerShell\nClick here and type at the prompt.\n\n", "system")

    def _send(self, kind: str, **fields) -> None:
        """Αποστέλλει μόνο μεταδεδομένα στο log, χωρίς εντολές ή έξοδο."""
        if not self.on_terminal_command_callback:
            raise RuntimeError("Δεν έχει οριστεί σύνδεση Terminal.")
        self.on_terminal_command_callback({"type": kind, "client_code": self.client_code,
            "session_id": self.session_id, "request_id": fields.pop("request_id", self.request_id), **fields})
        logger.info("Ενέργεια Terminal. type=%s client_code=%s", kind, self.client_code)

    def _ensure_session(self, _event=None) -> None:
        """Ανοίγει το shell μόνο όταν ο χρήστης προβάλει για πρώτη φορά το tab."""
        if not self.session_id:
            self.reconnect()

    def reconnect(self, _event=None) -> str:
        """Κλείνει την προηγούμενη συνεδρία και ξεκινά καθαρό shell."""
        if self.running or self.opening:
            return "break"
        self._close_remote()
        self.session_id = str(uuid.uuid4())
        self.request_id = str(uuid.uuid4())
        self.ready = False
        self.opening = True
        self.current_directory = ""
        self.last_autocomplete_request_id = ""
        self.output_box.accept_input = False
        if self.output_box._has_prompt:
            self.output_box.submit()
        self.connection_label.configure(text="● Connecting", text_color=COLORS.warning)
        self.status_label.configure(text="Opening shell session…")
        self.directory_label.configure(text="Working directory pending")
        self.shell_option.configure(state="disabled")
        self.timer = self.after(18000, self._timeout)
        try:
            self._send("terminal_session_open", shell=self.shell_option.get())
        except Exception as exc:
            self._fail(str(exc))
        return "break"

    def send_terminal_command(self, _event=None) -> str:
        """Εκτελεί μόνο το ενεργό command και προστατεύει το transcript."""
        if not self.ready or self.running:
            return "break"
        command = self.output_box.command().strip()
        if not command:
            return "break"
        if len(command) > 8000:
            self.status_label.configure(text="Command exceeds 8000 characters")
            return "break"
        self.output_box.submit()
        if not self.command_history or self.command_history[-1] != command:
            self.command_history.append(command)
            del self.command_history[:-200]
        self.history_index = None
        self.last_autocomplete_request_id = ""
        self.request_id = str(uuid.uuid4())
        self.running = True
        self.started = time.monotonic()
        self.status_label.configure(text="Running…")
        self.stop_button.configure(state="normal")
        self.shell_option.configure(state="disabled")
        self.timer = self.after(80000, self._timeout)
        try:
            self._send("terminal_session_command", command=command)
        except Exception as exc:
            self._fail(str(exc))
        return "break"

    def handle_terminal_result(self, payload: dict) -> None:
        """Απορρίπτει ξένες/παλιές απαντήσεις και επαναφέρει το prompt μετά το τέλος."""
        if payload.get("client_code") != self.client_code or payload.get("session_id") != self.session_id:
            return
        if payload.get("request_id") != self.request_id:
            if not (payload.get("session_closed") and not payload.get("request_id")):
                return
        if payload.get("type") == "terminal_session_output":
            self.output_box.append(payload.get("text", ""))
            elapsed = time.monotonic() - self.started
            self.status_label.configure(text=f"Running… {elapsed:.1f}s")
            return
        self._cancel_timer()
        self.opening = False
        self.running = False
        self.ready = bool(payload.get("success")) and not payload.get("session_closed")
        self.stop_button.configure(state="disabled")
        self.shell_option.configure(state="normal")
        if not payload.get("success"):
            self._fail(payload.get("message", "Terminal request failed"))
            return
        self.current_directory = payload.get("current_directory", self.current_directory)
        self.directory_label.configure(text=self.current_directory)
        exit_code = payload.get("exit_code")
        if payload.get("operation") == "command":
            duration = payload.get("duration_seconds", time.monotonic() - self.started)
            self.details_label.configure(text=f"Exit {exit_code}  •  {duration:.2f}s  •  {time.strftime('%H:%M:%S')}")
        if self.ready:
            self.connection_label.configure(text="● Connected", text_color=COLORS.success)
            self.status_label.configure(text="Ready" if exit_code in (0, None) else f"Completed with exit code {exit_code}")
            self._prompt()
        else:
            self.connection_label.configure(text="● Session closed", text_color=COLORS.warning)
            self.status_label.configure(text="Session closed — Reconnect to continue")
            self.output_box.accept_input = False

    def _prompt(self) -> None:
        """Εμφανίζει τον πραγματικό φάκελο της συνεδρίας χωρίς ξεχωριστό entry."""
        prefix = "PS " if self.shell_option.get() == "powershell" else ""
        self.output_box.prompt(f"{prefix}{self.current_directory}> ")

    def handle_terminal_error(self, payload: dict) -> None:
        """Εμφανίζει μόνο σφάλματα του συγκεκριμένου Client."""
        if payload.get("client_code") == self.client_code:
            self._fail(payload.get("message", "Terminal error"))

    def _fail(self, message: str) -> None:
        """Τερματίζει την τοπική αναμονή χωρίς να εμφανίζει ψευδή ένδειξη Connected."""
        self._cancel_timer()
        self.opening = self.running = self.ready = False
        self.output_box.append(f"\n{message}\n", "error")
        self.output_box.accept_input = False
        self.connection_label.configure(text="● Not connected", text_color=COLORS.danger)
        self.status_label.configure(text="Reconnect to continue")
        self.stop_button.configure(state="disabled")
        self.shell_option.configure(state="normal")

    def connection_lost(self) -> None:
        """Κλειδώνει τη συνεδρία αμέσως όταν χαθεί η σύνδεση του Dashboard."""
        if self.ready or self.running or self.opening:
            self._fail("Dashboard connection lost. Reconnect when online.")

    def _timeout(self) -> None:
        """Κλείνει την αναμονή ακόμη και όταν ο Server δεν γνωρίζει το νέο πρωτόκολλο."""
        self.timer = None
        self._close_remote()
        self._fail("No response received. Check connection and update Server/Client.")

    def _cancel_timer(self) -> None:
        """Ακυρώνει το χρονόμετρο σε ολοκλήρωση, σφάλμα ή κλείσιμο."""
        if self.timer:
            self.after_cancel(self.timer)
            self.timer = None

    def stop_command(self, _event=None) -> str:
        """Τερματίζει όλο το process tree· η συνεδρία χρειάζεται έπειτα Reconnect."""
        if self.running:
            try:
                self._send("terminal_session_stop", request_id=str(uuid.uuid4()))
                self.status_label.configure(text="Stopping…")
                self.stop_button.configure(state="disabled")
            except Exception as exc:
                self._fail(str(exc))
        return "break"

    def _control_c(self, _event=None) -> str:
        """Δίνει προτεραιότητα στην αντιγραφή επιλογής και αλλιώς εκτελεί Stop."""
        if self.output_box.text.tag_ranges("sel"):
            return self.output_box.copy_selection()
        return self.stop_command()

    def clear_terminal(self, _event=None) -> str:
        """Καθαρίζει μόνο την προβολή, διατηρώντας φάκελο, μεταβλητές και ιστορικό."""
        draft = self.output_box.command()
        self.output_box.clear()
        if self.ready and not self.running:
            self._prompt()
            self.output_box.set_command(draft)
        logger.info("Καθαρισμός προβολής Terminal. client_code=%s", self.client_code)
        return "break"

    def copy_all(self, _event=None) -> str:
        """Αντιγράφει το transcript στο clipboard."""
        logger.info("Αντιγραφή transcript Terminal. client_code=%s", self.client_code)
        return self.output_box.copy_all()

    def append_output(self, text: str) -> None:
        """Διατηρεί συμβατότητα με τις υπάρχουσες κλήσεις του Manage window."""
        self.output_box.append(text)

    def _toggle_scroll(self) -> None:
        """Αφήνει τον χρήστη να διαβάζει παλιά έξοδο χωρίς ανεπιθύμητη μετακίνηση."""
        self.output_box.auto_scroll = self.auto_scroll.get()
        if self.auto_scroll.get():
            self.output_box.text.see("end")
        logger.info("Αλλαγή auto-scroll. enabled=%s", self.auto_scroll.get())

    def _toggle_scroll_shortcut(self, _event=None) -> str:
        """Αλλάζει το auto-scroll από το πληκτρολόγιο."""
        self.auto_scroll.set(not self.auto_scroll.get())
        self._toggle_scroll()
        return "break"

    def _cycle_shell(self, _event=None) -> str:
        """Εναλλάσσει τα shells μόνο όταν δεν εκτελείται εντολή."""
        if not self.running and not self.opening:
            self.shell_option.set("powershell" if self.shell_option.get() == "cmd" else "cmd")
            self._change_shell(self.shell_option.get())
        return "break"

    def _change_shell(self, _value=None) -> None:
        """Ξεκινά νέα συνεδρία όταν αλλάξει το shell."""
        if not self.running and not self.opening:
            self.reconnect()

    def _close_remote(self) -> None:
        """Κλείνει τη συνεδρία χωρίς να περιμένει απάντηση στο κλειστό παράθυρο."""
        if self.session_id and self.on_terminal_command_callback:
            try:
                self._send("terminal_session_close", request_id=str(uuid.uuid4()))
            except Exception:
                logger.warning("Δεν εστάλη κλείσιμο Terminal.")

    def _show_previous_command(self, _event=None) -> str:
        """Φέρνει προηγούμενη εντολή διατηρώντας το αρχικό draft."""
        if self.ready and not self.running and self.command_history:
            if self.history_index is None:
                self.history_draft = self.output_box.command()
                self.history_index = len(self.command_history) - 1
            else:
                self.history_index = max(0, self.history_index - 1)
            self.output_box.set_command(self.command_history[self.history_index])
        return "break"

    def _show_next_command(self, _event=None) -> str:
        """Επιστρέφει και στο ημιτελές command όταν τελειώσει το ιστορικό."""
        if self.ready and not self.running and self.history_index is not None:
            self.history_index += 1
            if self.history_index >= len(self.command_history):
                self.history_index = None
                self.output_box.set_command(self.history_draft)
            else:
                self.output_box.set_command(self.command_history[self.history_index])
        return "break"

    def _request_terminal_autocomplete(self, _event=None) -> str:
        """Ζητά autocomplete από τον Client με τον πραγματικό φάκελο της συνεδρίας."""
        if not self.ready or self.running:
            return "break"
        current = self.output_box.command()
        if self.autocomplete_matches and current == getattr(self, "autocomplete_applied", None):
            self.autocomplete_index = (self.autocomplete_index + 1) % len(self.autocomplete_matches)
            self._apply_autocomplete_match(self.autocomplete_matches[self.autocomplete_index])
            return "break"
        if current.strip() and self.on_terminal_autocomplete_callback:
            self.last_autocomplete_request_id = str(uuid.uuid4())
            self.autocomplete_source = current
            self.autocomplete_matches = []
            self.on_terminal_autocomplete_callback({"type": "terminal_autocomplete",
                "client_code": self.client_code, "request_id": self.last_autocomplete_request_id,
                "shell": self.shell_option.get(), "command_text": current,
                "session_id": self.session_id})
        return "break"

    def handle_terminal_autocomplete_result(self, payload: dict[str, Any]) -> None:
        """Απορρίπτει καθυστερημένες προτάσεις αν ο χρήστης έχει ήδη αλλάξει την εντολή."""
        if (payload.get("client_code") == self.client_code
                and payload.get("request_id") == self.last_autocomplete_request_id
                and self.ready and not self.running and self.output_box.command() == self.autocomplete_source):
            self.autocomplete_matches = payload.get("matches") or []
            self.autocomplete_index = 0
            if self.autocomplete_matches:
                self._apply_autocomplete_match(self.autocomplete_matches[0])

    def _apply_autocomplete_match(self, match) -> None:
        """Αντικαθιστά το τελευταίο token, διατηρώντας paths με κενά και εισαγωγικά."""
        value = (match.get("insert_value") or match.get("name", "")) if isinstance(match, dict) else str(match)
        source = self.autocomplete_source
        if source.count('"') % 2:
            prefix = source[:source.rfind('"')]
        elif source.rstrip().endswith('"'):
            prefix = source[:source.rfind('"', 0, source.rfind('"'))]
        else:
            prefix = source[:source.rfind(" ") + 1]
        self.autocomplete_applied = prefix + value
        self.output_box.set_command(self.autocomplete_applied)

    def handle_terminal_autocomplete_error(self, payload: dict[str, Any]) -> None:
        """Δείχνει σφάλμα συμπλήρωσης χωρίς αλλαγή του command ή της συνεδρίας."""
        if payload.get("client_code") == self.client_code and payload.get("request_id") == self.last_autocomplete_request_id:
            self.status_label.configure(text=payload.get("message", "Autocomplete unavailable"))

    def destroy(self) -> None:
        """Κλείνει τη συνεδρία και ακυρώνει callbacks πριν καταστραφεί η προβολή."""
        self._cancel_timer()
        self._close_remote()
        super().destroy()
