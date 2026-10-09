# AttendancePro Nova — Fresh build

A new Flask + SQLite attendance application with a responsive dark violet campus dashboard inspired by the reference image. This is a fresh implementation and does not import the earlier app modules or database.

## Features
- Separate admin and student sessions with hashed passwords
- Admin overview with live metrics and database-driven attendance activity
- Create/search student accounts and pause/reactivate access
- Add and view subjects
- Mark or update attendance per student + subject + date (Present, Absent, OD, Leave)
- Attendance search and date filter; CSV export
- Publish announcements visible on student dashboard
- Recent activity/audit log
- Student dashboard with personal attendance totals, subject-wise progress, history and announcements
- Student password change
- CSRF token validation on POST forms, session cookie protections, responsive layout

## Requirements
- Python 3.10 or newer recommended
- Windows / macOS / Linux

## Run on Windows with VS Code
1. Extract the ZIP and open this folder in VS Code.
2. Open Terminal → New Terminal.
3. Run:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   python app.py
   ```
   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate again.
4. Visit `http://127.0.0.1:5000`.

On macOS/Linux, activate with `source .venv/bin/activate` and copy `.env.example` to `.env`.

## First-run demo accounts
- Admin email: `admin@attendancepro.local`
- Admin password: `Admin@12345`
- Student ID: `STU0001`
- Student password: `Student@123`

The app creates `attendancepro.db` automatically on first launch. Default demo credentials are for local development only. Change them before using real data. For the admin, set `ADMIN_PASSWORD` in `.env` **before the first run**. The initial admin is not automatically reset if the database already exists. Student demo password can similarly be set with `DEMO_STUDENT_PASSWORD` before first launch.

## Database behavior
- SQLite stores student IDs, subjects, attendance, notices, and audit events in `attendancepro.db`.
- Student ID and email are unique.
- Re-marking attendance for the same student, subject and date updates the existing row.
- Back up the database file regularly. Do not delete it unless you intend to reset all local records.

## Production notes
This is a portfolio/local-development foundation, not a certified college information system. Before deployment: use a long random `SECRET_KEY`; change every demo password; configure HTTPS; use a production WSGI server; add rate limiting and account recovery; review authorization and privacy; test backups/restoration; and consider PostgreSQL for multi-user deployment. Avoid placing student personal data in a public repository. Use a production database and proper migration/backup practices before storing institution-wide data.
