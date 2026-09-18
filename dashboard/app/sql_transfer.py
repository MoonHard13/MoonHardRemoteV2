"""Συναρμολογεί SQL πακέτα μόνο για ένα ήδη συσχετισμένο ενεργό αίτημα."""

import base64
import json


class SqlResultAssembler:
    """Περιμένει όλα τα διαδοχικά πακέτα πριν εμφανίσει πλήρες αποτέλεσμα."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Απελευθερώνει μερικά δεδομένα σε νέο αίτημα, σφάλμα ή αποσύνδεση."""
        self._data = bytearray()
        self._next = 0
        self._total = None
        self._identity = None

    def feed(self, payload):
        """Επιστρέφει None όσο λείπουν πακέτα· απορρίπτει ανάμειξη ή αλλαγή σειράς."""
        packet = payload.get('transfer')
        if packet is None:
            if self._next:
                raise ValueError('Incomplete SQL transfer.')
            return payload
        if not isinstance(packet, dict):
            raise ValueError('Invalid SQL transfer packet.')
        identity = tuple(payload.get(key) for key in ('type', 'request_id', 'client_code', 'bo_connection_id'))
        index, total = packet.get('index'), packet.get('total')
        if (type(index) is not int or type(total) is not int or total < 1 or index != self._next
                or index >= total or (self._total is not None and (total != self._total or identity != self._identity))):
            raise ValueError('Invalid SQL transfer sequence.')
        self._total, self._identity = total, identity
        chunk = base64.b64decode(packet.get('data', ''), validate=True)
        if not chunk or len(chunk) > 192 * 1024:
            raise ValueError('Invalid SQL transfer packet.')
        self._data.extend(chunk)
        self._next += 1
        if self._next < total:
            return None
        result = json.loads(self._data.decode('utf-8'))
        if tuple(result.get(key) for key in ('type', 'request_id', 'client_code', 'bo_connection_id')) != identity:
            raise ValueError('SQL transfer identity mismatch.')
        self.reset()
        return result
