# Database Backup & Scheduling

## Σκοπός

Η λειτουργία **Database Backup & Scheduling** επιτρέπει τη δημιουργία και τη διαχείριση πλήρων αντιγράφων ασφαλείας SQL Server από το MoonHard Remote V2.

Υποστηρίζονται:

- Άμεση χειροκίνητη δημιουργία backup.
- Αυτόματη εκτέλεση σε ημερήσιο, εβδομαδιαίο ή μηνιαίο πρόγραμμα.
- Αποθήκευση σε τοπικό φάκελο του SQL Server.
- Αποθήκευση σε δικτυακό φάκελο UNC.
- Μεταφόρτωση σε OneDrive, MEGA, Dropbox, Google Drive, S3 και άλλους παρόχους μέσω `rclone`.
- Έλεγχος εγκυρότητας του backup με `RESTORE VERIFYONLY` και `CHECKSUM`.
- Επιλογές αντικατάστασης, διατήρησης όλων ή διατήρησης συγκεκριμένου αριθμού backups.
- Ιστορικό αποτελεσμάτων και αυτόματη επανάληψη αποτυχημένων cloud uploads.

{% hint style="info" %}
Τα schedules αποθηκεύονται και εκτελούνται στον απομακρυσμένο MoonHard Remote Client. Το Dashboard δεν χρειάζεται να παραμένει ανοιχτό.
{% endhint %}

## Τρόπος λειτουργίας

Για τοπικό ή UNC προορισμό, ο SQL Server δημιουργεί το αρχείο `.bak` απευθείας στον επιλεγμένο φάκελο. Μετά την ολοκλήρωση εκτελείται έλεγχος `RESTORE VERIFYONLY`.

Για cloud προορισμό ακολουθείται η παρακάτω διαδικασία:

1. Δημιουργείται το `.bak` στον φάκελο staging.
2. Εκτελείται `RESTORE VERIFYONLY WITH CHECKSUM`.
3. Υπολογίζεται SHA-256, εφόσον το αρχείο είναι προσβάσιμο από το MoonHard Remote Client.
4. Το αρχείο μεταφορτώνεται στον επιλεγμένο `rclone` remote.
5. Επιβεβαιώνεται ότι το μέγεθος του απομακρυσμένου αρχείου είναι ίδιο με το τοπικό.
6. Εφαρμόζεται η επιλεγμένη πολιτική διατήρησης.
7. Το staging αρχείο διαγράφεται μόνο μετά από επιτυχημένη μεταφόρτωση.

{% hint style="success" %}
Σε αποτυχία cloud upload, το ήδη επαληθευμένο staging backup διατηρείται. Η μεταφόρτωση μπορεί να επαναληφθεί χωρίς να δημιουργηθεί νέο SQL backup.
{% endhint %}

## Προϋποθέσεις

### SQL Server

- Το επιλεγμένο `BOConnection` πρέπει να λειτουργεί.
- Ο SQL login πρέπει να έχει δικαίωμα `BACKUP DATABASE` και `RESTORE VERIFYONLY`.
- Ο λογαριασμός υπηρεσίας του SQL Server πρέπει να έχει δικαίωμα εγγραφής στον προορισμό.
- Ο φάκελος πρέπει να διαθέτει αρκετό ελεύθερο χώρο.

### UNC προορισμός

Για διαδρομή όπως:

```text
\\NAS01\MoonHardBackups
```

απαιτούνται δικαιώματα κοινής χρήσης και NTFS για τον λογαριασμό υπηρεσίας SQL Server. Τα δικαιώματα του χρήστη που έχει ανοίξει το Dashboard δεν χρησιμοποιούνται από την εντολή backup.

{% hint style="warning" %}
Μη χρησιμοποιείτε mapped drive όπως `Z:\Backups`. Οι Windows services συνήθως δεν βλέπουν τα drive mappings ενός συνδεδεμένου χρήστη. Χρησιμοποιείτε πλήρη UNC διαδρομή.
{% endhint %}

### Cloud προορισμός

Το `rclone.exe` και το `rclone.conf` αναζητούνται από προεπιλογή στις διαδρομές:

```text
C:\ProgramData\MoonHardRemoteV2\rclone\rclone.exe
C:\ProgramData\MoonHardRemoteV2\rclone\rclone.conf
```

Οι διαδρομές μπορούν να αλλάξουν τοπικά στον client μέσω:

