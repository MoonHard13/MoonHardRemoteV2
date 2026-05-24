MoonHard Remote V2 — UAT Test Plan
1. Current feature scope covered

This UAT covers:

1. Render server startup
2. Supabase database connection
3. Client auto-registration
4. Client online/offline status
5. Dashboard WebSocket connection
6. Dashboard client list
7. Manage window
8. Rename client
9. Remote CMD/PowerShell terminal
10. Persistent terminal current directory
11. Terminal command history
12. Terminal Tab autocomplete
13. appsettings.production.json auto-read
14. AppSettings tab display
15. BOConnection ID selection
16. SQL Test Connection
17. SQL query execution
18. .sql file loading/execution
19. SQL Stop/Cancel
20. SQL result output

The server stores clients and appsettings through ClientRepository, including client upsert, heartbeat, offline marking, rename, and appsettings retrieval.
The client sends appsettings automatically after registration and supports terminal, autocomplete, SQL execute, SQL test connection, and SQL cancel handlers.
The SQL executor supports SQL Server ODBC driver detection, GO batch splitting, query execution, connection testing, cancellation, driver reporting, and elapsed time.
The dashboard routes WebSocket messages to the correct Manage window for terminal, appsettings, SQL result, SQL error, test connection, and cancel results.

2. UAT prerequisites

Before testing, prepare:

1. Render server is deployed and live.
2. Supabase tables exist:
   - clients
   - client_appsettings
3. Render environment variables exist:
   - CLIENT_TOKEN
   - DASHBOARD_TOKEN
   - ADMIN_TOKEN
   - SUPABASE_URL
   - SUPABASE_SERVICE_ROLE_KEY
4. Client PC has:
   - Python environment / exe build
   - ODBC Driver 17 or 18 for SQL Server
   - appsettings.production.json if testing AppSettings/SQL
5. Dashboard PC can connect to Render WebSocket.
6. Test SQL Server database is available.

Recommended test file path for appsettings:

C:\Program Files (x86)\Sunsoft Ltd\ExternalTaxProvider\External.Tax.Provider\appsettings.production.json
3. UAT test data

Use at least two client PCs or two test clients:

Client A:
- Has appsettings.production.json
- Has SQL Server access
- Expected status: online

Client B:
- May not have appsettings.production.json
- Used to test missing appsettings
- Expected status: online/offline depending on test

Use SQL test queries:

SELECT @@SERVERNAME AS ServerName, DB_NAME() AS DatabaseName;
SELECT TOP 10 * FROM INFORMATION_SCHEMA.TABLES;
SELECT TOP 5 * FROM INFORMATION_SCHEMA.TABLES;
SELECT TOP 5 * FROM INFORMATION_SCHEMA.COLUMNS;
WAITFOR DELAY '00:01:00';
SELECT 1 AS Done;

Use .sql file content:

SELECT @@SERVERNAME AS ServerName;
GO
SELECT DB_NAME() AS DatabaseName;
GO
SELECT TOP 10 * FROM INFORMATION_SCHEMA.TABLES;
GO
4. UAT cases
UAT-001 — Render server starts successfully

Purpose: Verify that the backend server starts on Render.

Steps:

1. Push latest code to GitHub.
2. Wait for Render deployment.
3. Open Render logs.
4. Confirm Uvicorn starts successfully.

Expected result:

Server starts without crash.
Routes are registered.
Render shows service live.

Pass/Fail:

PASS if Render service is live.
FAIL if startup crashes or missing env variable error appears unexpectedly.
UAT-002 — Server rejects missing/invalid dashboard token

Purpose: Verify dashboard WebSocket authentication.

Steps:

1. Temporarily use wrong dashboard token in dashboard config/env.
2. Start dashboard.
3. Observe connection state and server log.

Expected result:

Dashboard is rejected.
Server sends authentication failed.
Dashboard should not receive clients list.
UAT-003 — Client connects to Render server

Purpose: Verify client WebSocket registration.

Steps:

1. Start client.
2. Watch client logs.
3. Watch Render logs.
4. Open dashboard.

Expected result:

Client log shows WebSocket connected.
Client receives registered response.
Server saves/updates client in Supabase.
Dashboard displays the client.
UAT-004 — Client is saved in Supabase

Purpose: Verify database persistence.

