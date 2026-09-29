-- Step 1: materialize conflicts
SELECT
    MyDATA_ResponseSalesTransPosHdr,
    LatestOID = MAX(MyDATA_ResponseOID),
    OlderOID  = MIN(MyDATA_ResponseOID)
INTO #Conflicts
FROM TblSnMyDATA_Response
WHERE
    MyDATA_ResponseStatusCode = 'Success'
    AND ISNULL(MyDATA_ResponseSalesTransPosHdr,0) > 0
GROUP BY MyDATA_ResponseSalesTransPosHdr
HAVING COUNT(*) = 2;

-- Step 2: UPDATE latest row (merge values)
UPDATE latest
SET
    MyDATA_ResponseInvoiceMARK =
        COALESCE(NULLIF(latest.MyDATA_ResponseInvoiceMARK,''),
                 older.MyDATA_ResponseInvoiceMARK),
    MyDATA_ResponseCancellationMARK =
        COALESCE(NULLIF(latest.MyDATA_ResponseCancellationMARK,''),
                 older.MyDATA_ResponseCancellationMARK)
FROM TblSnMyDATA_Response latest
JOIN #Conflicts c
    ON latest.MyDATA_ResponseOID = c.LatestOID
JOIN TblSnMyDATA_Response older
    ON older.MyDATA_ResponseOID = c.OlderOID

-- Step 3: DELETE older row
DELETE older
FROM TblSnMyDATA_Response older
JOIN #Conflicts c
    ON older.MyDATA_ResponseOID = c.OlderOID

DROP TABLE #Conflicts
