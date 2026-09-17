# Provider Diagnostic Center — Έλεγχος project και Phase 1

## Βάση ελέγχου

Repository: https://github.com/MoonHard13/MoonHardRemoteV2

Ελέγχθηκε το `main`, commit `6491d991acefe72b46edbfff383577d176445779`.

## 1. Πού δημιουργούνται τα tabs

Τα tabs διαχείρισης ενός πελάτη δημιουργούνται στο `dashboard/app/views/client_manage_window.py`, στην `ClientManageWindow._build_ui()`. Το Provider δεν είναι tab της αρχικής λίστας πελατών: βρίσκεται μέσα στο Manage window. Το νέο Provider Diagnostic Center προστίθεται ακριβώς μετά το Provider στην ίδια σειρά tabs. Η υφιστάμενη σειρά των άλλων tabs διατηρείται.

## 2. Ποια κλάση αλλάζει

Η `ClientManageWindow` δημιουργεί το νέο container και ένα ανεξάρτητο `ProviderDiagnosticTab`. Το υπάρχον `ProviderTab` και οι λειτουργίες του διατηρούνται.

## 3. Πώς κρατιέται ο πελάτης

Η `MoonHardDashboardApp._open_manage_window(client)` περνά το `client` dict στο παράθυρο. Το `self.client_code` προσδιορίζει την εγκατάσταση. Το dashboard κρατά `manage_windows` ανά client code. Το `update_client_data()` ενημερώνει το ανοιχτό παράθυρο.

Το ήδη επιλεγμένο BOConnection κρατιέται στο `selected_bo_connection_id`. Ο νέος adapter διαβάζει αυτό το context μέσω callbacks και απορρίπτει fallback σε άλλη βάση. Δεν δημιουργείται customer ή BO selector μέσα στο Diagnostic Center.

## 4. ΑΦΜ εκδότη

Δεν βρέθηκε επιβεβαιωμένο πεδίο ΑΦΜ εκδότη στο customer model, στην αποθήκευση client ή στα γνωστά appsettings. Το φίλτρο AFM του παλιού Provider αφορά αναζήτηση παραστατικών, όχι verified issuer identity. Δεν χρησιμοποιείται ως ΑΦΜ εταιρείας. Απαιτείται επιβεβαίωση της πραγματικής πηγής πριν από live requests.

## 5. Provider credentials

Η `AppSettingsReader.read_appsettings_production()` διαβάζει πραγματικά δεδομένα μόνο στον Client. Η `read_appsettings_for_server()` αποκρύπτει SQL credentials, `ClientAuth`, `ClientAuthFO` και `subscriptionKey`. Από τα ProviderConnections προωθούνται μόνο `ID`, `BaseURL`, `OfflineURL`.

Η `ClientRepository` αποθηκεύει και επιστρέφει safe/masked appsettings. Δεν υπάρχει αποδεδειγμένη αντιστοίχιση των παραπάνω πεδίων στο S1Ecos `APIKey`. Επίσης το BaseURL μπορεί να αφορά άλλο επίπεδο της υφιστάμενης εγκατάστασης· δεν μετατρέπεται αυθαίρετα σε diagnostic API URL.

Η Phase 1 παρέχει typed `VerifiedProviderCredentials` και resolver integration point. Δεν παρέχει UI εισαγωγής νέων credentials ούτε θεωρεί το subscriptionKey Provider APIKey. Ο resolver δεν συνδέεται με guessed field. Μέχρι την επιβεβαίωση πηγής/ασφαλούς διάθεσης, ο live έλεγχος είναι απενεργοποιημένος.

## 6. Επικοινωνία Dashboard–Client

Το `DashboardWebSocketClient` χρησιμοποιεί worker thread με asyncio loop. Το `server/app/routes/websocket_routes.py` δρομολογεί αιτήματα προς τον Client. Το `client/app/client_agent.py` εκτελεί τοπικές εργασίες. Για τα διαβιβασμένα υπάρχει `TransmittedRequestRouter`, με request ID, client/BO correlation, timeout και απάντηση μόνο στο dashboard που έκανε το αίτημα.

## 7. ERP / SQL Server

Ο Client διαβάζει το πραγματικό connection string του επιλεγμένου BOConnection από τα τοπικά appsettings. Οι `ProviderService` και `SqlExecutor` χρησιμοποιούν pyodbc. Το Dashboard δεν χρειάζεται SQL password. Η σύνδεση WebSocket του Client δεν θεωρείται επιτυχής SQL σύνδεση.

## 8. Επαναχρησιμοποίηση

