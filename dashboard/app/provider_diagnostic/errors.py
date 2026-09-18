from enum import Enum


class ErrorCategory(str, Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    HTTP_4XX = "http_4xx"
    NOT_FOUND = "not_found"
    END_OF_LIST = "end_of_list"
    ERP_READ = "erp_read"
    ERP_TIMEOUT = "erp_timeout"
    ERP_CONNECTION = "erp_connection"
    DATA_LIMIT = "data_limit"
    HTTP_5XX = "http_5xx"
    INVALID_JSON = "invalid_json"
    MALFORMED_RESPONSE = "malformed_response"
    INCOMPLETE_RESPONSE = "incomplete_response"
    UNSUPPORTED = "unsupported_operation"
    CONFIGURATION = "configuration"
    CANCELLED = "cancelled"


MESSAGES = {
    ErrorCategory.AUTHENTICATION: "Απέτυχε η αυθεντικοποίηση στον Provider.",
    ErrorCategory.AUTHORIZATION: "Δεν επιτρέπεται η πρόσβαση στα ζητούμενα στοιχεία.",
    ErrorCategory.VALIDATION: "Ελέγξτε τα στοιχεία του αιτήματος.",
    ErrorCategory.TIMEOUT: "Ο Provider δεν απάντησε μέσα στο χρονικό όριο.",
    ErrorCategory.CONNECTION: "Δεν ήταν δυνατή η ασφαλής σύνδεση με τον Provider.",
    ErrorCategory.HTTP_4XX: "Ο Provider απέρριψε το αίτημα.",
    ErrorCategory.NOT_FOUND: "HTTP 404: Δεν βρέθηκαν τα ζητούμενα στοιχεία ή το endpoint. Ελέγξτε διάστημα, ΑΦΜ και URL ανάκτησης. Το 404 δεν επιβεβαιώνει κενή λίστα.",
    ErrorCategory.END_OF_LIST: "Ο Provider δήλωσε ότι η ζητούμενη σελίδα υπερβαίνει τις διαθέσιμες σελίδες.",
    ErrorCategory.ERP_TIMEOUT: "Ο Client δεν απάντησε εγκαίρως στην ανάκτηση ERP.",
    ErrorCategory.ERP_CONNECTION: "Δεν ήταν δυνατή η αποστολή του αιτήματος ERP στον Client.",
    ErrorCategory.ERP_READ: "Απέτυχε η ανάγνωση ERP. Ελέγξτε έκδοση Client/server, σχήμα και σύνδεση εταιρείας.",
    ErrorCategory.DATA_LIMIT: "Η ανάκτηση υπερέβη το όριο δεδομένων. Επιλέξτε μικρότερο διάστημα· δεν εμφανίζεται μερική λίστα.",
    ErrorCategory.HTTP_5XX: "Ο Provider αντιμετώπισε προσωρινό πρόβλημα.",
    ErrorCategory.INVALID_JSON: "Η απάντηση του Provider δεν είναι έγκυρο JSON.",
    ErrorCategory.MALFORMED_RESPONSE: "Η απάντηση έχει μη αναμενόμενη δομή.",
    ErrorCategory.INCOMPLETE_RESPONSE: "Η απάντηση του Provider είναι ελλιπής ή υπερβολικά μεγάλη.",
    ErrorCategory.UNSUPPORTED: "Η λειτουργία δεν υποστηρίζεται στην τρέχουσα φάση.",
    ErrorCategory.CONFIGURATION: "Δεν έχει επιβεβαιωθεί η πηγή του Provider APIKey και του ΑΦΜ εκδότη.",
    ErrorCategory.CANCELLED: "Η εργασία ακυρώθηκε.",
}


class ProviderAPIError(Exception):
    """Μεταφέρει ελεγχόμενο μήνυμα χωρίς raw response, URL ή credentials."""

    def __init__(self, category: ErrorCategory, status: int | None = None) -> None:
        self.category = category
        self.status = status
        self.message = MESSAGES[category]
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {"category": self.category.value, "message": self.message,
                "http_status": self.status}
