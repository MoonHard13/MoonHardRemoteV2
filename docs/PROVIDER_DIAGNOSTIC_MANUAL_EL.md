# Provider Diagnostic Center — Εγχειρίδιο Phase 1

## Σκοπός

Η Phase 1 προσθέτει βάση ανάγνωσης και διαγνωστικών, δίπλα στο Provider στο Manage window του πελάτη.

## Σύντομη περιγραφή

Το module ακολουθεί τον υπάρχοντα πελάτη/BOConnection. Παρέχει Overview και API Diagnostics. Οι επόμενες ενότητες δείχνουν τη φάση τους και δεν εκτελούν ακόμη εργασίες.

## Προϋποθέσεις

- Το ενημερωμένο Dashboard και οι υφιστάμενες ρυθμίσεις σύνδεσής του.
- Διαθέσιμα safe appsettings για την εγκατάσταση, για εμφάνιση server/database.
- Επιβεβαιωμένη πηγή ΑΦΜ εκδότη και Provider APIKey πριν από live Provider έλεγχο.

{% hint style="warning" %}
Στην παρούσα ενσωμάτωση ο live έλεγχος Provider είναι απενεργοποιημένος: το υπάρχον Dashboard λαμβάνει masked appsettings και δεν έχει επιβεβαιωθεί ποιο πεδίο είναι το S1Ecos APIKey. Μην αντικαταστήσετε αυθαίρετα το APIKey με subscriptionKey και μην αφαιρέσετε την απόκρυψη των appsettings.
{% endhint %}

## Βήματα χρήσης

1. Επιλέξτε τον πελάτη στην υπάρχουσα λίστα του Dashboard.
2. Ανοίξτε το Manage window.
3. Επιλέξτε το κατάλληλο BOConnection από την υφιστάμενη λειτουργία επιλογής βάσης.
4. Ανοίξτε το Provider Diagnostic Center δίπλα στο Provider.
5. Ελέγξτε τα στοιχεία στο Overview.
6. Χρησιμοποιήστε το εσωτερικό dropdown για επιλογή ενότητας.
7. Επιλέξτε Context ή F5 για επαναανάγνωση των ήδη φορτωμένων στοιχείων. Αυτό δεν εκτελεί νέο SQL ή Provider request.

## Επεξήγηση πεδίων Overview

| Πεδίο | Σημασία |
|---|---|
| Πελάτης/εγκατάσταση | Το υπάρχον display name ή PC name, όχι επιβεβαιωμένη νομική επωνυμία |
| Client | Ο υπάρχων client code |
| BOConnection | Το επιλεγμένο υπάρχον connection ID |
| Server / Database | Μεταδεδομένα του συγκεκριμένου BOConnection |
| ΑΦΜ εκδότη | Εμφανίζεται μόνο όταν υπάρχει επιβεβαιωμένη πηγή |
| ERP | Σύνδεση Client· ο SQL έλεγχος αναφέρεται ξεχωριστά ως μη εκτελεσμένος |
| Provider | Κατάσταση readiness, χωρίς ψευδή ένδειξη επιτυχούς σύνδεσης |
| Τελευταία επιτυχία | Χρόνος επιτυχούς πραγματικού API attempt, σε UTC |
| Διάρκεια / HTTP Status | Στοιχεία του τελευταίου πραγματικού attempt |

{% hint style="info" %}
Δεν εμφανίζονται μηδενικά documents totals ως αποτέλεσμα ελέγχου. Η πλήρης φόρτωση παραστατικών, οι counters και το reconciliation ανήκουν στις επόμενες φάσεις.
{% endhint %}

## API Diagnostics

Καταγράφονται μόνο πραγματικά API attempts. Κάθε retry είναι ξεχωριστή κλήση. Δεν καταγράφονται υποθετικά requests, παλιές Provider εργασίες ή background availability polling.

1. Επιλέξτε API Diagnostics.
2. Χρησιμοποιήστε All, Success ή Errors.
3. Πληκτρολογήστε μέρος του Endpoint ή συγκεκριμένο HTTP status, π.χ. 401.
4. Πατήστε το όνομα στήλης για ταξινόμηση. Διάρκεια, status και records ταξινομούνται αριθμητικά.
5. Προσαρμόστε πλάτος στηλών από τα όρια της κεφαλίδας.
6. Επιλέξτε μία ή περισσότερες γραμμές και χρησιμοποιήστε Copy ή δεξί κλικ.
7. Με Export αποθηκεύστε τις ορατές εγγραφές σε JSON.

Το ιστορικό κρατά έως 1.000 attempts στη RAM του συγκεκριμένου context. Αλλαγή πελάτη/βάσης δημιουργεί νέο diagnostic store. Το κλείσιμο του παραθύρου καθαρίζει το store. Το προαιρετικό export δεν είναι Provider cache database.

## Χειροκίνητος Provider έλεγχος

Μετά την επιβεβαιωμένη σύνδεση credential resolver, ο έλεγχος διαβάζει μόνο την πρώτη σελίδα σημερινών εξερχόμενων παραστατικών απευθείας από το Dashboard μέσω HTTPS. Τα records δεν είναι πλήρες ημερήσιο σύνολο. Δεν γίνονται εγγραφές.

Η εργασία εκτελείται σε worker thread. Με Ακύρωση ή Esc σταματούν οι επόμενες ενέργειες και τα retries. Ένα ενεργό socket μπορεί να περιμένει έως το πεπερασμένο timeout. Τα TLS certificates ελέγχονται και redirects δεν ακολουθούνται.

## Συντομεύσεις

