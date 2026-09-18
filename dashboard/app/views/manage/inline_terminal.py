"""Ενιαίο terminal με προστατευμένο ιστορικό και επεξεργάσιμο ενεργό prompt."""

import tkinter as tk
import logging
from contextlib import contextmanager

import customtkinter as ctk

from app.ui.theme import COLORS


logger = logging.getLogger(__name__)


class InlineTerminal(ctk.CTkTextbox):
    """Προστατεύει το ιστορικό στο επίπεδο του Tk widget, μαζί με cut/paste/drag."""

    MAX_LINES = 5000
    MAX_CHARS = 500000

    def __init__(self, parent, **kwargs):
        self._after_jobs = set()
        super().__init__(parent, **kwargs)
        self.accept_input = False
        self.auto_scroll = True
        self._internal_edit = False
        self._has_prompt = False
        self.text = self._textbox
        self.text.configure(undo=False, insertbackground=COLORS.accent,
                            selectbackground=COLORS.accent_soft, selectforeground=COLORS.text_primary)
        self.text.tag_configure("prompt", foreground=COLORS.accent)
        self.text.tag_configure("command", foreground=COLORS.text_primary)
        self.text.tag_configure("error", foreground=COLORS.danger)
        self.text.tag_configure("system", foreground=COLORS.text_muted)
        self._original = self.text._w + "_original"
        self.text.tk.call("rename", self.text._w, self._original)
        self.text.tk.createcommand(self.text._w, self._proxy)
        self.text.mark_set("input_start", "end-1c")
        self.text.mark_set("prompt_start", "end-1c")
        self.text.mark_gravity("input_start", "left")
        self.text.mark_gravity("prompt_start", "left")
        self.text.bind("<Home>", self._home)
        self.text.bind("<End>", self._end)
        self.text.bind("<Left>", self._left)
        self.text.bind("<Escape>", lambda _: self.clear_command())
        self.text.bind("<<Paste>>", self.paste)
        self.text.bind("<Control-Shift-V>", self.paste)
        self.text.bind("<Control-Shift-v>", self.paste)
        self.text.bind("<Control-Shift-C>", self.copy_selection)
        self.text.bind("<Control-Shift-c>", self.copy_selection)
        self.text.bind("<Control-a>", self._select_command)
        self.text.bind("<Button-3>", self._context_menu)
        self.menu = tk.Menu(self.text, tearoff=False, bg=COLORS.surface, fg=COLORS.text_primary)
        self.menu.add_command(label="Copy selection", command=self.copy_selection)
        self.menu.add_command(label="Paste", command=self.paste)

    def after(self, ms, func=None, *args):
        """Παρακολουθεί τα callbacks του widget ώστε να ακυρωθούν κατά το κλείσιμο."""
        if func is None:
            return super().after(ms)
        scheduled = {}
        def call():
            self._after_jobs.discard(scheduled["id"])
            func(*args)
        job = super().after(ms, call)
        scheduled["id"] = job
        self._after_jobs.add(job)
        return job

    @contextmanager
    def edit(self):
        """Επιτρέπει μόνο στις εσωτερικές ενέργειες να μεταβάλλουν το ιστορικό."""
        previous = self._internal_edit
        self._internal_edit = True
        try:
            yield
        finally:
            self._internal_edit = previous

    def _proxy(self, operation, *args):
        """Περιορίζει όλες τις αλλαγές του Tk σε κείμενο μετά το ενεργό prompt."""
        if not self._internal_edit and operation in ("insert", "delete", "replace"):
            if not self.accept_input or not self._has_prompt:
                return ""
            if operation == "insert":
                position = args[0]
                if self.text.compare(position, "<", "input_start"):
                    position = "end-1c"
                    self.text.mark_set("insert", position)
                cleaned = tuple(str(value).replace("\r", " ").replace("\n", " ").replace("\x00", "")
                                if i % 2 == 1 else value for i, value in enumerate(args))
                args = (position, *cleaned[1:])
            else:
                start = self.text.index(args[0])
                end = self.text.index(args[1]) if len(args) > 1 else self.text.index(f"{start}+1c")
                if self.text.compare(end, "<=", "input_start"):
                    return ""
                if self.text.compare(start, "<", "input_start"):
                    start = "input_start"
                end = "end-1c" if self.text.compare(end, ">", "end-1c") else end
                replacement = args[2:]
                if operation == "replace":
                    replacement = tuple(str(value).replace("\r", " ").replace("\n", " ").replace("\x00", "")
                                        if i % 2 == 0 else value for i, value in enumerate(replacement))
                args = (start, end, *replacement)
        return self.text.tk.call(self._original, operation, *args)

    def command(self) -> str:
        """Επιστρέφει μόνο το επεξεργάσιμο command και όχι το prompt."""
        return self.text.get("input_start", "end-1c") if self._has_prompt else ""

    def set_command(self, command: str) -> None:
        """Αλλάζει το ενεργό command για ιστορικό και autocomplete."""
        if not self.accept_input:
            return
        self.text.delete("input_start", "end-1c")
        self.text.insert("end-1c", command)
        self.text.mark_set("insert", "end-1c")
        self.text.see("insert")

    def clear_command(self) -> str:
        """Καθαρίζει μόνο την τρέχουσα εντολή."""
        self.set_command("")
        return "break"

    def prompt(self, text: str) -> None:
        """Προσθέτει νέο prompt και ενεργοποιεί την πληκτρολόγηση μετά από αυτό."""
        with self.edit():
            if self._has_prompt:
                self.text.delete("prompt_start", "end-1c")
            if self.text.get("end-2c", "end-1c") not in ("", "\n"):
                self.text.insert("end-1c", "\n")
            self.text.mark_set("prompt_start", "end-1c")
            self.text.insert("end-1c", text, "prompt")
            self.text.mark_set("input_start", "end-1c")
        self._has_prompt = True
        self.accept_input = True
        self.text.mark_set("insert", "end-1c")
        if self.auto_scroll:
            self.text.see("end")

    def submit(self) -> str:
        """Μετατρέπει το ενεργό command σε προστατευμένο ιστορικό."""
        command = self.command()
        with self.edit():
            self.text.tag_add("command", "input_start", "end-1c")
            self.text.insert("end-1c", "\n")
        self._has_prompt = False
        self.accept_input = False
        return command

    def append(self, text: str, tag="") -> None:
        """Προσθέτει output πριν το prompt διατηρώντας την ημιτελή εντολή."""
        command = self.command()
        prompt_text = self.text.get("prompt_start", "input_start") if self._has_prompt else ""
        with self.edit():
            if self._has_prompt:
                self.text.delete("prompt_start", "end-1c")
                self._has_prompt = False
            self.text.insert("end-1c", text, tag)
            lines = int(self.text.index("end-1c").split(".")[0])
            if lines > self.MAX_LINES:
                self.text.delete("1.0", f"{lines - self.MAX_LINES + 1}.0")
            count = self.text.count("1.0", "end-1c", "chars")
            if count and count[0] > self.MAX_CHARS:
                self.text.delete("1.0", f"1.0+{count[0] - self.MAX_CHARS}c")
        if prompt_text:
            self.prompt(prompt_text)
            self.set_command(command)
        if self.auto_scroll:
            self.text.see("end")

    def clear(self) -> None:
        """Καθαρίζει την τοπική προβολή διατηρώντας την κατάσταση της συνεδρίας."""
        with self.edit():
            self.text.delete("1.0", "end")
        self._has_prompt = False

    def copy_selection(self, _event=None) -> str:
        """Αντιγράφει την επιλογή από οποιοδήποτε σημείο του terminal."""
        try:
            selected = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        self.clipboard_clear()
        self.clipboard_append(selected)
        logger.info("Αντιγραφή επιλογής Terminal.")
        return "break"

    def copy_all(self) -> str:
        """Αντιγράφει όλο το εμφανιζόμενο transcript."""
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))
        return "break"

    def paste(self, _event=None) -> str:
        """Επικολλά μόνο στο ενεργό command χωρίς αυτόματη εκτέλεση πολλών γραμμών."""
        if not self.accept_input:
            return "break"
        try:
            value = self.clipboard_get().replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
            if self.text.tag_ranges("sel"):
                self.text.delete("sel.first", "sel.last")
            self.text.insert("insert", value[:8000])
            logger.info("Επικόλληση στο ενεργό prompt Terminal.")
            self.text.see("insert")
        except tk.TclError:
            pass
        return "break"

    def _home(self, _event=None) -> str:
        """Μετακινεί τον δρομέα στην αρχή της τρέχουσας εντολής."""
        self.text.mark_set("insert", "input_start" if self._has_prompt else "end-1c")
        return "break"

    def _end(self, _event=None) -> str:
        """Μετακινεί τον δρομέα στο τέλος της τρέχουσας εντολής."""
        self.text.mark_set("insert", "end-1c")
        return "break"

    def _left(self, _event=None):
        """Εμποδίζει τον δρομέα να περάσει αριστερά από το ενεργό prompt."""
        if self._has_prompt and self.text.compare("insert", "<=", "input_start"):
            return "break"

    def _select_command(self, _event=None) -> str:
        """Επιλέγει μόνο την ενεργή εντολή για ασφαλή αντικατάσταση."""
        self.text.tag_remove("sel", "1.0", "end")
        if self._has_prompt:
            self.text.tag_add("sel", "input_start", "end-1c")
        return "break"

    def _context_menu(self, event) -> str:
        """Εμφανίζει τις ενέργειες αντιγραφής και επικόλλησης."""
        self.menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def destroy(self) -> None:
        """Αφαιρεί και τον Tcl proxy όταν καταστραφεί το widget."""
        path = self.text._w
        for job in list(self._after_jobs):
            self.after_cancel(job)
        self._after_jobs.clear()
        super().destroy()
        self.text.tk.deletecommand(path)
