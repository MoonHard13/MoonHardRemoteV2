"""Κοινή, ασφαλής παρουσίαση στοιχείων Client για Overview και CLI."""

from datetime import datetime


class OverviewPresenter:
    """Επιλέγει μόνο δημόσια metadata, ποτέ tokens ή connection strings."""

    FIELDS = ('client_code', 'display_name', 'pc_name', 'username', 'status', 'ws_connected',
              'group_name', 'last_seen', 'app_version', 'amv_version', 'bo_version', 'etp_version', 'aws_version')

    @classmethod
    def safe_data(cls, client):
        """Παράγει ρητή λίστα πεδίων χωρίς μεταβολή του αρχικού Client."""
        data = {key: client.get(key) for key in cls.FIELDS}
        data['display_name'] = client.get('display_name') or client.get('pc_name') or '—'
        data['group_name'] = client.get('group_name') or 'Ungrouped'
        return data

    @staticmethod
    def last_seen(value):
        """Μορφοποιεί ημερομηνία στην τοπική ζώνη ώρας με εμφανή UTC offset."""
        if not value:
            return '—'
        try:
            moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if moment.tzinfo is None:
                return moment.strftime('%d/%m/%Y · %H:%M:%S') + ' (timezone unknown)'
            return moment.astimezone().strftime('%d/%m/%Y · %H:%M:%S %z')
        except (ValueError, TypeError):
            return str(value)

    @staticmethod
    def validate_name(value):
        """Απορρίπτει κενό όνομα ή χαρακτήρες ελέγχου πριν αποσταλεί αίτημα."""
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('Δώστε μη κενό όνομα χωρίς αλλαγές γραμμής ή χαρακτήρες ελέγχου.')
        return value