```text
MOONHARD_RCLONE_PATH
MOONHARD_RCLONE_CONFIG
```

Οι ρυθμίσεις σύνδεσης των cloud providers παραμένουν αποκλειστικά στο `rclone.conf` του απομακρυσμένου client και δεν μεταδίδονται στο Dashboard ή στον Render server.

## Προετοιμασία rclone

1. Δημιουργήστε τον φάκελο:

```text
C:\ProgramData\MoonHardRemoteV2\rclone
```

2. Τοποθετήστε εκεί το `rclone.exe`.
3. Ανοίξτε PowerShell ως Administrator.
4. Εκτελέστε:

```powershell
& "C:\ProgramData\MoonHardRemoteV2\rclone\rclone.exe" config `
  --config "C:\ProgramData\MoonHardRemoteV2\rclone\rclone.conf"
```

5. Δημιουργήστε remote για τον επιθυμητό provider.
6. Ελέγξτε τα διαθέσιμα remotes:

```powershell
& "C:\ProgramData\MoonHardRemoteV2\rclone\rclone.exe" listremotes `
  --config "C:\ProgramData\MoonHardRemoteV2\rclone\rclone.conf"
```

Παράδειγμα αποτελέσματος:

```text
mega:
onedrive:
```

7. Περιορίστε τα δικαιώματα NTFS του φακέλου `rclone`, ώστε να είναι προσβάσιμος μόνο από Administrators, SYSTEM και τον λογαριασμό της υπηρεσίας MoonHard Remote Client.
8. Επανεκκινήστε την υπηρεσία MoonHard Remote Client.

{% hint style="danger" %}
Μην αντιγράφετε το `rclone.conf` στο Dashboard, στο GitHub ή στον Render server. Το αρχείο περιέχει tokens πρόσβασης των cloud λογαριασμών.
{% endhint %}

## Άνοιγμα Backup Manager

1. Ανοίξτε το MoonHard Remote Dashboard.
2. Επιλέξτε τον επιθυμητό online client.
3. Ανοίξτε το παράθυρο **Manage Client**.
4. Επιλέξτε το tab **Database**.
5. Πατήστε **Backup & Scheduling** ή χρησιμοποιήστε `Ctrl+7`.
6. Επιλέξτε το σωστό `BOConnection`.

Το Backup Manager είναι κανονικό ανεξάρτητο παράθυρο: μπορεί να γίνει minimize,
maximize και resize από τα Windows.

## Δημιουργία χειροκίνητου backup

1. Επιλέξτε **Backup Now**.
2. Επιλέξτε τύπο προορισμού.
3. Συμπληρώστε τις απαιτούμενες διαδρομές.
4. Επιλέξτε πολιτική διατήρησης.
5. Ελέγξτε τις επιλογές **Compression** και **COPY_ONLY**.
6. Πατήστε **Start Backup** ή `Ctrl+B`.
7. Επιβεβαιώστε τη βάση, τον προορισμό και την πολιτική διατήρησης.
8. Παρακολουθήστε το live progress.
9. Περιμένετε τελική ένδειξη επιτυχίας και `Verified: True`.

## Τύποι προορισμού

### Local folder

Παράδειγμα:

```text
D:\SQLBackups
```

Η διαδρομή αφορά τον υπολογιστή όπου εκτελείται ο SQL Server. Αν SQL Server και MoonHard Remote Client βρίσκονται σε διαφορετικούς υπολογιστές, η τοπική διαδρομή μπορεί να μην είναι αναγνώσιμη από τον client. Σε αυτή την περίπτωση χρησιμοποιήστε κοινό UNC path.

### UNC network share

Παράδειγμα:

```text
\\NAS01\MoonHardBackups\Customer01
```

Η διαδρομή πρέπει να είναι προσβάσιμη ταυτόχρονα από:

- Την υπηρεσία SQL Server για δημιουργία και verification του backup.
- Την υπηρεσία MoonHard Remote Client για retention, SHA-256 και cloud staging όπου απαιτείται.

### Cloud via rclone

Συμπληρώστε:

- **Cloud staging folder:** Τοπική ή UNC διαδρομή προσβάσιμη από SQL Server και MoonHard Remote Client.
- **rclone destination:** Remote και προαιρετικός υποφάκελος.

Παραδείγματα:

```text
mega:MoonHardBackups/Customer01
onedrive:ERP/SQLBackups
dropbox:MoonHard/Backups
```

## Πολιτικές διατήρησης

### Replace previous backup

