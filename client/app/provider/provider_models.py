from dataclasses import dataclass


@dataclass
class ProviderInvoiceRow:
    """
    Μοντέλο γραμμής παραστατικού για το remote Provider/MUPT feature.
    """

    InvoiceType: str
    DocumentName: str
    IssueDate: str
    aa: str
    InvoiceId: str
    CustAFM: str

    def to_dict(self) -> dict:
        """
        Μετατρέπει το παραστατικό σε dictionary για αποστολή μέσω WebSocket.
        """

        return {
            "InvoiceType": self.InvoiceType,
            "DocumentName": self.DocumentName,
            "IssueDate": self.IssueDate,
            "aa": self.aa,
            "InvoiceId": self.InvoiceId,
            "CustAFM": self.CustAFM,
        }