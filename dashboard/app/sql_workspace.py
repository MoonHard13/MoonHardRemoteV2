"""Κοινά βοηθήματα SSMS για αρχεία, SQL αποτελέσματα και CLI."""

import csv
import io
from pathlib import Path


class SqlFiles:
    """Διαβάζει ελληνικά SQL scripts χωρίς να εκτελεί το περιεχόμενό τους."""

    @staticmethod
    def read(path: Path) -> tuple[str, str]:
        """Αναγνωρίζει BOM και αποφεύγει λανθασμένο UTF-16 για αρχεία Windows-1253."""
        raw = path.read_bytes()
        if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
            return raw.decode('utf-16'), 'utf-16'
        if raw.startswith(b'\xef\xbb\xbf'):
            return raw.decode('utf-8-sig'), 'utf-8-sig'
        if b'\x00' in raw[:256]:
            encoding = 'utf-16-be' if raw[:1] == b'\x00' else 'utf-16-le'
            return raw.decode(encoding), encoding
        for encoding in ('utf-8', 'cp1253', 'cp1252'):
            try:
                return raw.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        return raw.decode('cp1253', errors='replace'), 'cp1253 (αντικατάσταση χαρακτήρων)'


class SqlResultData:
    """Μορφοποιεί τα ήδη επιστρεφόμενα result sets χωρίς εξάρτηση από το GUI."""

    @staticmethod
    def sets(payload: dict) -> list[dict]:
        """Κρατά την αντιστοίχιση result set και batch, συμπεριλαμβανομένων των ορίων."""
        result = []
        for batch in payload.get('batches') or []:
            for index, item in enumerate(batch.get('result_sets') or [], 1):
                if item.get('columns'):
                    result.append({**item, 'batch_index': batch.get('batch_index'), 'result_index': index,
                                   'limited': bool(item.get('limited') or batch.get('limited')),
                                   'limit_message': batch.get('limit_message')})
        return result

    @staticmethod
    def failed(payload: dict) -> bool:
        """Αναγνωρίζει και αποτυχίες batch όταν το συνολικό success είναι true."""
        return not payload.get('success') or any(item.get('error') for item in payload.get('batches') or [])

    @staticmethod
    def cell(value) -> str:
        """Διακρίνει το SQL NULL από το κενό string."""
        return 'NULL' if value is None else str(value)

    @classmethod
    def delimited(cls, columns: list, rows: list, delimiter: str = '\t', headers: bool = True) -> str:
        """Χρησιμοποιεί quoting ώστε tabs, κόμματα και νέες γραμμές να παραμένουν στο ίδιο κελί."""
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, delimiter=delimiter, lineterminator='\n')
        if headers:
            writer.writerow(columns)
        writer.writerows([[cls.cell(value) for value in row] for row in rows])
        return stream.getvalue()

    @classmethod
    def messages(cls, payload: dict) -> str:
        """Συνοψίζει την εκτέλεση χωρίς να επαναλαμβάνει το SQL script."""
        lines = ['Εκτέλεση SQL: ' + ('Σφάλμα' if cls.failed(payload) else 'Ολοκληρώθηκε'),
                 f"BOConnection ID: {payload.get('bo_connection_id', '—')}",
                 f"Driver: {payload.get('driver') or '—'}",
                 f"Διάρκεια: {payload.get('elapsed_ms') if payload.get('elapsed_ms') is not None else '—'} ms"]
        if payload.get('error'):
            lines += ['', str(payload['error'])]
        for batch in payload.get('batches') or []:
            lines += ['', f"Batch {batch.get('batch_index')}"]
            if batch.get('error'):
                lines.append(str(batch['error']))
            if not batch.get('result_sets'):
                lines.append(f"Rows affected: {batch.get('rowcount')}")
            for index, item in enumerate(batch.get('result_sets') or [], 1):
                lines.append(f"Result {index}: {len(item.get('rows') or [])} γραμμές · {len(item.get('columns') or [])} στήλες")
            if batch.get('limited'):
                lines.append(batch.get('limit_message') or 'Τα αποτελέσματα περιορίστηκαν από τον Client.')
        return '\n'.join(lines)