Steps:

1. Start client.
2. Open Supabase clients table.
3. Find client_code.

Expected result:

clients table contains:
- client_code
- display_name
- pc_name
- username
- app_version
- status = online
- last_seen
- connected_at

The repository preserves display_name on reconnect and updates status/heartbeat fields.

UAT-005 — Dashboard displays client list

Purpose: Verify dashboard UI receives clients.

Steps:

1. Start dashboard.
2. Confirm WebSocket status is Online.
3. Check Connected Clients list.

Expected result:

Client appears in list.
Online client has green status indicator.
Offline client has red status indicator.
Manage button is visible.
UAT-006 — Client goes offline after closing client

Purpose: Verify offline marking.

Steps:

1. Start client and dashboard.
2. Confirm client is online.
3. Close client process.
4. Wait a few seconds.
5. Watch dashboard and Supabase.

Expected result:

Dashboard changes client to offline.
Supabase status changes to offline.
disconnected_at is updated.
last_seen is updated.
UAT-007 — Heartbeat updates online client

Purpose: Verify last_seen updates while client stays connected.

Steps:

1. Start client.
2. Keep it running for more than 30 seconds.
3. Check dashboard/Supabase last_seen.

Expected result:

last_seen updates repeatedly.
Client remains online.
UAT-008 — Rename client from Manage

Purpose: Verify friendly name rename.

Steps:

1. Open dashboard.
2. Click Manage on a client.
3. In Overview tab, change display name.
4. Press Save Name.
5. Close and reopen dashboard.
6. Restart client.

Expected result:

New display_name is saved in Supabase.
Dashboard shows renamed client.
Restarting client does not overwrite display_name.
pc_name remains unchanged.

The repository intentionally updates existing clients without changing display_name.

UAT-009 — Manage window opens per client

Purpose: Verify Manage window routing.

Steps:

1. Click Manage for Client A.
2. Click Manage for Client B.
3. Send actions to each client separately.

Expected result:

Each Manage window opens for the correct client.
Terminal/SQL/AppSettings results return to the correct window.
UAT-010 — CMD terminal command execution

Purpose: Verify remote CMD command.

Steps:

1. Open Manage → Terminal.
2. Select cmd.
3. Run:
   whoami
4. Run:
   hostname

Expected result:

Output appears in terminal output box.
Command runs on client PC, not dashboard PC.
Exit code appears.
Current directory appears.
UAT-011 — PowerShell command execution

Purpose: Verify remote PowerShell command.

Steps:

1. Open Manage → Terminal.
2. Select powershell.
3. Run:
   Get-Location
4. Run:
   $env:USERNAME

Expected result:

PowerShell output appears correctly.
No UI freeze.
UAT-012 — Persistent terminal current directory

Purpose: Verify cd state is kept.

Steps:

1. In cmd terminal, run:
   cd C:\Users
2. Run:
   cd
3. Run:
   dir

Expected result:

Current directory remains C:\Users.
dir lists files from C:\Users.
UAT-013 — Terminal command history

Purpose: Verify Up/Down arrow history.

Steps:

1. Run:
   hostname
2. Run:
   whoami
3. Press Up arrow.
4. Press Up arrow again.
5. Press Down arrow.

Expected result:

Previous commands appear in input.
Down arrow moves forward in history.
No command is executed until Enter is pressed.
UAT-014 — Terminal Tab autocomplete basic

Purpose: Verify Tab autocomplete.

Steps:

1. Open Manage → Terminal.
2. Use cmd.
3. Type:
   de
4. Press Tab.

Expected result:

Input becomes:
Desktop\

This was already fixed so the dashboard inserts insert_value instead of the full returned dictionary.

UAT-015 — Terminal Tab autocomplete with command prefix

Purpose: Verify autocomplete keeps command prefix.

Steps:

1. Type:
   cd de
2. Press Tab.

Expected result:

Input becomes:
cd Desktop\
UAT-016 — AppSettings auto-read on client connect

Purpose: Verify client reads appsettings.production.json automatically.

Steps:

1. Ensure file exists at expected path.
2. Start client.
3. Watch client log.
4. Check Supabase client_appsettings table.

Expected result:

Client sends appsettings_result.
Server saves row in client_appsettings.
file_found = true.
raw_json and raw_text are saved.
bo_connections and provider_connections are saved.

