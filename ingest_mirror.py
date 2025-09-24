# ingest_mirror.py
import os, json, time, glob, uuid, datetime, requests

DASH_URL   = os.getenv("INGEST_URL", "https://etrikedashboard.com")
INGEST_KEY = os.getenv("INGEST_KEY", "")
DEVICE_ID  = os.getenv("PI_ID", "PI_CANARY_001")
STATE_PATH = os.getenv("INGEST_STATE", "ingest_state.json")
LOG_ROOT   = os.getenv("LOG_ROOT", "logs")  # path to existing logs root
BATCH_SIZE = int(os.getenv("INGEST_BATCH_SIZE", "50"))
INTERVAL_S = int(os.getenv("INGEST_INTERVAL", "5"))

def load_state():
    try:
        with open(STATE_PATH, "r") as f: return json.load(f)
    except Exception:
        return {"last_seq": 0}

def save_state(s):
    with open(STATE_PATH, "w") as f: json.dump(s, f)

def today_files():
    t = datetime.date.today()
    # Matches your actual pattern: logs/YYYY/M/D.json
    return sorted(glob.glob(f"{LOG_ROOT}/{t.year}/{t.month}/{t.day}.json"))

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

def build_events(rows, start_seq):
    seq = start_seq
    events = []
    for r in rows:
        seq += 1
        evt_time = r.get("exit_timestamp") or r.get("entry_timestamp") or time.time()
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
    rows = read_entries()
    if not rows:
        return "no-rows"
    events, new_seq = build_events(rows, last_seq)
    if not events:
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
            save_state(state)
        return f"posted={len(events)} ack={ack}"
    except Exception as e:
        return f"error:{e}"

if __name__ == "__main__":
    while True:
        print("[ingest-mirror]", run_once())
        time.sleep(INTERVAL_S)