- Το νέο backup δημιουργείται αρχικά με μοναδικό προσωρινό όνομα.
- Το προηγούμενο έγκυρο backup παραμένει διαθέσιμο κατά τη δημιουργία και το verification.
- Μετά την επιτυχία, το νέο backup αντικαθιστά το αρχείο `<Database>_latest.bak`.
- Σε αποτυχία, το προηγούμενο backup δεν διαγράφεται.

### Keep all backups

- Κάθε backup διατηρείται με timestamp.
- Δεν εκτελείται αυτόματη διαγραφή.
- Απαιτείται τακτικός έλεγχος διαθέσιμου χώρου.

### Keep last N backups

- Κάθε backup διατηρείται με timestamp.
- Μετά από επιτυχημένο backup ή cloud upload διατηρούνται τα νεότερα `N` αρχεία.
- Διαγράφονται μόνο αρχεία που ακολουθούν αυστηρά το naming pattern του MoonHard Remote.
- Άλλα `.bak` αρχεία στον ίδιο φάκελο δεν επηρεάζονται.

{% hint style="warning" %}
Η retention policy εφαρμόζεται μόνο μετά την επιτυχημένη δημιουργία και επαλήθευση του νέου backup. Για cloud εφαρμόζεται μετά και από την επιβεβαίωση του upload.
{% endhint %}

## Επιλογές backup

### Compression

Ζητά από τον SQL Server να δημιουργήσει συμπιεσμένο backup. Μειώνει συνήθως τον απαιτούμενο χώρο και τον χρόνο cloud upload, αλλά αυξάνει τη χρήση CPU κατά τη δημιουργία.

Αν η συγκεκριμένη έκδοση SQL Server δεν υποστηρίζει compression, απενεργοποιήστε την επιλογή και επαναλάβετε.

### COPY_ONLY

Δημιουργεί ανεξάρτητο full backup χωρίς να αλλάζει τη βάση των differential backups μιας υπάρχουσας στρατηγικής backup. Συνιστάται να παραμένει ενεργό όταν το MoonHard Remote λειτουργεί παράλληλα με άλλο backup system ή SQL Agent job.

## Δημιουργία schedule

1. Επιλέξτε το tab **Schedules**.
2. Πατήστε **New**.
3. Συμπληρώστε όνομα schedule.
4. Επιλέξτε το σωστό `BOConnection`.
5. Επιλέξτε συχνότητα:
   - `Daily`
   - `Weekly`
   - `Monthly`
6. Συμπληρώστε ώρα σε μορφή `HH:MM`.
7. Για weekly schedule επιλέξτε ημέρα εβδομάδας.
8. Για monthly schedule επιλέξτε ημέρα μήνα από `1` έως `31`.
9. Συμπληρώστε προορισμό, retention και επιλογές backup.
10. Ενεργοποιήστε ή απενεργοποιήστε το **Schedule enabled**.
11. Πατήστε **Save Schedule** ή `Ctrl+S`.
12. Ελέγξτε την τιμή **Next** στη λίστα schedules.

Αν επιλεγεί ημέρα που δεν υπάρχει σε κάποιον μήνα, χρησιμοποιείται η τελευταία ημερολογιακή ημέρα του μήνα.

{% hint style="info" %}
Οι ώρες των schedules υπολογίζονται με την τοπική ώρα και ζώνη ώρας του απομακρυσμένου client, όχι με την ώρα του Dashboard ή του Render server.
{% endhint %}

## Διαχείριση schedule

- **Run selected:** Εκτελεί άμεσα το αποθηκευμένο schedule χωρίς να αλλάξει το επόμενο αυτόματο run.
- **Delete:** Διαγράφει μόνο το schedule. Δεν διαγράφει υπάρχοντα backup αρχεία.
- **Schedule enabled:** Επιτρέπει προσωρινή απενεργοποίηση χωρίς διαγραφή.
- **Refresh:** Φορτώνει ξανά schedules, ιστορικό και διαθέσιμα cloud remotes από τον client.

## Ιστορικό και cloud retries

Το tab **History** εμφανίζει:

- Ημερομηνία και ώρα έναρξης.
- Κατάσταση.
- Βάση δεδομένων.
- Χειροκίνητη ή προγραμματισμένη εκτέλεση.
- Τελικό αρχείο ή cloud προορισμό.
- Μέγεθος.
- Αποτέλεσμα verification.
- Μήνυμα ή σφάλμα.

