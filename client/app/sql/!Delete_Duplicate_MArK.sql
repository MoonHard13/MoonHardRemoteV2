-- Διαγραφή ίδιων Παραστατικών με ίδιο Μ.Αρ.Κ.
;With Multi As (
    Select  r.MyDATA_ResponseOID,
            Counts = 
            Row_Number() Over (
                Partition By
                IsNull(r.NoteHdrOID, 0),
                IsNull(r.SNoteHdrOID, 0),
                IsNull(r.PayBookOID, 0),
                IsNull(r.MyDATA_ResponseSalesTransPosHdr, 0),
                IsNull(r.MyDATA_ResponseTransAccHdrOID, 0),
                IsNull(r.MyDATA_ResponseInvoiceMARK, '')
                Order By r.MyDATA_ResponseOID
            )
    From    TblSnMyDATA_Response    r
    Where   r.MyDATA_ResponseStatusCode = 'Success'
            And (
                NoteHdrOID Is Not Null
                Or SNoteHdrOID Is Not Null
                Or PayBookOID Is Not Null
                Or IsNull(MyDATA_ResponseSalesTransPosHdr, 0) > 0
                Or IsNull(MyDATA_ResponseTransAccHdrOID, 0) > 0
            )
            And IsNull(r.MyDATA_ResponseInvoiceMARK, '') <> ''
)
Delete Multi Where Counts > 1;
Go

-- Διαγραφή ίδιων Παραστατικών με διαφορετικό Μ.Αρ.Κ.
;With
DuplicateMArK As (
    Select      NoteHdrOID = IsNull(r.NoteHdrOID, 0),
                SNoteHdrOID = IsNull(r.SNoteHdrOID, 0),
                PayBookOID = IsNull(r.PayBookOID, 0),
                MyDATA_ResponseSalesTransPosHdr = IsNull(r.MyDATA_ResponseSalesTransPosHdr, 0),
                MyDATA_ResponseTransAccHdrOID = IsNull(r.MyDATA_ResponseTransAccHdrOID, 0),
                Counts = Count(Distinct IsNull(r.MyDATA_ResponseInvoiceMARK, ''))
    From        TblSnMyDATA_Response    r
    Where       r.MyDATA_ResponseStatusCode = 'Success'
                And (
                    NoteHdrOID Is Not Null
                    Or SNoteHdrOID Is Not Null
                    Or PayBookOID Is Not Null
                    Or IsNull(MyDATA_ResponseSalesTransPosHdr, 0) > 0
                    Or IsNull(MyDATA_ResponseTransAccHdrOID, 0) > 0
                )
                And IsNull(r.MyDATA_ResponseInvoiceMARK, '') <> ''
    Group By    IsNull(r.NoteHdrOID, 0),
                IsNull(r.SNoteHdrOID, 0),
                IsNull(r.PayBookOID, 0),
                IsNull(r.MyDATA_ResponseSalesTransPosHdr, 0),
                IsNull(r.MyDATA_ResponseTransAccHdrOID, 0)
    Having      Count(Distinct IsNull(r.MyDATA_ResponseInvoiceMARK, '')) > 1
),
RecsToKeep As (
    Select      MinOID = Min(r.MyDATA_ResponseOID)
    From        TblSnMyDATA_Response    r
    Inner Join  DuplicateMArK           m   On  IsNull(r.NoteHdrOID, 0) = IsNull(m.NoteHdrOID, 0)
                                                And IsNull(r.SNoteHdrOID, 0) = IsNull(m.SNoteHdrOID, 0)
                                                And IsNull(r.PayBookOID, 0) = IsNull(m.PayBookOID, 0)
                                                And IsNull(r.MyDATA_ResponseSalesTransPosHdr, 0) = IsNull(m.MyDATA_ResponseSalesTransPosHdr, 0)
                                                And IsNull(r.MyDATA_ResponseTransAccHdrOID, 0) = IsNull(m.MyDATA_ResponseTransAccHdrOID, 0)
    Group By    IsNull(m.NoteHdrOID, 0),
                IsNull(m.SNoteHdrOID, 0),
                IsNull(m.PayBookOID, 0),
                IsNull(m.MyDATA_ResponseSalesTransPosHdr, 0),
                IsNull(m.MyDATA_ResponseTransAccHdrOID, 0)
)
Delete      r
From        TblSnMyDATA_Response    r
Inner Join  DuplicateMArK           m   On  IsNull(r.NoteHdrOID, 0) = IsNull(m.NoteHdrOID, 0)
                                            And IsNull(r.SNoteHdrOID, 0) = IsNull(m.SNoteHdrOID, 0)
                                            And IsNull(r.PayBookOID, 0) = IsNull(m.PayBookOID, 0)
                                            And IsNull(r.MyDATA_ResponseSalesTransPosHdr, 0) = IsNull(m.MyDATA_ResponseSalesTransPosHdr, 0)
                                            And IsNull(r.MyDATA_ResponseTransAccHdrOID, 0) = IsNull(m.MyDATA_ResponseTransAccHdrOID, 0)
Where       r.MyDATA_ResponseOID Not In (Select MinOID From RecsToKeep)
Go
