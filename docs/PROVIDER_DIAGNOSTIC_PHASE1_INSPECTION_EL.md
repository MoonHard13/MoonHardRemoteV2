# Provider Diagnostic Center — Έλεγχος και ενσωμάτωση Phase 1

## 1. Δημιουργία tabs

Το dashboard/app/views/client_manage_window.py, ClientManageWindow._build_ui(), δημιουργεί τα Manage tabs. Το Provider Diagnostic Center προστίθεται αμέσως μετά το Provider.

## 2. Κλάσεις ενσωμάτωσης

Το ClientManageWindow συνδέει CustomerContextAdapter, ProviderContextSession, ProviderDiagnosticService και ProviderDiagnosticTab. Το νέο UI χρησιμοποιεί το υπάρχον CustomTkinter theme.

## 3. Επιλεγμένος πελάτης

Το MoonHardDashboardApp περνά το client dict και χρησιμοποιεί client_code για το Manage window. Το adapter επαναχρησιμοποιεί την υπάρχουσα επιλογή BOConnection. Δεν προστίθεται δεύτερη επιλογή πελάτη ή βάσης.

## 4. ΑΦΜ εκδότη

Επιβεβαιωμένη πηγή από τον χρήστη: dbo.TblSnCompany.CompanyAFM στην επιλεγμένη βάση. Ο Client ανακτά διαφορετικά ΑΦΜ και διαθέσιμη CompanyName/CompanyCode. Η τεκμηρίωση του συνημμένου περιγράφει CompanyAFM ως κείμενο και CompanyName ως επίσημη επωνυμία. Αρχικά μηδενικά διατηρούνται. Προαιρετικά EL/GR κανονικοποιούνται σε EL. Τα ΑΦΜ πρέπει να έχουν 9 ψηφία μετά την αφαίρεση προθέματος. Δεν εκτελείται πιστοποίηση ενεργότητας ή checksum.

Μία μοναδική εταιρεία επιλέγεται αυτόματα. Πολλά ΑΦΜ απαιτούν ρητή επιλογή. Διπλότυπα ΑΦΜ συγχωνεύονται. Καμία κλήση Provider δεν επιλέγει αυθαίρετα την πρώτη γραμμή.

## 5. Provider credentials

Επιβεβαιωμένη αντιστοίχιση από τον χρήστη: S1Ecos APIKey = subscriptionKey του επιλεγμένου BOConnection. Το κλειδί ανακτάται από πραγματικά τοπικά appsettings στον Client, αφού το επιλεγμένο ΑΦΜ επιβεβαιωθεί ξανά στη βάση. Δεν χρησιμοποιείται masked τιμή και δεν γίνεται fallback σε άλλη σύνδεση.

Τα γενικά appsettings προς Dashboard/server παραμένουν masked. Το κλειδί βρίσκεται προσωρινά στη συνεδρία Dashboard, λήγει σε 10 λεπτά και αφαιρείται σε αλλαγή βάσης, αποσύνδεση και κλείσιμο. Δεν καταγράφεται σε exports, logs ή αποθηκευμένες ρυθμίσεις. Ένας ήδη ενεργός HTTPS worker κρατά τα στοιχεία μέχρι να ολοκληρωθεί/λήξει.

## 6. Επικοινωνία Dashboard–Client

Νέο αίτημα provider_diagnostic_context και απάντηση provider_diagnostic_context_result. Χρησιμοποιούνται η υπάρχουσα αυθεντικοποίηση WebSocket και request UUID. Ο νέος server router επαναχρησιμοποιεί την αποκλειστική δρομολόγηση των διαβιβασμένων και προωθεί μόνο επιτρεπόμενα πεδία. Το κλειδί αποστέλλεται αποκλειστικά στο Dashboard που το ζήτησε, χωρίς broadcast ή αποθήκευση στη βάση server. Ο Client δηλώνει provider_diagnostic_v1. Απαιτείται WSS για την ανάκτηση κλειδιού.

## 7. Πρόσβαση ERP

