import os, sqlite3, csv, io, secrets
from datetime import date, datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv('DATABASE_PATH', os.path.join(BASE_DIR, 'attendancepro.db'))
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or 'dev-only-change-this-secret-' + secrets.token_hex(12)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT UNIQUE, name TEXT NOT NULL,
 email TEXT UNIQUE, department TEXT DEFAULT 'ECE', year INTEGER DEFAULT 2, class_name TEXT DEFAULT 'A',
 role TEXT NOT NULL DEFAULT 'student', password_hash TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS departments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS subjects (
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 department TEXT DEFAULT 'ECE', year INTEGER DEFAULT 2, faculty TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS attendance (
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, attendance_date TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('Present','Absent','OD','Leave')), note TEXT DEFAULT '',
 marked_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(user_id, subject_id, attendance_date)
);
CREATE TABLE IF NOT EXISTS notices (
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL,
 audience TEXT NOT NULL DEFAULT 'all', created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT NOT NULL, details TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
'''

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(_=None):
    conn = g.pop('db', None)
    if conn is not None: conn.close()

def log_action(action, details=''):
    db().execute('INSERT INTO audit_logs(actor_id, action, details) VALUES(?,?,?)', (session.get('user_id'), action, details))
    db().commit()

def init_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(SCHEMA)
    # Safe migrations for databases created by earlier Nova builds.
    cols = {r[1] for r in conn.execute('PRAGMA table_info(users)').fetchall()}
    if 'class_name' not in cols: conn.execute("ALTER TABLE users ADD COLUMN class_name TEXT DEFAULT 'A'")
    for dep in ('ECE','CSE','EEE','IT','MECH','CIVIL','AI&DS'): conn.execute('INSERT OR IGNORE INTO departments(name) VALUES(?)',(dep,))
    if not conn.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone():
        conn.execute('INSERT INTO users(student_id,name,email,department,year,role,password_hash) VALUES(NULL,?,?,?,?,?,?)',
            ('Administrator', 'admin@attendancepro.local', 'Administration', 0, 'admin', generate_password_hash(os.getenv('ADMIN_PASSWORD','Admin@12345'))))
    if not conn.execute('SELECT id FROM users WHERE role="student" LIMIT 1').fetchone():
        conn.execute('INSERT INTO users(student_id,name,email,department,year,role,password_hash) VALUES(?,?,?,?,?,?,?)',
            ('STU0001','Demo Student','student@attendancepro.local','ECE',2,'student',generate_password_hash(os.getenv('DEMO_STUDENT_PASSWORD','Student@123'))))
    defaults = [('EC201','Electromagnetic Fields','ECE',2,'Dr. Kumar'),('EC202','Electronic Circuits','ECE',2,'Dr. Priya'),('MA201','Engineering Mathematics','ECE',2,'Dr. Anand'),('CS201','Python Programming','CSE',2,'Ms. Divya')]
    for item in defaults:
        conn.execute('INSERT OR IGNORE INTO subjects(code,name,department,year,faculty) VALUES(?,?,?,?,?)',item)
    conn.commit(); conn.close()

@app.before_request
def csrf_and_active_user():
    if 'csrf_token' not in session: session['csrf_token'] = secrets.token_urlsafe(24)
    if session.get('user_id'):
        g.current_user = db().execute('SELECT * FROM users WHERE id=? AND active=1', (session['user_id'],)).fetchone()
        if not g.current_user:
            session.clear()

@app.context_processor
def inject_globals():
    return {'csrf_token': session.get('csrf_token',''), 'current_user': getattr(g,'current_user',None), 'today': date.today().isoformat()}

@app.before_request
def csrf_protect():
    if request.method == 'POST':
        supplied = request.form.get('csrf_token','')
        if not supplied or not secrets.compare_digest(supplied, session.get('csrf_token','')):
            return 'Security token expired. Refresh the page and try again.', 400

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not getattr(g,'current_user',None): return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if g.current_user['role'] != 'admin':
            flash('Administrator access is required.','error'); return redirect(url_for('student_dashboard'))
        return fn(*args, **kwargs)
    return wrapped

@app.route('/')
def index():
    if getattr(g,'current_user',None):
        return redirect(url_for('admin_dashboard' if g.current_user['role']=='admin' else ('staff_dashboard' if g.current_user['role']=='staff' else 'student_dashboard')))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier','').strip()
        password = request.form.get('password','')
        user = db().execute('SELECT * FROM users WHERE active=1 AND (email=? OR student_id=?)', (identifier,identifier)).fetchone()
        if user and check_password_hash(user['password_hash'],password):
            session.clear(); session['user_id']=user['id']; session['csrf_token']=secrets.token_urlsafe(24)
            log_action('login', f"Successful login: {user['name']}")
            return redirect(url_for('admin_dashboard' if user['role']=='admin' else ('staff_dashboard' if user['role']=='staff' else 'student_dashboard')))
        flash('Invalid login details. Please try again.','error')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    log_action('logout','User logged out'); session.clear(); flash('You have been signed out.','success'); return redirect(url_for('login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn=db(); total_students=conn.execute("SELECT COUNT(*) FROM users WHERE role='student' AND active=1").fetchone()[0]
    total_subjects=conn.execute('SELECT COUNT(*) FROM subjects').fetchone()[0]
    today_total=conn.execute('SELECT COUNT(*) FROM attendance WHERE attendance_date=?',(date.today().isoformat(),)).fetchone()[0]
    present=conn.execute("SELECT COUNT(*) FROM attendance WHERE attendance_date=? AND status='Present'",(date.today().isoformat(),)).fetchone()[0]
    records=conn.execute('''SELECT a.*,u.name student_name,u.student_id,s.code subject_code,s.name subject_name FROM attendance a JOIN users u ON u.id=a.user_id JOIN subjects s ON s.id=a.subject_id ORDER BY attendance_date DESC,a.id DESC LIMIT 8''').fetchall()
    students=conn.execute("SELECT * FROM users WHERE role='student' ORDER BY created_at DESC LIMIT 5").fetchall()
    month=conn.execute("SELECT substr(attendance_date,1,7) m, COUNT(*) total, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) present FROM attendance WHERE attendance_date>=date('now','-5 months') GROUP BY m ORDER BY m").fetchall()
    return render_template('admin.html', total_students=total_students,total_subjects=total_subjects,today_total=today_total,present=present,records=records,students=students,month=month)

@app.route('/admin/students', methods=['GET','POST'])
@admin_required
def students_page():
    conn=db()
    if request.method=='POST':
        sid=request.form.get('student_id','').strip().upper(); name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); dept=request.form.get('department','ECE').strip(); year=request.form.get('year','2'); class_name=request.form.get('class_name','A').strip().upper(); password=request.form.get('password','Student@123')
        if not sid or not name or not email or len(password)<8:
            flash('Enter student ID, name, email, and a password of at least 8 characters.','error')
        else:
            try:
                conn.execute("INSERT INTO users(student_id,name,email,department,year,class_name,role,password_hash) VALUES(?,?,?,?,?,?,'student',?)",(sid,name,email,dept,int(year),class_name,generate_password_hash(password)))
                log_action('student_created',f'{sid} · {name}'); conn.commit(); flash(f'Student {sid} created successfully.','success')
            except sqlite3.IntegrityError: conn.rollback(); flash('Student ID or email already exists.','error')
        return redirect(url_for('students_page'))
    q=request.args.get('q','').strip()
    students=conn.execute("SELECT * FROM users WHERE role='student' AND (student_id LIKE ? OR name LIKE ? OR email LIKE ?) ORDER BY active DESC,name",(f'%{q}%',f'%{q}%',f'%{q}%')).fetchall()
    return render_template('students.html',students=students,q=q)

@app.route('/admin/students/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_student(user_id):
    user=db().execute("SELECT * FROM users WHERE id=? AND role='student'",(user_id,)).fetchone()
    if user:
        db().execute('UPDATE users SET active=? WHERE id=?',(0 if user['active'] else 1,user_id)); log_action('student_status_changed',user['student_id']); db().commit(); flash('Student status updated.','success')
    return redirect(url_for('students_page'))

@app.route('/admin/subjects', methods=['GET','POST'])
@admin_required
def subjects_page():
    conn=db()
    if request.method=='POST':
        code=request.form.get('code','').strip().upper(); name=request.form.get('name','').strip(); dept=request.form.get('department','ECE').strip(); year=request.form.get('year','2'); faculty=request.form.get('faculty','').strip()
        try:
            conn.execute('INSERT INTO subjects(code,name,department,year,faculty) VALUES(?,?,?,?,?)',(code,name,dept,int(year),faculty)); log_action('subject_created',f'{code} · {name}'); conn.commit(); flash('Subject created.','success')
        except (sqlite3.IntegrityError,ValueError): conn.rollback(); flash('Check the fields. Subject code must be unique.','error')
        return redirect(url_for('subjects_page'))
    subjects=conn.execute('SELECT s.*,COUNT(a.id) records FROM subjects s LEFT JOIN attendance a ON a.subject_id=s.id GROUP BY s.id ORDER BY s.department,s.code').fetchall()
    return render_template('subjects.html',subjects=subjects)

@app.route('/admin/attendance', methods=['GET','POST'])
@admin_required
def attendance_page():
    """Dean attendance workspace: select department/class/subject, then mark the whole roster."""
    conn = db()
    if request.method == 'POST':
        try:
            dept = request.form.get('department', '').strip()
            cls = request.form.get('class_name', '').strip()
            subject_id = int(request.form.get('subject_id', ''))
            dt = request.form.get('attendance_date', date.today().isoformat())
            datetime.strptime(dt, '%Y-%m-%d')
            if dt > date.today().isoformat(): raise ValueError('future date')
            subject = conn.execute('SELECT * FROM subjects WHERE id=? AND department=?', (subject_id, dept)).fetchone()
            if not dept or not cls or not subject: raise ValueError('class or subject')
            roster = conn.execute("SELECT id,student_id,name FROM users WHERE role='student' AND active=1 AND department=? AND class_name=? ORDER BY student_id COLLATE NOCASE", (dept, cls)).fetchall()
            if not roster: raise ValueError('empty class')
            allowed = {'Present', 'Absent', 'OD', 'Leave'}; counts = {status: 0 for status in allowed}
            for student in roster:
                status = request.form.get(f"status_{student['id']}", '')
                if status not in allowed: raise ValueError('status')
                note = request.form.get(f"note_{student['id']}", '').strip()[:250]
                conn.execute("""INSERT INTO attendance(user_id,subject_id,attendance_date,status,note,marked_by) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(user_id,subject_id,attendance_date) DO UPDATE SET status=excluded.status,note=excluded.note,marked_by=excluded.marked_by""",
                    (student['id'], subject_id, dt, status, note, g.current_user['id']))
                counts[status] += 1
            log_action('admin_class_attendance_saved', f'{dept}/{cls}, subject={subject_id}, date={dt}, counts={counts}')
            conn.commit()
            flash(f"Saved {len(roster)} students: {counts['Present']} present, {counts['Absent']} absent, {counts['OD']} OD, {counts['Leave']} leave.", 'success')
            return redirect(url_for('attendance_page', department=dept, class_name=cls, subject_id=subject_id, attendance_date=dt))
        except (ValueError, TypeError):
            conn.rollback(); flash('Please choose a valid department, class, subject and date. No attendance was saved.', 'error')
            return redirect(url_for('attendance_page'))
    departments = conn.execute("SELECT DISTINCT department FROM users WHERE role='student' AND active=1 AND department IS NOT NULL AND department<>'' ORDER BY department").fetchall()
    dept = request.args.get('department', (departments[0]['department'] if departments else '')).strip()
    classes = conn.execute("SELECT DISTINCT class_name FROM users WHERE role='student' AND active=1 AND department=? ORDER BY class_name", (dept,)).fetchall() if dept else []
    cls = request.args.get('class_name', (classes[0]['class_name'] if classes else '')).strip()
    subjects = conn.execute('SELECT * FROM subjects WHERE department=? ORDER BY code', (dept,)).fetchall() if dept else []
    selected_subject = request.args.get('subject_id', ''); dt = request.args.get('attendance_date', date.today().isoformat())
    try: datetime.strptime(dt, '%Y-%m-%d')
    except ValueError: dt = date.today().isoformat()
    roster = conn.execute("""SELECT u.id,u.student_id,u.name,a.status,a.note FROM users u
        LEFT JOIN attendance a ON a.user_id=u.id AND a.subject_id=? AND a.attendance_date=?
        WHERE u.role='student' AND u.active=1 AND u.department=? AND u.class_name=?
        ORDER BY u.student_id COLLATE NOCASE""", (int(selected_subject) if selected_subject.isdigit() else -1, dt, dept, cls)).fetchall() if dept and cls else []
    q = request.args.get('q', '').strip(); filter_date = request.args.get('date', '')
    sql = """SELECT a.*,u.name student_name,u.student_id,s.code subject_code,s.name subject_name,u.department,u.class_name FROM attendance a JOIN users u ON u.id=a.user_id JOIN subjects s ON s.id=a.subject_id WHERE (u.name LIKE ? OR u.student_id LIKE ? OR s.name LIKE ?)"""
    args = [f'%{q}%', f'%{q}%', f'%{q}%']
    if filter_date: sql += ' AND a.attendance_date=?'; args.append(filter_date)
    sql += ' ORDER BY a.attendance_date DESC,a.id DESC LIMIT 300'
    records = conn.execute(sql, args).fetchall()
    return render_template('attendance.html', students=roster, subjects=subjects, records=records, q=q, filter_date=filter_date,
        departments=departments, classes=classes, selected_department=dept, selected_class=cls, selected_subject=selected_subject, attendance_date=dt)


@app.route('/admin/staff', methods=['GET','POST'])
@admin_required
def staff_page():
    conn=db()
    if request.method=='POST':
        sid=request.form.get('staff_id','').strip().upper(); name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); dept=request.form.get('department','ECE').strip(); class_name=request.form.get('class_name','A').strip().upper(); password=request.form.get('password','')
        if not sid or not name or not email or len(password)<10:
            flash('Enter staff ID, name, email, and a password of at least 10 characters.','error')
        else:
            try:
                conn.execute("INSERT INTO users(student_id,name,email,department,class_name,role,password_hash) VALUES(?,?,?,?,?,'staff',?)",(sid,name,email,dept,class_name,generate_password_hash(password)))
                log_action('staff_created',f'{sid} · {name} · {dept}/{class_name}'); conn.commit(); flash(f'Staff account {sid} created.','success')
            except sqlite3.IntegrityError: conn.rollback(); flash('Staff ID or email already exists.','error')
        return redirect(url_for('staff_page'))
    staff=conn.execute("SELECT * FROM users WHERE role='staff' ORDER BY active DESC,name").fetchall()
    return render_template('staff.html',staff=staff)

@app.route('/admin/staff/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_staff(user_id):
    u=db().execute("SELECT * FROM users WHERE id=? AND role='staff'",(user_id,)).fetchone()
    if u:
        db().execute('UPDATE users SET active=? WHERE id=?',(0 if u['active'] else 1,user_id)); log_action('staff_status_changed',u['student_id']); db().commit(); flash('Staff access updated.','success')
    return redirect(url_for('staff_page'))

@app.route('/staff')
@login_required
def staff_dashboard():
    if g.current_user['role']=='admin': return redirect(url_for('admin_dashboard'))
    if g.current_user['role']!='staff': return redirect(url_for('student_dashboard'))
    conn=db(); dept=g.current_user['department']; cls=g.current_user['class_name'] or 'A'
    students=conn.execute("SELECT COUNT(*) FROM users WHERE role='student' AND active=1 AND department=? AND class_name=?",(dept,cls)).fetchone()[0]
    today_count=conn.execute("SELECT COUNT(*) FROM attendance a JOIN users u ON u.id=a.user_id WHERE a.attendance_date=? AND u.department=? AND u.class_name=?",(date.today().isoformat(),dept,cls)).fetchone()[0]
    return render_template('staff_dashboard.html',students=students,today_count=today_count)

@app.route('/staff/students', methods=['GET','POST'])
@login_required
def staff_students_page():
    if g.current_user['role']!='staff': return redirect(url_for('admin_dashboard' if g.current_user['role']=='admin' else 'student_dashboard'))
    conn=db(); dept=g.current_user['department']; cls=g.current_user['class_name'] or 'A'
    if request.method=='POST':
        sid=request.form.get('student_id','').strip().upper(); name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','Student@123')
        if not sid or not name or not email or len(password)<8: flash('Enter all fields and a password of at least 8 characters.','error')
        else:
            try:
                conn.execute("INSERT INTO users(student_id,name,email,department,year,class_name,role,password_hash) VALUES(?,?,?,?,?,?, 'student',?)",(sid,name,email,dept,g.current_user['year'] or 2,cls,generate_password_hash(password)))
                log_action('student_created_by_staff',f'{sid} · {dept}/{cls}'); conn.commit(); flash(f'Student {sid} added to {dept} / {cls}.','success')
            except sqlite3.IntegrityError: conn.rollback(); flash('Student ID or email already exists.','error')
        return redirect(url_for('staff_students_page'))
    students=conn.execute("SELECT * FROM users WHERE role='student' AND department=? AND class_name=? ORDER BY student_id",(dept,cls)).fetchall()
    return render_template('staff_students.html',students=students,department=dept,class_name=cls)

@app.route('/staff/attendance', methods=['GET','POST'])
@login_required
def staff_group_attendance():
    """Fast class roll-call with roll-number range and four explicit statuses."""
    if g.current_user['role']!='staff':
        return redirect(url_for('admin_dashboard' if g.current_user['role']=='admin' else 'student_dashboard'))
    conn=db(); dept=g.current_user['department']; cls=g.current_user['class_name'] or 'A'
    all_students=conn.execute("SELECT id,student_id,name FROM users WHERE role='student' AND active=1 AND department=? AND class_name=? ORDER BY student_id COLLATE NOCASE",(dept,cls)).fetchall()
    subjects=conn.execute('SELECT * FROM subjects WHERE department=? ORDER BY code',(dept,)).fetchall()
    allowed_statuses={'Present','Absent','OD','Leave'}
    if request.method=='POST':
        try:
            subject_id=int(request.form.get('subject_id',''))
            dt=request.form.get('attendance_date',date.today().isoformat())
            datetime.strptime(dt,'%Y-%m-%d')
            if dt > date.today().isoformat(): raise ValueError('future date')
            subject=conn.execute('SELECT * FROM subjects WHERE id=? AND department=?',(subject_id,dept)).fetchone()
            if not subject: raise ValueError('subject')
            start_roll=request.form.get('roll_start','').strip(); end_roll=request.form.get('roll_end','').strip()
            roster=[r for r in all_students if (not start_roll or r['student_id'].casefold() >= start_roll.casefold()) and (not end_roll or r['student_id'].casefold() <= end_roll.casefold())]
            if start_roll and end_roll and start_roll.casefold()>end_roll.casefold(): raise ValueError('range')
            if not roster: raise ValueError('empty roster')
            counts={status:0 for status in allowed_statuses}
            for r in roster:
                status=request.form.get(f"status_{r['id']}",'')
                if status not in allowed_statuses: raise ValueError('status')
                conn.execute("""INSERT INTO attendance(user_id,subject_id,attendance_date,status,marked_by) VALUES(?,?,?,?,?)
                    ON CONFLICT(user_id,subject_id,attendance_date) DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by""",
                    (r['id'],subject_id,dt,status,g.current_user['id']))
                counts[status]+=1
            log_action('group_attendance_saved',f'{dept}/{cls}, subject={subject_id}, date={dt}, range={start_roll or "FIRST"}-{end_roll or "LAST"}, counts={counts}')
            conn.commit()
            flash(f"Saved {len(roster)} records: {counts['Present']} present, {counts['Absent']} absent, {counts['OD']} OD, {counts['Leave']} leave.",'success')
        except (ValueError,TypeError):
            conn.rollback(); flash('Invalid subject, date, roll-number range or attendance status. No records were saved.','error')
        return redirect(url_for('staff_group_attendance',roll_start=request.form.get('roll_start',''),roll_end=request.form.get('roll_end',''),subject_id=request.form.get('subject_id','')))
    start_roll=request.args.get('roll_start','').strip(); end_roll=request.args.get('roll_end','').strip()
    students=[r for r in all_students if (not start_roll or r['student_id'].casefold() >= start_roll.casefold()) and (not end_roll or r['student_id'].casefold() <= end_roll.casefold())]
    selected_subject=request.args.get('subject_id','')
    return render_template('staff_attendance.html',students=students,all_students=all_students,subjects=subjects,department=dept,class_name=cls,roll_start=start_roll,roll_end=end_roll,selected_subject=selected_subject)

@app.route('/admin/notices', methods=['GET','POST'])
@admin_required
def notices_page():
    conn=db()
    if request.method=='POST':
        title=request.form.get('title','').strip(); body=request.form.get('body','').strip(); audience=request.form.get('audience','all')
        if title and body and audience in ('all','students'):
            conn.execute('INSERT INTO notices(title,body,audience,created_by) VALUES(?,?,?,?)',(title,body,audience,g.current_user['id'])); log_action('notice_created',title); conn.commit(); flash('Notice published.','success')
        else: flash('Enter a title and message.','error')
        return redirect(url_for('notices_page'))
    notices=conn.execute('SELECT n.*,u.name author FROM notices n LEFT JOIN users u ON u.id=n.created_by ORDER BY n.id DESC').fetchall()
    return render_template('notices.html',notices=notices)

@app.route('/admin/reports.csv')
@admin_required
def export_csv():
    rows=db().execute('''SELECT u.student_id,u.name,u.department,s.code,s.name,a.attendance_date,a.status,a.note FROM attendance a JOIN users u ON u.id=a.user_id JOIN subjects s ON s.id=a.subject_id ORDER BY a.attendance_date DESC''').fetchall()
    output=io.StringIO(); writer=csv.writer(output); writer.writerow(['Student ID','Student Name','Department','Subject Code','Subject','Date','Status','Note'])
    for r in rows: writer.writerow(list(r))
    response=make_response('\ufeff'+output.getvalue()); response.headers['Content-Type']='text/csv; charset=utf-8'; response.headers['Content-Disposition']='attachment; filename=attendancepro-report.csv'; return response

@app.route('/admin/audit')
@admin_required
def audit_page():
    logs=db().execute('SELECT l.*,u.name actor FROM audit_logs l LEFT JOIN users u ON u.id=l.actor_id ORDER BY l.id DESC LIMIT 200').fetchall()
    return render_template('audit.html',logs=logs)

@app.route('/student')
@login_required
def student_dashboard():
    if g.current_user['role']=='admin': return redirect(url_for('admin_dashboard'))
    if g.current_user['role']=='staff': return redirect(url_for('staff_dashboard'))
    conn=db(); user_id=g.current_user['id']
    totals=conn.execute("SELECT COUNT(*) total,SUM(CASE WHEN status IN ('Present','OD') THEN 1 ELSE 0 END) attended FROM attendance WHERE user_id=?",(user_id,)).fetchone()
    total=totals['total'] or 0; attended=totals['attended'] or 0; percentage=round(attended*100/total) if total else 0
    subjects=conn.execute('''SELECT s.id,s.code,s.name,s.faculty,COUNT(a.id) total,SUM(CASE WHEN a.status IN ('Present','OD') THEN 1 ELSE 0 END) attended FROM subjects s LEFT JOIN attendance a ON a.subject_id=s.id AND a.user_id=? GROUP BY s.id ORDER BY s.code''',(user_id,)).fetchall()
    history=conn.execute('''SELECT a.*,s.code subject_code,s.name subject_name FROM attendance a JOIN subjects s ON s.id=a.subject_id WHERE a.user_id=? ORDER BY attendance_date DESC,a.id DESC LIMIT 12''',(user_id,)).fetchall()
    notices=conn.execute("SELECT * FROM notices WHERE audience IN ('all','students') ORDER BY id DESC LIMIT 5").fetchall()
    return render_template('student.html',total=total,attended=attended,percentage=percentage,subjects=subjects,history=history,notices=notices)

@app.route('/student/profile', methods=['GET','POST'])
@login_required
def profile_page():
    if g.current_user['role']=='admin': return redirect(url_for('admin_dashboard'))
    if request.method=='POST':
        old=request.form.get('current_password',''); new=request.form.get('new_password','')
        if not check_password_hash(g.current_user['password_hash'],old): flash('Current password is incorrect.','error')
        elif len(new)<8: flash('New password must contain at least 8 characters.','error')
        else:
            db().execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(new),g.current_user['id'])); log_action('password_changed','Student changed password'); db().commit(); flash('Password changed successfully.','success')
        return redirect(url_for('profile_page'))
    return render_template('profile.html')

@app.errorhandler(404)
def not_found(_): return render_template('error.html',code=404,message='This page could not be found.'),404

if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=int(os.getenv('PORT','5000')), debug=os.getenv('FLASK_DEBUG','0')=='1')
