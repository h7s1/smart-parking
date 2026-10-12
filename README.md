# Smart Parking System (T4): Code Snapshot 1

SW 341 Software Security Engineering · Group 4 · Section O53 · Week 8

This snapshot covers the Week 8 scope in the project brief: **authentication,
roles, API and database**. All data is synthetic.

## Run it

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/setup_dev.py          # creates .env (encryption key) and a local HTTPS certificate
python scripts/init_db.py            # creates the database and prints the synthetic accounts
python run.py                        # https://localhost:5000
```

The certificate is self-signed, so the browser shows a warning the first time.
Choose "Advanced", then continue to localhost. (For a trusted local
certificate, install `mkcert`, run `mkcert localhost 127.0.0.1`, and save the
files as `certs/dev-cert.pem` and `certs/dev-key.pem`.)

`init_db.py` prints random passwords for one admin, one support agent and one
driver. Copy them when they are shown; they are not stored anywhere else.

### Run the tests

```bash
python -m unittest discover -s tests -v
```

64 tests. Each test names the requirement it checks, and tests marked
"(negative)" try an attack and confirm the system refuses it. These can be
reused as evidence for the Week 11 security testing.

## Code structure (matches Figure 1 of the report)

| Folder | Layer (Figure 1) | What it does |
|---|---|---|
| `app/web/` | Presentation: web pages | Pages for drivers, the admin and support agents. Make no security decisions. |
| `app/api/` | Business logic: API | Single entry point. `guards.py` checks login and role; `validation.py` checks every input. |
| `app/logic/` | Business logic | Accounts, vehicles, reservations, spot management. |
| `app/security/` | Business logic: security services | Encryption, bcrypt, sessions, audit logger, request limit. |
| `app/data_access/` | Data access code | The only code that touches the database. Parameterized queries only. |
| `app/data_access/schema.sql` | Database | Tables built from the Personal Data Map. |
| `.env` (not in Git) | Encryption key | Read once at start-up. |

How one request moves through the layers, for example "cancel a reservation":

1. `api/reservation_routes.py`: `@roles_required(DRIVER)` checks the session and the role (SR-03, SR-04).
2. `api/validation.py`: `path_id()` checks that the ID is a valid UUID (SR-14).
3. `logic/reservations.py`: `cancel()` applies the 30-minute rule (FR-07).
4. `data_access/reservations_repo.py`: the query includes `driver_id = ?`, so another driver's reservation is "Not found" (SR-05, SR-15).

## Requirements implemented in this snapshot

| Requirement | Where | Test file |
|---|---|---|
| FR-01 register as DRIVER only | `logic/accounts.py` `register_driver` | test_authentication |
| FR-02 session gets the user's role | `security/sessions.py`, `data_access/sessions_repo.py` | test_authentication |
| FR-03 delete account | `logic/accounts.py` `delete_driver_account` | test_authentication |
| FR-04, FR-05 add and remove vehicles | `logic/vehicles.py` | test_parking |
| FR-06, FR-07 reserve and cancel | `logic/reservations.py` | test_parking |
| FR-12, FR-13, FR-14 admin spots and audit log | `logic/admin.py` | test_parking, test_authorization |
| NFR-03, NFR-04 confirmation and error messages | `api/*_routes.py`, `api/validation.py` | test_parking |
| NFR-07 log logins and account changes | `security/audit.py` | test_authentication |
| NFR-09 no double booking | `logic/reservations.py` (write lock + overlap check) | test_parking |
| SR-01, SR-02 login and 15-minute block | `logic/accounts.py` `log_in` | test_authentication |
| SR-03, SR-04 login and role on the server | `api/guards.py` | test_authorization |
| SR-05 own records only | `data_access/*_repo.py` (`owner_id = ?`, `driver_id = ?`) | test_authorization |
| SR-07 random UUIDs | every `uuid.uuid4()` | test_authorization |
| SR-08, SR-09 audit account changes; admin reads log | `security/audit.py`, `api/admin_routes.py` | test_authentication, test_authorization |
| SR-10 bcrypt, work factor >= 10 | `security/passwords.py`, `config.py` | test_authentication, test_input_and_errors |
| SR-11 admin does not see who reserved | `data_access/reservations_repo.py` `list_times_from` | test_authorization |
| SR-12 drivers cannot edit parking sessions | no route exists that changes them | (by design) |
| SR-13 HTTPS | `run.py` (HTTPS only), Secure cookie, HSTS header | test_authentication |
| SR-14 server-side input validation | `api/validation.py` | test_input_and_errors, test_parking |
| SR-15 parameterized queries | `data_access/` | test_input_and_errors (also scans the code) |
| SR-16 safe error messages | `errors.py`, error handlers in `app/__init__.py` | test_input_and_errors |
| SR-18 key outside code and database | `config.py`, `.env`, `.gitignore` | test_input_and_errors |
| SR-19 60 requests per minute | `security/rate_limit.py` | test_input_and_errors |
| PR-02 no names, phones or GPS | `schema.sql` has no such columns | (by design) |
| PR-03, PR-04 email and plate encrypted | `security/crypto.py` (AES-256-GCM) | test_authentication, test_parking |
| PR-05, PR-06 IDs only in sessions and audit log | `schema.sql`, `security/audit.py` | test_authentication |
| PR-11 deleting the account deletes the data | `ON DELETE CASCADE` in `schema.sql` | test_authentication |

## Proposed requirements (add to the report)

The code needed these, but the report has no requirement for them yet. They
are marked `PROPOSED-n` in the code.

| ID | Proposed requirement | Why |
|---|---|---|
| PROPOSED-1 | The system shall end a user's session when the user logs out. | The brief asks for "logout/session or token handling". |
| PROPOSED-2 | The system shall end a session after 30 minutes of inactivity. | Same; limits the use of a stolen or forgotten session. |
| PROPOSED-3 | The system shall not allow any user to change audit log entries, or to delete them before they are 180 days old. | TH-06 says the log "can only be displayed"; this makes it enforceable. |
| PROPOSED-4 | The system shall accept requests that change data only in JSON format. | Blocks cross-site request forgery, together with the SameSite cookie. |
| PROPOSED-5 | The system shall require passwords of 15 to 64 characters. | NIST SP 800-63B-4 (report reference [1]) for single-factor passwords. |

## Not in this snapshot (later weeks)

* Gate simulator and gate decision: FR-09, FR-10, FR-11, SR-17, PR-01, NFR-02.
* Disputes and support agent access: FR-15, FR-16, FR-17, SR-06, NFR-08.
* Reservation email (simulated notification service): FR-08.
* Cleanup job for retention: PR-07 to PR-10, and deleting accounts after 12 months without a login.

The tables for parking sessions and disputes already exist in `schema.sql`.

## Known limitations

* **Lookup by decrypting.** Login and the plate uniqueness check decrypt every
  stored email or plate and compare (team design decision). This only suits a
  small data set; a larger system would search by a keyed hash.
* **Registration shows whether an email is taken.** The message does not say
  so, but the failed status does. The request limit (SR-19) slows mass
  checking; a full fix needs email verification.
* **Request counts are kept in memory.** They reset when the server restarts.
* **Flask's built-in server** is used for the prototype; it is not meant for production.
