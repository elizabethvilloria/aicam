from flask import Flask, jsonify, render_template, request, session, redirect, url_for, flash
import json
import datetime
from collections import defaultdict
import os
import hashlib

app = Flask(__name__)
app.secret_key = 'etrike-secret-key-change-this'  # Change this to a random string

# Simple authentication (in production, use proper user database)
USERS = {
    'admin': hashlib.sha256('1010'.encode()).hexdigest()
}

LOG_DIR = "logs"
HISTORICAL_FILE = "historical_summary.json"

def get_latest_log_time():
    """Finds the timestamp of the most recent log entry."""
    latest_time = None
    latest_timestamp = 0

    if not os.path.exists(LOG_DIR):
        return datetime.datetime.now()

    for year_dir in os.listdir(LOG_DIR):
        year_path = os.path.join(LOG_DIR, year_dir)
        if not os.path.isdir(year_path): continue
        for month_dir in os.listdir(year_path):
            month_path = os.path.join(year_path, month_dir)
            if not os.path.isdir(month_path): continue
            for day_file in os.listdir(month_path):
                if day_file.endswith('.json'):
                    try:
                        day_date = datetime.datetime(int(year_dir), int(month_dir), int(day_file.split('.')[0]))
                        if latest_time is None or day_date.date() > latest_time.date():
                            log_path = os.path.join(month_path, day_file)
                            with open(log_path, 'r') as f:
                                log_data = json.load(f)
                                if not log_data: continue
                                # Find the max timestamp in the latest day's file
                                file_max_ts = max(entry.get('entry_timestamp', 0) for entry in log_data)
                                if file_max_ts > latest_timestamp:
                                    latest_timestamp = file_max_ts
                                    latest_time = day_date

                    except (ValueError, json.JSONDecodeError):
                        continue
    
    if latest_timestamp > 0:
        return datetime.datetime.fromtimestamp(latest_timestamp)
    
    return datetime.datetime.now()


def update_historical_summary():
    """
    Updates the historical summary with current data.
    This function now runs every time and provides real-time historical data.
    """
    today = datetime.datetime.now()
    
    # Ensure historical file exists
    if not os.path.exists(HISTORICAL_FILE):
        with open(HISTORICAL_FILE, 'w') as f:
            json.dump({"daily": [], "weekly": [], "monthly": [], "last_run": today.isoformat()}, f, indent=4)

    # Always update with current data
    daily_data = []
    weekly_data = []
    monthly_data = []
    
    # Get daily data for the last 7 days
    for i in range(7):
        check_date = today.date() - datetime.timedelta(days=i)
        log_path = os.path.join(LOG_DIR, str(check_date.year), str(check_date.month), f"{check_date.day}.json")
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r') as log_file:
                    log_data = json.load(log_file)
                    daily_total = len(log_data)
                    if daily_total > 0:
                        daily_data.append({
                            "date": check_date.strftime("%Y-%m-%d"),
                            "total": daily_total
                        })
            except (json.JSONDecodeError, FileNotFoundError):
                continue
    
    # Get weekly data (current week and last week)
    for week_offset in range(2):
        week_start = today.date() - datetime.timedelta(days=today.weekday() + (week_offset * 7))
        weekly_total = 0
        for i in range(7):
            check_date = week_start + datetime.timedelta(days=i)
            log_path = os.path.join(LOG_DIR, str(check_date.year), str(check_date.month), f"{check_date.day}.json")
            if os.path.exists(log_path):
                try:
                    with open(log_path, 'r') as log_file:
                        log_data = json.load(log_file)
                        weekly_total += len(log_data)
                except (json.JSONDecodeError, FileNotFoundError):
                    continue
        
        if weekly_total > 0:
            weekly_data.append({
                "week_of": week_start.strftime("%Y-%m-%d"),
                "total": weekly_total
            })
    
    # Get monthly data (current month and last month)
    for month_offset in range(2):
        if month_offset == 0:
            # Current month
            month_start = today.replace(day=1)
            month_total = 0
            current_day = month_start
            while current_day.month == month_start.month:
                log_path = os.path.join(LOG_DIR, str(current_day.year), str(current_day.month), f"{current_day.day}.json")
                if os.path.exists(log_path):
                    try:
                        with open(log_path, 'r') as log_file:
                            log_data = json.load(log_file)
                            month_total += len(log_data)
                    except (json.JSONDecodeError, FileNotFoundError):
                        pass
                current_day += datetime.timedelta(days=1)
            
            if month_total > 0:
                monthly_data.append({
                    "month_of": month_start.strftime("%Y-%m"),
                    "total": month_total
                })
        else:
            # Last month
            last_month = today.replace(day=1) - datetime.timedelta(days=1)
            month_start = last_month.replace(day=1)
            month_total = 0
            current_day = month_start
            while current_day.month == month_start.month:
                log_path = os.path.join(LOG_DIR, str(current_day.year), str(current_day.month), f"{current_day.day}.json")
                if os.path.exists(log_path):
                    try:
                        with open(log_path, 'r') as log_file:
                            log_data = json.load(log_file)
                            month_total += len(log_data)
                    except (json.JSONDecodeError, FileNotFoundError):
                        pass
                current_day += datetime.timedelta(days=1)
            
            if month_total > 0:
                monthly_data.append({
                    "month_of": month_start.strftime("%Y-%m"),
                    "total": month_total
                })
    
    # Save updated data
    summary_data = {
        "daily": daily_data,
        "weekly": weekly_data,
        "monthly": monthly_data,
        "last_run": today.isoformat()
    }
    
    with open(HISTORICAL_FILE, 'w') as f:
        json.dump(summary_data, f, indent=4)


