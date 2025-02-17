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
ADMIN_PASSWORD_HASH = hashlib.sha256("password".encode('utf-8')).hexdigest()

# --- List of Admin Phone Numbers ---
ADMIN_PHONES = ["5414154332", "0987654321"]  # Replace with actual admin phone numbers

def authenticate_admin(username, password):
    if username == ADMIN_USERNAME:
        if hashlib.sha256(password.encode('utf-8')).hexdigest() == ADMIN_PASSWORD_HASH:
            return True
    return False

# --- Helper Functions ---

def calculate_rubies(last_login_str, streak):
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
        rubies_earned, new_streak = calculate_rubies(member['last_login'], member['streak'])
        cur.execute("UPDATE members SET last_login = ?, streak = ?, rubies = rubies + ? WHERE id = ?",
                    (datetime.date.today().isoformat(), new_streak, rubies_earned, member['id']))

        cur.execute("INSERT INTO signins (member_id, timestamp) VALUES (?, ?)",
                    (member['id'], datetime.datetime.now().isoformat()))

        db.commit()
        db.close()

        session['member_id'] = member['id']  # Store member ID
        session['rubies_earned'] = rubies_earned
        session.modified = True #Very important!

        return redirect(url_for('home'))
    else:
        db.close()
        flash('No matching account found. Please sign up.', 'error')
        return redirect(url_for('index'))

@app.route('/home')
def home():
    member_id = session.get('member_id') # Use get
    rubies_earned = session.pop('rubies_earned', 0) # Use get


    if not member_id:  # If no member ID, they haven't checked in
        return redirect(url_for('index'))

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM members WHERE id = ?", (member_id,)) # Get info by ID
    member = cur.fetchone()
    db.close()
    if not member: # Added: Handle the case where a user logs out, then uses back button.
        session.pop('member_id', None)  # Clear potentially stale session data
        flash("Your session has expired. Please check in again.")
        return redirect(url_for('index'))

    first_name = member['name'].split()[0]
    is_admin = member['phone'] in ADMIN_PHONES # Use ID to check if admin


    return render_template('home.html', member=member, rubies_earned=rubies_earned, is_admin=is_admin, first_name=first_name)