The server stores raw appsettings and extracted fields through upsert_client_appsettings().

UAT-017 — AppSettings missing file

Purpose: Verify missing appsettings does not break client.

Steps:

1. Temporarily rename appsettings.production.json.
2. Start client.
3. Open Manage → AppSettings.

Expected result:

Client still connects.
AppSettings tab says file not found.
No crash.
file_found = false in Supabase.
UAT-018 — AppSettings tab displays BOConnections

Purpose: Verify BOConnection display.

Steps:

1. Start client with valid appsettings.
2. Open Manage → AppSettings.
3. Check BOConnection dropdown.

Expected result:

Dropdown shows available BOConnection IDs.
Default selected ID is 1.
Details display:
- Server
- Database
- User ID
- Password
- UserOID
- Email
- ClientAuth
- SubscriptionKey
UAT-019 — SQL Test Connection default BOConnection ID 1

Purpose: Verify SQL connection test.

Steps:

1. Open Manage → SQL.
2. Confirm BOConnection dropdown is ID 1.
3. Press Test Connection.

Expected result:

Success: True
BOConnection ID: 1
Driver is displayed.
Elapsed time is displayed.
Server is displayed.
Database is displayed.
Login is displayed.

The client test connection handler runs SQL connection testing in a background thread.

UAT-020 — SQL Test Connection other BOConnection ID

Purpose: Verify alternative BOConnection selection.

Steps:

1. Open Manage → SQL.
2. Select another BOConnection ID.
3. Press Test Connection.

Expected result:

Test uses selected BOConnection ID.
Displayed database/server matches selected ID.
UAT-021 — SQL SELECT query execution

Purpose: Verify query execution.

Steps:

1. Open Manage → SQL.
2. Run:
   SELECT @@SERVERNAME AS ServerName, DB_NAME() AS DatabaseName;

Expected result:

Success: True.
Driver appears.
Elapsed time appears.
Result rows appear.
No client disconnect.

The SQL executor returns driver, elapsed_ms, and result batches.

UAT-022 — SQL INFORMATION_SCHEMA query

Purpose: Verify result sets with multiple columns.

Steps:

Run:
SELECT TOP 10 * FROM INFORMATION_SCHEMA.TABLES;

Expected result:

Result contains columns and rows.
At least one result set is returned.
Rows are readable.
UAT-023 — SQL multiple result sets

Purpose: Verify multiple SELECT statements in same batch.

Steps:

Run:
SELECT TOP 5 * FROM INFORMATION_SCHEMA.TABLES;
SELECT TOP 5 * FROM INFORMATION_SCHEMA.COLUMNS;

Expected result:

Both result sets are returned.
Batch output separates Result Set 1 and Result Set 2.
UAT-024 — SQL GO batch execution

Purpose: Verify .sql style batch splitting.

Steps:

Run:
SELECT @@SERVERNAME AS ServerName;
GO
SELECT DB_NAME() AS DatabaseName;
GO

Expected result:

Batch 1 executes.
Batch 2 executes.
Both result sets appear separately.

The SQL executor splits batches on standalone GO lines.

UAT-025 — Load .sql file

Purpose: Verify loading SQL file into editor.

Steps:

1. Create a .sql file with several SELECT statements and GO separators.
2. Open Manage → SQL.
3. Press Load .sql.
4. Select file.

Expected result:

File content appears in SQL editor.
Loaded file path appears in result/messages area.
UAT-026 — Execute .sql file

Purpose: Verify loaded script execution.

Steps:

1. Load .sql file.
2. Press Execute.

Expected result:

All batches execute.
Errors are shown per batch if any.
Success/driver/elapsed time displayed.
UAT-027 — SQL Stop/Cancel long query

Purpose: Verify query cancellation.

Steps:

1. Run:
   WAITFOR DELAY '00:01:00';
   SELECT 1 AS Done;
2. Immediately press Stop.

Expected result:

Dashboard shows cancel requested/result.
Client does not freeze.
Query stops or returns SQL cancellation/error response.
Stop button becomes disabled.
Final SQL result may return after cancel; this is acceptable.

The SQL executor tracks active cursors and calls cursor.cancel() for cancellation.

UAT-028 — SQL invalid query

Purpose: Verify error handling.

