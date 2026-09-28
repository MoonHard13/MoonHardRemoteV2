"""Ασφαλής τοπική πρόσβαση στο Windows Registry για το MoonHard Remote Client."""

from __future__ import annotations

import base64
import json
import logging
import os
import platform
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:  # Το module πρέπει να μπορεί να γίνει import και σε non-Windows CI.
    import winreg  # type: ignore
except ImportError:  # pragma: no cover - αναμενόμενο σε Linux CI.
    winreg = None  # type: ignore


logger = logging.getLogger(__name__)


class RegistryService:
    """Εκτελεί allowlisted Registry λειτουργίες αποκλειστικά στον τοπικό client."""

    MAX_PATH_LENGTH = 2048
    MAX_VALUE_NAME_LENGTH = 16383
    MAX_TEXT_VALUE_LENGTH = 1_000_000
    MAX_BINARY_BYTES = 512_000
    MAX_SEARCH_RESULTS = 500
    MAX_SEARCH_DEPTH = 20
    MAX_SNAPSHOT_ENTRIES = 20_000

    HIVE_NAMES = {
        "HKLM": "HKEY_LOCAL_MACHINE",
        "HKCU": "HKEY_CURRENT_USER",
        "HKCR": "HKEY_CLASSES_ROOT",
        "HKU": "HKEY_USERS",
        "HKCC": "HKEY_CURRENT_CONFIG",
    }

    TYPE_NAMES = {
        0: "REG_NONE",
        1: "REG_SZ",
        2: "REG_EXPAND_SZ",
        3: "REG_BINARY",
        4: "REG_DWORD",
        7: "REG_MULTI_SZ",
        11: "REG_QWORD",
    }

    TYPE_BY_NAME = {
        "REG_NONE": 0,
        "REG_SZ": 1,
        "REG_EXPAND_SZ": 2,
        "REG_BINARY": 3,
        "REG_DWORD": 4,
        "REG_MULTI_SZ": 7,
        "REG_QWORD": 11,
    }

    MUTATING_OPERATIONS = frozenset(
        {
            "create_key",
            "set_value",
            "delete_value",
            "delete_key",
            "restore_backup",
            "profile_save",
            "profile_delete",
            "profile_apply",
            "import_reg_apply",
        }
    )

    def __init__(self, state_root: str | Path | None = None) -> None:
        """Αρχικοποιεί storage για backups/profiles χωρίς τρίτες βιβλιοθήκες."""

        default_root = Path(
            os.environ.get("PROGRAMDATA")
            or tempfile.gettempdir()
        ) / "MoonHardRemoteV2" / "Registry"
        self.state_root = Path(state_root) if state_root else default_root
        self.backup_root = self.state_root / "Backups"
        self.profile_root = self.state_root / "Profiles"
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.profile_root.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Κεντρικό dispatch μόνο σε ρητά υποστηριζόμενες Registry λειτουργίες."""

        params = parameters or {}
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "context": self.get_context,
            "list_key": self.list_key,
            "get_value": self.get_value,
            "search": self.search,
            "create_key": self.create_key,
            "set_value": self.set_value,
            "delete_value": self.delete_value,
            "delete_key": self.delete_key,
            "snapshot": self.snapshot,
            "compare_snapshot": self.compare_snapshot,
            "history": self.history,
            "restore_backup": self.restore_backup,
            "diagnostics": self.diagnostics,
            "profile_list": self.profile_list,
            "profile_save": self.profile_save,
            "profile_delete": self.profile_delete,
            "profile_check": self.profile_check,
            "profile_apply": self.profile_apply,
            "export_reg": self.export_reg,
            "import_reg_preview": self.import_reg_preview,
            "import_reg_apply": self.import_reg_apply,
        }
        handler = handlers.get(str(operation))
        if handler is None:
            raise ValueError("Unsupported registry operation.")

        started = time.perf_counter()
        try:
            if operation == "search":
                result = handler(progress_callback=progress_callback, **params)
            elif operation == "profile_apply":
                result = handler(progress_callback=progress_callback, **params)
            else:
                result = handler(**params)
            return {
                "operation": operation,
                "success": True,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                **result,
            }
        except Exception as exc:
            logger.warning(
                "Registry operation failed. operation=%s exception_type=%s",
                operation,
                type(exc).__name__,
            )
            return {
                "operation": operation,
                "success": False,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "error": self._safe_error(exc),
            }

    def get_context(self) -> dict[str, Any]:
        """Επιστρέφει πληροφορίες context χωρίς να αποκαλύπτει Registry δεδομένα."""

        self._require_windows()
        username = str(os.environ.get("USERNAME") or "")
        user_domain = str(os.environ.get("USERDOMAIN") or "")
        running_as_system = username.upper() in {"SYSTEM", "LOCAL SYSTEM"}
        process_arch = platform.architecture()[0]
        os_arch = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or process_arch
        is_admin = self._is_admin()
        warning = ""
        if running_as_system:
            warning = (
                "Ο Client τρέχει ως SYSTEM. Το HKCU αφορά τον λογαριασμό του service, "
                "όχι απαραίτητα τον συνδεδεμένο χρήστη. Για user registry χρησιμοποιήστε HKU/SID."
            )

        return {
            "is_windows": True,
            "process_architecture": process_arch,
            "os_architecture": str(os_arch),
            "username": username,
            "user_domain": user_domain,
            "running_as_system": running_as_system,
            "is_admin": is_admin,
            "hkcu_warning": warning,
            "supported_hives": list(self.HIVE_NAMES),
            "supported_views": ["default", "64", "32"],
            "supported_types": list(self.TYPE_BY_NAME),
        }

    def list_key(self, hive: str, path: str = "", view: str = "default") -> dict[str, Any]:
        """Επιστρέφει άμεσα subkeys και values ενός key."""

        root, clean_path, access = self._resolve(hive, path, view, write=False)
        subkeys: list[dict[str, Any]] = []
        values: list[dict[str, Any]] = []
        with winreg.OpenKey(root, clean_path, 0, access) as key:
            subkey_count, value_count, modified = winreg.QueryInfoKey(key)
            for index in range(subkey_count):
                name = winreg.EnumKey(key, index)
                subkeys.append({"name": name})
            for index in range(value_count):
                name, value, value_type = winreg.EnumValue(key, index)
                values.append(self._value_payload(name, value, value_type))

        return {
            "hive": self._normalize_hive(hive),
            "path": clean_path,
            "view": self._normalize_view(view),
            "subkeys": subkeys,
            "values": values,
            "subkey_count": len(subkeys),
            "value_count": len(values),
            "last_modified": modified,
        }

    def get_value(
        self,
        hive: str,
        path: str,
        value_name: str = "",
        view: str = "default",
    ) -> dict[str, Any]:
        """Διαβάζει μία συγκεκριμένη Registry value."""

        root, clean_path, access = self._resolve(hive, path, view, write=False)
        clean_name = self._validate_value_name(value_name)
        with winreg.OpenKey(root, clean_path, 0, access) as key:
            value, value_type = winreg.QueryValueEx(key, clean_name)
        return {
            "hive": self._normalize_hive(hive),
            "path": clean_path,
            "view": self._normalize_view(view),
            "value": self._value_payload(clean_name, value, value_type),
        }

    def search(
        self,
        query: str,
        hive: str = "HKLM",
        path: str = "",
        view: str = "default",
        search_keys: bool = True,
        search_names: bool = True,
        search_data: bool = True,
        max_results: int = 200,
        max_depth: int = 12,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Κάνει bounded αναζήτηση ώστε να μην μπλοκάρει ανεξέλεγκτα ο client."""

        needle = str(query or "").strip().casefold()
        if not needle or len(needle) > 256:
            raise ValueError("Invalid search query.")
        limit = self._bounded_int(max_results, 1, self.MAX_SEARCH_RESULTS, "max_results")
        depth_limit = self._bounded_int(max_depth, 0, self.MAX_SEARCH_DEPTH, "max_depth")
        normalized_hive = self._normalize_hive(hive)
        clean_start = self._normalize_path(path)
        root, _, access = self._resolve(normalized_hive, clean_start, view, write=False)
        results: list[dict[str, Any]] = []
        visited = 0
        access_denied = 0
        stack: list[tuple[str, int]] = [(clean_start, 0)]

        while stack and len(results) < limit:
            current_path, depth = stack.pop()
            visited += 1
            if progress_callback and visited % 100 == 0:
                progress_callback(
                    {
                        "stage": "searching",
                        "message": f"Registry search: {visited} keys checked, {len(results)} matches.",
                        "current": visited,
                    }
                )
            try:
                with winreg.OpenKey(root, current_path, 0, access) as key:
                    subkey_count, value_count, _ = winreg.QueryInfoKey(key)
                    if search_keys:
                        key_name = current_path.rsplit("\\", 1)[-1] if current_path else normalized_hive
                        if needle in key_name.casefold() or needle in current_path.casefold():
                            results.append(
                                {
                                    "kind": "key",
                                    "hive": normalized_hive,
                                    "path": current_path,
                                    "name": key_name,
                                }
                            )
                            if len(results) >= limit:
                                break

                    for index in range(value_count):
                        name, value, value_type = winreg.EnumValue(key, index)
                        match_name = search_names and needle in str(name).casefold()
                        data_preview = self._display_data(value, value_type)
                        match_data = search_data and needle in data_preview.casefold()
                        if match_name or match_data:
                            results.append(
                                {
                                    "kind": "value",
                                    "hive": normalized_hive,
                                    "path": current_path,
                                    **self._value_payload(name, value, value_type),
                                }
                            )
                            if len(results) >= limit:
                                break

                    if depth < depth_limit:
                        children: list[str] = []
                        for index in range(subkey_count):
                            children.append(winreg.EnumKey(key, index))
                        for child in reversed(children):
                            stack.append((self._join_path(current_path, child), depth + 1))
            except PermissionError:
                access_denied += 1
            except OSError:
                continue

        return {
            "query": str(query),
            "hive": normalized_hive,
            "path": clean_start,
            "view": self._normalize_view(view),
            "results": results,
            "count": len(results),
            "visited_keys": visited,
            "access_denied_keys": access_denied,
            "truncated": bool(stack) or len(results) >= limit,
        }

    def create_key(self, hive: str, path: str, view: str = "default") -> dict[str, Any]:
        """Δημιουργεί key αφού πρώτα καταγράψει backup του parent."""

        clean_path = self._normalize_path(path)
        if not clean_path:
            raise ValueError("Root hive cannot be created.")
        parent, _, leaf = clean_path.rpartition("\\")
        backup_id = self._backup_scope(hive, parent, view, reason="before_create_key")
        root, _, access = self._resolve(hive, clean_path, view, write=True)
        with winreg.CreateKeyEx(root, clean_path, 0, access):
            pass
        self._audit("create_key", hive, clean_path, view, backup_id, True)
        return {"hive": self._normalize_hive(hive), "path": clean_path, "view": self._normalize_view(view), "created": leaf, "backup_id": backup_id}

    def set_value(
        self,
        hive: str,
        path: str,
        value_name: str,
        value_type: str,
        value: Any,
        view: str = "default",
    ) -> dict[str, Any]:
        """Δημιουργεί/ενημερώνει value με type validation και automatic backup."""

        clean_name = self._validate_value_name(value_name)
        type_name = str(value_type or "").upper()
        if type_name not in self.TYPE_BY_NAME:
            raise ValueError("Unsupported registry value type.")
        native_type = self.TYPE_BY_NAME[type_name]
        native_value = self._decode_input_value(value, native_type)
        backup_id = self._backup_scope(hive, path, view, reason="before_set_value")
        root, clean_path, access = self._resolve(hive, path, view, write=True)
        with winreg.CreateKeyEx(root, clean_path, 0, access) as key:
            winreg.SetValueEx(key, clean_name, 0, native_type, native_value)
        self._audit("set_value", hive, clean_path, view, backup_id, True, value_name=clean_name)
        return {"hive": self._normalize_hive(hive), "path": clean_path, "view": self._normalize_view(view), "value": self._value_payload(clean_name, native_value, native_type), "backup_id": backup_id}

    def delete_value(self, hive: str, path: str, value_name: str, view: str = "default") -> dict[str, Any]:
        """Διαγράφει value μόνο αφού αποθηκευτεί backup του key."""

        clean_name = self._validate_value_name(value_name)
        backup_id = self._backup_scope(hive, path, view, reason="before_delete_value")
        root, clean_path, access = self._resolve(hive, path, view, write=True)
        with winreg.OpenKey(root, clean_path, 0, access) as key:
            winreg.DeleteValue(key, clean_name)
        self._audit("delete_value", hive, clean_path, view, backup_id, True, value_name=clean_name)
        return {"hive": self._normalize_hive(hive), "path": clean_path, "view": self._normalize_view(view), "value_name": clean_name, "backup_id": backup_id}

    def delete_key(
        self,
        hive: str,
        path: str,
        view: str = "default",
        recursive: bool = False,
    ) -> dict[str, Any]:
        """Διαγράφει key, με recursive delete μόνο όταν ζητηθεί ρητά."""

        clean_path = self._normalize_path(path)
        if not clean_path:
            raise ValueError("Root hive cannot be deleted.")
        backup_id = self._backup_scope(hive, clean_path, view, reason="before_delete_key")
        root, _, access = self._resolve(hive, clean_path, view, write=True)
        if recursive:
            self._delete_tree(root, clean_path, access)
        else:
            winreg.DeleteKeyEx(root, clean_path, access & (winreg.KEY_WOW64_32KEY | winreg.KEY_WOW64_64KEY), 0)
        self._audit("delete_key", hive, clean_path, view, backup_id, True)
        return {"hive": self._normalize_hive(hive), "path": clean_path, "view": self._normalize_view(view), "recursive": bool(recursive), "backup_id": backup_id}

    def snapshot(
        self,
        hive: str,
        path: str = "",
        view: str = "default",
        max_entries: int = 5000,
    ) -> dict[str, Any]:
        """Δημιουργεί scoped JSON snapshot για compare/restore."""

        limit = self._bounded_int(max_entries, 1, self.MAX_SNAPSHOT_ENTRIES, "max_entries")
        tree, count, truncated = self._capture_tree(hive, path, view, limit)
        snapshot_id = str(uuid.uuid4())
        document = {
            "snapshot_id": snapshot_id,
            "created_at": self._utc_now(),
            "hive": self._normalize_hive(hive),
            "path": self._normalize_path(path),
            "view": self._normalize_view(view),
            "entry_count": count,
            "truncated": truncated,
            "tree": tree,
        }
        file_path = self.backup_root / f"snapshot_{snapshot_id}.json"
        self._atomic_json_write(file_path, document)
        return {**document, "tree": tree, "backup_id": snapshot_id}

    def compare_snapshot(
        self,
        backup_id: str,
        hive: str | None = None,
        path: str | None = None,
        view: str | None = None,
    ) -> dict[str, Any]:
        """Συγκρίνει αποθηκευμένο snapshot με την τρέχουσα κατάσταση του ίδιου scope."""

        saved = self._load_backup(backup_id)
        target_hive = hive or saved.get("hive")
        target_path = saved.get("path") if path is None else path
        target_view = view or saved.get("view") or "default"
        current_tree, _, current_truncated = self._capture_tree(target_hive, target_path, target_view, self.MAX_SNAPSHOT_ENTRIES)
        saved_flat = self._flatten_tree(saved.get("tree") or {}, str(saved.get("path") or ""))
        current_flat = self._flatten_tree(current_tree, self._normalize_path(target_path))
        added: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []
        for key in sorted(current_flat.keys() - saved_flat.keys()):
            added.append({"identity": key, "current": current_flat[key]})
        for key in sorted(saved_flat.keys() - current_flat.keys()):
            removed.append({"identity": key, "before": saved_flat[key]})
        for key in sorted(saved_flat.keys() & current_flat.keys()):
            if saved_flat[key] != current_flat[key]:
                changed.append({"identity": key, "before": saved_flat[key], "current": current_flat[key]})
        return {
            "backup_id": backup_id,
            "hive": self._normalize_hive(target_hive),
            "path": self._normalize_path(target_path),
            "view": self._normalize_view(target_view),
            "added": added,
            "removed": removed,
            "changed": changed,
            "same_count": len(saved_flat.keys() & current_flat.keys()) - len(changed),
            "different_count": len(added) + len(removed) + len(changed),
            "truncated": bool(saved.get("truncated")) or current_truncated,
        }

    def history(self, limit: int = 100) -> dict[str, Any]:
        """Επιστρέφει πρόσφατα local registry backups χωρίς Registry data στο log."""

        max_items = self._bounded_int(limit, 1, 500, "limit")
        items: list[dict[str, Any]] = []
        for path in sorted(self.backup_root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append(
                    {
                        "backup_id": data.get("backup_id") or data.get("snapshot_id"),
                        "created_at": data.get("created_at"),
                        "reason": data.get("reason") or "snapshot",
                        "hive": data.get("hive"),
                        "path": data.get("path"),
                        "view": data.get("view"),
                        "entry_count": data.get("entry_count", 0),
                        "truncated": bool(data.get("truncated", False)),
                    }
                )
            except (OSError, ValueError, TypeError):
                continue
            if len(items) >= max_items:
                break
        return {"items": items, "count": len(items)}

    def restore_backup(self, backup_id: str) -> dict[str, Any]:
        """Επαναφέρει snapshot αφού κρατήσει νέο pre-restore backup."""

        saved = self._load_backup(backup_id)
        if saved.get("truncated"):
            raise ValueError("Truncated backups cannot be restored safely.")
        hive = str(saved.get("hive") or "")
        path = str(saved.get("path") or "")
        view = str(saved.get("view") or "default")
        before_restore = self._backup_scope(hive, path, view, reason="before_restore")
        root, clean_path, access = self._resolve(hive, path, view, write=True)
        if clean_path:
            try:
                self._delete_tree(root, clean_path, access)
            except FileNotFoundError:
                pass
        tree = saved.get("tree")
        if not isinstance(tree, dict):
            raise ValueError("Invalid backup content.")
        self._restore_tree(root, clean_path, access, tree)
        self._audit("restore_backup", hive, clean_path, view, before_restore, True)
        return {"restored_backup_id": backup_id, "pre_restore_backup_id": before_restore, "hive": hive, "path": clean_path, "view": view}

    def diagnostics(self) -> dict[str, Any]:
        """Εκτελεί ασφαλείς γενικούς Registry diagnostics χωρίς αυθαίρετες ERP παραδοχές."""

        context = self.get_context()
        checks: list[dict[str, Any]] = []
        for hive in self.HIVE_NAMES:
            try:
                listing = self.list_key(hive, "", "default")
                checks.append({"name": f"{hive} access", "status": "ok", "details": f"Readable ({listing['subkey_count']} root subkeys)."})
            except PermissionError:
                checks.append({"name": f"{hive} access", "status": "warning", "details": "Access denied."})
            except Exception as exc:
                checks.append({"name": f"{hive} access", "status": "error", "details": self._safe_error(exc)})
        if not context.get("is_admin"):
            checks.append({"name": "Administrator rights", "status": "warning", "details": "HKLM write operations may fail without elevation."})
        if context.get("running_as_system"):
            checks.append({"name": "HKCU context", "status": "warning", "details": context.get("hkcu_warning")})
        return {"context": context, "checks": checks, "count": len(checks)}

    def profile_list(self) -> dict[str, Any]:
        """Λίστα Registry profiles που είναι αποθηκευμένα τοπικά στον client."""

        profiles: list[dict[str, Any]] = []
        for path in sorted(self.profile_root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                profiles.append({"profile_id": data.get("profile_id"), "name": data.get("name"), "description": data.get("description", ""), "entry_count": len(data.get("entries") or [])})
            except (OSError, ValueError, TypeError):
                continue
        return {"profiles": profiles, "count": len(profiles)}

    def profile_save(
        self,
        name: str,
        entries: list[dict[str, Any]],
        description: str = "",
        profile_id: str = "",
    ) -> dict[str, Any]:
        """Αποθηκεύει validated expected Registry values σε JSON profile."""

        clean_name = str(name or "").strip()
        if not 1 <= len(clean_name) <= 120:
            raise ValueError("Invalid profile name.")
        if not isinstance(entries, list) or len(entries) > 1000:
            raise ValueError("Invalid profile entries.")
        normalized_entries = [self._validate_profile_entry(item) for item in entries]
        clean_id = self._validate_identifier(profile_id) if profile_id else str(uuid.uuid4())
        document = {"profile_id": clean_id, "name": clean_name, "description": str(description or "")[:1000], "updated_at": self._utc_now(), "entries": normalized_entries}
        self._atomic_json_write(self.profile_root / f"{clean_id}.json", document)
        return {"profile_id": clean_id, "name": clean_name, "entry_count": len(normalized_entries)}

    def profile_delete(self, profile_id: str) -> dict[str, Any]:
        """Διαγράφει profile μόνο από το local Registry profile storage."""

        clean_id = self._validate_identifier(profile_id)
        path = self.profile_root / f"{clean_id}.json"
        path.unlink()
        return {"profile_id": clean_id, "deleted": True}

    def profile_check(self, profile_id: str) -> dict[str, Any]:
        """Συγκρίνει profile expectations με το Registry χωρίς αλλαγές."""

        profile = self._load_profile(profile_id)
        results = [self._check_profile_entry(entry) for entry in profile.get("entries") or []]
        return {"profile_id": profile["profile_id"], "name": profile["name"], "results": results, "count": len(results), "ok_count": sum(1 for item in results if item["status"] == "ok"), "problem_count": sum(1 for item in results if item["status"] != "ok")}

    def profile_apply(
        self,
        profile_id: str,
        mode: str = "missing",
        dry_run: bool = True,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Εφαρμόζει profile με dry-run default και backup πριν από κάθε πραγματική αλλαγή."""

        if mode not in {"missing", "all"}:
            raise ValueError("Invalid profile apply mode.")
        profile = self._load_profile(profile_id)
        checks = [self._check_profile_entry(entry) for entry in profile.get("entries") or []]
        planned = [item for item in checks if item["status"] == "missing" or (mode == "all" and item["status"] != "ok")]
        applied: list[dict[str, Any]] = []
        if not dry_run:
            entries_by_identity = {self._profile_identity(entry): entry for entry in profile.get("entries") or []}
            for index, item in enumerate(planned, start=1):
                entry = entries_by_identity[item["identity"]]
                result = self.set_value(entry["hive"], entry["path"], entry["value_name"], entry["value_type"], entry["value"], entry["view"])
                applied.append({"identity": item["identity"], "backup_id": result.get("backup_id")})
                if progress_callback:
                    progress_callback({"stage": "applying_profile", "message": f"Applied {index}/{len(planned)} profile entries.", "current": index, "total": len(planned)})
        return {"profile_id": profile["profile_id"], "dry_run": bool(dry_run), "mode": mode, "planned": planned, "applied": applied, "planned_count": len(planned), "applied_count": len(applied)}

    def export_reg(self, hive: str, path: str, view: str = "default", max_entries: int = 5000) -> dict[str, Any]:
        """Δημιουργεί .reg text για preview/download στο Dashboard χωρίς shell command."""

        tree, count, truncated = self._capture_tree(hive, path, view, self._bounded_int(max_entries, 1, self.MAX_SNAPSHOT_ENTRIES, "max_entries"))
        if truncated:
            raise ValueError("Registry export exceeded the safe entry limit.")
        normalized_hive = self._normalize_hive(hive)
        lines = ["Windows Registry Editor Version 5.00", ""]
        self._append_reg_lines(lines, normalized_hive, self._normalize_path(path), tree)
        return {"hive": normalized_hive, "path": self._normalize_path(path), "view": self._normalize_view(view), "entry_count": count, "reg_text": "\r\n".join(lines) + "\r\n"}

    def import_reg_preview(self, reg_text: str, view: str = "default") -> dict[str, Any]:
        """Κάνει strict preview ενός ασφαλούς subset .reg πριν επιτραπεί apply."""

        operations = self._parse_reg_text(reg_text, view)
        return {"view": self._normalize_view(view), "operations": operations, "count": len(operations)}

    def import_reg_apply(self, reg_text: str, view: str = "default") -> dict[str, Any]:
        """Εφαρμόζει μόνο το subset που πέρασε από τον ίδιο strict parser, με backups."""

        operations = self._parse_reg_text(reg_text, view)
        results: list[dict[str, Any]] = []
        for item in operations:
            if item["action"] == "set_value":
                result = self.set_value(item["hive"], item["path"], item["value_name"], item["value_type"], item["value"], item["view"])
                results.append({"identity": item["identity"], "backup_id": result.get("backup_id")})
            else:
                raise ValueError("Unsupported .reg operation.")
        return {"count": len(results), "results": results}

    def _require_windows(self) -> None:
        if winreg is None:
            raise RuntimeError("Windows Registry is available only on Windows clients.")

    def _normalize_hive(self, hive: str) -> str:
        self._require_windows()
        clean = str(hive or "").upper().strip()
        aliases = {full: short for short, full in self.HIVE_NAMES.items()}
        clean = aliases.get(clean, clean)
        if clean not in self.HIVE_NAMES:
            raise ValueError("Invalid registry hive.")
        return clean

    def _root(self, hive: str):
        normalized = self._normalize_hive(hive)
        return getattr(winreg, self.HIVE_NAMES[normalized])

    def _normalize_path(self, path: Any) -> str:
        clean = str(path or "").strip().replace("/", "\\").strip("\\")
        if len(clean) > self.MAX_PATH_LENGTH or "\x00" in clean:
            raise ValueError("Invalid registry path.")
        if any(part in {".", ".."} for part in clean.split("\\") if part):
            raise ValueError("Invalid registry path.")
        return clean

    def _normalize_view(self, view: Any) -> str:
        clean = str(view or "default").lower().strip()
        if clean not in {"default", "32", "64"}:
            raise ValueError("Invalid registry view.")
        return clean

    def _view_flag(self, view: str) -> int:
        normalized = self._normalize_view(view)
        if normalized == "32":
            return int(winreg.KEY_WOW64_32KEY)
        if normalized == "64":
            return int(winreg.KEY_WOW64_64KEY)
        return 0

    def _resolve(self, hive: str, path: str, view: str, *, write: bool) -> tuple[Any, str, int]:
        root = self._root(hive)
        clean_path = self._normalize_path(path)
        access = int(winreg.KEY_READ)
        if write:
            access = int(winreg.KEY_READ | winreg.KEY_WRITE)
        access |= self._view_flag(view)
        return root, clean_path, access

    def _validate_value_name(self, value_name: Any) -> str:
        clean = str(value_name or "")
        if len(clean) > self.MAX_VALUE_NAME_LENGTH or "\x00" in clean or "\\" in clean:
            raise ValueError("Invalid registry value name.")
        return clean

    @staticmethod
    def _join_path(parent: str, child: str) -> str:
        return f"{parent}\\{child}" if parent else child

    @staticmethod
    def _bounded_int(value: Any, minimum: int, maximum: int, field: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"Invalid {field}.")
        parsed = int(value)
        if not minimum <= parsed <= maximum:
            raise ValueError(f"Invalid {field}.")
        return parsed

    def _value_payload(self, name: str, value: Any, value_type: int) -> dict[str, Any]:
        type_name = self.TYPE_NAMES.get(int(value_type), f"REG_TYPE_{int(value_type)}")
        return {"name": name, "type": type_name, "type_code": int(value_type), "data": self._encode_value(value, int(value_type)), "display_data": self._display_data(value, int(value_type))}

    def _encode_value(self, value: Any, value_type: int) -> Any:
        if value_type == self.TYPE_BY_NAME["REG_BINARY"]:
            raw = bytes(value or b"")
            return {"encoding": "base64", "value": base64.b64encode(raw).decode("ascii"), "length": len(raw)}
        if value_type == self.TYPE_BY_NAME["REG_MULTI_SZ"]:
            return [str(item) for item in (value or [])]
        if value_type in {self.TYPE_BY_NAME["REG_DWORD"], self.TYPE_BY_NAME["REG_QWORD"]}:
            return int(value)
        return "" if value is None else str(value)

    def _display_data(self, value: Any, value_type: int) -> str:
        if value_type == self.TYPE_BY_NAME["REG_BINARY"]:
            raw = bytes(value or b"")
            preview = raw[:64].hex(" ").upper()
            return preview + (" …" if len(raw) > 64 else "")
        if value_type == self.TYPE_BY_NAME["REG_MULTI_SZ"]:
            return " | ".join(str(item) for item in (value or []))
        if value_type in {self.TYPE_BY_NAME["REG_DWORD"], self.TYPE_BY_NAME["REG_QWORD"]}:
            number = int(value)
            return f"{number} (0x{number:X})"
        text = "" if value is None else str(value)
        return text if len(text) <= 300 else text[:297] + "..."

    def _decode_input_value(self, value: Any, value_type: int) -> Any:
        if value_type == self.TYPE_BY_NAME["REG_BINARY"]:
            if isinstance(value, dict) and value.get("encoding") == "base64":
                raw = base64.b64decode(str(value.get("value") or ""), validate=True)
            elif isinstance(value, str):
                compact = re.sub(r"[^0-9A-Fa-f]", "", value)
                if len(compact) % 2:
                    raise ValueError("Invalid binary hex data.")
                raw = bytes.fromhex(compact)
            else:
                raise ValueError("Invalid binary registry value.")
            if len(raw) > self.MAX_BINARY_BYTES:
                raise ValueError("Binary registry value is too large.")
            return raw
        if value_type == self.TYPE_BY_NAME["REG_MULTI_SZ"]:
            if isinstance(value, str):
                result = value.splitlines()
            elif isinstance(value, list):
                result = [str(item) for item in value]
            else:
                raise ValueError("Invalid REG_MULTI_SZ value.")
            if sum(len(item) for item in result) > self.MAX_TEXT_VALUE_LENGTH:
                raise ValueError("Registry value is too large.")
            return result
        if value_type in {self.TYPE_BY_NAME["REG_DWORD"], self.TYPE_BY_NAME["REG_QWORD"]}:
            if isinstance(value, bool):
                raise ValueError("Invalid numeric registry value.")
            number = int(str(value), 0) if isinstance(value, str) else int(value)
            maximum = 0xFFFFFFFF if value_type == self.TYPE_BY_NAME["REG_DWORD"] else 0xFFFFFFFFFFFFFFFF
            if not 0 <= number <= maximum:
                raise ValueError("Numeric registry value is out of range.")
            return number
        text = "" if value is None else str(value)
        if len(text) > self.MAX_TEXT_VALUE_LENGTH or "\x00" in text:
            raise ValueError("Registry value is too large or invalid.")
        return text

    def _capture_tree(self, hive: str, path: str, view: str, limit: int) -> tuple[dict[str, Any], int, bool]:
        root, clean_path, access = self._resolve(hive, path, view, write=False)
        counter = [0]
        truncated = [False]

        def walk(current_path: str) -> dict[str, Any]:
            node: dict[str, Any] = {"values": [], "subkeys": {}}
            if counter[0] >= limit:
                truncated[0] = True
                return node
            with winreg.OpenKey(root, current_path, 0, access) as key:
                subkey_count, value_count, _ = winreg.QueryInfoKey(key)
                for index in range(value_count):
                    if counter[0] >= limit:
                        truncated[0] = True
                        break
                    name, value, value_type = winreg.EnumValue(key, index)
                    node["values"].append(self._value_payload(name, value, value_type))
                    counter[0] += 1
                for index in range(subkey_count):
                    if counter[0] >= limit:
                        truncated[0] = True
                        break
                    child = winreg.EnumKey(key, index)
                    counter[0] += 1
                    child_path = self._join_path(current_path, child)
                    try:
                        node["subkeys"][child] = walk(child_path)
                    except (PermissionError, OSError):
                        node["subkeys"][child] = {"values": [], "subkeys": {}, "access_error": True}
            return node

        return walk(clean_path), counter[0], truncated[0]

    def _backup_scope(self, hive: str, path: str, view: str, reason: str) -> str:
        backup_id = str(uuid.uuid4())
        clean_path = self._normalize_path(path)
        document: dict[str, Any]
        try:
            tree, count, truncated = self._capture_tree(hive, clean_path, view, self.MAX_SNAPSHOT_ENTRIES)
            document = {"backup_id": backup_id, "created_at": self._utc_now(), "reason": reason, "hive": self._normalize_hive(hive), "path": clean_path, "view": self._normalize_view(view), "entry_count": count, "truncated": truncated, "tree": tree, "existed": True}
        except FileNotFoundError:
            document = {"backup_id": backup_id, "created_at": self._utc_now(), "reason": reason, "hive": self._normalize_hive(hive), "path": clean_path, "view": self._normalize_view(view), "entry_count": 0, "truncated": False, "tree": {"values": [], "subkeys": {}}, "existed": False}
        if document.get("truncated"):
            raise RuntimeError("Automatic backup exceeded the safe limit; operation cancelled.")
        self._atomic_json_write(self.backup_root / f"backup_{backup_id}.json", document)
        return backup_id

    def _load_backup(self, backup_id: str) -> dict[str, Any]:
        clean_id = self._validate_identifier(backup_id)
        candidates = [self.backup_root / f"backup_{clean_id}.json", self.backup_root / f"snapshot_{clean_id}.json"]
        for path in candidates:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    break
                return data
        raise FileNotFoundError("Registry backup was not found.")

    def _delete_tree(self, root: Any, path: str, access: int) -> None:
        with winreg.OpenKey(root, path, 0, access) as key:
            children: list[str] = []
            index = 0
            while True:
                try:
                    children.append(winreg.EnumKey(key, index))
                    index += 1
                except OSError:
                    break
        for child in children:
            self._delete_tree(root, self._join_path(path, child), access)
        view_flag = access & (winreg.KEY_WOW64_32KEY | winreg.KEY_WOW64_64KEY)
        winreg.DeleteKeyEx(root, path, view_flag, 0)

    def _restore_tree(self, root: Any, path: str, access: int, tree: dict[str, Any]) -> None:
        with winreg.CreateKeyEx(root, path, 0, access) as key:
            for value_item in tree.get("values") or []:
                native_type = int(value_item.get("type_code", self.TYPE_BY_NAME.get(str(value_item.get("type")), 1)))
                native_value = self._decode_input_value(value_item.get("data"), native_type)
                winreg.SetValueEx(key, self._validate_value_name(value_item.get("name", "")), 0, native_type, native_value)
        for child, child_tree in (tree.get("subkeys") or {}).items():
            if isinstance(child_tree, dict) and not child_tree.get("access_error"):
                self._restore_tree(root, self._join_path(path, self._normalize_path(child)), access, child_tree)

    def _flatten_tree(self, tree: dict[str, Any], base_path: str) -> dict[str, Any]:
        flat: dict[str, Any] = {}
        flat[f"K|{base_path}"] = "key"
        for item in tree.get("values") or []:
            identity = f"V|{base_path}|{item.get('name', '')}"
            flat[identity] = {"type": item.get("type"), "data": item.get("data")}
        for child, child_tree in (tree.get("subkeys") or {}).items():
            if isinstance(child_tree, dict):
                flat.update(self._flatten_tree(child_tree, self._join_path(base_path, str(child))))
        return flat

    def _validate_profile_entry(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("Invalid profile entry.")
        hive = self._normalize_hive(item.get("hive"))
        path = self._normalize_path(item.get("path"))
        view = self._normalize_view(item.get("view", "default"))
        value_name = self._validate_value_name(item.get("value_name", ""))
        value_type = str(item.get("value_type") or "REG_SZ").upper()
        if value_type not in self.TYPE_BY_NAME:
            raise ValueError("Invalid profile value type.")
        native_value = self._decode_input_value(item.get("value"), self.TYPE_BY_NAME[value_type])
        return {"hive": hive, "path": path, "view": view, "value_name": value_name, "value_type": value_type, "value": self._encode_value(native_value, self.TYPE_BY_NAME[value_type])}

    @staticmethod
    def _profile_identity(entry: dict[str, Any]) -> str:
        return f"{entry['hive']}|{entry['view']}|{entry['path']}|{entry['value_name']}"

    def _check_profile_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        identity = self._profile_identity(entry)
        expected_type = entry["value_type"]
        expected_native = self._decode_input_value(entry["value"], self.TYPE_BY_NAME[expected_type])
        expected_encoded = self._encode_value(expected_native, self.TYPE_BY_NAME[expected_type])
        try:
            current = self.get_value(entry["hive"], entry["path"], entry["value_name"], entry["view"])["value"]
        except FileNotFoundError:
            return {"identity": identity, "status": "missing", "expected": {"type": expected_type, "data": expected_encoded}, "current": None}
        current_min = {"type": current.get("type"), "data": current.get("data")}
        expected_min = {"type": expected_type, "data": expected_encoded}
        return {"identity": identity, "status": "ok" if current_min == expected_min else "different", "expected": expected_min, "current": current_min}

    def _load_profile(self, profile_id: str) -> dict[str, Any]:
        clean_id = self._validate_identifier(profile_id)
        path = self.profile_root / f"{clean_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            raise ValueError("Invalid registry profile.")
        return data

    def _append_reg_lines(self, lines: list[str], hive: str, path: str, tree: dict[str, Any]) -> None:
        full_hive = self.HIVE_NAMES[hive]
        key_name = f"{full_hive}\\{path}" if path else full_hive
        lines.extend([f"[{key_name}]" ])
        for item in tree.get("values") or []:
            name = item.get("name", "")
            prefix = "@" if name == "" else json.dumps(str(name), ensure_ascii=False)
            value_type = item.get("type")
            data = item.get("data")
            if value_type == "REG_SZ":
                encoded = json.dumps(str(data), ensure_ascii=False)
            elif value_type == "REG_DWORD":
                encoded = f"dword:{int(data):08x}"
            elif value_type == "REG_QWORD":
                raw = int(data).to_bytes(8, "little")
                encoded = "hex(b):" + ",".join(f"{byte:02x}" for byte in raw)
            elif value_type == "REG_BINARY" and isinstance(data, dict):
                raw = base64.b64decode(str(data.get("value") or ""))
                encoded = "hex:" + ",".join(f"{byte:02x}" for byte in raw)
            else:
                # Για types που χρειάζονται escaping/multiline, το JSON export παραμένει authoritative.
                continue
            lines.append(f"{prefix}={encoded}")
        lines.append("")
        for child, child_tree in (tree.get("subkeys") or {}).items():
            if isinstance(child_tree, dict) and not child_tree.get("access_error"):
                self._append_reg_lines(lines, hive, self._join_path(path, str(child)), child_tree)

    def _parse_reg_text(self, reg_text: Any, view: str) -> list[dict[str, Any]]:
        text = str(reg_text or "")
        if not 1 <= len(text) <= 2_000_000:
            raise ValueError("Invalid .reg content.")
        normalized_view = self._normalize_view(view)
        lines = text.replace("\r\n", "\n").split("\n")
        if not lines or lines[0].strip() not in {"Windows Registry Editor Version 5.00", "REGEDIT4"}:
            raise ValueError("Unsupported .reg header.")
        current_hive = ""
        current_path = ""
        operations: list[dict[str, Any]] = []
        for raw_line in lines[1:]:
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                key_text = line[1:-1]
                if key_text.startswith("-"):
                    raise ValueError(".reg key deletion is not allowed by safe import.")
                parts = key_text.split("\\", 1)
                full_hive = parts[0].upper()
                aliases = {full.upper(): short for short, full in self.HIVE_NAMES.items()}
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
            if data_text.startswith('"'):
                value_type = "REG_SZ"
                value = json.loads(data_text)
            elif data_text.lower().startswith("dword:"):
                value_type = "REG_DWORD"
                value = int(data_text.split(":", 1)[1], 16)
            elif data_text.lower().startswith("hex:"):
                value_type = "REG_BINARY"
                raw = bytes(int(part, 16) for part in data_text.split(":", 1)[1].split(",") if part)
                value = {"encoding": "base64", "value": base64.b64encode(raw).decode("ascii"), "length": len(raw)}
            else:
                raise ValueError("Unsupported .reg data type. Preview supports REG_SZ, REG_DWORD and REG_BINARY.")
            operation = {"action": "set_value", "hive": current_hive, "path": current_path, "view": normalized_view, "value_name": self._validate_value_name(value_name), "value_type": value_type, "value": value}
            operation["identity"] = self._profile_identity(operation)
            operations.append(operation)
            if len(operations) > 5000:
                raise ValueError(".reg import contains too many operations.")
        return operations

    def _audit(self, operation: str, hive: str, path: str, view: str, backup_id: str, success: bool, *, value_name: str = "") -> None:
        # Δεν γράφουμε ποτέ value data στο log.
        logger.info(
            "Registry mutation. operation=%s hive=%s path=%s value_name=%s view=%s backup_id=%s success=%s",
            operation,
            self._normalize_hive(hive),
            self._normalize_path(path),
            value_name,
            self._normalize_view(view),
            backup_id,
            success,
        )

    @staticmethod
    def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    @staticmethod
    def _validate_identifier(value: Any) -> str:
        clean = str(value or "").strip()
        try:
            return str(uuid.UUID(clean))
        except (ValueError, AttributeError):
            raise ValueError("Invalid identifier.") from None

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, PermissionError):
            return "Access denied. The MoonHard Remote Client may need Administrator/System rights for this Registry location."
        if isinstance(exc, FileNotFoundError):
            return "Registry key/value was not found."
        return str(exc)[:2000]

    @staticmethod
    def _is_admin() -> bool:
        if os.name != "nt":
            return False
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