def get_passenger_counts():
    """Calculates passenger counts for different time periods."""
    now = get_latest_log_time()
    counts = defaultdict(int) # Simple defaultdict for totals

    # Hourly and Daily
    today_log_path = os.path.join(LOG_DIR, str(now.year), str(now.month), f"{now.day}.json")
    if os.path.exists(today_log_path):
        with open(today_log_path, 'r') as f:
            try:
                log_data = json.load(f)
                # Daily count
                counts['daily'] = len(log_data)
                
                # Hourly count (rolling)
                hourly_count = 0
                for entry in log_data:
                    entry_time = datetime.datetime.fromtimestamp(entry['entry_timestamp'])
                    if (now - entry_time).total_seconds() <= 3600:
                        hourly_count += 1
                counts['hourly'] = hourly_count
                        
            except json.JSONDecodeError:
                pass

    # Weekly
    start_of_week = now - datetime.timedelta(days=now.weekday())
    weekly_total = 0
    for i in range(7):
        current_day = start_of_week + datetime.timedelta(days=i)
        week_log_path = os.path.join(LOG_DIR, str(current_day.year), str(current_day.month), f"{current_day.day}.json")
        if os.path.exists(week_log_path):
            with open(week_log_path, 'r') as f:
                try:
                    log_data = json.load(f)
                    weekly_total += len(log_data)
                except json.JSONDecodeError:
                    pass
    counts['weekly'] = weekly_total
    
    # Monthly
    month_log_dir = os.path.join(LOG_DIR, str(now.year), str(now.month))
    monthly_total = 0
    if os.path.exists(month_log_dir):
        for day_file in os.listdir(month_log_dir):
            if day_file.endswith('.json'):
                day_path = os.path.join(month_log_dir, day_file)
                with open(day_path, 'r') as f:
                    try:
                        log_data = json.load(f)
                        monthly_total += len(log_data)
                    except json.JSONDecodeError:
                        pass
    counts['monthly'] = monthly_total

    return dict(counts)

