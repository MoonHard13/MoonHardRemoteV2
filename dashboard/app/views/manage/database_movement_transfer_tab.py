from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.theme import COLORS, FONTS, secondary_button_style
from app.views.manage.database_duplicate_mark_tab import DuplicateMarkDatabaseTab


class MovementTransferDatabaseTab(DuplicateMarkDatabaseTab):
    """Adds the Μεταφορά κινήσεων workflow to the Database tab."""

    REST_MODE = "Εστιατορική ημερομηνία"
    REAL_MODE = "Πραγματική ημερομηνία"
    RECEIPT_MODE = "Απόδειξη"

    ACTION_TITLES = {
        **DuplicateMarkDatabaseTab.ACTION_TITLES,
        "movement_stations": "SalesStations",
        "movement_receipt_search": "Αναζήτηση απόδειξης",
        "movement_transfer_date": "Μεταφορά κινήσεων",
        "movement_transfer_receipt": "Μεταφορά απόδειξης",
    }

    def _build_ui(self) -> None:
        super()._build_ui()

        self._station_map: dict[str, int] = {}
        self._receipt_map: dict[str, dict] = {}
        self.use_station_var = tk.BooleanVar(value=False)

        self.movement_card = self._card(
            self.left_stack,
            "Μεταφορά κινήσεων",
            "Μεταφορά ανά εστιατορική ημερομηνία, πραγματική ημερομηνία ή συγκεκριμένη απόδειξη.",
            warning=True,
        )
        self.movement_card.grid(row=3, column=0, pady=(0, 10), sticky="ew")
        self.movement_card.grid_columnconfigure(0, weight=1)
        self.movement_card.grid_columnconfigure(1, weight=1)

        mode_row = ctk.CTkFrame(self.movement_card, fg_color="transparent")
        mode_row.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")
        mode_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            mode_row,
            text="Τρόπος μεταφοράς",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        ).grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.movement_mode = ctk.CTkOptionMenu(
            mode_row,
            values=[self.REST_MODE, self.REAL_MODE, self.RECEIPT_MODE],
            command=self._on_movement_mode,
        )
        self.movement_mode.grid(row=0, column=1, sticky="ew")
        self.movement_mode.set(self.REST_MODE)

        station_row = ctk.CTkFrame(self.movement_card, fg_color="transparent")
        station_row.grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="ew")
        station_row.grid_columnconfigure(1, weight=1)
        self.station_checkbox = ctk.CTkCheckBox(
            station_row,
            text="Φίλτρο SalesStation",
            variable=self.use_station_var,
            command=self._on_station_toggle,
            font=FONTS.small,
            text_color=COLORS.text_primary,
        )
        self.station_checkbox.grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.station_option = ctk.CTkOptionMenu(
            station_row,
            values=["Δεν έχει φορτωθεί SalesStation"],
            state="disabled",
        )
        self.station_option.grid(row=0, column=1, sticky="ew")
        self.reload_stations_button = ctk.CTkButton(
            station_row,
            text="↻",
            width=38,
            height=30,
            command=self.request_stations,
            **secondary_button_style(),
        )
        self.reload_stations_button.grid(row=0, column=2, padx=(8, 0))

        self.rest_frame = ctk.CTkFrame(self.movement_card, fg_color="transparent")
        self.rest_frame.grid_columnconfigure(0, weight=1)
        self.rest_frame.grid_columnconfigure(1, weight=1)
        self.rest_old_entry = self._date_field(
            self.rest_frame, "Από εστιατορική · YYYYMMDD", 0, 0
        )
        self.rest_new_entry = self._date_field(
            self.rest_frame, "Σε εστιατορική · YYYYMMDD", 0, 1
        )
        self.rest_transfer_button = self._action_button(
            self.rest_frame,
            text="Μεταφορά κινήσεων",
            command=self.request_rest_transfer,
            style="danger",
        )
        self.rest_transfer_button.grid(
            row=1, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="ew"
        )

        self.real_frame = ctk.CTkFrame(self.movement_card, fg_color="transparent")
        self.real_frame.grid_columnconfigure(0, weight=1)
        self.real_frame.grid_columnconfigure(1, weight=1)
        self.real_old_entry = self._date_field(
            self.real_frame, "Από εστιατορική · YYYYMMDD", 0, 0
        )
        self.real_real_entry = self._date_field(
            self.real_frame, "Πραγματική ημερομηνία · YYYYMMDD", 0, 1
        )
        self.real_new_entry = self._date_field(
            self.real_frame, "Σε εστιατορική · YYYYMMDD", 1, 0
        )
        self.real_transfer_button = self._action_button(
            self.real_frame,
            text="Μεταφορά κινήσεων",
            command=self.request_real_transfer,
            style="danger",
        )
        self.real_transfer_button.grid(
            row=1, column=1, padx=16, pady=(0, 10), sticky="ew"
        )

        self.receipt_frame = ctk.CTkFrame(self.movement_card, fg_color="transparent")
        self.receipt_frame.grid_columnconfigure(0, weight=1)
        self.receipt_frame.grid_columnconfigure(1, weight=1)

        receipt_search = ctk.CTkFrame(self.receipt_frame, fg_color="transparent")
        receipt_search.grid(row=0, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="ew")
        receipt_search.grid_columnconfigure(0, weight=1)
        receipt_search.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            receipt_search,
            text="Αριθμός απόδειξης",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")
        ctk.CTkLabel(
            receipt_search,
            text="Ημερομηνία (προαιρετική) · YYYYMMDD",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        ).grid(row=0, column=1, padx=(8, 0), sticky="w")
        self.receipt_no_entry = ctk.CTkEntry(receipt_search)
        self.receipt_no_entry.grid(row=1, column=0, padx=(0, 8), sticky="ew")
        self.receipt_date_entry = ctk.CTkEntry(receipt_search)
        self.receipt_date_entry.grid(row=1, column=1, padx=(8, 0), sticky="ew")

        self.receipt_search_button = self._action_button(
            self.receipt_frame,
            text="Αναζήτηση απόδειξης",
            command=self.request_receipt_search,
        )
        self.receipt_search_button.grid(
            row=1, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="ew"
        )

        ctk.CTkLabel(
            self.receipt_frame,
            text="Αποτέλεσμα αναζήτησης",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        ).grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 4), sticky="w")
        self.receipt_option = ctk.CTkOptionMenu(
            self.receipt_frame,
            values=["Δεν έχει επιλεγεί απόδειξη"],
            state="disabled",
        )
        self.receipt_option.grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="ew")

        self.receipt_new_entry = self._date_field(
            self.receipt_frame, "Νέα εστιατορική · YYYYMMDD", 4, 0
        )
        self.receipt_transfer_button = self._action_button(
            self.receipt_frame,
            text="Μεταφορά επιλεγμένης απόδειξης",
            command=self.request_receipt_transfer,
            style="danger",
        )
        self.receipt_transfer_button.grid(
            row=4, column=1, padx=16, pady=(18, 10), sticky="ew"
        )

        self.rest_frame.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.real_frame.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.receipt_frame.grid(row=4, column=0, columnspan=2, sticky="ew")
        self._on_movement_mode(self.REST_MODE)

    def _on_movement_mode(self, value: str) -> None:
        for frame in (self.rest_frame, self.real_frame, self.receipt_frame):
            frame.grid_remove()
        if value == self.REAL_MODE:
            self.real_frame.grid()
        elif value == self.RECEIPT_MODE:
            self.receipt_frame.grid()
        else:
            self.rest_frame.grid()

    def _on_station_toggle(self) -> None:
        if not self.use_station_var.get():
            self.station_option.configure(state="disabled")
            return
        self.station_option.configure(state="normal")
        if not self._station_map and not self.current_request_id:
            self.request_stations()

    def request_stations(self) -> None:
        if self.current_request_id:
            return
        self.request_action("movement_stations")

    def _selected_station_oid(self) -> str | None:
        if not self.use_station_var.get():
            return ""
        display = self.station_option.get()
        oid = self._station_map.get(display)
        if oid is None:
            self._set_status("Επίλεξε έγκυρο SalesStation.", COLORS.danger)
            return None
        return str(oid)

    def request_rest_transfer(self) -> None:
        old_date = self.rest_old_entry.get().strip()
        new_date = self.rest_new_entry.get().strip()
        if not self._valid_date(old_date) or not self._valid_date(new_date):
            self._set_status("Οι ημερομηνίες πρέπει να είναι YYYYMMDD.", COLORS.danger)
            return
        if old_date == new_date:
            self._set_status("Η παλιά και η νέα ημερομηνία πρέπει να διαφέρουν.", COLORS.danger)
            return
        station_oid = self._selected_station_oid()
        if station_oid is None:
            return
        station_text = self.station_option.get() if station_oid else "Όλα τα SalesStations"
        if not self._confirm(
            "Επιβεβαίωση μεταφοράς κινήσεων",
            f"Τρόπος: Εστιατορική ημερομηνία\nΑπό: {old_date}\nΣε: {new_date}\n"
            f"SalesStation: {station_text}\n\nΘα ενημερωθούν κινήσεις, πληρωμές και transfers. Συνέχεια;",
        ):
            return
        self._request_date_transfer("rest", old_date, "", new_date, station_oid)

    def request_real_transfer(self) -> None:
        old_date = self.real_old_entry.get().strip()
        real_date = self.real_real_entry.get().strip()
        new_date = self.real_new_entry.get().strip()
        if not all(self._valid_date(value) for value in (old_date, real_date, new_date)):
            self._set_status("Οι ημερομηνίες πρέπει να είναι YYYYMMDD.", COLORS.danger)
            return
        if old_date == new_date:
            self._set_status("Η παλιά και η νέα εστιατορική ημερομηνία πρέπει να διαφέρουν.", COLORS.danger)
            return
        station_oid = self._selected_station_oid()
        if station_oid is None:
            return
        station_text = self.station_option.get() if station_oid else "Όλα τα SalesStations"
        if not self._confirm(
            "Επιβεβαίωση μεταφοράς κινήσεων",
            f"Τρόπος: Πραγματική ημερομηνία\nΕστιατορική από: {old_date}\n"
            f"Πραγματική: {real_date}\nΕστιατορική σε: {new_date}\nSalesStation: {station_text}\n\n"
            "Θα ενημερωθούν κινήσεις, πληρωμές και transfers. Συνέχεια;",
        ):
            return
        self._request_date_transfer("real", old_date, real_date, new_date, station_oid)

    def _request_date_transfer(
        self,
        mode: str,
        old_date: str,
        real_date: str,
        new_date: str,
        station_oid: str,
    ) -> None:
        self.request_action(
            "movement_transfer_date",
            {
                "mode": mode,
                "old_date": old_date,
                "real_date": real_date,
                "new_date": new_date,
                "station_oid": station_oid,
            },
        )
        if self.current_action == "movement_transfer_date":
            self.progress_bar.set(0)
            self.progress_bar.grid()

    def request_receipt_search(self) -> None:
        note_no = self.receipt_no_entry.get().strip()
        search_date = self.receipt_date_entry.get().strip()
        if not note_no.isdigit():
            self._set_status("Ο αριθμός απόδειξης πρέπει να είναι αριθμητικός.", COLORS.danger)
            return
        if search_date and not self._valid_date(search_date):
            self._set_status("Η προαιρετική ημερομηνία πρέπει να είναι YYYYMMDD.", COLORS.danger)
            return
        station_oid = self._selected_station_oid()
        if station_oid is None:
            return
        self._receipt_map.clear()
        self.receipt_option.configure(values=["Αναζήτηση..."], state="disabled")
        self.receipt_option.set("Αναζήτηση...")
        self.request_action(
            "movement_receipt_search",
            {
                "note_no": note_no,
                "search_date": search_date,
                "station_oid": station_oid,
            },
        )

    def request_receipt_transfer(self) -> None:
        selected = self._receipt_map.get(self.receipt_option.get())
        if not selected:
            self._set_status("Αναζήτησε και επίλεξε πρώτα μία απόδειξη.", COLORS.danger)
            return
        new_date = self.receipt_new_entry.get().strip()
        if not self._valid_date(new_date):
            self._set_status("Η νέα εστιατορική ημερομηνία πρέπει να είναι YYYYMMDD.", COLORS.danger)
            return
        if new_date == str(selected.get("init_date") or ""):
            self._set_status("Η νέα ημερομηνία είναι ίδια με την υπάρχουσα.", COLORS.danger)
            return

        if not self._confirm(
            "Επιβεβαίωση μεταφοράς απόδειξης",
            f"Πηγή: {selected.get('source')}\n"
            f"Απόδειξη: {selected.get('note_no')} · Code {selected.get('note_code')}\n"
            f"Εστιατορική: {selected.get('init_date')} → {new_date}\n"
            f"SalesStation: {selected.get('station_descr') or selected.get('station_oid')}\n"
            f"POS Header: {selected.get('pos_hdr')}\n\n"
            "Θα μεταφερθούν όλες οι γραμμές της απόδειξης, οι πληρωμές και τα σχετικά transfers. Συνέχεια;",
        ):
            return

        self.request_action(
            "movement_transfer_receipt",
            {
                "source": str(selected["source"]),
                "pos_hdr": str(selected["pos_hdr"]),
                "note_no": str(selected["note_no"]),
                "note_code": str(selected["note_code"]),
                "old_date": str(selected["init_date"]),
                "new_date": new_date,
                "station_oid": str(selected["station_oid"]),
            },
        )
        if self.current_action == "movement_transfer_receipt":
            self.progress_bar.set(0)
            self.progress_bar.grid()

    def handle_progress(self, payload: dict) -> None:
        if payload.get("action") not in {"movement_transfer_date", "movement_transfer_receipt"}:
            super().handle_progress(payload)
            return
        if payload.get("client_code") != self.client_code:
            return
        if payload.get("request_id") != self.current_request_id:
            return
        if payload.get("action") != self.current_action:
            return

        message = str(payload.get("message") or "").strip()
        percent = payload.get("percent")
        if type(percent) is int:
            self.progress_bar.set(max(0, min(percent, 100)) / 100)
        if message:
            self._set_status(message, COLORS.accent)
            if message not in self._progress_messages:
                self._progress_messages.add(message)
                self._append_output(f"\n- {message}")

    def handle_result(self, payload: dict) -> None:
        action = payload.get("action")
        is_current = (
            payload.get("client_code") == self.client_code
            and payload.get("request_id") == self.current_request_id
            and action == self.current_action
        )
        super().handle_result(payload)
        if not is_current or not payload.get("success"):
            return

        if action == "movement_stations":
            self._apply_stations(payload.get("stations") or [])
        elif action == "movement_receipt_search":
            self._apply_receipts(payload.get("receipts") or [])
        elif action in {"movement_transfer_date", "movement_transfer_receipt"}:
            self.progress_bar.set(1)
            if action == "movement_transfer_receipt":
                self._receipt_map.clear()
                self.receipt_option.configure(values=["Αναζήτησε ξανά την απόδειξη"], state="disabled")
                self.receipt_option.set("Αναζήτησε ξανά την απόδειξη")

    def _apply_stations(self, stations: list[dict]) -> None:
        self._station_map.clear()
        values = []
        for station in stations:
            oid = station.get("oid")
            if type(oid) is not int:
                continue
            descr = str(station.get("description") or "").strip() or "SalesStation"
            number = station.get("number")
            rest_date = str(station.get("rest_date") or "")
            display = f"{descr} · No {number if number is not None else '-'} · OID {oid}"
            if rest_date:
                display += f" · {rest_date}"
            self._station_map[display] = oid
            values.append(display)
        if not values:
            values = ["Δεν βρέθηκαν SalesStations"]
            self.station_option.configure(values=values, state="disabled")
        else:
            self.station_option.configure(
                values=values,
                state="normal" if self.use_station_var.get() else "disabled",
            )
        self.station_option.set(values[0])

    def _apply_receipts(self, receipts: list[dict]) -> None:
        self._receipt_map.clear()
        values = []
        for receipt in receipts:
            source = str(receipt.get("source") or "")
            source_label = "Current" if source == "current" else "History"
            value = receipt.get("value")
            amount = "-" if value is None else f"{float(value):.2f}"
            station = str(receipt.get("station_descr") or "").strip() or f"OID {receipt.get('station_oid')}"
            display = (
                f"{source_label} · {receipt.get('init_date')} · No {receipt.get('note_no')} · "
                f"Code {receipt.get('note_code')} · {station} · {amount}"
            )
            self._receipt_map[display] = receipt
            values.append(display)
        if not values:
            values = ["Δεν βρέθηκε απόδειξη"]
            self.receipt_option.configure(values=values, state="disabled")
        else:
            self.receipt_option.configure(values=values, state="normal")
        self.receipt_option.set(values[0])

    def _on_bo_selected(self, selected_value: str) -> None:
        super()._on_bo_selected(selected_value)
        self._station_map.clear()
        self._receipt_map.clear()
        if hasattr(self, "station_option"):
            self.station_option.configure(values=["Φόρτωσε SalesStations"], state="disabled")
            self.station_option.set("Φόρτωσε SalesStations")
        if hasattr(self, "receipt_option"):
            self.receipt_option.configure(values=["Δεν έχει επιλεγεί απόδειξη"], state="disabled")
            self.receipt_option.set("Δεν έχει επιλεγεί απόδειξη")

    def _format_result(self, payload: dict) -> str:
        action = payload.get("action")
        if action == "movement_stations":
            stations = payload.get("stations") or []
            return f"Action: SalesStations\nLoaded: {len(stations)}"
        if action == "movement_receipt_search":
            receipts = payload.get("receipts") or []
            lines = [
                "Action: Αναζήτηση απόδειξης",
                f"Source: {payload.get('source') or '-'}",
                f"Results: {len(receipts)}",
            ]
            for receipt in receipts[:20]:
                lines.append(
                    f"- {receipt.get('init_date')} | No {receipt.get('note_no')} | "
                    f"Code {receipt.get('note_code')} | Station {receipt.get('station_oid')} | "
                    f"POS Hdr {receipt.get('pos_hdr')}"
                )
            return "\n".join(lines)
        if action in {"movement_transfer_date", "movement_transfer_receipt"}:
            return "\n".join(
                [
                    f"Action: {self.ACTION_TITLES.get(str(action), str(action))}",
                    f"Database: {payload.get('database_name') or '-'}",
                    f"Source: {payload.get('source') or '-'}",
                    f"From: {payload.get('old_date') or '-'}",
                    f"To: {payload.get('new_date') or '-'}",
                    f"SalesStation OID: {payload.get('station_oid') if payload.get('station_oid') is not None else 'All'}",
                    f"Movement rows: {payload.get('movement_rows')}",
                    f"Payment rows: {payload.get('payment_rows')}",
                    f"Transfer rows: {payload.get('transfer_rows')}",
                    f"Elapsed: {payload.get('elapsed_ms')} ms",
                ]
            )
        return super()._format_result(payload)
