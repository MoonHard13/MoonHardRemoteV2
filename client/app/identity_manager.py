import json
import socket
import getpass
import uuid
from pathlib import Path


class ClientIdentityManager:
    """
    Διαχειρίζεται τη μοναδική ταυτότητα του client PC.
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
            return self._load_identity()

        return self._create_identity()

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
            "username": username
        }

        with self.identity_file.open("w", encoding="utf-8") as file:
            json.dump(identity, file, indent=4, ensure_ascii=False)

        return identity