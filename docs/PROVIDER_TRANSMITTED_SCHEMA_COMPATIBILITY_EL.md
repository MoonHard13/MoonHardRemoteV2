# Συμβατότητα Σχήματος Διαβιβασμένων Παραστατικών

## Σκοπός

Η λειτουργία **Διαβιβασμένα Παραστατικά** του MoonHard Remote υποστηρίζει
βάσεις δεδομένων που διαθέτουν είτε μόνο τον πίνακα
`TblSnMyDATA_Response` είτε και τον νεότερο πίνακα
`TblSnMyDATA_ResponseSuccess`.

## Υποστηριζόμενα σχήματα

### Νεότερο σχήμα

Όταν υπάρχει ο πίνακας `TblSnMyDATA_ResponseSuccess`, η αναζήτηση χρησιμοποιεί:

- `TblSnMyDATA_Response`
- `TblSnMyDATA_ResponseSuccess`
- `VSnVSalesPayWay`
- `TblSnNoteType`

Το MARK λαμβάνεται πρώτα από το `MyDATA_ResponseInvoiceMARK` και, όταν αυτό
είναι κενό, από το `MyDATA_ResponseSuccessInvoiceMARK`.

### Παλαιότερο σχήμα

Όταν δεν υπάρχει ο πίνακας `TblSnMyDATA_ResponseSuccess`, η αναζήτηση δεν τον
αναφέρει καθόλου στο SQL. Ως διαβιβασμένα επιστρέφονται οι εγγραφές του
`TblSnMyDATA_Response` για τις οποίες ισχύουν ταυτόχρονα:

```sql
MyDATA_ResponseStatusCode = N'Success'
```

και:

```sql
MyDATA_ResponseInvoiceMARK IS NOT NULL
```

μετά την αφαίρεση κενών χαρακτήρων.

{% hint style="info" %}
Η ανίχνευση του σχήματος εκτελείται ξεχωριστά στην επιλεγμένη βάση κάθε
απομακρυσμένου client. Δεν απαιτείται αλλαγή ή δημιουργία πίνακα στη βάση.
{% endhint %}

## Προϋποθέσεις

- Το επιλεγμένο `BOConnection` πρέπει να περιέχει έγκυρο `DatabaseConnection`.
- Πρέπει να υπάρχει ο πίνακας `dbo.TblSnMyDATA_Response`.
- Ο SQL χρήστης χρειάζεται δικαίωμα `SELECT` στα απαιτούμενα tables/views.
- Ο client πρέπει να έχει ενημερωθεί στην έκδοση `1.0.13` ή νεότερη.

## Διαδικασία ελέγχου

1. Ενημερώστε τον MoonHard Remote Client.
2. Περιμένετε να επανεκκινηθεί η υπηρεσία και να επανασυνδεθεί στο Dashboard.
3. Επιβεβαιώστε ότι εμφανίζεται έκδοση client `1.0.13` ή νεότερη.
4. Ανοίξτε **Manage Client → Provider → Διαβιβασμένα Παραστατικά**.
5. Επιλέξτε το σωστό `BOConnection`.
6. Εκτελέστε αρχικά αναζήτηση χωρίς φίλτρα.
7. Επαναλάβετε με φίλτρο ημερομηνίας, αριθμού ή MARK.

## Logging

Ο client καταγράφει ποια παραλλαγή σχήματος εντοπίστηκε:

```text
Σχήμα διαβιβασμένων: response_success_table=True
```

ή:

```text
Σχήμα διαβιβασμένων: response_success_table=False
```

Σε SQL error καταγράφεται ασφαλής τεχνική λεπτομέρεια. Connection strings,
SQL usernames και passwords αφαιρούνται πριν από την εγγραφή στο log.

## Troubleshooting

### Δεν εμφανίζονται εγγραφές σε παλιό σχήμα

Ελέγξτε αν οι επιτυχείς εγγραφές διαθέτουν τιμή στο
`MyDATA_ResponseInvoiceMARK`. Χωρίς τον πίνακα `TblSnMyDATA_ResponseSuccess`
δεν υπάρχει δεύτερη πηγή από την οποία μπορεί να ανακτηθεί MARK.

### Invalid object name

Ελέγξτε στο client log ποιο object λείπει. Η έκδοση `1.0.13` δεν πρέπει να
αναφέρει το `TblSnMyDATA_ResponseSuccess` όταν αυτό δεν υπάρχει.

### Η λίστα «Παραστατικά προς αποστολή» λειτουργεί αλλά τα διαβιβασμένα όχι

Οι δύο λειτουργίες χρησιμοποιούν διαφορετικές πηγές. Τα παραστατικά προς
αποστολή διαβάζονται από `VSnMyDATAInvoicesAMV` ή `VSnMyDATAInvoices`, ενώ τα
διαβιβασμένα διαβάζονται από τους πίνακες απόκρισης MyData.

## Checklist

- [ ] Ο client εμφανίζεται online.
- [ ] Η έκδοση client είναι `1.0.13` ή νεότερη.
- [ ] Επιλέχθηκε το σωστό `BOConnection`.
- [ ] Υπάρχει το `dbo.TblSnMyDATA_Response`.
- [ ] Ο SQL χρήστης έχει δικαίωμα `SELECT`.
- [ ] Η αναζήτηση χωρίς φίλτρα ολοκληρώνεται.
- [ ] Ελέγχθηκε αναζήτηση με MARK.
- [ ] Ελέγχθηκε τουλάχιστον ένας client με νέο σχήμα.
- [ ] Ελέγχθηκε τουλάχιστον ένας client χωρίς `TblSnMyDATA_ResponseSuccess`.