- Το υφιστάμενο client/BO context και connection-string parser.
- Το theme, Treeview styling και rotating logging του Dashboard.
- Η υφιστάμενη WebSocket αυθεντικοποίηση για CLI ανάγνωση context.
- Στις επόμενες φάσεις: `client/app/provider/transmitted_invoices.py`, `provider_models.py`, `provider_service.py`, `server/app/websocket/transmitted_requests.py` και το existing transmitted UI pattern.

Το `TransmittedInvoicesService.search()` ανιχνεύει ήδη την ύπαρξη `TblSnMyDATA_ResponseSuccess` και υποστηρίζει μόνο `TblSnMyDATA_Response` όταν η πρώτη λείπει. Δεν αντιγράφεται δεύτερος schema-specific SQL μηχανισμός στη Phase 1.

## 9. Ακριβές scope Phase 1

- Νέο Manage tab δίπλα στο Provider.
- Overview με πραγματικό διαθέσιμο context, ειλικρινή κατάσταση readiness και τελευταία πραγματική API κλήση.
- API Diagnostics στη RAM, έως 1.000 attempts ανά context, filters, sorting, copy και export.
- API client με documented HTTPS GET, TLS verification, blocked redirects, timeouts, bounded responses, ελεγχόμενα retries και ακύρωση.
- Κεντρικά ασφαλή errors και redacting log formatter.
- Worker thread και Queue: καμία Tk ενέργεια από τον worker.
- CLI για context, ενότητες και exported diagnostics.
- Σαφώς προγραμματισμένες επόμενες ενότητες και QR Tools σε αναμονή πλήρους schema.

Δεν υλοποιούνται ακόμη documents dataset, pagination traversal, reconciliation ή advanced diagnostics. Ο χειροκίνητος Provider probe είναι μία ανάγνωση της πρώτης σελίδας σημερινών outgoing documents και απαιτεί verified resolver. Δεν αποτελεί πλήρη μέτρηση περιόδου ή background monitor.

## 10. Υπάρχοντα αρχεία που τροποποιούνται

- `dashboard/app/views/client_manage_window.py`: tab, component και context update hooks.
- `dashboard/app/logger_config.py`: ασφαλής formatter, μαζί με tracebacks.
- `dashboard/app/main.py`: diagnostic CLI entry point και GUI import μετά το CLI dispatch.

Δεν απαιτούνται αλλαγές Client/server, migration, νέα βάση ή νέα dependency.

## 11. Νέα αρχεία

Το package `dashboard/app/provider_diagnostic/` περιέχει `__init__.py`, `api_client.py`, `cli.py`, `context.py`, `diagnostics.py`, `errors.py`, `models.py`, `sections.py`, `security.py`, `service.py`, `tasks.py`, `ui.py`.

Προστίθενται επίσης `tests/test_provider_diagnostic.py`, `scripts/build_dashboard_exe.ps1`, αυτό το σημείωμα και το `docs/PROVIDER_DIAGNOSTIC_MANUAL_EL.md`.

## Τεκμηρίωση Provider

- Authentication: https://developers.s1ecos.com/api-authentication-3187997f0
- Document retrieval: https://developers.s1ecos.com/retrieving-a-document-869812m0

Η τρέχουσα public τεκμηρίωση δείχνει `getdocuments/{IssuerVatNumber}/{PageNumber}/?From=...&dateTo=...`, APIKey header, country prefix, JSON array και `NextPage` response header. Σε επόμενη παράγραφο χρησιμοποιεί `To` και διαφορετικό example route· αυτή η ασυνέπεια χρειάζεται επιβεβαίωση πριν από επέκταση pagination/incremental refresh στη Phase 2.

## Εκκρεμή integration στοιχεία

Χρειάζονται μόνο ονόματα πεδίων/διαδρομές προέλευσης ή ανωνυμοποιημένο configuration sample που τεκμηριώνει την πηγή issuer VAT και APIKey. Δεν χρειάζεται κοινοποίηση πραγματικών secrets. Αν το APIKey βρίσκεται αποκλειστικά στον Client, πρέπει να επιλεγεί ασφαλής, προσωρινή διάθεσή του στο Dashboard ή διαφορετική αρχιτεκτονική, με διατήρηση της υπάρχουσας απόκρυψης στην αποθήκευση appsettings.

## Όρια επαλήθευσης

Οι automated δοκιμές χρησιμοποιούν fixtures και mocks. Δεν έγιναν πραγματικά Provider requests ή SQL queries. Το περιβάλλον ελέγχου είναι Linux και δεν έχει CustomTkinter, PyInstaller ή Windows runtime. Δεν επιβεβαιώθηκαν οπτικό layout, πραγματικό Windows EXE build ή λειτουργία EXE σε ξεχωριστό Windows περιβάλλον. Απαιτούνται πριν από merge/διανομή.