@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if authenticate_admin(username, password):
            session['admin_logged_in'] = True
            session['admin_username'] = username
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

    # --- Member Search ---
    search_query = request.args.get('search', '')
    if search_query:
        cur.execute("""
            SELECT * FROM members
            WHERE name LIKE ? OR email LIKE ? OR phone LIKE ?
        """, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        cur.execute("SELECT * FROM members")
    members = cur.fetchall()

    # --- Pagination and Sign-in History with Filtering ---
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')

    query = """
        SELECT signins.timestamp, members.name, members.id
        FROM signins
        INNER JOIN members ON signins.member_id = members.id
    """
    params = []

    where_clauses = []
    if from_date_str:
        try:
            from_date = datetime.date.fromisoformat(from_date_str)
            where_clauses.append("signins.timestamp >= ?")
            params.append(from_date_str)
        except ValueError:
            flash("Invalid 'from' date format.  Use YYYY-MM-DD.", "error")

    if to_date_str:
        try:
            to_date = datetime.date.fromisoformat(to_date_str)
            where_clauses.append("signins.timestamp <= ?")
            params.append(to_date_str + " 23:59:59")  # Include the whole day
        except ValueError:
            flash("Invalid 'to' date format.  Use YYYY-MM-DD.", "error")

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY signins.timestamp DESC"

    count_query = "SELECT COUNT(*) FROM (" + query + ") AS subquery"
    cur.execute(count_query, params)
    total_signins = cur.fetchone()[0]
    total_pages = (total_signins + per_page - 1) // per_page

    query += " LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    cur.execute(query, params)
    signins = cur.fetchall()


    redemptions_page = request.args.get('redemptions_page', 1, type=int)
    redemptions_per_page = 10
    redemptions_offset = (redemptions_page - 1) * redemptions_per_page

    redemptions_from_date_str = request.args.get('redemptions_from_date', '')
    redemptions_to_date_str = request.args.get('redemptions_to_date', '')

    redemptions_query = """
        SELECT redemptions.timestamp, members.name AS member_name, rewards.name AS reward_name, rewards.ruby_cost
        FROM redemptions
        INNER JOIN members ON redemptions.member_id = members.id
        INNER JOIN rewards ON redemptions.reward_id = rewards.id
    """
    redemptions_params = []

    redemptions_where_clauses = []
    if redemptions_from_date_str:
        try:
            datetime.date.fromisoformat(redemptions_from_date_str)
            redemptions_where_clauses.append("redemptions.timestamp >= ?")
            redemptions_params.append(redemptions_from_date_str)
        except ValueError:
            flash("Invalid 'from' date format for Redemptions. Use YYYY-MM-DD.", "error")

    if redemptions_to_date_str:
        try:
            datetime.date.fromisoformat(redemptions_to_date_str)
            redemptions_where_clauses.append("redemptions.timestamp <= ?")
            redemptions_params.append(redemptions_to_date_str + " 23:59:59")
        except ValueError:
            flash("Invalid 'to' date format for Redemptions. Use YYYY-MM-DD.", "error")

    if redemptions_where_clauses:
        redemptions_query += " WHERE " + " AND ".join(redemptions_where_clauses)

    redemptions_query += " ORDER BY redemptions.timestamp DESC"

    redemptions_count_query = "SELECT COUNT(*) FROM (" + redemptions_query + ") AS subquery"
    cur.execute(redemptions_count_query, redemptions_params)
    total_redemptions = cur.fetchone()[0]

    redemptions_query += " LIMIT ? OFFSET ?"
    redemptions_params.extend([redemptions_per_page, redemptions_offset])
    cur.execute(redemptions_query, redemptions_params)
    redemptions = cur.fetchall()

    redemptions_total_pages = (total_redemptions + redemptions_per_page - 1) // redemptions_per_page
    # --- End Redemptions ---

    # --- Calculate Statistics (Existing) ---
    today = datetime.date.today()
    one_month_ago = today - datetime.timedelta(days=30)
    one_day_ago = today - datetime.timedelta(days=1)

    cur.execute("SELECT COUNT(*) FROM members WHERE signup_date >= ?", (one_month_ago.isoformat(),))
    new_members_last_month = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM signins WHERE timestamp >= ?", (one_month_ago.isoformat(),))
    signins_last_month = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM signins WHERE timestamp >= ?", (one_day_ago.isoformat(),))
    signins_last_24_hours = cur.fetchone()[0]

    db.close()
    return render_template('admin_dashboard.html', members=members, signins=signins,
                           page=page, total_pages=total_pages,
                           new_members_last_month=new_members_last_month,
                           signins_last_month=signins_last_month,
                           signins_last_24_hours=signins_last_24_hours,
                           search_query=search_query,
                           from_date=from_date_str, to_date=to_date_str,
                           redemptions=redemptions, redemptions_page=redemptions_page, redemptions_total_pages=redemptions_total_pages,  # NEW
                           redemptions_from_date=redemptions_from_date_str, redemptions_to_date=redemptions_to_date_str)  # NEW

@app.route('/edit_rubies/<int:member_id>', methods=['GET', 'POST'])
def edit_rubies(member_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        # Get form data
        try:
            ruby_change = int(request.form['ruby_change'])  # Ensure it's an integer
        except ValueError:
            flash('Invalid ruby change amount. Please enter a valid integer.', 'error')
            cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
            member = cur.fetchone()
            cur.execute("""
                SELECT * FROM ruby_adjustments
                WHERE member_id = ?
                ORDER BY timestamp DESC
                LIMIT 5""", (member_id,))
            recent_adjustments = cur.fetchall()
            db.close()
            return render_template('edit_rubies.html', member=member, recent_adjustments = recent_adjustments)
        reason = request.form['reason']
        sign = int(request.form['sign']) # Get the sign from hidden input

        if not reason:  # Check for empty reason
            flash('Please provide a reason for the ruby adjustment.', 'error')
            cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
            member = cur.fetchone()
            cur.execute("""
                SELECT * FROM ruby_adjustments
                WHERE member_id = ?
                ORDER BY timestamp DESC
                LIMIT 5""", (member_id,))
            recent_adjustments = cur.fetchall()
            db.close()
            return render_template('edit_rubies.html', member=member, recent_adjustments = recent_adjustments)

        # Apply the sign to the ruby change
        ruby_change *= sign
        cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
        member = cur.fetchone()
        
        # --- Update Database ---
        # 1. Update member's ruby count
        cur.execute("UPDATE members SET rubies = rubies + ? WHERE id = ?", (ruby_change, member_id))

        # 2. Record the ruby adjustment
        cur.execute("""
            INSERT INTO ruby_adjustments (member_id, admin_user, amount, reason, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (member_id, session.get('admin_username', 'Unknown'), ruby_change, reason, datetime.datetime.now().isoformat()))
        
        cur.execute("""
                SELECT * FROM ruby_adjustments
                WHERE member_id = ?
                ORDER BY timestamp DESC
                LIMIT 5""", (member_id,))
        recent_adjustments = cur.fetchall()
            
        db.commit()
        db.close()

        flash(f'Ruby count updated by {ruby_change}!', 'success')
        session['rubies_earned'] = abs(ruby_change)  # Use absolute value for animation
        return render_template('edit_rubies.html', member=member, recent_adjustments=recent_adjustments)

    # --- GET request: Display the form ---
    cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    member = cur.fetchone()

    # --- Get recent ruby adjustments (for display) ---
    cur.execute("""
        SELECT * FROM ruby_adjustments
        WHERE member_id = ?
        ORDER BY timestamp DESC
        LIMIT 5""", (member_id,))  # Get last 5 adjustments
    recent_adjustments = cur.fetchall()

    db.close()

    if not member:
        flash('Member not found.', 'error')
        return redirect(url_for('admin_dashboard'))


    return render_template('edit_rubies.html', member=member, recent_adjustments=recent_adjustments)
 
@app.route('/my_rewards')
def my_rewards():
    member_id = session.get('member_id')
    if not member_id:
        flash('You must be checked in to view your rewards.', 'error')
        return redirect(url_for('index'))

    db = get_db()
    cur = db.cursor()

    # Get redemptions for the logged-in member, joining with rewards table
    cur.execute("""
        SELECT redemptions.timestamp, rewards.name, rewards.description, rewards.ruby_cost
        FROM redemptions
        INNER JOIN rewards ON redemptions.reward_id = rewards.id
        WHERE redemptions.member_id = ?
        ORDER BY redemptions.timestamp DESC
    """, (member_id,))
    redemptions = cur.fetchall()
    db.close()

    return render_template('my_rewards.html', redemptions=redemptions)   
    
@app.route('/admin/rewards')
def admin_rewards():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()

    # --- Pagination Logic ---
    page = request.args.get('page', 1, type=int)  # Get page from query string
    per_page = 2  #  Rewards per page (adjust as needed)
    offset = (page - 1) * per_page

    # Get total count of rewards
    cur.execute("SELECT COUNT(*) FROM rewards")
    total_rewards = cur.fetchone()[0]
    total_pages = (total_rewards + per_page - 1) // per_page

    # Fetch rewards for the current page
    cur.execute("SELECT * FROM rewards ORDER BY name LIMIT ? OFFSET ?", (per_page, offset))
    rewards = cur.fetchall()
    db.close()

    # Pass pagination variables to the template
    return render_template('admin/rewards.html', rewards=rewards, page=page, total_pages=total_pages)


@app.route('/admin/rewards/new', methods=['GET', 'POST'])
def new_reward():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        ruby_cost = request.form['ruby_cost']
        # --- Corrected Quantity Handling ---
        quantity_available_str = request.form.get('quantity_available')  # Get as string
        quantity_available = None  # Default to None
        if quantity_available_str:  # Check if it's NOT empty
            try:
                quantity_available = int(quantity_available_str)
                if quantity_available < 0:
                    raise ValueError("Quantity must be non-negative")
            except ValueError:
                flash('Invalid quantity. Please enter a non-negative integer or leave blank for unlimited.', 'error')
                return render_template('admin/reward_form.html', reward=None)

        image_path = request.form.get('image_path')
        active = 'active' in request.form

        if not name or not ruby_cost:
            flash('Name and Ruby Cost are required.', 'error')
            return render_template('admin/reward_form.html', reward=None)
        try:
            ruby_cost = int(ruby_cost)
            if ruby_cost < 1:
                raise ValueError("Ruby cost must be positive.")
        except ValueError as e:
            flash(f'Invalid input: {e}', 'error')
            return render_template('admin/reward_form.html', reward=None)

        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO rewards (name, description, ruby_cost, quantity_available, image_path, active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, description, ruby_cost, quantity_available, image_path, active))
        db.commit()
        db.close()

        flash('Reward created successfully!', 'success')
        return redirect(url_for('admin_rewards'))

    return render_template('admin/reward_form.html', reward=None)


@app.route('/admin/rewards/<int:reward_id>/edit', methods=['GET', 'POST'])
def edit_reward(reward_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        ruby_cost = request.form['ruby_cost']
         # --- Corrected Quantity Handling ---
        quantity_available_str = request.form.get('quantity_available')
        quantity_available = None  # Default to None
        if quantity_available_str:  # Check if NOT empty
            try:
                quantity_available = int(quantity_available_str)
                if quantity_available < 0:
                    raise ValueError("Quantity must be non-negative")
            except ValueError:
                flash('Invalid quantity.  Please enter a non-negative integer or leave blank for unlimited.', 'error')
                cur.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,))
                reward = cur.fetchone()
                db.close()
                return render_template('admin/reward_form.html', reward=reward)


        image_path = request.form.get('image_path')
        active = 'active' in request.form

        if not name or not ruby_cost:
            flash('Name and Ruby Cost are required.', 'error')
            cur.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,))
            reward = cur.fetchone()
            db.close()
            return render_template('admin/reward_form.html', reward=reward)
        try:
            ruby_cost = int(ruby_cost)
            if ruby_cost < 1:
                raise ValueError("Ruby cost must be positive")
        except ValueError as e:
            flash(f'Invalid input: {e}', 'error')
            cur.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,))
            reward = cur.fetchone()
            db.close()
            return render_template('admin/reward_form.html', reward=reward)

        cur.execute("""
            UPDATE rewards
            SET name = ?, description = ?, ruby_cost = ?, quantity_available = ?, image_path = ?, active = ?
            WHERE id = ?
        """, (name, description, ruby_cost, quantity_available, image_path, active, reward_id))
        db.commit()
        db.close()

        flash('Reward updated successfully!', 'success')
        return redirect(url_for('admin_rewards'))

    cur.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,))
    reward = cur.fetchone()
    db.close()

    if not reward:
        flash('Reward not found.', 'error')
        return redirect(url_for('admin_rewards'))

    return render_template('admin/reward_form.html', reward=reward)


@app.route('/admin/rewards/<int:reward_id>/delete', methods=['POST'])
def delete_reward(reward_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()
    # Optional, but good practice: Check if reward exists
    cur.execute("SELECT id FROM rewards WHERE id = ?", (reward_id,))
    if not cur.fetchone():
        db.close()
        flash('Reward not found.', 'error')
        return redirect(url_for('admin_rewards'))
    # Delete associated redemptions *first* (because of foreign key constraint)
    cur.execute("DELETE FROM redemptions WHERE reward_id = ?", (reward_id,))
    cur.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
    db.commit()
    db.close()
    flash('Reward deleted successfully!', 'success')
    return redirect(url_for('admin_rewards'))
    
@app.route('/rewards')
def rewards():
    # Get member_id from session, if logged in
    member_id = session.get('member_id')
    member = None

    db = get_db()
    cur = db.cursor()

    if member_id:
        cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
        member = cur.fetchone()

    # --- Pagination Logic ---
    page = request.args.get('page', 1, type=int)  # Get page number, default to 1
    per_page = 4  # Rewards per page.  Adjust as needed!
    offset = (page - 1) * per_page

    # Get total count of *active* rewards
    cur.execute("SELECT COUNT(*) FROM rewards WHERE active = TRUE")
    total_rewards = cur.fetchone()[0]
    total_pages = (total_rewards + per_page - 1) // per_page  # Integer division

    # Fetch rewards for the current page, only active ones
    cur.execute("SELECT * FROM rewards WHERE active = TRUE ORDER BY name LIMIT ? OFFSET ?", (per_page, offset))
    rewards = cur.fetchall()
    db.close()

    # Pass member, rewards, page, and total_pages to the template
    return render_template('rewards.html', rewards=rewards, member=member, page=page, total_pages=total_pages)


@app.route('/redeem_reward/<int:reward_id>', methods=['POST'])
def redeem_reward(reward_id):
    member_id = session.get('member_id')
    if not member_id:
        flash('You must be checked in to redeem a reward.', 'error')
        return redirect(url_for('index'))

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    member = cur.fetchone()

    if not member:
        session.pop('member_id',None)
        flash ("Your session has expired. Please check in again.", "error")
        return redirect(url_for('index'))

    cur.execute("SELECT * FROM rewards WHERE id = ? AND active = TRUE", (reward_id,))
    reward = cur.fetchone()

    if not reward:
        db.close()
        flash('Reward not found or is not available.', 'error')
        return redirect(url_for('rewards'))

    if member['rubies'] < reward['ruby_cost']:
        db.close()
        flash('You do not have enough rubies to redeem this reward.', 'error')
        return redirect(url_for('rewards'))
        
    if reward['quantity_available'] is not None and int(reward['quantity_available']) <= 0:
        db.close()
        flash('This reward is currently out of stock.', 'error')
        return redirect(url_for('rewards'))
    cur.execute("UPDATE members SET rubies = rubies - ? WHERE id = ?", (reward['ruby_cost'], member['id']))
    cur.execute("""
        INSERT INTO redemptions (member_id, reward_id, timestamp)
        VALUES (?, ?, ?)
    """, (member['id'], reward['id'], datetime.datetime.now().isoformat()))

    if reward['quantity_available'] is not None:
        cur.execute("UPDATE rewards SET quantity_available = quantity_available - 1 WHERE id = ?", (reward_id,))

    db.commit()
    db.close()

    flash(f'You have successfully redeemed: {reward["name"]}!', 'success')
    flash('show_confetti', 'confetti')
    session['reward_redeemed'] = reward['name']
    session['show_confetti'] = True  # Set a flag for the animation
    session['rubies_earned'] = reward['ruby_cost']
    session.modified = True #Ensure session is saved
    return redirect(url_for('rewards'))


@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
def edit_member(member_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        # Get form data
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        email_opt_in = 'email_opt_in' in request.form  # Checkbox: True if checked, False if not
        sms_opt_in = 'sms_opt_in' in request.form      # Checkbox

        # --- Input Validation ---
        if not all([name, phone, email]):
            flash('All fields are required.', 'error')
             # Important: Re-fetch member data *before* re-rendering
            cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
            member = cur.fetchone()
            db.close()
            return render_template('edit_member.html', member=member)

        if not is_valid_email(email):
            flash('Invalid email format.', 'error')
            cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
            member = cur.fetchone()
            db.close()
            return render_template('edit_member.html', member=member)

        cleaned_phone = clean_phone_number(phone)

        # Check if email/phone are already used by *another* member
        cur.execute("SELECT id FROM members WHERE (email = ? OR phone = ?) AND id != ?", (email, cleaned_phone, member_id))
        existing_user = cur.fetchone()
        if existing_user:
            flash('Another member is already using that email or phone number.', 'error')
            cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
            member = cur.fetchone()
            db.close()
            return render_template('edit_member.html', member=member)

        # --- Update Database ---
        cur.execute("""
            UPDATE members
            SET name = ?, phone = ?, email = ?, email_opt_in = ?, sms_opt_in = ?
            WHERE id = ?
        """, (name, cleaned_phone, email, email_opt_in, sms_opt_in, member_id))
        db.commit()
        db.close()

        flash('Member details updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))  # Redirect after successful update

    # --- GET request: Display the form ---
    cur.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    member = cur.fetchone()
    db.close()

    if not member:
        flash('Member not found.', 'error')  # Handle case where member doesn't exist
        return redirect(url_for('admin_dashboard'))

    return render_template('edit_member.html', member=member)  # Pass member data to the template


@app.route('/delete_member/<int:member_id>', methods=['POST'])
def delete_member(member_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    db = get_db()
    cur = db.cursor()

    # --- IMPORTANT: Foreign Key Constraint Handling ---
    # Delete associated sign-ins *first* to avoid foreign key constraint errors.
    cur.execute("DELETE FROM signins WHERE member_id = ?", (member_id,))

    # Now, delete the member.
    cur.execute("DELETE FROM members WHERE id = ?", (member_id,))
    db.commit()
    db.close()

    flash('Member deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))
    
@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_new_password = request.form['confirm_new_password']

        if not authenticate_admin(ADMIN_USERNAME, old_password):
            flash('Incorrect old password.', 'error')
            return render_template('change_password.html') 

        if new_password != confirm_new_password:
            flash('New passwords do not match.', 'error')
            return render_template('change_password.html')

        if len(new_password) < 8:  # Enforce minimum password length
            flash('New password must be at least 8 characters long.', 'error')
            return render_template('change_password.html')

        # --- Update Password (Hash it!) ---
        global ADMIN_PASSWORD_HASH  # Access the global variable
        ADMIN_PASSWORD_HASH = hashlib.sha256(new_password.encode('utf-8')).hexdigest()

        flash('Admin password changed successfully!', 'success')
        return redirect(url_for('admin_dashboard'))  

    return render_template('change_password.html') 

@app.route('/test_confetti')
def test_confetti():
    return render_template('confetti.html')
  
@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# --- Initialization ---

if not os.path.exists(DATABASE):
    init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)