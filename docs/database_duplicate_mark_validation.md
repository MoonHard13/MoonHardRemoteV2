# Validation checklist - Διαγραφή διπλών ΜΑΡΚ

- Επιλογή σωστής BOConnection πριν την εκτέλεση.
- Confirmation πριν από το destructive cleanup.
- Step 1 εκτελείται πρώτο και τυχόν αποτυχία του εμφανίζεται ως warning.
- Step 2 εκτελείται πάντα μετά το Step 1.
- Αποτυχία Step 1 δεν σταματά το Step 2.
- Αποτυχία Step 2 αποτυγχάνει τη συνολική ενέργεια.
- Τα δύο SQL resources περιλαμβάνονται στο client EXE/installer build.
- Το Activity εμφανίζει progress και τελικό αποτέλεσμα.