| Shortcut | Λειτουργία όταν είναι ενεργό το Diagnostic Center |
|---|---|
| F5 | Επαναανάγνωση διαθέσιμου context |
| Ctrl+Enter | Χειροκίνητος Provider έλεγχος, όταν είναι διαθέσιμος |
| Ctrl+F | Άνοιγμα API Diagnostics και focus στο φίλτρο Endpoint |
| Ctrl+C | Αντιγραφή επιλεγμένων γραμμών όταν το focus είναι στον πίνακα |
| Ctrl+E | Εξαγωγή ορατών API diagnostics |
| Esc | Αίτημα ακύρωσης ενεργής εργασίας |

Full Refresh και Ctrl+Shift+R θα συνδεθούν με πραγματικό document dataset στη Phase 2.

## CLI / CMD

Από τον φάκελο `dashboard`:

```powershell
python -m app.main --provider-diagnostic --sections
python -m app.main --provider-diagnostic --client CLIENT_CODE --bo-connection 1
python -m app.main --provider-diagnostic --diagnostics-file provider-api-diagnostics.json --outcome Errors --status 401
python -m app.main --provider-diagnostic --diagnostics-file provider-api-diagnostics.json --endpoint getdocuments --output filtered.json
```

Το CLI χρησιμοποιεί το υπάρχον DASHBOARD_TOKEN για context. Δεν ζητά SQL password, Provider APIKey ή ΑΦΜ. Δεν προσπελαύνει τη RAM άλλου GUI process: για diagnostics διαβάζει το επιλεγμένο export. Χωρίς `--output`, το JSON εκτυπώνεται για pipe/copy. Κωδικοί εξόδου: 0 επιτυχία, 1 αποτυχία, 130 ακύρωση με Ctrl+C.

## Πότε χρησιμοποιείται / δεν χρησιμοποιείται

Χρησιμοποιείται για context και πραγματικά API attempts. Document lookup, recovery, reconciliation, analytics, F&B, POS, B2G, IRIS, VAT και archive εμφανίζουν προγραμματισμένη φάση. Το QR Tools αναμένει πλήρες API definition.

## Έλεγχοι πριν και μετά

### Πριν

- Ελέγξτε client code και BOConnection/database.
- Επιβεβαιώστε ότι το Overview ακολουθεί αλλαγή επιλογής βάσης.
- Μη θεωρείτε Client online ως επιτυχή SQL σύνδεση.

### Μετά

- Ελέγξτε result, HTTP status και error category.
- Επιβεβαιώστε ότι το export περιλαμβάνει τα ζητούμενα filtered records.
- Ελέγξτε ότι το παλιό Provider και τα Διαβιβασμένα Παραστατικά λειτουργούν.

## Checklist εγκατάστασης και build

- [ ] `python -m unittest discover -s tests -q` από το root του project.
- [ ] `python -m compileall -q dashboard client server`.
- [ ] Οπτικός έλεγχος του Manage window σε μικρή και μεγάλη ανάλυση και σε maximize.
- [ ] Επιβεβαίωση θέσης του tab αμέσως μετά το Provider.
- [ ] Εγκατάσταση `dashboard/requirements.txt` και PyInstaller στο Windows build environment.
- [ ] GUI build: `powershell -ExecutionPolicy Bypass -File scripts\build_dashboard_exe.ps1`.
- [ ] CMD build: ίδια εντολή με `-CLI`.
- [ ] Δοκιμή GUI και CLI EXE σε ξεχωριστό Windows περιβάλλον χωρίς Python.
- [ ] Χρήση του υπάρχοντος εξωτερικού configuration, χωρίς secrets μέσα στο EXE.

{% hint style="warning" %}
Δεν εκτελέστηκε Windows EXE build ή δοκιμή σε ξεχωριστό Windows περιβάλλον από το Linux περιβάλλον ανάπτυξης. Οι automated δοκιμές δεν αντικαθιστούν τον απαιτούμενο οπτικό έλεγχο και το Windows UAT πριν από διανομή.
{% endhint %}

## Αντιμετώπιση προβλημάτων

| Σύμπτωμα | Έλεγχος |
|---|---|
| Ο Provider έλεγχος είναι disabled | Επιβεβαίωση πηγής APIKey/issuer VAT και resolver integration |
| Δεν εμφανίζεται Database | Διαθεσιμότητα appsettings και συγκεκριμένου BOConnection |
| Δεν υπάρχουν API Diagnostics | Δεν έχει γίνει πραγματική API κλήση ή έχει αλλάξει context |
| 401 / 403 | Authentication / authorization, χωρίς δημοσιοποίηση secrets |
| Timeout / connection | Δίκτυο, TLS και Provider endpoint· όχι απενεργοποίηση certificate checks |
| Invalid JSON / malformed response | Έλεγχος documented response contract |
| Αποτυχία export | Δικαιώματα φακέλου και διαθέσιμος χώρος |
| Δεν φαίνεται CMD output | Χρήση console CLI build, όχι του windowed GUI EXE |

## Συνηθισμένα λάθη και βέλτιστες πρακτικές

Μην χρησιμοποιείτε subscriptionKey ως APIKey χωρίς απόδειξη. Μην επικολλάτε πραγματικά credentials σε tickets. Μην εκλαμβάνετε το diagnostic export ως πλήρες ιστορικό Provider. Επιβεβαιώστε πελάτη/βάση πριν από εξαγωγή. Τα logs έχουν rotation και redaction.

## Σημειώσεις μελλοντικών αλλαγών

Επόμενο απαιτούμενο βήμα είναι η επιβεβαίωση πηγής APIKey και ΑΦΜ. Έπειτα ακολουθούν Documents, documented pagination, session dataset και incremental refresh, με διευκρίνιση των ασυνεπειών `dateTo`/`To` στην public τεκμηρίωση. Η παλιά λειτουργία διαβιβασμένων παραμένει μέχρι πλήρη κάλυψη και δοκιμή της νέας.