Σε κατάσταση `UPLOAD_FAILED`:

- Το SQL backup έχει ήδη ολοκληρωθεί και επαληθευτεί.
- Το staging αρχείο δεν διαγράφεται.
- Ο client κάνει αυτόματα περιοδικές επαναλήψεις.
- Μπορείτε να πατήσετε **Retry Pending Cloud Uploads** για άμεση επανάληψη.

## Keyboard shortcuts

| Shortcut | Λειτουργία |
|---|---|
| `Ctrl+7` | Άνοιγμα Backup Manager από το Database tab |
| `Ctrl+B` | Εκτέλεση χειροκίνητου backup |
| `Ctrl+S` | Αποθήκευση schedule |
| `Ctrl+R` | Ανανέωση schedules, history και cloud remotes |
| `Esc` | Κλείσιμο Backup Manager |

## CLI

Οι ίδιες λειτουργίες είναι διαθέσιμες από το Dashboard package.

### Χειροκίνητο local backup

```powershell
python -m app.main --backup run `
  --client "CLIENT-CODE" `
  --bo-connection 1 `
  --destination-type local `
  --destination-path "D:\SQLBackups" `
  --retention-mode keep-last `
  --keep 7 `
  --yes
```

### UNC backup με αντικατάσταση

```powershell
python -m app.main --backup run `
  --client "CLIENT-CODE" `
  --bo-connection 1 `
  --destination-type unc `
  --destination-path "\\NAS01\MoonHardBackups" `
  --retention-mode replace `
  --yes
```

### Cloud backup σε MEGA

```powershell
python -m app.main --backup run `
  --client "CLIENT-CODE" `
  --bo-connection 1 `
  --destination-type cloud `
  --staging-path "D:\BackupStage" `
  --cloud-remote "mega:MoonHardBackups" `
  --retention-mode keep-last `
  --keep 10 `
  --yes
```

### Προβολή schedules και history

```powershell
python -m app.main --backup list --client "CLIENT-CODE"
```

### Προβολή configured cloud remotes

```powershell
python -m app.main --backup list-cloud-remotes --client "CLIENT-CODE"
```

### Δημιουργία ημερήσιου schedule

```powershell
python -m app.main --backup save-schedule `
  --client "CLIENT-CODE" `
  --bo-connection 1 `
  --name "Nightly InitialTest" `
  --frequency daily `
  --time "02:00" `
  --destination-type local `
  --destination-path "D:\SQLBackups" `
  --retention-mode keep-last `
  --keep 7 `
  --yes
```

### Επανάληψη pending cloud uploads

```powershell
python -m app.main --backup retry-pending `
  --client "CLIENT-CODE" `
  --yes
