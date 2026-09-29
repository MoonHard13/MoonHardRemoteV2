# Database - Διαγραφή διπλών ΜΑΡΚ

Η λειτουργία εκτελεί δύο προκαθορισμένα SQL resources στην επιλεγμένη BOConnection βάση.

1. `!Delete_Duplicate_Success_Mark.sql` εκτελείται πρώτο ως best-effort βήμα. Αν αποτύχει λόγω διαφορετικού schema, η διαδικασία συνεχίζει και το αποτέλεσμα εμφανίζεται ως warning.
2. `!Delete_Duplicate_MArK.sql` εκτελείται πάντα μετά το πρώτο. Η επιτυχία αυτού του βήματος καθορίζει το τελικό αποτέλεσμα της λειτουργίας.

Τα SQL resources είναι allowlisted και αποστέλλεται μόνο το action name μέσω WebSocket. Δεν επιτρέπεται arbitrary SQL από το Dashboard.

Για client update packages που πρέπει να περιλαμβάνουν τα SQL resources χρησιμοποιήστε:

```powershell
.\scripts\build_client_update_package_resources.ps1 -Version X.Y.Z
```
