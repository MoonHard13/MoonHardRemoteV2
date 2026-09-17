import re

from app.websocket.transmitted_requests import PendingTransmittedRequest, TransmittedRequestRouter


class ProviderDiagnosticRequestRouter(TransmittedRequestRouter):
    """Δρομολογεί προσωρινά στοιχεία μόνο στο Dashboard που τα ζήτησε."""

    REQUEST_TYPES = ("provider_diagnostic_context",)
    RESULT_TYPES = ("provider_diagnostic_context_result",)
    ALLOWED_FIELDS = ("type", "request_id", "client_code", "bo_connection_id", "issuer_vat")
    CAPABILITY = "provider_diagnostic_v1"

    @staticmethod
    def error_payload(request_id, pending, error):
        return {"type": pending.result_type, "request_id": request_id,
                "client_code": pending.client_code, "bo_connection_id": pending.bo_connection_id,
                "success": False, "error": error, "companies": [], "issuer_vat": ""}

    async def request(self, dashboard, data):
        issuer = data.get("issuer_vat", "")
        error = ""
        if not isinstance(issuer, str) or (issuer and not re.fullmatch(r"EL[0-9]{9}", issuer)):
            error = "Μη έγκυρο ΑΦΜ εκδότη."
        elif not isinstance(data.get("client_code"), str):
            error = "Μη έγκυρος κωδικός Client."
        elif self.CAPABILITY not in self.manager.client_capabilities.get(data.get("client_code", ""), ()):
            error = "Απαιτείται ενημερωμένος και συνδεδεμένος Client με Provider Diagnostic Center."
        if error:
            pending = PendingTransmittedRequest(dashboard, data.get("client_code", ""),
                self.RESULT_TYPES[0], data.get("bo_connection_id"))
            await self.manager.send_to_dashboard(dashboard, self.error_payload(data.get("request_id", ""), pending, error))
            return
        await super().request(dashboard, data)

    async def result(self, client_code, data):
        # Η επιτρεπόμενη λίστα αποκλείει SQL credentials και raw appsettings.
        allowed = ("type", "request_id", "bo_connection_id", "success", "error", "error_code", "companies",
                   "issuer_vat", "api_key", "invalid_afm_count", "sql_verified", "provider_base_url")
        await super().result(client_code, {key: data[key] for key in allowed if key in data})