Steps:

Run:
SELECT * FROM TableThatDoesNotExist;

Expected result:

Success may be False or batch error shown.
Error text is displayed.
Dashboard does not crash.
Client remains online.
UAT-029 — SQL wrong BOConnection credentials

Purpose: Verify connection error handling.

Steps:

1. Use BOConnection with wrong SQL credentials, or temporarily test invalid password.
2. Press Test Connection.

Expected result:

Success: False.
Error explains login/connection failure.
Dashboard stays responsive.
UAT-030 — SQL missing ODBC driver

Purpose: Verify driver detection failure.

Steps:

1. Test on PC without ODBC Driver 17/18/Native Client/SQL Server driver.
2. Press Test Connection.

Expected result:

Error says no SQL Server ODBC driver found.
Client does not crash.
UAT-031 — Dashboard reconnect behavior

Purpose: Verify dashboard can recover after network interruption.

Steps:

1. Start dashboard.
2. Disconnect internet briefly or restart dashboard WebSocket.
3. Reconnect.

Expected result:

Dashboard reconnects.
Client list reloads.
Manage actions work again after reconnect.
UAT-032 — Client reconnect behavior

Purpose: Verify client auto-reconnect.

Steps:

1. Start client.
2. Stop Render service temporarily or disconnect internet.
3. Restore connection.

Expected result:

Client retries connection.
Client reconnects automatically.
Same client_code is used.
Display name is not overwritten.
UAT-033 — Multiple clients

Purpose: Verify routing to correct client.

Steps:

1. Start Client A and Client B.
2. Open Manage for both.
3. Run hostname on both terminals.
4. Run SQL Test Connection on Client A only.

Expected result:

Terminal result from Client A appears only in Client A Manage window.
Terminal result from Client B appears only in Client B Manage window.
SQL result appears only for selected client.
UAT-034 — Multiple dashboards

Purpose: Verify behavior with more than one dashboard.

Steps:

1. Open dashboard on PC A.
2. Open dashboard on PC B.
3. Rename client from PC A.
4. Observe PC B.

Expected result:

Both dashboards receive updated client list.
Rename appears in both.
UAT-035 — AppSettings refresh after client reconnect

Purpose: Verify appsettings is reread on reconnect.

Steps:

1. Start client and let appsettings save.
2. Modify appsettings.production.json.
3. Restart client.
4. Open Manage → AppSettings.

Expected result:

New appsettings data is saved.
Dashboard shows updated BOConnection/provider data.
5. Regression test checklist

Run this checklist before every major commit/release:

[ ] Server deploys on Render.
[ ] Dashboard connects.
[ ] Client connects.
[ ] Client appears online.
[ ] Closing client marks offline.
[ ] Rename persists after reconnect.
[ ] CMD command works.
[ ] PowerShell command works.
[ ] cd persists.
[ ] Up/Down history works.
[ ] Tab autocomplete works.
[ ] appsettings saves.
[ ] AppSettings tab loads.
[ ] BOConnection ID 1 is default.
[ ] SQL Test Connection works.
[ ] SQL SELECT works.
[ ] .sql file load works.
[ ] GO batch works.
[ ] Stop query works.
[ ] Invalid SQL shows error.
[ ] Multiple clients route correctly.
6. Known issues / improvements not part of UAT pass/fail yet

These are not blockers, but should be addressed later:

1. SQL results are still text-based unless we add the planned table/tab result UI.
2. Manage window is too large and should eventually be split into modules.
3. Dashboard WebSocket send uses a thread per message; later, a queue-based sender would be cleaner.
4. AppSettings tab should later become structured cards/tables instead of large text output.
5. Terminal autocomplete currently applies first match; repeated Tab cycling can be added later.
6. SQL logs/history are intentionally not saved to Supabase to save free-tier space.
7. Recommended UAT execution order

Do UAT in this order:

Phase 1 — Core connectivity:
UAT-001 to UAT-007

Phase 2 — Dashboard/client management:
UAT-008 to UAT-009

Phase 3 — Terminal:
UAT-010 to UAT-015

Phase 4 — AppSettings:
UAT-016 to UAT-018

Phase 5 — SQL:
UAT-019 to UAT-030

Phase 6 — Reliability/multi-client:
UAT-031 to UAT-035