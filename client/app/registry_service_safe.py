"""Safety refinements for RegistryService mutation/restore and .reg support."""

from __future__ import annotations

import base64
import json
from typing import Any

from app.registry_service import RegistryService

try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore


class SafeRegistryService(RegistryService):
    """RegistryService με ακριβέστερο rollback και συμμετρικό .reg import/export."""

    def create_key(self, hive: str, path: str, view: str = "default") -> dict[str, Any]:
        """Κρατά backup του ίδιου target key αντί ολόκληρου του parent."""

        clean_path = self._normalize_path(path)
        if not clean_path:
            raise ValueError("Root hive cannot be created.")
        backup_id = self._backup_scope(hive, clean_path, view, reason="before_create_key")
        root, _, access = self._resolve(hive, clean_path, view, write=True)
        with winreg.CreateKeyEx(root, clean_path, 0, access):
            pass
        self._audit("create_key", hive, clean_path, view, backup_id, True)
        return {
            "hive": self._normalize_hive(hive),
            "path": clean_path,
            "view": self._normalize_view(view),
            "created": clean_path.rsplit("\\", 1)[-1],
            "backup_id": backup_id,
        }

    def restore_backup(self, backup_id: str) -> dict[str, Any]:
        """Επαναφέρει ακριβώς το saved scope και χειρίζεται σωστά nonexistent targets."""

        saved = self._load_backup(backup_id)
        if saved.get("truncated"):
            raise ValueError("Truncated backups cannot be restored safely.")

        hive = str(saved.get("hive") or "")
        path = str(saved.get("path") or "")
        view = str(saved.get("view") or "default")
        if not self._normalize_path(path):
            raise ValueError("Restoring an entire root hive is not allowed.")

        before_restore = self._backup_scope(hive, path, view, reason="before_restore")
        root, clean_path, access = self._resolve(hive, path, view, write=True)
        try:
            self._delete_tree(root, clean_path, access)
        except FileNotFoundError:
            pass

        if bool(saved.get("existed", True)):
            tree = saved.get("tree")
            if not isinstance(tree, dict):
                raise ValueError("Invalid backup content.")
            self._restore_tree(root, clean_path, access, tree)

        self._audit("restore_backup", hive, clean_path, view, before_restore, True)
        return {
            "restored_backup_id": backup_id,
            "pre_restore_backup_id": before_restore,
            "hive": hive,
            "path": clean_path,
            "view": view,
            "target_existed_before_original_change": bool(saved.get("existed", True)),
        }

    @staticmethod
    def _utf16_hex(text: str, *, multi: bool = False) -> str:
        if multi:
            parts = text.split("\n") if text else []
            raw = ("\x00".join(parts) + "\x00\x00").encode("utf-16le")
        else:
            raw = (text + "\x00").encode("utf-16le")
        return ",".join(f"{byte:02x}" for byte in raw)

    def _append_reg_lines(self, lines: list[str], hive: str, path: str, tree: dict[str, Any]) -> None:
        full_hive = self.HIVE_NAMES[hive]
        key_name = f"{full_hive}\\{path}" if path else full_hive
        lines.append(f"[{key_name}]")

        for item in tree.get("values") or []:
            name = item.get("name", "")
            prefix = "@" if name == "" else json.dumps(str(name), ensure_ascii=False)
            value_type = item.get("type")
            data = item.get("data")

            if value_type == "REG_SZ":
                encoded = json.dumps(str(data), ensure_ascii=False)
            elif value_type == "REG_EXPAND_SZ":
                encoded = "hex(2):" + self._utf16_hex(str(data))
            elif value_type == "REG_DWORD":
                encoded = f"dword:{int(data):08x}"
            elif value_type == "REG_QWORD":
                raw = int(data).to_bytes(8, "little")
                encoded = "hex(b):" + ",".join(f"{byte:02x}" for byte in raw)
            elif value_type == "REG_BINARY" and isinstance(data, dict):
                raw = base64.b64decode(str(data.get("value") or ""))
                encoded = "hex:" + ",".join(f"{byte:02x}" for byte in raw)
            elif value_type == "REG_MULTI_SZ" and isinstance(data, list):
                raw = ("\x00".join(str(part) for part in data) + "\x00\x00").encode("utf-16le")
                encoded = "hex(7):" + ",".join(f"{byte:02x}" for byte in raw)
            else:
                continue
            lines.append(f"{prefix}={encoded}")

        lines.append("")
        for child, child_tree in (tree.get("subkeys") or {}).items():
            if isinstance(child_tree, dict) and not child_tree.get("access_error"):
                self._append_reg_lines(lines, hive, self._join_path(path, str(child)), child_tree)

    @staticmethod
    def _parse_hex_bytes(data_text: str) -> bytes:
        payload = data_text.split(":", 1)[1]
        parts = [part.strip() for part in payload.split(",") if part.strip()]
        return bytes(int(part, 16) for part in parts)

    def _parse_reg_text(self, reg_text: Any, view: str) -> list[dict[str, Any]]:
        text = str(reg_text or "")
        if not 1 <= len(text) <= 2_000_000:
            raise ValueError("Invalid .reg content.")
        normalized_view = self._normalize_view(view)
        # Safe importer intentionally rejects line-continuation syntax. The exporter
        # emits single-line values, so preview/apply remains deterministic.
        lines = text.replace("\r\n", "\n").split("\n")
        if not lines or lines[0].lstrip("\ufeff").strip() not in {"Windows Registry Editor Version 5.00", "REGEDIT4"}:
            raise ValueError("Unsupported .reg header.")

        current_hive = ""
        current_path = ""
        operations: list[dict[str, Any]] = []
        aliases = {full.upper(): short for short, full in self.HIVE_NAMES.items()}

        for raw_line in lines[1:]:
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            if line.endswith("\\"):
                raise ValueError("Multiline .reg continuation is not allowed by safe import.")
            if line.startswith("[") and line.endswith("]"):
                key_text = line[1:-1]
                if key_text.startswith("-"):
                    raise ValueError(".reg key deletion is not allowed by safe import.")
                parts = key_text.split("\\", 1)
                full_hive = parts[0].upper()
                if full_hive not in aliases:
                    raise ValueError("Unsupported .reg hive.")
                current_hive = aliases[full_hive]
                current_path = self._normalize_path(parts[1] if len(parts) > 1 else "")
                continue

            if not current_hive or "=" not in line:
                raise ValueError("Unsupported .reg syntax.")
            name_text, data_text = line.split("=", 1)
            if name_text == "@":
                value_name = ""
            elif name_text.startswith('"') and name_text.endswith('"'):
                value_name = json.loads(name_text)
            else:
                raise ValueError("Unsupported .reg value name syntax.")
            if data_text == "-":
                raise ValueError(".reg value deletion is not allowed by safe import.")

            lower = data_text.lower()
            if data_text.startswith('"'):
                value_type = "REG_SZ"
                value = json.loads(data_text)
            elif lower.startswith("dword:"):
                value_type = "REG_DWORD"
                value = int(data_text.split(":", 1)[1], 16)
            elif lower.startswith("hex(b):"):
                raw = self._parse_hex_bytes(data_text)
                if len(raw) != 8:
                    raise ValueError("Invalid REG_QWORD byte length.")
                value_type = "REG_QWORD"
                value = int.from_bytes(raw, "little")
            elif lower.startswith("hex(2):"):
                raw = self._parse_hex_bytes(data_text)
                value_type = "REG_EXPAND_SZ"
                value = raw.decode("utf-16le").rstrip("\x00")
            elif lower.startswith("hex(7):"):
                raw = self._parse_hex_bytes(data_text)
                decoded = raw.decode("utf-16le").rstrip("\x00")
                value_type = "REG_MULTI_SZ"
                value = decoded.split("\x00") if decoded else []
            elif lower.startswith("hex:"):
                raw = self._parse_hex_bytes(data_text)
                value_type = "REG_BINARY"
                value = {"encoding": "base64", "value": base64.b64encode(raw).decode("ascii"), "length": len(raw)}
            else:
                raise ValueError("Unsupported .reg data type.")

            operation = {
                "action": "set_value",
                "hive": current_hive,
                "path": current_path,
                "view": normalized_view,
                "value_name": self._validate_value_name(value_name),
                "value_type": value_type,
                "value": value,
            }
            operation["identity"] = self._profile_identity(operation)
            operations.append(operation)
            if len(operations) > 5000:
                raise ValueError(".reg import contains too many operations.")

        return operations
