import json
import socket
import getpass
import uuid
import secrets
from datetime import datetime, timezone
from pathlib import Path


class ClientIdentityManager:
    """
    Διαχειρίζεται τη μοναδική ταυτότητα του client PC.

    Το client_instance_token είναι μοναδικό ανά εγκατάσταση και αποθηκεύεται μόνο τοπικά.
    Ο server αποθηκεύει μόνο hash του token.
    """

    def __init__(self, identity_file: Path) -> None:
        """
        Αρχικοποιεί το αρχείο ταυτότητας του client.
        """

        self.identity_file = identity_file

    def load_or_create_identity(self) -> dict:
        """
        Φορτώνει υπάρχουσα ταυτότητα ή δημιουργεί νέα αν δεν υπάρχει.
        """

        self.identity_file.parent.mkdir(parents=True, exist_ok=True)

        if self.identity_file.exists():
            identity = self._load_identity()
            return self._ensure_identity_security_fields(identity)

        return self._create_identity()

    def save_identity(self, identity: dict) -> None:
        """
        Αποθηκεύει την ταυτότητα στο local identity file.
        """

        self.identity_file.parent.mkdir(parents=True, exist_ok=True)

        with self.identity_file.open("w", encoding="utf-8") as file:
            json.dump(identity, file, indent=4, ensure_ascii=False)

    def ensure_client_instance_token(self, identity: dict) -> str:
        """
        Επιστρέφει ή δημιουργεί μοναδικό token για τον συγκεκριμένο client.
        """

        changed = False

        if not identity.get("client_instance_token"):
            identity["client_instance_token"] = self._generate_client_instance_token()
            identity["client_token_registered"] = False
            changed = True

        if "client_token_registered" not in identity:
            identity["client_token_registered"] = False
            changed = True

        if changed:
            self.save_identity(identity)

        return str(identity["client_instance_token"])

    def mark_client_token_registered(self, identity: dict) -> None:
        """
        Σημειώνει ότι ο server έχει αποθηκεύσει hash για το per-client token.
        """

        identity["client_token_registered"] = True
        self.save_identity(identity)

    def rotate_client_instance_token(self, identity: dict) -> str:
        """
        Δημιουργεί νέο per-client token και το σημειώνει ως μη registered.

        Χρησιμοποιείται όταν ο server απαντήσει TOKEN_RESET_REQUIRED.
        """

        identity["client_instance_token"] = self._generate_client_instance_token()
        identity["client_token_registered"] = False
        identity["client_token_rotated_at"] = datetime.now(timezone.utc).isoformat()

        self.save_identity(identity)

        return str(identity["client_instance_token"])

    def _load_identity(self) -> dict:
        """
        Διαβάζει την ταυτότητα από το αρχείο JSON.
        """

        with self.identity_file.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _create_identity(self) -> dict:
        """
        Δημιουργεί νέα μοναδική ταυτότητα για το PC.
        """

        pc_name = socket.gethostname()
        username = getpass.getuser()

        identity = {
            "client_code": f"CLIENT-{uuid.uuid4().hex[:12].upper()}",
            "display_name": pc_name,
            "pc_name": pc_name,
            "username": username,
            "client_instance_token": self._generate_client_instance_token(),
            "client_token_registered": False
        }

        self.save_identity(identity)

        return identity

    def _ensure_identity_security_fields(self, identity: dict) -> dict:
        """
        Προσθέτει security fields σε παλιό identity file χωρίς να αλλάζει το client_code.
        """

        self.ensure_client_instance_token(identity)

        return identity

    def _generate_client_instance_token(self) -> str:
        """
        Δημιουργεί cryptographically random per-client token.
        """

        return secrets.token_urlsafe(48)