# AttendancePro Nova — Faculty & Group Attendance Edition

A fresh Flask + SQLite attendance application with role-based access for the dean/administrator, staff, and students. The interface uses a dark futuristic campus dashboard style.

## Features
- **Class management:** the dean creates each department/class/section in a dedicated Classes page before assigning staff, registering students, or creating class-specific subjects. Duplicate class names are allowed across different departments but not within the same department.
- **Department/class subject scope:** class-specific subjects appear only for the matching department and class; shared subjects can be assigned to all classes in one department.
- **Login fix:** student ID and email login is case-insensitive, so capitalization differences in the entered ID/email no longer cause a false invalid-login message. Passwords still must match.
- **Role-specific login:** the login page requires selecting Student, Staff, or Admin/Dean; credentials are validated against the selected role, so one role cannot sign in through another role option.
- **Staff workflow:** staff no longer see an overview page after login; they are sent directly to attendance. The staff sidebar and server permissions expose only Attendance and Announcements; student management and profile routes are not available to staff.
- **Dean / admin:** create and pause staff accounts; assign each staff member a department and class/section; create students and subjects; view attendance; publish notices; export CSV; review audit logs.
- **Staff:** see only their assigned department/class; add students within that assignment; take whole-class attendance with checkboxes (checked = Present, unchecked = Absent); save the entire roster at once. Subject selection is limited to the staff member's department.
- **Students:** view their own attendance dashboard, subject totals, attendance history, announcements, and change password.
- Passwords are stored as Werkzeug password hashes; forms use session CSRF tokens; changes are recorded in audit logs. SQLite database is created on first launch. A safe migration creates the class catalog and backfills it from existing student, staff, and subject records.

## Setup (Windows PowerShell)
Open this folder in VS Code, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in the same terminal and retry activation. Use the same environment folder name (`.venv`) in all commands.

Visit `http://127.0.0.1:5000`.

## First-run demo accounts
- Dean/admin: `admin@attendancepro.local` / `Admin@12345`
- Demo student: `STU0001` / `Student@123`

The login page first asks whether the user is Student, Staff, or Admin/Dean. Admin and staff use their separate accounts created/configured for their respective roles; choosing the wrong role intentionally fails authentication. No staff account is created by default. Sign in as admin, open **Classes** and create the department/class first. Then open **Subjects** to assign subjects to the right department/class, register students, and open **Staff & access** to create a staff ID for that class. Then log in using that staff email and password.

Change demo passwords and set a strong random `SECRET_KEY` in `.env` before any non-local use. Do not commit `.env` or a live database to GitHub. These safeguards are a development baseline, not a claim of production certification; review deployment security, backups, and access policies before storing real college records.

## Quick roll-call workflow
1. Dean creates a staff account and assigns department + class/section (e.g. ECE / A).
2. Staff adds students to that assigned class with unique roll numbers/student IDs.
3. Staff opens **Group attendance**, chooses the subject and starting/ending roll number, then selects **Load class & roll range**. Leave the range blank to load everyone in the assigned class.
4. Each student row has a status: **Present**, **Absent**, **OD (On Duty)**, or **Leave**. Use **All Present**, **All Absent**, **All OD**, or **All Leave** for a fast bulk action, then adjust exceptions.
5. Select the date, review the live totals and confirmation, and save once. Only students in the displayed roll-number range are saved. Saving the same student + subject + date updates that record rather than duplicating it.

The staff member's department and class are enforced by the server and cannot be changed through the form. Subject choices are limited to the assigned department. Roll ranges use the student IDs' case-insensitive lexical order; keep roll-number formats consistent within a class (for example, `ECE001`, `ECE002`, `ECE003`).

## Notes
- Class section is a text value such as `A`, `B`, or `A1`; use the same value consistently.
- Add subjects for each department from the admin **Subjects** page before taking attendance.
- Run tests and verify all workflows before using the app for a whole college.

## Dean class-wise attendance (updated)

The administrator's **Attendance** page now uses a class register instead of the old one-student-at-a-time form:

1. Choose a department.
2. Choose a class/section (the options are drawn from the students assigned to that department).
3. Choose a subject and date, then click **Load class register**.
4. Every active student in that class is listed with roll number and name. Choose Present, Absent, OD, or Leave per student, or use a bulk status button and adjust exceptions.
5. Review the summary and save the class in one action.

The server re-queries the active roster by department and class, verifies the subject belongs to the selected department, rejects future dates, validates each status, and updates the unique student/subject/date record rather than duplicating it. Back up `attendancepro.db` before replacing a deployed codebase and test the workflow with demo records first.

## Sequential one-student roll call

The admin attendance page and staff Quick Roll Call now use a one-student-at-a-time flow. Select the department/class/subject/date (admin) or assigned subject and range (staff), then tap **Present**, **Absent**, **OD**, or **Leave**. The screen automatically advances to the next roll number. Use **Previous** to correct an earlier student. Keyboard shortcuts are `1` Present, `2` Absent, `3` OD, and `4` Leave. The save button stays disabled until every student in the selected roster/range has a status. Attendance is saved only when the user confirms the final summary.

The server also rejects missing/invalid statuses rather than silently treating unmarked students as Present.


## Department/class subjects and timed event announcements
- Subjects now support a class scope: all classes in a department or one particular class. Staff attendance lists only show subjects assigned to their department and class. Existing subjects migrate as department-wide (`*`).
- Staff and the dean can publish events with a start and end date/time and target all students, one department, or one class. Staff targeting is server-validated: they can only target their assigned class/department, or all students.
- Event announcements are automatically deleted after their end date/time on subsequent app requests; students only see events targeted to their department/class or all students.
- Back up `attendancepro.db` before updating. Database migrations add the new subject scope and event fields automatically.


## Staff attendance across all classes
- Staff can choose any configured department and class from the attendance screen. The roster and subject list reload for that selection; only subjects assigned to the chosen department/class (or department-wide subjects) are offered.
- The server validates the selected class and subject on every attendance save, and writes records only for active students in that selected class. Staff still only have Attendance and Announcements in their navigation.

## Student forgotten-password recovery
- Students can open **Forgot student password?** on the login page and submit their student ID plus registered email. This only creates an admin-reviewed request; it does not reset a password based on ID/email alone.
- Admin opens **Password reset requests**, verifies the student's identity using an approved college channel, then issues a one-time temporary password. The temporary password is shown once in the admin success message and must be delivered privately after identity verification.
- The student signs in using the temporary password and is forced to set a new password (12+ characters with uppercase, lowercase, number, and symbol) before accessing the app. Students who remember their current password can change it in My Profile.
- Reset request approval is audited. Do not send temporary passwords in public groups or expose them in screenshots. Configure verified email OTP delivery before offering unattended self-service password resets.
