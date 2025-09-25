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
LOG_ROOT   = os.getenv("LOG_ROOT", "/home/pi/aicam/logs")  # path to existing logs root
BATCH_SIZE = int(os.getenv("INGEST_BATCH_SIZE", "50"))
INTERVAL_S = int(os.getenv("INGEST_INTERVAL", "5"))

def load_state():
    try:
        with open(STATE_PATH, "r") as f: return json.load(f)
    except Exception:
        return {"last_seq": 0, "last_sent_timestamp": 0}

def save_state(s):
    with open(STATE_PATH, "w") as f: json.dump(s, f)

def today_files():
    t = datetime.date.today()
    # matches logs/YYYY/M/D.json
    pattern = f"{LOG_ROOT}/{t.year}/{t.month}/{t.day}.json"
    files = glob.glob(pattern)
    # fallback: check yesterday (in case timezone offset causes mismatch)
    if not files:
        y = t - datetime.timedelta(days=1)
        pattern = f"{LOG_ROOT}/{y.year}/{y.month}/{y.day}.json"
        files = glob.glob(pattern)
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

def build_events(rows, start_seq, last_sent_timestamp):
    seq = start_seq
    events = []
    
    # Only process rows that haven't been sent yet (by timestamp)
    for r in rows:
        entry_timestamp = r.get("entry_timestamp", 0)
        
        # Skip if this event has already been sent (by timestamp)
        if entry_timestamp <= last_sent_timestamp:
            continue
            
        seq += 1
        evt_time = r.get("exit_timestamp") or entry_timestamp or time.time()
        
        # DEBUG: Print what we're sending
        print(f"[DEBUG] Sending event {seq}: person_id={r.get('person_id')}, entry_timestamp={entry_timestamp}")
        
        events.append({
            "event_id": f"{DEVICE_ID}-{seq}-{uuid.uuid4().hex[:6]}",
            "device_id": DEVICE_ID,
            "seq": seq,
            "session_id": r.get("person_id", "session"),
            "type": "PASSENGER",
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
    rows = read_entries()
    if not rows:
        vlog("[ingest-mirror] no-rows")
        return "no-rows"
    events, new_seq = build_events(rows, last_seq, last_sent_timestamp)
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
        resp.raise_for_status()
        ack = int(resp.json().get("ack_seq", last_seq))
        if ack > last_seq:
            state["last_seq"] = ack
            # Update last_sent_timestamp to the latest event timestamp
            if events:
                latest_timestamp = max(event["payload_json"].get("entry_timestamp", 0) for event in events)
                state["last_sent_timestamp"] = latest_timestamp
            save_state(state)
        
        posted = len(events)
        vlog(f"[ingest-mirror] posted={posted} ack={ack}")
        # optionally show a tiny heartbeat only when something was sent
        if not VERBOSE and posted:
            print(f"[ingest-mirror] batch ok: +{posted}, ack={ack}")
        
        return f"posted={posted} ack={ack}"
    except Exception as e:
        print(f"[ingest-mirror] error:{e}")
        return f"error:{e}"

if __name__ == "__main__":
    while True:
        print("[ingest-mirror]", run_once())
        time.sleep(INTERVAL_S)