Ο Client εκτελεί μόνο SELECT από τον dbo.TblSnCompany, χρησιμοποιώντας τον υπάρχοντα ODBC connection converter. Timeout σύνδεσης 15 s και SQL 30 s, με ρητό κλείσιμο cursor/connection. CompanyName/CompanyCode είναι προαιρετικά. Πάνω από 2.000 εγγραφές απορρίπτονται για να μη χρησιμοποιηθεί μερική λίστα. SQL και ανάγνωση appsettings εκτελούνται εκτός asyncio loop.

## 8. Επαναχρησιμοποίηση

Client/customer context, επιλογή BOConnection, WebSocket callbacks, theme/Treeview styling, rotating logs, resource_path και PyInstaller entry point. Οι υπάρχουσες λειτουργίες Provider, SQL, Database και Backup διατηρούνται. Το schema-aware TransmittedInvoicesService θα χρησιμοποιηθεί στο reconciliation επόμενης φάσης.

## 9. Scope Phase 1

Overview, επιλογή εταιρείας/ΑΦΜ, ασφαλής προσωρινή ανάκτηση κλειδιού, HTTPS client, ελεγχόμενα errors, bounded API Diagnostics, worker/Queue, ακύρωση και CLI. Το probe ανακτά μόνο την πρώτη σελίδα σημερινών outgoing documents απευθείας από Dashboard. Δεν αποτελεί πλήρη φόρτωση περιόδου, αποστολή παραστατικών ή background polling. Οι επόμενες ενότητες εμφανίζουν σαφή φάση υλοποίησης.

Αλλαγές βάσης, ΑΦΜ ή ανανέωση συνεδρίας ακυρώνουν παλιούς ελέγχους και απομονώνουν το ιστορικό. Request UUID και generation εμποδίζουν καθυστερημένα αποτελέσματα να ενημερώσουν νέο context.

## 10. Υπάρχοντα αρχεία που αλλάζουν

- dashboard/app/views/client_manage_window.py: tab και hooks.
- dashboard/app/dashboard_app.py: routing απάντησης και WSS έλεγχος.
- dashboard/app/main.py και logger_config.py: CLI και redacting formatter.
- client/app/client_agent.py: request handler και capability.
- server/app/routes/websocket_routes.py: αποκλειστικό routing και logging μόνο message type.
- server/app/websocket/transmitted_requests.py: επεκτάσιμη επιτρεπόμενη λίστα request πεδίων.
- tests/test_backup_feature.py: ο έλεγχος capability δέχεται την προσθήκη νέας capability.

## 11. Νέα αρχεία

Package dashboard/app/provider_diagnostic με api_client, cli, context, diagnostics, errors, models, security, service, session, sections, tasks και ui. Client reader: client/app/provider/diagnostic_context.py. Server router: server/app/websocket/provider_diagnostic_requests.py. Προστίθενται tests και scripts/build_dashboard_exe.ps1. Δεν προστίθενται dependencies ή database migrations.

## Provider contract

Επίσημη τεκμηρίωση: https://developers.s1ecos.com/retrieving-a-document-869812m0

Το υλοποιημένο GET είναι https://einvoice.impact.gr/api/invoice/getdocuments/{IssuerVatNumber}/{PageNumber}/?From=YYYYMMDD&dateTo=YYYYMMDD με header APIKey. Το response είναι JSON array και διαθέτει NextPage header. TLS επαληθεύεται, redirects αποκλείονται, απαντήσεις περιορίζονται σε 8 MiB και έως 3 attempts. Η τεκμηρίωση περιέχει και εναλλακτική αναφορά To/example route· δεν υλοποιείται guessed pagination traversal στη Phase 1.

## Επαλήθευση και εγκατάσταση

Αυτοματοποιημένες δοκιμές με mocks ελέγχουν HTTP errors/retries, εταιρείες, αρχικά μηδενικά, απομόνωση πελάτη/βάσης/ΑΦΜ, αποκλειστική δρομολόγηση και CLI. Δεν έγιναν πραγματικά SQL/Provider requests ούτε οπτικός έλεγχος ή Windows EXE UAT από το Linux περιβάλλον.

Ενημερώστε server, Client και Dashboard για τη νέα δυνατότητα. Εκτελέστε τα υπάρχοντα Windows build scripts και ελέγξτε τα EXE σε ξεχωριστό Windows PC χωρίς Python πριν από διανομή. Δεν δημοσιεύεται νέο client manifest ή installer χωρίς αυτόν τον έλεγχο.
