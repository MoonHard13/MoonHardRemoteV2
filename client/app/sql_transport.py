"""Μεταφέρει πλήρη SQL αποτελέσματα χωρίς υπέρβαση του ορίου WebSocket ανά μήνυμα."""

import base64
import json


class SqlResultTransport:
    """Κρατά κάθε JSON μήνυμα κάτω από 300 KiB, ακόμη με μεγάλα Unicode κελιά."""

    CHUNK_BYTES = 192 * 1024

    @classmethod
    def messages(cls, result):
        """Διατηρεί απλή απάντηση για μικρά αποτελέσματα και αριθμεί μεγάλα πακέτα."""
        raw = json.dumps(result, ensure_ascii=False).encode('utf-8')
        if len(raw) <= cls.CHUNK_BYTES:
            yield raw.decode('utf-8')
            return
        total = (len(raw) + cls.CHUNK_BYTES - 1) // cls.CHUNK_BYTES
        identity = {key: result[key] for key in ('type', 'request_id', 'client_code', 'bo_connection_id')}
        for index in range(total):
            packet = {**identity, 'transfer': {'index': index, 'total': total,
                'data': base64.b64encode(raw[index * cls.CHUNK_BYTES:(index + 1) * cls.CHUNK_BYTES]).decode('ascii')}}
            yield json.dumps(packet)
