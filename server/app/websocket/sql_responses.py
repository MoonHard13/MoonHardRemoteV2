"""Δρομολογεί SQL πακέτα προς το Dashboard που ξεκίνησε το αίτημα."""

import logging

logger = logging.getLogger(__name__)


class SqlResponseRouter:
    """Διατηρεί το pending request μέχρι να σταλεί το τελευταίο πακέτο."""

    @staticmethod
    async def forward(data, pending_requests, connection_manager):
        """Δεν κοινοποιεί πακέτα μεταφοράς σε άλλα Dashboards."""
        request_id = data.get('request_id', '')
        transfer = data.get('transfer')
        complete = data.get('type') != 'sql_cancel_result'
        if transfer is not None:
            if (not isinstance(transfer, dict) or type(transfer.get('index')) is not int
                    or type(transfer.get('total')) is not int
                    or not 0 <= transfer['index'] < transfer['total']):
                logger.warning('Invalid SQL packet. request_id=%s', request_id)
                return
            complete = transfer['index'] == transfer['total'] - 1
        dashboard = pending_requests.pop(request_id, None) if complete else pending_requests.get(request_id)
        if dashboard is not None:
            await connection_manager.send_to_dashboard(dashboard, data)
        elif transfer is None:
            await connection_manager.broadcast_to_dashboards(data)
