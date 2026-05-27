import uuid
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

import customtkinter as ctk


class SqlTab(ctk.CTkFrame):
    """
    SQL tab για εκτέλεση queries, .sql files, test connection και προβολή αποτελεσμάτων.
    """

    def __init__(
        self,
        parent,
        client_code: str,
        on_sql_execute_callback: Callable[[dict], None] | None = None,
        on_bo_selected_callback: Callable[[str], None] | None = None
    ) -> None:
        """
        Δημιουργεί το SQL tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client_code = client_code
        self.on_sql_execute_callback = on_sql_execute_callback
        self.on_bo_selected_callback = on_bo_selected_callback

        self.selected_bo_connection_id: int = 1
        self.current_sql_request_id: str = ""
        self.sql_result_tab_names: list[str] = []
        self.sql_table_widgets: dict[str, ttk.Treeview] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_ui()


    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του SQL tab.
        """

        top_frame = ctk.CTkFrame(self, corner_radius=16)
        top_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="SQL Server Query Executor",
            font=("Segoe UI", 20, "bold")
        )
        title.grid(row=0, column=0, columnspan=6, padx=18, pady=(18, 8), sticky="w")

        bo_label = ctk.CTkLabel(
            top_frame,
            text="BOConnection:",
            font=("Segoe UI", 14, "bold")
        )
        bo_label.grid(row=1, column=0, padx=(18, 10), pady=(5, 18), sticky="w")

        self.sql_bo_option = ctk.CTkOptionMenu(
            top_frame,
            values=["ID 1"],
            command=self._on_sql_bo_selected
        )
        self.sql_bo_option.set("ID 1")
        self.sql_bo_option.grid(row=1, column=1, padx=(0, 10), pady=(5, 18), sticky="w")

        test_connection_button = ctk.CTkButton(
            top_frame,
            text="Test Connection",
            width=130,
            command=self.test_sql_connection
        )
        test_connection_button.grid(row=1, column=2, padx=(0, 10), pady=(5, 18))

        load_file_button = ctk.CTkButton(
            top_frame,
            text="Load .sql",
            width=100,
            command=self._load_sql_file
        )
        load_file_button.grid(row=1, column=3, padx=(0, 10), pady=(5, 18))

        execute_button = ctk.CTkButton(
            top_frame,
            text="Execute",
            width=100,
            command=self.execute_sql
        )
        execute_button.grid(row=1, column=4, padx=(0, 10), pady=(5, 18))

        self.stop_sql_button = ctk.CTkButton(
            top_frame,
            text="Stop",
            width=90,
            command=self.stop_sql_execution,
            state="disabled"
        )
        self.stop_sql_button.grid(row=1, column=5, padx=(0, 18), pady=(5, 18))

        self.sql_editor = ctk.CTkTextbox(
            self,
            font=("Consolas", 13),
            wrap="none"
        )
        self.sql_editor.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.sql_editor.insert("1.0", "SELECT TOP 10 * FROM INFORMATION_SCHEMA.TABLES;")

        self.sql_results_tabs = ctk.CTkTabview(
            self,
            corner_radius=14
        )
        self.sql_results_tabs.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")

        self.sql_messages_tab = self.sql_results_tabs.add("Messages")
        self.sql_messages_tab.grid_columnconfigure(0, weight=1)
        self.sql_messages_tab.grid_rowconfigure(0, weight=1)

        self.sql_result_box = ctk.CTkTextbox(
            self.sql_messages_tab,
            font=("Consolas", 13),
            wrap="none"
        )
        self.sql_result_box.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.sql_result_box.configure(state="disabled")

        self.sql_result_tab_names = ["Messages"]


    def set_bo_values(
        self,
        values: list[str],
        selected_value: str | None = None
    ) -> None:
        """
        Ενημερώνει τις επιλογές BOConnection του SQL tab.
        """

        safe_values = values if values else ["No BOConnections"]

        self.sql_bo_option.configure(values=safe_values)

        if selected_value and selected_value in safe_values:
            self.sql_bo_option.set(selected_value)
            self._update_selected_bo_id(selected_value)
        else:
            self.sql_bo_option.set(safe_values[0])
            self._update_selected_bo_id(safe_values[0])


    def _on_sql_bo_selected(self, selected_value: str) -> None:
        """
        Επιλέγει BOConnection ID για SQL εκτέλεση.
        """

        self._update_selected_bo_id(selected_value)

        if self.on_bo_selected_callback:
            self.on_bo_selected_callback(selected_value)


    def _update_selected_bo_id(self, selected_value: str) -> None:
        """
        Ενημερώνει το selected BOConnection ID από επιλογή τύπου 'ID 1 - Database'.
        """

        connection_id = self._extract_bo_id_from_option(selected_value)

        if connection_id is not None:
            self.selected_bo_connection_id = connection_id


    def _extract_bo_id_from_option(self, selected_value: str) -> int | None:
        """
        Εξάγει το ID από επιλογή τύπου 'ID 1 - DatabaseName'.
        """

        try:
            parts = selected_value.split()
            return int(parts[1])
        except Exception:
            return None


    def _load_sql_file(self) -> None:
        """
        Φορτώνει .sql αρχείο στο SQL editor.
        """

        file_path = filedialog.askopenfilename(
            title="Select SQL file",
            filetypes=[("SQL files", "*.sql"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            content = Path(file_path).read_text(encoding="utf-8-sig")

            self.sql_editor.delete("1.0", "end")
            self.sql_editor.insert("1.0", content)
            self._set_sql_result_text(f"Loaded SQL file:\n{file_path}\n")

        except Exception as exc:
            self._set_sql_result_text(f"Failed to load SQL file:\n{exc}\n")


    def execute_sql(self) -> None:
        """
        Στέλνει SQL query για εκτέλεση στον client.
        """

        sql_text = self.sql_editor.get("1.0", "end").strip()

        if not sql_text:
            self._set_sql_result_text("SQL text is empty.\n")
            return

        request_id = str(uuid.uuid4())
        self.current_sql_request_id = request_id
        self.stop_sql_button.configure(state="normal")
        self._clear_sql_result_tabs()

        self._set_sql_result_text(
            f"Executing SQL on BOConnection ID {self.selected_bo_connection_id}...\n"
        )

        if self.on_sql_execute_callback:
            self.on_sql_execute_callback(
                {
                    "type": "sql_execute",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "bo_connection_id": self.selected_bo_connection_id,
                    "sql_text": sql_text,
                    "timeout": 120
                }
            )


    def test_sql_connection(self) -> None:
        """
        Στέλνει αίτημα δοκιμής SQL σύνδεσης για το επιλεγμένο BOConnection.
        """

        request_id = str(uuid.uuid4())
        self.current_sql_request_id = request_id
        self._clear_sql_result_tabs()

        self._set_sql_result_text(
            f"Testing SQL connection on BOConnection ID {self.selected_bo_connection_id}...\n"
        )

        if self.on_sql_execute_callback:
            self.on_sql_execute_callback(
                {
                    "type": "sql_test_connection",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "bo_connection_id": self.selected_bo_connection_id,
                    "timeout": 15
                }
            )


    def stop_sql_execution(self) -> None:
        """
        Στέλνει αίτημα ακύρωσης του τρέχοντος SQL query.
        """

        if not self.current_sql_request_id:
            self._set_sql_result_text("No active SQL request to stop.\n")
            return

        self._set_sql_result_text(
            f"Stopping SQL request: {self.current_sql_request_id}\n"
        )

        if self.on_sql_execute_callback:
            self.on_sql_execute_callback(
                {
                    "type": "sql_cancel",
                    "request_id": self.current_sql_request_id,
                    "client_code": self.client_code
                }
            )


    def handle_sql_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτελέσματα SQL εκτέλεσης σε Messages tab και result table tabs.
        """

        if payload.get("client_code") != self.client_code:
            return

        self._clear_sql_result_tabs()

        success = payload.get("success")
        error = payload.get("error")
        batches = payload.get("batches") or []

        message_lines: list[str] = []

        message_lines.append("=== SQL Execution Summary ===")
        message_lines.append(f"Success: {success}")
        message_lines.append(f"BOConnection ID: {payload.get('bo_connection_id')}")
        message_lines.append(f"Driver: {payload.get('driver')}")
        message_lines.append(f"Elapsed: {payload.get('elapsed_ms')} ms")

        if error:
            message_lines.append("")
            message_lines.append("=== Error ===")
            message_lines.append(str(error))

        message_lines.append("")

        total_result_tabs = 0

        for batch in batches:
            batch_index = batch.get("batch_index")
            batch_error = batch.get("error")
            rowcount = batch.get("rowcount")
            result_sets = batch.get("result_sets") or []

            message_lines.append(f"=== Batch {batch_index} ===")

            if batch_error:
                message_lines.append(f"Batch error: {batch_error}")

            if not result_sets:
                message_lines.append(f"Rows affected: {rowcount}")
                message_lines.append("")
                continue

            for result_index, result_set in enumerate(result_sets, start=1):
                columns = result_set.get("columns") or []
                rows = result_set.get("rows") or []

                message_lines.append(
                    f"Result Set {result_index}: {len(rows)} rows, {len(columns)} columns"
                )

                tab_name = f"Batch {batch_index} - Result {result_index}"

                if columns:
                    self._add_sql_result_table_tab(
                        tab_name=tab_name,
                        columns=columns,
                        rows=rows
                    )
                    total_result_tabs += 1

            message_lines.append("")

        if total_result_tabs == 0:
            message_lines.append("No SELECT result sets returned.")

        self._set_sql_result_text("\n".join(message_lines))

        self.stop_sql_button.configure(state="disabled")
        self.current_sql_request_id = ""


    def handle_sql_error(self, payload: dict) -> None:
        """
        Εμφανίζει SQL routing/server error.
        """

        self._set_sql_result_text(
            f"SQL ERROR:\n{payload.get('message', 'Unknown SQL error.')}\n"
        )


    def handle_sql_test_connection_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα δοκιμής SQL σύνδεσης.
        """

        if payload.get("client_code") != self.client_code:
            return

        text = (
            "=== SQL Connection Test ===\n"
            f"Success: {payload.get('success')}\n"
            f"BOConnection ID: {payload.get('bo_connection_id')}\n"
            f"Driver: {payload.get('driver')}\n"
            f"Elapsed: {payload.get('elapsed_ms')} ms\n"
            f"Server: {payload.get('server_name')}\n"
            f"Database: {payload.get('database_name')}\n"
            f"Login: {payload.get('login_name')}\n"
        )

        if payload.get("error"):
            text += f"\nError:\n{payload.get('error')}\n"

        self._set_sql_result_text(text)


    def handle_sql_cancel_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα ακύρωσης SQL query.
        """

        if payload.get("client_code") != self.client_code:
            return

        self.stop_sql_button.configure(state="disabled")

        self._set_sql_result_text(
            "=== SQL Cancel Result ===\n"
            f"Success: {payload.get('success')}\n"
            f"Message: {payload.get('message')}\n"
        )


    def _set_sql_result_text(self, text: str) -> None:
        """
        Ενημερώνει το SQL result textbox.
        """

        self.sql_result_box.configure(state="normal")
        self.sql_result_box.delete("1.0", "end")
        self.sql_result_box.insert("end", text)
        self.sql_result_box.configure(state="disabled")


    def _clear_sql_result_tabs(self) -> None:
        """
        Καθαρίζει όλα τα SQL result tabs εκτός από το Messages tab.
        """

        for tab_name in list(self.sql_result_tab_names):
            if tab_name == "Messages":
                continue

            try:
                self.sql_results_tabs.delete(tab_name)
            except Exception:
                pass

        self.sql_result_tab_names = ["Messages"]
        self.sql_table_widgets.clear()

        self._set_sql_result_text("")


    def _add_sql_result_table_tab(
        self,
        tab_name: str,
        columns: list[str],
        rows: list[list]
    ) -> None:
        """
        Δημιουργεί νέο tab με πίνακα αποτελεσμάτων SQL.
        """

        safe_tab_name = tab_name

        if safe_tab_name in self.sql_result_tab_names:
            suffix = 2

            while f"{safe_tab_name} ({suffix})" in self.sql_result_tab_names:
                suffix += 1

            safe_tab_name = f"{safe_tab_name} ({suffix})"

        table_tab = self.sql_results_tabs.add(safe_tab_name)
        table_tab.grid_columnconfigure(0, weight=1)
        table_tab.grid_rowconfigure(0, weight=1)

        table_frame = ctk.CTkFrame(table_tab, corner_radius=10)
        table_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=15
        )
        tree.grid(row=0, column=0, sticky="nsew")

        vertical_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=tree.yview
        )
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")

        horizontal_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=tree.xview
        )
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")

        tree.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set
        )

        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=160, minwidth=80, stretch=True)

        for row in rows:
            tree.insert("", "end", values=row)

        tree.bind("<Control-c>", lambda _event, t=tree: self._copy_selected_sql_rows(t))
        tree.bind("<Button-3>", lambda event, t=tree: self._show_sql_table_context_menu(event, t))

        self.sql_result_tab_names.append(safe_tab_name)
        self.sql_table_widgets[safe_tab_name] = tree


    def _copy_selected_sql_rows(self, tree: ttk.Treeview) -> None:
        """
        Αντιγράφει τις επιλεγμένες γραμμές SQL result table στο clipboard.
        """

        selected_items = tree.selection()

        if not selected_items:
            return

        copied_lines: list[str] = []

        for item in selected_items:
            values = tree.item(item, "values")
            copied_lines.append("\t".join(str(value) for value in values))

        copied_text = "\n".join(copied_lines)

        self.clipboard_clear()
        self.clipboard_append(copied_text)


    def _copy_all_sql_rows(self, tree: ttk.Treeview) -> None:
        """
        Αντιγράφει όλες τις γραμμές SQL result table στο clipboard.
        """

        copied_lines: list[str] = []

        for item in tree.get_children():
            values = tree.item(item, "values")
            copied_lines.append("\t".join(str(value) for value in values))

        copied_text = "\n".join(copied_lines)

        self.clipboard_clear()
        self.clipboard_append(copied_text)


    def _show_sql_table_context_menu(self, event, tree: ttk.Treeview) -> None:
        """
        Εμφανίζει context menu για αντιγραφή γραμμών SQL result table.
        """

        context_menu = __import__("tkinter").Menu(self, tearoff=0)

        context_menu.add_command(
            label="Copy selected rows",
            command=lambda: self._copy_selected_sql_rows(tree)
        )

        context_menu.add_command(
            label="Copy all rows",
            command=lambda: self._copy_all_sql_rows(tree)
        )

        context_menu.tk_popup(event.x_root, event.y_root)
        context_menu.grab_release()