# Release notes - Διαγραφή διπλών ΜΑΡΚ

Η νέα database action απαιτεί ενημερωμένο Dashboard, Server και Client.

Για νέο installer χρησιμοποιήστε το υπάρχον `build_client_installer.ps1`, το οποίο πλέον πακετάρει τα SQL resources.

Για client self-update package χρησιμοποιήστε το νέο:

```powershell
.\scripts\build_client_update_package_resources.ps1 -Version X.Y.Z
```

Το παραγόμενο ZIP διατηρεί το ίδιο naming convention `moonhard-client-X.Y.Z.zip`.