```

## Αρχεία και logs στον client

Το state αποθηκεύεται στο:

```text
C:\ProgramData\MoonHardRemoteV2\backups\backup_state.json
```

Διατηρείται επίσης last-good αντίγραφο:

```text
C:\ProgramData\MoonHardRemoteV2\backups\backup_state.json.bak
```

Οι ενέργειες καταγράφονται στα υπάρχοντα logs του MoonHard Remote Client.

{% hint style="danger" %}
Μην τροποποιείτε χειροκίνητα το `backup_state.json` ενώ εκτελείται η υπηρεσία. Χρησιμοποιείτε το Dashboard ή το CLI.
{% endhint %}

## Έλεγχοι πριν από ενεργοποίηση schedule

- [ ] Επιβεβαιώθηκε το σωστό `BOConnection`.
- [ ] Εκτελέστηκε επιτυχές manual backup με τις ίδιες ρυθμίσεις.
- [ ] Το αποτέλεσμα έδειξε `Verified: True`.
- [ ] Επιβεβαιώθηκε ο διαθέσιμος χώρος.
- [ ] Επιβεβαιώθηκαν τα δικαιώματα SQL Server service account.
- [ ] Για cloud, εμφανίζεται το remote στη λίστα configured remotes.
- [ ] Για cloud, ολοκληρώθηκε δοκιμαστικό upload.
- [ ] Επιλέχθηκε η σωστή retention policy.
- [ ] Επιβεβαιώθηκε η τοπική ώρα του client.

## Έλεγχοι μετά την πρώτη προγραμματισμένη εκτέλεση

- [ ] Το schedule εμφανίζει νέο `Last finished` και επιτυχημένο status.
- [ ] Το αρχείο υπάρχει στον τελικό προορισμό.
- [ ] Το history δείχνει `Verified: True`.
- [ ] Η retention policy κράτησε τον σωστό αριθμό αρχείων.
- [ ] Για cloud, το staging αρχείο αφαιρέθηκε μετά το επιτυχημένο upload.
- [ ] Έγινε δοκιμαστικό restore σε ξεχωριστό test environment.

## Troubleshooting

### The remote client did not acknowledge the backup request

Αιτία: Το Dashboard ή ο Render server έστειλε το αίτημα, αλλά ο συνδεδεμένος
client δεν δήλωσε υποστήριξη του backup protocol ή δεν απάντησε μέσα σε 15
δευτερόλεπτα. Συνήθως εκτελείται παλιότερο client/service.

Ενέργειες:

1. Εγκαταστήστε ή εκκινήστε τον MoonHard Remote Client `1.0.12` ή νεότερο.
2. Επανεκκινήστε την υπηρεσία ώστε να γίνει νέο WebSocket registration.
3. Επιβεβαιώστε ότι έχει ολοκληρωθεί το deployment του ενημερωμένου server.
4. Κλείστε και ανοίξτε ξανά το Dashboard και επαναλάβετε το backup.

Η εμφάνιση αυτού του μηνύματος δεν επιβεβαιώνει ότι ξεκίνησε SQL backup.

### Cannot open backup device / Operating system error 5

Αιτία: Ο λογαριασμός υπηρεσίας SQL Server δεν έχει δικαίωμα εγγραφής.

Ενέργειες:

1. Ελέγξτε ποιος λογαριασμός εκτελεί την υπηρεσία SQL Server.
2. Δώστε Modify permission στον φάκελο και στο share.
3. Χρησιμοποιήστε UNC και όχι mapped drive.
4. Επαναλάβετε manual backup.

### The client service cannot read the backup path

Αιτία: Ο SQL Server μπόρεσε να γράψει το backup, αλλά ο MoonHard Remote Client δεν βλέπει την ίδια διαδρομή.

Ενέργειες:

1. Ελέγξτε αν SQL Server και client βρίσκονται στον ίδιο υπολογιστή.
2. Αν βρίσκονται σε διαφορετικούς υπολογιστές, χρησιμοποιήστε κοινό UNC path.
3. Δώστε read/modify permission και στην υπηρεσία MoonHard Remote Client.

### rclone was not found

Τοποθετήστε το `rclone.exe` στην προεπιλεγμένη διαδρομή ή ορίστε τοπικά το `MOONHARD_RCLONE_PATH` και επανεκκινήστε την υπηρεσία.

### rclone configuration was not found

Δημιουργήστε το `rclone.conf` στην προεπιλεγμένη διαδρομή ή ορίστε τοπικά το `MOONHARD_RCLONE_CONFIG`.

### Cloud upload failed

1. Μην διαγράψετε το staging `.bak`.
2. Ελέγξτε σύνδεση Internet και quota cloud provider.
3. Ελέγξτε το remote με `rclone listremotes`.
4. Πατήστε **Retry Pending Cloud Uploads**.

### Backup compression is not supported

Απενεργοποιήστε το **Compression**, εκτελέστε ξανά manual backup και ενημερώστε το schedule.

## Πότε χρησιμοποιείται

- Για τακτικά πλήρη backups βάσεων BackOffice/Αμβροσίας.
- Πριν από εργασίες cleanup, history, shrink, rebuild ή αναβάθμιση.
- Για δεύτερο αντίγραφο σε NAS ή cloud provider.
- Για εγκαταστάσεις χωρίς διαθέσιμο SQL Server Agent.

## Πότε δεν πρέπει να χρησιμοποιείται

- Ως μοναδικό backup χωρίς δοκιμασμένο restore.
- Σε μη αξιόπιστο προορισμό χωρίς έλεγχο διαθέσιμου χώρου.
- Σε cloud staging folder που δεν είναι προσβάσιμο από SQL Server και client.
- Ως αντικατάσταση μιας ολοκληρωμένης στρατηγικής full/differential/log backups όταν απαιτείται point-in-time recovery.

{% hint style="warning" %}
Η ένδειξη `RESTORE VERIFYONLY` επιβεβαιώνει ότι το backup set είναι αναγνώσιμο και πλήρες ως backup media. Η τελική επιχειρησιακή επιβεβαίωση γίνεται με περιοδικό πραγματικό restore σε ξεχωριστή test βάση.
{% endhint %}