def login_required(f):
    """Decorator to require login for routes"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if username in USERS and USERS[username] == password_hash:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials')
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>E-Trike Dashboard Login</title>
        <style>
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: linear-gradient(135deg, #059669, #0d9488, #0891b2); 
                display: flex; justify-content: center; align-items: center; 
                height: 100vh; margin: 0; 
            }
            .login-box { 
                background: rgba(255, 255, 255, 0.95); 
                padding: 3rem 2.5rem; 
                border-radius: 20px; 
                box-shadow: 0 15px 35px rgba(0,0,0,0.2); 
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.3);
                min-width: 350px;
            }
            .logo {
                text-align: center;
                margin-bottom: 2rem;
            }
            .logo h1 {
                color: #059669;
                font-size: 2rem;
                font-weight: 700;
                margin: 0;
                text-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .logo p {
                color: #0d9488;
                font-size: 0.9rem;
                margin: 0.5rem 0 0 0;
                font-weight: 500;
            }
            input { 
                width: 100%; 
                padding: 1rem; 
                margin: 0.75rem 0; 
                border: 2px solid #e5e7eb; 
                border-radius: 10px; 
                font-size: 1rem;
                transition: border-color 0.3s ease;
                box-sizing: border-box;
            }
            input:focus {
                outline: none;
                border-color: #059669;
                box-shadow: 0 0 0 3px rgba(5, 150, 105, 0.1);
            }
            button { 
                width: 100%; 
                padding: 1rem; 
                background: linear-gradient(135deg, #059669, #0d9488); 
                color: white; 
                border: none; 
                border-radius: 10px; 
                cursor: pointer; 
                font-size: 1rem;
                font-weight: 600;
                margin-top: 1rem;
                transition: all 0.3s ease;
            }
            button:hover { 
                background: linear-gradient(135deg, #047857, #0f766e); 
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(5, 150, 105, 0.3);
            }
            .error { 
                color: #dc2626; 
                margin: 1rem 0; 
                padding: 0.75rem;
                background: rgba(220, 38, 38, 0.1);
                border-radius: 8px;
                text-align: center;
                font-weight: 500;
            }
        </style>
    </head>
    <body>
        <div class="login-box">
            <div class="logo">
                <h1>E-Trike</h1>
                <p>Passenger Dashboard</p>
            </div>
            <form method="POST">
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Access Dashboard</button>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # Check if user has completed selection
    if 'selection_completed' not in session:
        return redirect(url_for('selection'))
    
    update_historical_summary()
    return render_template('index.html')

@app.route('/options')
@login_required
def options():
    # Check if user has completed selection
    if 'selection_completed' not in session:
        return redirect(url_for('selection'))
    
    return render_template('options.html')

@app.route('/selection')
@login_required
def selection():
    # If selection is already completed, redirect to dashboard
    if 'selection_completed' in session:
        return redirect(url_for('index'))
    return render_template('selection.html')

@app.route('/process-selection', methods=['POST'])
@login_required
def process_selection():
    city = request.form.get('city')
    
    if not city:
        flash('Please select a city')
        return redirect(url_for('selection'))
    
    # Store city selection in session
    session['city'] = city
    session['selection_completed'] = True
    
    return redirect(url_for('index'))

@app.route('/clear-selection', methods=['POST'])
@login_required
def clear_selection():
    # Clear selection from session
    session.pop('city', None)
    session.pop('selection_completed', None)
    return jsonify({'success': True})

@app.route('/get-todas')
@login_required
def get_todas():
    """Get available TODAs for the selected city"""
    city = session.get('city', 'manila')
    
    # Mock data - in real implementation, this would come from a database
    if city == 'manila':
        todas = [
            {'id': 'bltmpc', 'name': 'BLTMPC', 'full_name': 'Barangay Laging Tapat Motorcycle and Pedicab Cooperative'},
            {'id': 'mtmpc', 'name': 'MTMPC', 'full_name': 'Manila Tricycle and Motorcycle Operators Cooperative'},
            {'id': 'stmpc', 'name': 'STMPC', 'full_name': 'San Miguel Tricycle and Motorcycle Operators Cooperative'}
        ]
    else:
        todas = []
    
    return jsonify({'todas': todas})

@app.route('/get-etrikes')
@login_required
def get_etrikes():
    """Get available e-trikes for the selected TODA"""
    toda = request.args.get('toda', '')
    city = session.get('city', 'manila')
    
    if not toda:
        return jsonify({'etikes': []})
    
    # Mock data - in real implementation, this would come from a database
    if toda == 'bltmpc':
        etikes = [
            {'id': '00001', 'name': 'E-Trike 00001', 'status': 'active'},
            {'id': '00002', 'name': 'E-Trike 00002', 'status': 'active'},
            {'id': '00003', 'name': 'E-Trike 00003', 'status': 'maintenance'}
        ]
    elif toda == 'mtmpc':
        etikes = [
            {'id': '00004', 'name': 'E-Trike 00004', 'status': 'active'},
            {'id': '00005', 'name': 'E-Trike 00005', 'status': 'active'}
        ]
    else:
        etikes = []
    
    return jsonify({'etikes': etikes})

# Pi Registration System
@app.route('/pi-registration')
@login_required
def pi_registration():
    """Pi registration page"""
    return render_template('pi_registration.html')

@app.route('/register-pi', methods=['POST'])
@login_required
def register_pi():
    """Register a new Pi device"""
    pi_id = request.form.get('pi_id')
    toda_id = request.form.get('toda_id')
    etrike_id = request.form.get('etrike_id')
    city = request.form.get('city')
    location = request.form.get('location', '')
    
    if not all([pi_id, toda_id, etrike_id, city]):
        return jsonify({'success': False, 'message': 'All fields are required'})
    
    # Store Pi registration in a simple JSON file
    pi_assignments = load_pi_assignments()
    pi_assignments[pi_id] = {
        'toda_id': toda_id,
        'etrike_id': etrike_id,
        'city': city,
        'location': location,
        'status': 'active',
        'registered_at': datetime.datetime.now().isoformat(),
        'last_seen': None
    }
    save_pi_assignments(pi_assignments)
    
    return jsonify({
        'success': True, 
        'message': f'Pi {pi_id} registered successfully for {toda_id.upper()} - {etrike_id}'
    })

@app.route('/get-pi-assignments')
@login_required
def get_pi_assignments():
    """Get all Pi device assignments"""
    return jsonify(load_pi_assignments())

@app.route('/get-filtered-data')
@login_required
def get_filtered_data_route():
    """Get filtered passenger data based on selection"""
    toda_id = request.args.get('toda_id', '')
    etrike_id = request.args.get('etrike_id', '')
    pi_id = request.args.get('pi_id', '')
    
    # Convert empty strings to None for filtering
    if not toda_id:
        toda_id = None
    if not etrike_id:
        etrike_id = None
    if not pi_id:
        pi_id = None
    
    filtered_data = get_filtered_data(toda_id, etrike_id, pi_id)
    
    # Count by type
    adult_count = len([entry for entry in filtered_data if entry.get('type') == 'Adult'])
    child_count = len([entry for entry in filtered_data if entry.get('type') == 'Child'])
    total_count = len(filtered_data)
    
    return jsonify({
        'total': total_count,
        'adults': adult_count,
        'children': child_count,
        'filtered_data': filtered_data
    })

def load_pi_assignments():
    """Load Pi assignments from JSON file"""
    try:
        if os.path.exists('pi_assignments.json'):
            with open('pi_assignments.json', 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        pass
    return {}

def save_pi_assignments(assignments):
    """Save Pi assignments to JSON file"""
    with open('pi_assignments.json', 'w') as f:
        json.dump(assignments, f, indent=4)

def get_filtered_data(toda_id=None, etrike_id=None, pi_id=None):
    """
    Get filtered passenger data based on TODA, E-Trike, or Pi device selection.
    Returns data that matches the filter criteria.
    """
    today = datetime.datetime.now()
    filtered_data = []
    
    # Get data for the last 7 days
    for i in range(7):
        check_date = today.date() - datetime.timedelta(days=i)
        log_path = os.path.join(LOG_DIR, str(check_date.year), str(check_date.month), f"{check_date.day}.json")
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r') as f:
                    log_data = json.load(f)
                    for entry in log_data:
                        # Check if entry matches filter criteria
                        matches_filter = True
                        
                        if toda_id and entry.get('toda_id') != toda_id:
                            matches_filter = False
                        if etrike_id and entry.get('etrike_id') != etrike_id:
                            matches_filter = False
                        if pi_id and entry.get('pi_id') != pi_id:
                            matches_filter = False
                        
                        if matches_filter:
                            filtered_data.append(entry)
            except (json.JSONDecodeError, FileNotFoundError):
                continue
    
    return filtered_data

@app.route('/data')
@login_required
def data():
    return jsonify(get_passenger_counts())

@app.route('/historical-data')
@login_required
def historical_data():
    # Always update historical data when requested
    update_historical_summary()
    if not os.path.exists(HISTORICAL_FILE):
        return jsonify({"daily": [], "weekly": [], "monthly": []})
    with open(HISTORICAL_FILE, 'r') as f:
        return jsonify(json.load(f))

@app.route('/passenger-details')
@login_required
def passenger_details():
    """Get individual passenger records for a specific date."""
    date = request.args.get('date')
    period = request.args.get('period', 'daily')
    
    if not date:
        return jsonify({'error': 'Date parameter required'}), 400
    
    try:
        # Parse the date
        if period == 'daily':
            target_date = datetime.datetime.strptime(date, '%Y-%m-%d')
            log_file = os.path.join(LOG_DIR, str(target_date.year), str(target_date.month), f"{target_date.day}.json")
            
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    passengers = json.load(f)
                    return jsonify({'passengers': passengers})
            else:
                return jsonify({'passengers': []})
                
        elif period == 'weekly':
            # For weekly, we need to get all days in that week
            target_date = datetime.datetime.strptime(date, '%Y-%m-%d')
            start_of_week = target_date - datetime.timedelta(days=target_date.weekday())
            all_passengers = []
            
            for i in range(7):
                day = start_of_week + datetime.timedelta(days=i)
                log_file = os.path.join(LOG_DIR, str(day.year), str(day.month), f"{day.day}.json")
                if os.path.exists(log_file):
                    with open(log_file, 'r') as f:
                        day_passengers = json.load(f)
                        all_passengers.extend(day_passengers)
            
            return jsonify({'passengers': all_passengers})
            
        elif period == 'monthly':
            # For monthly, get all days in that month
            target_date = datetime.datetime.strptime(date, '%Y-%m')
            month_dir = os.path.join(LOG_DIR, str(target_date.year), str(target_date.month))
            all_passengers = []
            
            if os.path.exists(month_dir):
                for day_file in os.listdir(month_dir):
                    if day_file.endswith('.json'):
                        day_path = os.path.join(month_dir, day_file)
                        with open(day_path, 'r') as f:
                            day_passengers = json.load(f)
                            all_passengers.extend(day_passengers)
            
            return jsonify({'passengers': all_passengers})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    return jsonify({'passengers': []})

@app.route('/upload-data', methods=['POST'])
def upload_data():
    """Receive data package from Raspberry Pi"""
    try:
        if 'data_package' not in request.files:
            return jsonify({'error': 'No data package provided'}), 400
        
        file = request.files['data_package']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file and file.filename.endswith('.zip'):
            # Save the uploaded zip file temporarily
            import tempfile
            import zipfile
            
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                file.save(temp_file.name)
                
                # Extract the zip file
                with zipfile.ZipFile(temp_file.name, 'r') as zip_ref:
                    # Extract all files to current directory
                    zip_ref.extractall('.')
                
                # Clean up temp file
                os.remove(temp_file.name)
            
            print(f"✅ Data package received and extracted at {datetime.datetime.now()}")
            return jsonify({'message': 'Data uploaded successfully'}), 200
        
        return jsonify({'error': 'Invalid file format'}), 400
        
    except Exception as e:
        print(f"❌ Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown():
    shutdown_server = request.environ.get('werkzeug.server.shutdown')
    if shutdown_server is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    shutdown_server()
    return 'Server shutting down...'

if __name__ == '__main__':
    import ssl
    import os
    
    # Check if SSL certificates exist
    cert_path = '/etc/letsencrypt/live/etrikedashboard.com/fullchain.pem'
    key_path = '/etc/letsencrypt/live/etrikedashboard.com/privkey.pem'
    
    try:
        # Try HTTPS first
        if os.path.exists(cert_path) and os.path.exists(key_path):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS)  # Use TLS instead of TLSv1_2
            context.load_cert_chain(cert_path, key_path)
            print("Dashboard is running on https://etrikedashboard.com:5001/")
            app.run(debug=True, host='0.0.0.0', port=5001, ssl_context=context)
        else:
            # Fall back to HTTP
            print("Dashboard is running on http://0.0.0.0:5001/")
            app.run(debug=True, host='0.0.0.0', port=5001)
    except Exception as e:
        print(f"SSL Error: {e}")
        print("Falling back to HTTP mode...")
        app.run(debug=True, host='0.0.0.0', port=5001) 