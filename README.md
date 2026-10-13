# Smart Parking System (T4): Code Snapshot 2

SW 341 Software Security Engineering · Group 4 · Section O53 · Week 9

Code Snapshot 1 (Week 8) covered authentication, roles, the API and the
database. Code Snapshot 2 adds the rest of the design: the **gate simulator
and gate decision**, **disputes and support agent access**, the **simulated
confirmation email** and the **cleanup job**. All data is synthetic.

## Run it

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/setup_dev.py          # creates .env (encryption key, gate key) and a local HTTPS certificate
python scripts/init_db.py            # creates the database and prints the synthetic accounts
python run.py                        # https://localhost:5000
```

The certificate is self-signed, so the browser shows a warning the first time.
Choose "Advanced", then continue to localhost.

**On Windows**, after the setup above, double-click `start_website.bat` to
start the server and open the website. Close its window to stop the server.

`init_db.py` prints random passwords for one admin, one support agent and two
drivers. Copy them when they are shown; they are not stored anywhere else. It
also gives driver1's car (ABC1234) a reservation on A-01 that has already
started, so the gate can be tried right away.

### Updating from Code Snapshot 1

The Week 9 code needs a gate key and a new database column:

```bash
python scripts/setup_dev.py          # adds SP_GATE_KEY to .env; the encryption key is kept
python scripts/init_db.py --reset    # new database (synthetic data only), new passwords
```

`run.py` refuses to start with a Week 8 database and says which command to run.

### Gate simulator

With the server running, open a second terminal (activate `.venv` there too):

```bash
python scripts/gate_simulator.py entry ABC1234        # ALLOW: driver1 has a reservation now
python scripts/gate_simulator.py exit ABC1234         # ALLOW: exit time recorded, spot FREE again
python scripts/gate_simulator.py entry XYZ9876        # DENY: driver2 has no reservation now
python scripts/gate_simulator.py entry ABC1234 --no-key       # refused (SR-17)
python scripts/gate_simulator.py entry ABC1234 --wrong-key    # refused (SR-17)
```

Each answer shows how long it took (NFR-02: at most 2 seconds).

### Cleanup job

The cleanup job runs when the server starts and then every 24 hours; the
server console shows how many records it deleted. To run it once by hand
(for example after adding old records in DB Browser):

```bash
python scripts/run_cleanup.py
```

### Simulated email

After a reservation is confirmed, the server console shows the email that
would be sent (FR-08), with most of the address hidden.

### Run the tests

```bash
python -m unittest discover -s tests -v
```

113 tests. Each test names the requirement it checks, and tests marked
"(negative)" try an attack and confirm the system refuses it. These can be
reused as evidence for the Week 11 security testing.

## Code structure (matches Figure 1 of the report)

| Folder or file | Layer (Figure 1) | What it does |
|---|---|---|
| `app/web/` | Presentation: web pages | Pages for drivers, the admin and support agents. Make no security decisions. Fonts are served locally (`app/web/fonts/`, GUST Font License), so the pages load nothing from other websites. |
| `scripts/gate_simulator.py` | Presentation: gate simulator | Sends a plate and ENTRY or EXIT with the gate key; prints ALLOW or DENY. |
| `app/api/` | Business logic: API | Single entry point. `guards.py` checks login, role and gate key; `validation.py` checks every input. |
| `app/logic/` | Business logic | Accounts, vehicles, reservations, gate decision, disputes, spot management. |
| `app/notification.py` | Business logic: notification service | Simulated reservation confirmation email. |
| `app/cleanup.py` | Business logic: cleanup job | Deletes records whose retention period has ended. |
| `app/security/` | Business logic: security services | Encryption, bcrypt, sessions, audit logger, request limit. |
| `app/data_access/` | Data access code | The only code that touches the database. Parameterized queries only. |
| `app/data_access/schema.sql` | Database | Tables built from the Personal Data Map. |
| `.env` (not in Git) | Encryption key and gate key | Read once at start-up. |

How one request moves through the layers, for example "cancel a reservation":

1. `api/reservation_routes.py`: `@roles_required(DRIVER)` checks the session and the role (SR-03, SR-04).
2. `api/validation.py`: `path_id()` checks that the ID is a valid UUID (SR-14).
3. `logic/reservations.py`: `cancel()` applies the 30-minute rule (FR-07).
4. `data_access/reservations_repo.py`: the query includes `driver_id = ?`, so another driver's reservation is "Not found" (SR-05, SR-15).

And a gate event (flow 2):

1. `api/gate_routes.py`: `@gate_key_required` compares the `X-Gate-Key` header with the key from `.env` (SR-17).
2. `api/validation.py`: the plate and direction are checked (SR-14).
3. `logic/gate.py`: the plate is used to find the vehicle, then dropped (PR-01). With a reservation covering now and a FREE spot, the answer is ALLOW, a parking session is added (FR-10) and the spot becomes OCCUPIED.

## Requirements implemented

| Requirement | Where | Test file |
|---|---|---|
| FR-01 register as DRIVER only | `logic/accounts.py` `register_driver` | test_authentication |
| FR-02 session gets the user's role | `security/sessions.py`, `data_access/sessions_repo.py` | test_authentication |
| FR-03 delete account | `logic/accounts.py` `delete_driver_account` | test_authentication |
| FR-04, FR-05 add and remove vehicles | `logic/vehicles.py` | test_parking |
| FR-06, FR-07 reserve and cancel | `logic/reservations.py` | test_parking |
| FR-08 confirmation email (simulated) | `notification.py`, called by `logic/reservations.py` | test_notification |
| FR-09, FR-10, FR-11 gate decision, entry, exit | `logic/gate.py`, `api/gate_routes.py` | test_gate |
| FR-12, FR-13, FR-14 admin spots and audit log | `logic/admin.py` | test_parking, test_authorization, test_gate |
| FR-15, FR-16, FR-17 disputes | `logic/disputes.py`, `api/dispute_routes.py`, `api/support_routes.py` | test_disputes |
| NFR-02 gate answer within 2 seconds | `logic/gate.py` (one short transaction) | test_gate |
| NFR-03, NFR-04 confirmation and error messages | `api/*_routes.py`, `api/validation.py` | test_parking |
| NFR-07 log logins and account changes | `security/audit.py` | test_authentication |
| NFR-08 log every support agent access | `logic/disputes.py` `driver_data_for_support` | test_disputes |
| NFR-09 no double booking | `logic/reservations.py` (write lock + overlap check) | test_parking |
| SR-01, SR-02 login and 15-minute block | `logic/accounts.py` `log_in` | test_authentication |
| SR-03, SR-04 login and role on the server | `api/guards.py` | test_authorization, test_disputes |
| SR-05 own records only | `data_access/*_repo.py` (`owner_id = ?`, `driver_id = ?`) | test_authorization, test_disputes, test_gate |
| SR-06 support access only with an open dispute | `logic/disputes.py`, `data_access/disputes_repo.py` | test_disputes |
| SR-07 random UUIDs | every `uuid.uuid4()` | test_authorization |
| SR-08, SR-09 audit account changes; admin reads log | `security/audit.py`, `api/admin_routes.py` | test_authentication, test_authorization |
| SR-10 bcrypt, work factor >= 10 | `security/passwords.py`, `config.py` | test_authentication, test_input_and_errors |
| SR-11 admin does not see who reserved | `data_access/reservations_repo.py` `list_times_from` | test_authorization |
| SR-12 nobody edits parking sessions | only the gate writes them; no route changes them | test_gate, test_disputes |
| SR-13 HTTPS | `run.py` (HTTPS only), Secure cookie, HSTS header | test_authentication |
| SR-14 server-side input validation | `api/validation.py` | test_input_and_errors, test_parking, test_gate |
| SR-15 parameterized queries | `data_access/` | test_input_and_errors (also scans the code) |
| SR-16 safe error messages | `errors.py`, error handlers in `app/__init__.py` | test_input_and_errors |
| SR-17 gate key on every gate event | `api/guards.py` `gate_key_required`, `config.py` | test_gate, test_input_and_errors |
| SR-18 key outside code and database | `config.py`, `.env`, `.gitignore` | test_input_and_errors |
| SR-19 60 requests per minute | `security/rate_limit.py` | test_input_and_errors |
| SR-20 logout ends the session | `api/auth_routes.py` `logout`, `security/sessions.py` | test_authentication |
| SR-21 session ends after 30 idle minutes | `security/sessions.py` `current_user` | test_authentication, test_cleanup |
| SR-22 passwords of 15 to 64 characters | `api/validation.py` `new_password`, `config.py` | test_authentication |
| SR-23 audit entries cannot be changed or deleted early | triggers in `schema.sql` | test_authentication, test_cleanup |
| SR-24 changes only as JSON | `app/__init__.py` `protect_api` | test_input_and_errors |
| PR-01 plate dropped after the gate decision | `logic/gate.py` `decide` | test_gate |
| PR-02 no names, phones or GPS | `schema.sql` has no such columns; dispute reasons from a fixed list | test_disputes (by design) |
| PR-03, PR-04 email and plate encrypted | `security/crypto.py` (AES-256-GCM) | test_authentication, test_parking |
| PR-05, PR-06 IDs only in sessions and audit log | `schema.sql`, `security/audit.py` | test_gate, test_disputes |
| PR-07 to PR-10 retention periods | `cleanup.py`, `delete_expired()` in `data_access/` | test_cleanup |
| PR-11 deleting the account deletes the data | `ON DELETE CASCADE` in `schema.sql` | test_authentication, test_disputes |
| Data map: 12 months without login | `cleanup.py`, `users_repo.list_inactive` | test_cleanup |

## Decisions made while building Week 9 (for the team to review)

These are choices the requirements did not settle. Each one should be accepted
by the team and, where it changes the design, written into the report.

1. **Parking sessions store the spot.** `parking_sessions.spot_id` was added so
   the gate can set the spot to OCCUPIED on entry and back to FREE on exit
   (FR-12). The Personal Data Map row "Parking history" should list the spot.
2. **Entry is denied when the reserved spot is not FREE**, for example when it
   was disabled or the previous car has not left yet. The driver can then open
   a dispute ("The gate did not let me in" or "My reserved spot was taken").
3. **Exit without a recorded entry is denied** (nothing to close).
4. **A parked car cannot be removed, and the account cannot be deleted while a
   car is parked**, so a spot is never left OCCUPIED with no session behind it.
5. **Retention details.** A reservation's 30 days count from its end time.
   A session whose car is still inside is kept until the car leaves. An
   account whose car is parked is not deleted for inactivity. Inactive
   accounts of any role are deleted after 12 months, as the data map says.
6. **Closed disputes go with their record.** When a reservation or parking
   session reaches the end of its retention, the closed disputes about it are
   deleted with it (cascade), which can be sooner than 90 days after closing.
7. **Support access covers all of the driver's reservations, parking
   sessions and plates** while any of the driver's disputes is open, as SR-06
   is worded. A refused attempt (no open dispute, or an unknown ID) is
   recorded as `SUPPORT_ACCESS_DENIED`.
8. **New audit actions:** `DISPUTE_OPENED`, `DISPUTE_CLOSED`, `SUPPORT_ACCESS`,
   `SUPPORT_ACCESS_DENIED`, `INACTIVE_ACCOUNT_DELETED` (user ID empty: done by
   the system).
9. **The simulated email** is printed to the server console only, with the
   address masked (`d***@smartparking.test`), and holds no plate. Times are in UTC.
10. **Refused gate events** (missing or wrong key) are written to the server
    console without the plate, so spoofing attempts (TH-01) can be noticed.

## Known limitations

* **Lookup by decrypting.** Login, the plate uniqueness check and the gate
  decrypt every stored email or plate and compare (team design decision). This
  only suits a small data set; a larger system would search by a keyed hash.
  The gate answer was measured with 50 vehicles in the tests.
* **Registration shows whether an email is taken.** The message does not say
  so, but the failed status does. The request limit (SR-19) slows mass
  checking; a full fix needs email verification.
* **One shared gate key.** Every gate uses the same key, and changing it means
  editing `.env` and restarting. A real system would give each gate its own
  credential (for example a client certificate).
* **The cleanup job runs inside the server process.** If the server is down at
  the daily time, the job runs at the next start.
* **Request counts are kept in memory.** They reset when the server restarts.
* **Flask's built-in server and a self-signed certificate** are used for the
  prototype; neither is meant for production.
