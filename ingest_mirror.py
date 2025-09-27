# ingest_mirror.py
import os, json, time, glob, uuid, datetime, requests

VERBOSE = os.getenv("MIRROR_VERBOSE", "0") == "1"

def vlog(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)

DASH_URL   = os.getenv("INGEST_URL", "https://etrikedashboard.com")
INGEST_KEY = os.getenv("INGEST_KEY", "")
DEVICE_ID  = os.getenv("PI_ID", "PI_CANARY_001")
STATE_PATH = os.getenv("INGEST_STATE", "ingest_state.json")
# Auto-detect logs directory - try common locations
def find_logs_dir():
    # First try environment variable
    env_log_root = os.getenv("LOG_ROOT")
    if env_log_root and os.path.exists(env_log_root):
        return env_log_root
    
    # Try common locations relative to current directory
    possible_paths = [
        "logs",  # logs in current directory
        "../logs",  # logs in parent directory
        "/home/pi/aicam/logs",  # original default
        f"/home/{os.getenv('USER', 'pi')}/Desktop/aicam/logs",  # user's Desktop
        f"/home/{os.getenv('USER', 'pi')}/aicam/logs",  # user's home
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # Fallback to environment variable or default
    return env_log_root or "/home/pi/aicam/logs"

LOG_ROOT = find_logs_dir()
print(f"[ingest-mirror] Using logs directory: {LOG_ROOT}")
BATCH_SIZE = int(os.getenv("INGEST_BATCH_SIZE", "50"))
INTERVAL_S = int(os.getenv("INGEST_INTERVAL", "5"))

def load_state():
    try:
        state = json.load(open(STATE_PATH, "r"))
        # Ensure sent_events key exists for backward compatibility
        if "sent_events" not in state:
            state["sent_events"] = {}
        return state
    except Exception:
        return {"last_seq": 0, "last_sent_timestamp": 0, "sent_events": {}}

def save_state(s):
    with open(STATE_PATH, "w") as f: json.dump(s, f)

def today_files():
    # Look for the most recent log file instead of just today's
    # First try today
    t = datetime.date.today()
    pattern = f"{LOG_ROOT}/{t.year}/{t.month}/{t.day}.json"
    files = glob.glob(pattern)
    
    # If no file for today, look for the most recent file in the last 7 days
    if not files:
        for days_back in range(1, 8):
            check_date = t - datetime.timedelta(days=days_back)
            pattern = f"{LOG_ROOT}/{check_date.year}/{check_date.month}/{check_date.day}.json"
            files = glob.glob(pattern)
            if files:
                vlog(f"[ingest-mirror] Found log file from {days_back} days ago: {files[0]}")
                break
    
    # If still no files, look for any .json file in the log directory
    if not files:
        pattern = f"{LOG_ROOT}/**/*.json"
        all_files = glob.glob(pattern, recursive=True)
        if all_files:
            # Sort by modification time and take the most recent
            all_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            files = [all_files[0]]
            vlog(f"[ingest-mirror] Using most recent log file: {files[0]}")
    
    return files

def read_entries():
    rows = []
    for fp in today_files():
        try:
            data = json.load(open(fp))
            if isinstance(data, list):
                rows.extend(data)
        except Exception:
            continue
    return rows

def build_events(rows, start_seq, last_sent_timestamp, sent_events):
    seq = start_seq
    events = []
    
    # Only process rows that haven't been sent yet
    for r in rows:
        person_id = r.get("person_id")
        entry_timestamp = r.get("entry_timestamp", 0)
        exit_timestamp = r.get("exit_timestamp")
        
        # Create event key for tracking
        event_key = f"{person_id}_{int(entry_timestamp)}"
        
        # Skip if this exact event was already sent AND data hasn't changed
        if event_key in sent_events:
            # Handle backward compatibility - old events stored as True
            event_data = sent_events[event_key]
            if isinstance(event_data, bool):
                # Old format - assume no exit data was sent
                had_exit = False
            else:
                # New format - check had_exit flag
                had_exit = event_data.get("had_exit", False)
            
            # Check if this is an update (has exit data when previously didn't)
            if exit_timestamp and not had_exit:
                print(f"[UPDATE] Person {person_id} - sending exit update (key: {event_key})")
                # Allow this update to be sent
            else:
                print(f"[SKIP] Person {person_id} event already sent (key: {event_key})")
                continue
        
        seq += 1
        evt_time = r.get("exit_timestamp") or entry_timestamp or time.time()
        
        # Create session ID matching dashboard format
        import hashlib
        session_key = f"{DEVICE_ID}-{r.get('person_id')}-{int(entry_timestamp)}"
        session_id = hashlib.md5(session_key.encode()).hexdigest()[:16]
        
        # Always send as PASSENGER event (complete trip data)
        event_type = "PASSENGER"
        
        # Enhanced logging for passenger events
        if r.get('exit_timestamp'):
            exit_timestamp = r.get('exit_timestamp')
            dwell_time_minutes = r.get('dwell_time_minutes', 0)
            print(f"👤 [PASSENGER] Person {r.get('person_id')} - Complete trip: {dwell_time_minutes:.2f} minutes")
            print(f"   Entry: {datetime.datetime.fromtimestamp(entry_timestamp).strftime('%H:%M:%S')}")
            print(f"   Exit:  {datetime.datetime.fromtimestamp(exit_timestamp).strftime('%H:%M:%S')}")
        else:
            print(f"👤 [PASSENGER] Person {r.get('person_id')} - Entry only at {datetime.datetime.fromtimestamp(entry_timestamp).strftime('%H:%M:%S')}")
        
        # DEBUG: Print what we're sending
        print(f"[DEBUG] Sending {event_type} {seq}: person_id={r.get('person_id')}, entry_timestamp={entry_timestamp}, exit_timestamp={r.get('exit_timestamp')}")
        print(f"[DEBUG] Full payload: {r}")
        
        events.append({
            "event_id": f"{DEVICE_ID}-{seq}-{uuid.uuid4().hex[:6]}",
            "device_id": DEVICE_ID,
            "seq": seq,
            "session_id": session_id,  # Consistent session ID
            "type": event_type,        # ENTRY or EXIT
            "event_time_utc": float(evt_time),
            "payload_json": r  # <- uses existing log shape
        })
        
        if len(events) >= BATCH_SIZE:
            break
    
    return events, seq

def run_once():
    state = load_state()
    last_seq = int(state.get("last_seq", 0))
    last_sent_timestamp = float(state.get("last_sent_timestamp", 0))
    sent_events = state.get("sent_events", {})
    rows = read_entries()
    if not rows:
        vlog("[ingest-mirror] no-rows")
        return "no-rows"
    events, new_seq = build_events(rows, last_seq, last_sent_timestamp, sent_events)
    if not events:
        vlog("[ingest-mirror] no-events")
        return "no-events"
    try:
        resp = requests.post(
            f"{DASH_URL}/ingest",
            json={"device_id": DEVICE_ID, "since_seq": last_seq, "events": events},
            headers={"Content-Type": "application/json", "X-Ingest-Key": INGEST_KEY},
            timeout=10
        )
        print(f"[DEBUG] Dashboard response: {resp.status_code} - {resp.text}")
        resp.raise_for_status()
        ack = int(resp.json().get("ack_seq", last_seq))
        if ack > last_seq:
            state["last_seq"] = ack
            # Update last_sent_timestamp to the latest event timestamp
            if events:
                latest_timestamp = max(event["payload_json"].get("entry_timestamp", 0) for event in events)
                state["last_sent_timestamp"] = latest_timestamp
                
                # Track sent events
                for event in events:
                    person_id = event["payload_json"].get("person_id")
                    entry_timestamp = event["payload_json"].get("entry_timestamp", 0)
                    exit_timestamp = event["payload_json"].get("exit_timestamp")
                    event_key = f"{person_id}_{int(entry_timestamp)}"
                    state["sent_events"][event_key] = {
                        "sent": True,
                        "had_exit": bool(exit_timestamp)
                    }
                    
            save_state(state)
        
        posted = len(events)
        vlog(f"[ingest-mirror] posted={posted} ack={ack}")
        
        # Show summary of what was sent
        if posted > 0:
            entry_count = sum(1 for e in events if e["type"] == "PASSENGER_ENTRY")
            exit_count = sum(1 for e in events if e["type"] == "PASSENGER_EXIT")
            print(f"📤 [BATCH SENT] {posted} events: {entry_count} entries, {exit_count} exits")
            print(f"   Dashboard acknowledged up to sequence: {ack}")
            print("─" * 50)
        
        # optionally show a tiny heartbeat only when something was sent
        if not VERBOSE and posted:
            print(f"[ingest-mirror] batch ok: +{posted}, ack={ack}")
        
        return f"posted={posted} ack={ack}"
    except Exception as e:
        print(f"[ingest-mirror] error: {e}")
        import traceback
        traceback.print_exc()
        return f"error:{e}"

if __name__ == "__main__":
    while True:
        print("[ingest-mirror]", run_once())
        time.sleep(INTERVAL_S)
