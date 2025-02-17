from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import datetime
import os
import hashlib

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Database Setup ---
DATABASE = 'rockafairy.db'

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

# --- Admin Authentication (Basic) ---
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256("RockafairyAdmin123!".encode('utf-8')).hexdigest()

# --- List of Admin Phone Numbers ---
ADMIN_PHONES = ["5414154332", "0987654321"]  # Replace with actual admin phone numbers

def authenticate_admin(username, password):
    if username == ADMIN_USERNAME:
        if hashlib.sha256(password.encode('utf-8')).hexdigest() == ADMIN_PASSWORD_HASH:
            return True
    return False

# --- Helper Functions ---

def calculate_gems(last_login_str, streak):
    today = datetime.date.today()
    if last_login_str:
        last_login = datetime.date.fromisoformat(last_login_str)
        if last_login == today:
            return 0, streak
        elif last_login + datetime.timedelta(days=1) == today:
            streak = min(streak + 1, 10)
            return 10 + streak, streak
        else:
            return 10, 1
    else:
        return 10, 1

def clean_phone_number(phone):
    return ''.join(filter(str.isdigit, phone))

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        email_opt_in = 'email_opt_in' in request.form
        sms_opt_in = 'sms_opt_in' in request.form

        if not all([name, phone, email]):
            flash('All fields are required.', 'error')
            return render_template('signup.html')
        if not is_valid_email(email):
            flash('Invalid Email Format', 'error')
            return render_template('signup.html')

        cleaned_phone = clean_phone_number(phone)

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id FROM members WHERE email = ? OR phone = ?", (email, cleaned_phone))
        existing_user = cur.fetchone()
        if existing_user:
            flash('An account with this email or phone number already exists.', 'error')
            return render_template('signup.html')

        cur.execute("""
            INSERT INTO members (name, phone, email, email_opt_in, sms_opt_in)
            VALUES (?, ?, ?, ?, ?)
        """, (name, cleaned_phone, email, email_opt_in, sms_opt_in))
        db.commit()
        db.close()

        flash('Account created successfully! Please check in.', 'success')
        return redirect(url_for('index'))

    return render_template('signup.html')

def is_valid_email(email):
    import re
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

@app.route('/checkin', methods=['POST'])
def checkin():
    identifier = request.form['identifier']
    cleaned_identifier = clean_phone_number(identifier)

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM members WHERE email = ? OR phone = ?", (identifier, cleaned_identifier))
    member = cur.fetchone()

    if member:
        gems_earned, new_streak = calculate_gems(member['last_login'], member['streak'])
        cur.execute("UPDATE members SET last_login = ?, streak = ?, gems = gems + ? WHERE id = ?",
                    (datetime.date.today().isoformat(), new_streak, gems_earned, member['id']))

        cur.execute("INSERT INTO signins (member_id, timestamp) VALUES (?, ?)",
                    (member['id'], datetime.datetime.now().isoformat()))

        db.commit()
        db.close()

        session['member_name'] = member['name']
        session['member_phone'] = member['phone']
        session['gems_earned'] = gems_earned


        return redirect(url_for('home'))
    else:
        db.close()
        flash('No matching account found. Please sign up.', 'error')
        return redirect(url_for('index'))

@app.route('/home')
def home():
    member_name = session.pop('member_name', None)
    member_phone = session.pop('member_phone', None)
    gems_earned = session.pop('gems_earned', 0)


    if not member_name:
        return redirect(url_for('index'))
    first_name = member_name.split()[0]
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM members WHERE name = ?", (member_name,))
    member = cur.fetchone()
    db.close()

    is_admin = member_phone in ADMIN_PHONES

    return render_template('home.html', member=member, gems_earned=gems_earned, is_admin=is_admin, first_name=first_name)


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if authenticate_admin(username, password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials', 'error')
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM members")
    members = cur.fetchall()

    # --- Pagination Logic ---
    page = request.args.get('page', 1, type=int)  # Get page number from query parameters
    per_page = 10  # Number of sign-ins per page
    offset = (page - 1) * per_page

    # Get total count of sign-ins (for calculating total pages)
    cur.execute("SELECT COUNT(*) FROM signins")
    total_signins = cur.fetchone()[0]
    total_pages = (total_signins + per_page - 1) // per_page  # Integer division

    # Get sign-ins for the current page
    cur.execute("""
        SELECT signins.timestamp, members.name
        FROM signins
        INNER JOIN members ON signins.member_id = members.id
        ORDER BY signins.timestamp DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    signins = cur.fetchall()

    # --- Calculate Statistics ---
    today = datetime.date.today()
    one_month_ago = today - datetime.timedelta(days=30)
    one_day_ago = today - datetime.timedelta(days=1)

    # New Members in Last Month
    cur.execute("SELECT COUNT(*) FROM members WHERE signup_date >= ?", (one_month_ago.isoformat(),))  # Assuming you have a signup_date
    new_members_last_month = cur.fetchone()[0]

    # Sign-Ins in Last Month
    cur.execute("SELECT COUNT(*) FROM signins WHERE timestamp >= ?", (one_month_ago.isoformat(),))
    signins_last_month = cur.fetchone()[0]

    # Sign-Ins in Last 24 Hours
    cur.execute("SELECT COUNT(*) FROM signins WHERE timestamp >= ?", (one_day_ago.isoformat(),))
    signins_last_24_hours = cur.fetchone()[0]


    db.close()
    return render_template('admin_dashboard.html', members=members, signins=signins,
                           page=page, total_pages=total_pages,
                           new_members_last_month=new_members_last_month,  # Pass stats
                           signins_last_month=signins_last_month,
                           signins_last_24_hours=signins_last_24_hours)

@app.route('/edit_gems/<int:member_id>', methods=['GET', 'POST'])  # New route
def edit_gems(member_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        new_gems = request.form['gems']
        # Validate input (ensure it's an integer)
        try:
            new_gems = int(new_gems)
            cur.execute("UPDATE members SET gems = ? WHERE id = ?", (new_gems, member_id))
            db.commit()
            flash('Gem count updated successfully!', 'success')
            db.close()
            return redirect(url_for('admin_dashboard'))
        except ValueError:
            flash('Invalid gem count. Please enter a valid integer.', 'error')
            # *Don't* close the database connection here; we need it below
            # if the input is invalid.

    # GET request or failed validation:  Display the edit form.
    cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    member = cur.fetchone()
    db.close()

    if not member:
        flash('Member not found.', 'error')
        return redirect(url_for('admin_dashboard'))

    return render_template('edit_gems.html', member=member)


@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# --- Initialization ---

if not os.path.exists(DATABASE):
    init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)