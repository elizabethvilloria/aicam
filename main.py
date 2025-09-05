import cv2
import time
import datetime
from ultralytics import YOLO
import os
import json
from collections import defaultdict

# Optional: Picamera2 for Raspberry Pi camera support
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except Exception:
    PICAMERA2_AVAILABLE = False

# Optional: rpicam for newer Raspberry Pi systems
try:
    import subprocess
    import tempfile
    RPICAM_AVAILABLE = True
except Exception:
    RPICAM_AVAILABLE = False

CONFIG_FILE = "config.json"
LOG_DIR = "logs"

def load_config():
    """Load configuration from config.json file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Warning: Could not load {CONFIG_FILE}, using defaults")
        return {}

def log_passenger_entry(person_id, passenger_type):
    """Logs a passenger entry event with a timestamp and type."""
    now = datetime.datetime.now()
    log_dir = os.path.join(LOG_DIR, str(now.year), str(now.month))
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f"{now.day}.json")
    
    # Load config to get Pi identification
    config = load_config()
    
    new_entry = {
        "person_id": person_id, 
        "type": passenger_type, 
        "entry_timestamp": now.timestamp(),
        "exit_timestamp": None,
        "dwell_time_minutes": None,
        "pi_id": config.get("pi_id", "unknown"),
        "city": config.get("city", "unknown"),
        "toda_id": config.get("toda_id", "unknown"),
        "etrike_id": config.get("etrike_id", "unknown"),
        "location": config.get("location", "unknown")
    }
    
    # Read existing data and append the new entry
    try:
        if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
            with open(log_file, 'r') as f:
                logs = json.load(f)
        else:
            logs = []
    except (json.JSONDecodeError, FileNotFoundError):
        logs = [] # Reset if file is corrupted or not found
        
    logs.append(new_entry)
    
    with open(log_file, 'w') as f:
        json.dump(logs, f, indent=4)

def log_passenger_exit(person_id, dwell_time_seconds):
    """Updates a passenger entry with exit timestamp and dwell time."""
    now = datetime.datetime.now()
    log_dir = os.path.join(LOG_DIR, str(now.year), str(now.month))
    log_file = os.path.join(log_dir, f"{now.day}.json")
    
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                logs = json.load(f)
            
            # Find the most recent entry for this person_id that doesn't have an exit time
            for entry in reversed(logs):
                if entry.get("person_id") == person_id and entry.get("exit_timestamp") is None:
                    entry["exit_timestamp"] = now.timestamp()
                    entry["dwell_time_minutes"] = round(dwell_time_seconds / 60, 1)
                    break
            
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=4)
                
        except (json.JSONDecodeError, FileNotFoundError):
            pass  # If file is corrupted, skip exit logging

def classify_passenger(person_keypoints, box_height):
    """Classifies a passenger as 'Adult' or 'Child' based on bounding box height."""
    height_threshold = 125  # Pixels
    if box_height < height_threshold:
        return "Child"
    else:
        return "Adult"


def compute_head_box(keypoints):
    """Compute a square box around the head using COCO keypoints (nose/eyes/ears).
    Returns ((x1, y1), (x2, y2)) or None if not enough info.
    """
    head_indices = [0, 1, 2, 3, 4]  # nose, left eye, right eye, left ear, right ear
    visible = [keypoints[i] for i in head_indices if keypoints[i][0] > 0 and keypoints[i][1] > 0]
    if not visible:
        # fallback to nose if present
        nose = keypoints[0]
        if nose[0] > 0 and nose[1] > 0:
            cx, cy = int(nose[0]), int(nose[1])
            side = 60
            return (cx - side // 2, cy - side // 2), (cx + side // 2, cy + side // 2)
        return None

    min_x = int(min(kp[0] for kp in visible))
    min_y = int(min(kp[1] for kp in visible))
    max_x = int(max(kp[0] for kp in visible))
    max_y = int(max(kp[1] for kp in visible))

    cx = (min_x + max_x) // 2
    cy = (min_y + max_y) // 2
    width = max_x - min_x
    height = max_y - min_y
    side = int(max(width, height) * 1.4)
    if side < 30:
        side = 30
    x1 = cx - side // 2
    y1 = cy - side // 2
    x2 = x1 + side
    y2 = y1 + side
    return (x1, y1), (x2, y2)

def compute_person_center_for_zone(keypoints):
    """Choose a robust reference point to determine zones.
    Priority: nose → average of shoulders/hips → bbox center of visible keypoints.
    Returns (x, y) or None.
    """
    # 1) Nose
    nose = keypoints[0]
    if nose[0] > 0 and nose[1] > 0:
        return int(nose[0]), int(nose[1])

    # 2) Torso center (shoulders and hips)
    torso_indices = [5, 6, 11, 12]
    torso_pts = [(int(keypoints[i][0]), int(keypoints[i][1])) for i in torso_indices
                 if keypoints[i][0] > 0 and keypoints[i][1] > 0]
    if torso_pts:
        avg_x = sum(p[0] for p in torso_pts) // len(torso_pts)
        avg_y = sum(p[1] for p in torso_pts) // len(torso_pts)
        return avg_x, avg_y

    # 3) Visible keypoints bbox center
    visible = [kp for kp in keypoints if kp[0] > 0 and kp[1] > 0]
    if visible:
        min_x = int(min(kp[0] for kp in visible))
        min_y = int(min(kp[1] for kp in visible))
        max_x = int(max(kp[0] for kp in visible))
        max_y = int(max(kp[1] for kp in visible))
        return (min_x + max_x) // 2, (min_y + max_y) // 2

    return None

def load_config():
    """Load configuration from a JSON file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        # For backward compatibility, rename 'zone_margin' to 'side_margin'
        if 'zone_margin' in config:
            config['side_margin'] = config.pop('zone_margin')

    except (FileNotFoundError, json.JSONDecodeError):
        # Default config if file is missing or invalid
        config = {
            "camera_index": 1,
            "side_margin": 100,
            "bottom_margin": 100,
            "line_thickness": 2,
            "font_scale": 0.7,
            "font_thickness": 2,
            "colors": {
                "exit_red": [0, 0, 255],
                "inside_green": [0, 100, 0],
                "person_id_green": [0, 255, 0],
                "info_text_white": [255, 255, 255],
                "hover_yellow": [0, 255, 255] # Hover color
            },
            # posture_threshold removed - not currently used
        }
    
    # Ensure bottom_margin exists in case of old config file
    if 'bottom_margin' not in config:
        config['bottom_margin'] = 100

    # Convert color lists to tuples for OpenCV
    for key, value in config["colors"].items():
        config["colors"][key] = tuple(value)
    return config

def save_config(config_to_save):
    """Save configuration to a JSON file."""
    # Create a modifiable copy for saving (colors as lists)
    config_copy = config_to_save.copy()
    config_copy['colors'] = config_copy['colors'].copy()
    for key, value in config_copy["colors"].items():
        config_copy["colors"][key] = list(value)
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_copy, f, indent=4)

def run_detection(model):
    # Load configuration
    config = load_config()
    
    # --- State for Mouse Interaction ---
    shared_state = {
        'side_margin': config['side_margin'],
        'bottom_margin': config.get('bottom_margin', 100), # Default if not in config
        'dragging_line': None,  # 'left', 'right', 'bottom', or None
        'hovering_on': None,  # 'left', 'right', 'bottom', or None
        'shadow_position': None, # X or Y coordinate for the shadow line
        'feedback_message': '', # Message like "Saving..." or "Saved!"
        'feedback_timestamp': 0 # Timestamp for feedback message
    }
    
            # Posture detection removed - not currently used

    # Initialize video capture (try OpenCV indices, then fall back to Picamera2 on Raspberry Pi)
    cap = None
    picam2 = None
    use_picamera2 = False

    def try_opencv_indices(indices):
        for idx in indices:
            temp_cap = cv2.VideoCapture(idx)
            if not temp_cap.isOpened():
                temp_cap.release()
                continue
            ok, temp_frame = temp_cap.read()
            if ok and temp_frame is not None:
                return temp_cap, temp_frame, idx
            temp_cap.release()
        return None, None, None

    preferred_index = int(config.get("camera_index", 0))
    scan_order = [preferred_index] + [i for i in range(4) if i != preferred_index]
    cap, frame, used_index = try_opencv_indices(scan_order)

    if cap is None or frame is None:
        # Fallback to Picamera2 if available (Raspberry Pi)
        if PICAMERA2_AVAILABLE:
            try:
                picam2 = Picamera2()
                # Use a modest resolution for performance on Pi
                video_config = picam2.create_video_configuration(main={"size": (640, 480)})
                picam2.configure(video_config)
                picam2.start()
                time.sleep(0.5)  # warm-up
                frame = picam2.capture_array()
                # Picamera2 returns RGB; convert to BGR for OpenCV drawing consistency
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                if frame is None:
                    print("Error: Picamera2 started but returned an empty frame.")
                    return
                use_picamera2 = True
                # Using Picamera2 backend for frames
            except Exception as e:
                print(f"Error: Could not initialize Picamera2. {e}")
                print("Hint: On Raspberry Pi OS, install Picamera2: sudo apt update && sudo apt install -y python3-picamera2 libcamera-apps")
                return
        # Fallback to rpicam if available (newer Raspberry Pi systems)
        elif RPICAM_AVAILABLE:
            try:
                print("Trying rpicam...")
                # Use rpicam-still to capture a frame
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                    temp_image_path = tmp_file.name
                
                # Capture frame using rpicam-still
                result = subprocess.run([
                    'rpicam-still', 
                    '-o', temp_image_path,
                    '-t', '1000',  # 1 second timeout
                    '--width', '640',
                    '--height', '480'
                ], capture_output=True, timeout=10)
                
                if result.returncode == 0 and os.path.exists(temp_image_path):
                    # Read the captured image
                    frame = cv2.imread(temp_image_path)
                    if frame is not None:
                        print("rpicam capture successful!")
                        # Clean up temp file
                        os.unlink(temp_image_path)
                        use_picamera2 = False  # We'll use rpicam for frames
                    else:
                        print("Error: rpicam captured image but OpenCV couldn't read it")
                        os.unlink(temp_image_path)
                        return
                else:
                    print(f"Error: rpicam capture failed: {result.stderr.decode()}")
                    if os.path.exists(temp_image_path):
                        os.unlink(temp_image_path)
                    return
                    
            except Exception as e:
                print(f"Error: Could not initialize rpicam. {e}")
                print("Hint: Install rpicam-apps: sudo apt install rpicam-apps")
                return
        else:
            print("Error: Could not read frame from any OpenCV camera index (0-3).")
            print("If you're on Raspberry Pi, install rpicam-apps (sudo apt install rpicam-apps) or check camera connections.")
            return
    else:
        # Using OpenCV VideoCapture index
        pass

    frame_height, frame_width, _ = frame.shape

    # --- Mouse Callback for Zone Adjustment ---
    def adjust_zones_callback(event, x, y, flags, param):
        nonlocal shared_state, config
        
        # Click sensitivity for easier line grabbing
        click_sensitivity = 20
        is_near_left = abs(x - shared_state['side_margin']) < click_sensitivity
        is_near_right = abs(x - (frame_width - shared_state['side_margin'])) < click_sensitivity
        is_near_bottom = abs(y - (frame_height - shared_state['bottom_margin'])) < click_sensitivity

        # Handle mouse hover for visual feedback
        if event == cv2.EVENT_MOUSEMOVE:
            if shared_state['dragging_line'] is None: # Update hover only when not dragging
                if is_near_left:
                    shared_state['hovering_on'] = 'left'
                elif is_near_right:
                    shared_state['hovering_on'] = 'right'
                elif is_near_bottom:
                    shared_state['hovering_on'] = 'bottom'
                else:
                    shared_state['hovering_on'] = None

        if event == cv2.EVENT_LBUTTONDOWN:
            if is_near_left:
                shared_state['dragging_line'] = 'left'
                shared_state['shadow_position'] = x
            elif is_near_right:
                shared_state['dragging_line'] = 'right'
                shared_state['shadow_position'] = x
            elif is_near_bottom:
                shared_state['dragging_line'] = 'bottom'
                shared_state['shadow_position'] = y

        elif event == cv2.EVENT_MOUSEMOVE:
            if shared_state['dragging_line'] == 'left':
                if 20 < x < (frame_width / 2) - 20:
                    shared_state['shadow_position'] = x
            elif shared_state['dragging_line'] == 'right':
                if (frame_width / 2) + 20 < x < frame_width:
                     shared_state['shadow_position'] = x
            elif shared_state['dragging_line'] == 'bottom':
                if (frame_height / 2) + 20 < y < frame_height:
                     shared_state['shadow_position'] = y
        
        elif event == cv2.EVENT_LBUTTONUP:
            if shared_state['dragging_line'] == 'left':
                shared_state['side_margin'] = shared_state['shadow_position']
            elif shared_state['dragging_line'] == 'right':
                shared_state['side_margin'] = frame_width - shared_state['shadow_position']
            elif shared_state['dragging_line'] == 'bottom':
                shared_state['bottom_margin'] = frame_height - shared_state['shadow_position']

            if shared_state['dragging_line'] is not None:
                # Show "Saving..." message
                shared_state['feedback_message'] = 'Saving...'
                
                # Update config and save
                config['side_margin'] = shared_state['side_margin']
                config['bottom_margin'] = shared_state['bottom_margin']
                save_config(config)
                # Configuration saved to config.json
                
                # Show "Saved!" message
                shared_state['feedback_message'] = 'Configuration Saved!'
                shared_state['feedback_timestamp'] = time.time()
                
            shared_state['dragging_line'] = None
            shared_state['shadow_position'] = None

    # --- Colors from Config ---
    exit_red = config["colors"]["exit_red"]
    inside_green = config["colors"]["inside_green"]
    person_id_green = config["colors"]["person_id_green"]
    info_text_white = config["colors"]["info_text_white"]
    hover_yellow = config["colors"]["hover_yellow"]
    shadow_line_gray = config["colors"].get("shadow_line_gray", (200, 200, 200))
    adult_text_blue = config["colors"].get("adult_text_blue", (255, 0, 0))
    child_text_orange = config["colors"].get("child_text_orange", (0, 165, 255))

    # --- Zone Definitions ---
    side_margin = shared_state['side_margin']
    bottom_margin = shared_state['bottom_margin']
    # Left exit zone
    left_exit_zone = (0, 0, side_margin, frame_height)
    # Right exit zone
    right_exit_zone = (frame_width - side_margin, 0, frame_width, frame_height)
    # Bottom exit zone
    bottom_exit_zone = (0, frame_height - bottom_margin, frame_width, frame_height)
    # Area between exit zones (detection now uses full body center, not just nose)
    inside_zone = (side_margin, 0, frame_width - side_margin, frame_height - bottom_margin)

    # --- Passenger Counting ---
    person_last_zone = {}
    passenger_entry_times = {}
    person_last_seen = {}  # Track when each person was last seen
    exit_timeout_seconds = 3  # Force exit after 3 seconds of no detection
    exit_debounce = {}  # Prevent rapid exit/entry flickering
    person_exit_cooldown = {}  # Prevent re-entry after exit
    # Cache for skipped frames to avoid flicker
    latest_boxes = []  # list of ((x1, y1), (x2, y2))
    last_passengers_in_trike_count = 0

    # --- Main Loop ---
    frame_idx = 0
    # Camera flip settings from config
    flip_horizontal = bool(config.get('flip_horizontal', False))
    flip_vertical = bool(config.get('flip_vertical', False))
    # FPS tracking
    last_frame_time = time.time()
    smoothed_fps = 0.0
    while True:
        if use_picamera2:
            frame = picam2.capture_array()
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ret = frame is not None
        elif RPICAM_AVAILABLE and not use_picamera2:
            # Use rpicam-vid for continuous video streaming (much faster)
            try:
                # For now, use a simple approach - capture one frame and reuse it
                # This is a temporary solution until we implement proper video streaming
                if not hasattr(run_detection, 'last_frame'):
                    # First time: capture a frame
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                        temp_image_path = tmp_file.name
                    
                    result = subprocess.run([
                        'rpicam-still', 
                        '-o', temp_image_path,
                        '-t', '100',
                        '--width', '640',
                        '--height', '480',
                        '--nopreview'
                    ], capture_output=True, timeout=2)
                    
                    if result.returncode == 0 and os.path.exists(temp_image_path):
                        frame = cv2.imread(temp_image_path)
                        if frame is not None:
                            run_detection.last_frame = frame.copy()
                            ret = True
                        else:
                            ret = False
                        os.unlink(temp_image_path)
                    else:
                        ret = False
                        if os.path.exists(temp_image_path):
                            os.unlink(temp_image_path)
                else:
                    # Reuse the last frame for better performance
                    frame = run_detection.last_frame.copy()
                    ret = True
                    
            except Exception as e:
                print(f"rpicam capture error: {e}")
                ret = False
        else:
            ret, frame = cap.read()

        if not ret:
            break

        # Apply flips as configured
        if flip_horizontal and flip_vertical:
            frame = cv2.flip(frame, -1)
        elif flip_horizontal:
            frame = cv2.flip(frame, 1)
        elif flip_vertical:
            frame = cv2.flip(frame, 0)

        # Update FPS (EMA smoothing)
        now_t = time.time()
        dt = now_t - last_frame_time
        if dt > 0:
            inst_fps = 1.0 / dt
            smoothed_fps = (0.9 * smoothed_fps) + (0.1 * inst_fps) if smoothed_fps > 0 else inst_fps
        last_frame_time = now_t

        frame_idx += 1

        passengers_in_trike_count = 0

        # Pause AI model during drag to keep UI responsive
        # Also skip every other frame to reduce CPU load
        did_infer = False
        if shared_state['dragging_line'] is None and (frame_idx % 2 == 0):
            # Run YOLOv8 tracking on the frame with smaller inference size
            results = model.track(
                frame,
                persist=True,
                verbose=False,
                device="cpu",
                tracker="bytetrack.yaml",
                imgsz=320,
                conf=0.7,
                max_det=10
            )
            did_infer = True

            if results and results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes.xywh.cpu()
                track_ids = results[0].boxes.id.int().cpu().tolist()
                all_keypoints = results[0].keypoints.xy.cpu().numpy()
                confidences = results[0].boxes.conf.cpu().numpy()
                new_boxes = []
                for i, person_keypoints in enumerate(all_keypoints):
                    person_id = track_ids[i]
                    
                    # Get bounding box center (more reliable than nose keypoint)
                    box = boxes[i]  # xywh format: [center_x, center_y, width, height]
                    center_x, center_y = float(box[0]), float(box[1])
                    box_width, box_height = float(box[2]), float(box[3])
                    
                    # Check if person is near edges (likely exiting)
                    near_left_edge = center_x < 100  # Increased to 100 pixels
                    near_right_edge = center_x > frame_width - 100  # Increased to 100 pixels
                    near_bottom_edge = center_y > frame_height - 100  # Increased to 100 pixels
                    near_top_edge = center_y < 100  # Increased to 100 pixels
                    
                    # If person is near edge, force exit
                    if near_left_edge or near_right_edge or near_bottom_edge or near_top_edge:
                        if person_id in passenger_entry_times:
                            dwell_time_seconds = time.time() - passenger_entry_times.pop(person_id)
                            log_passenger_exit(person_id, dwell_time_seconds)
                            # Set exit cooldown to prevent re-entry
                            person_exit_cooldown[person_id] = time.time()
                            # Remove from tracking
                            if person_id in person_last_zone:
                                del person_last_zone[person_id]
                            if person_id in person_last_seen:
                                del person_last_seen[person_id]
                        continue  # Skip normal zone detection
                    
                    # Also get nose position for backup (in case we need it for drawing)
                    nose_x, nose_y = person_keypoints[0]

                    # Determine person's current zone by body center position (more reliable)
                    current_zone = None
                    if center_x > 0 and center_y > 0:
                        if left_exit_zone[0] <= center_x < left_exit_zone[2]:
                            current_zone = "left_exit"
                        elif right_exit_zone[0] <= center_x < right_exit_zone[2]:
                            current_zone = "right_exit"
                        elif bottom_exit_zone[1] <= center_y < bottom_exit_zone[3]:
                            current_zone = "bottom_exit"
                        elif inside_zone[0] <= center_x < inside_zone[2] and center_y < inside_zone[3]:
                            current_zone = "inside"
                            passengers_in_trike_count += 1

                    # --- Bounding box, classification, drawing, and logging ---
                    visible_keypoints = [kp for kp in person_keypoints if kp[0] > 0 and kp[1] > 0]
                    
                    if visible_keypoints:
                        min_x = int(min(kp[0] for kp in visible_keypoints))
                        min_y = int(min(kp[1] for kp in visible_keypoints))
                        max_x = int(max(kp[0] for kp in visible_keypoints))
                        max_y = int(max(kp[1] for kp in visible_keypoints))
                        
                        # Add some padding
                        padding = 10
                        start_point = (min_x - padding, min_y - padding)
                        end_point = (max_x + padding, max_y + padding)

                        # Draw a square head box instead of full-body box
                        head_box = compute_head_box(person_keypoints)
                        if head_box is not None:
                            hb_sp, hb_ep = head_box
                            cv2.rectangle(frame, hb_sp, hb_ep, (255, 0, 255), 2)
                            # Cache head box for skipped frames
                            new_boxes.append((hb_sp, hb_ep))

                        # Minimal classification to keep logging working
                        box_height = end_point[1] - start_point[1]
                        passenger_type = classify_passenger(person_keypoints, box_height)
                        # posture = classify_posture(person_keypoints, posture_threshold) # Removed as per edit hint

                        # --- Passenger Counting ---
                        if current_zone is not None:
                            last_zone = person_last_zone.get(person_id)
                            current_time = time.time()

                            if current_zone == "inside" and last_zone != "inside":
                                # Check exit cooldown: prevent re-entry for 3 seconds after exit
                                if person_id not in person_exit_cooldown or current_time - person_exit_cooldown[person_id] > 3.0:
                                    log_passenger_entry(person_id, passenger_type)
                                    passenger_entry_times[person_id] = current_time
                                    # Clear exit cooldown on successful entry
                                    if person_id in person_exit_cooldown:
                                        del person_exit_cooldown[person_id]
                            elif current_zone != "inside" and last_zone == "inside":
                                if person_id in passenger_entry_times:
                                    dwell_time_seconds = current_time - passenger_entry_times.pop(person_id)
                                    log_passenger_exit(person_id, dwell_time_seconds)
                                    # Record exit time for debouncing
                                    exit_debounce[person_id] = current_time
                    
                    # Update person's last known zone
                    if current_zone is not None:
                        person_last_zone[person_id] = current_zone
                    
                    # Update when person was last seen
                    person_last_seen[person_id] = time.time()

                # Save caches after processing all people this frame
                latest_boxes = new_boxes
                last_passengers_in_trike_count = passengers_in_trike_count
                
                # Update last detection frame
                run_detection.last_detection_frame = frame_idx
            else:
                pass  # No detections this frame
            
            # Force exit people who haven't been seen for too long
            current_time = time.time()
            people_to_exit = []
            
            for person_id in list(passenger_entry_times.keys()):
                if person_id in person_last_seen:
                    time_since_last_seen = current_time - person_last_seen[person_id]
                    if time_since_last_seen > exit_timeout_seconds:
                        # Force exit this person
                        dwell_time_seconds = current_time - passenger_entry_times.pop(person_id)
                        log_passenger_exit(person_id, dwell_time_seconds)
                        people_to_exit.append(person_id)
            
            # Remove from tracking
            for person_id in people_to_exit:
                if person_id in person_last_zone:
                    del person_last_zone[person_id]
                if person_id in person_last_seen:
                    del person_last_seen[person_id]

        # If we skipped inference this frame, draw last known boxes to avoid flicker
        if not did_infer and latest_boxes:
            # Only draw boxes for 1 frame after detection stops
            if not hasattr(run_detection, 'last_detection_frame'):
                run_detection.last_detection_frame = 0
            
            if frame_idx - run_detection.last_detection_frame < 2:  # Only 2 frames
                for (sp, ep) in latest_boxes:
                    cv2.rectangle(frame, sp, ep, (255, 0, 255), 2)
            else:
                # Clear boxes if no detection for 2+ frames
                latest_boxes = []

        # --- Draw Zones ---
        side_margin = shared_state['side_margin'] # Use updated margin
        bottom_margin = shared_state['bottom_margin']
        left_exit_zone = (0, 0, side_margin, frame_height - bottom_margin)
        right_exit_zone = (frame_width - side_margin, 0, frame_width, frame_height - bottom_margin)
        bottom_exit_zone = (side_margin, frame_height - bottom_margin, frame_width - side_margin, frame_height)
        inside_zone = (side_margin, 0, frame_width - side_margin, frame_height - bottom_margin)

        # --- Clear Feedback Message ---
        if shared_state['feedback_message'] == 'Configuration Saved!' and \
           time.time() - shared_state['feedback_timestamp'] > config.get('saved_confirmation_duration_sec', 2):
            shared_state['feedback_message'] = ''

        line_thickness = config["line_thickness"]
        # Set line colors based on hover state
        left_line_color = hover_yellow if shared_state['hovering_on'] == 'left' else inside_green
        right_line_color = hover_yellow if shared_state['hovering_on'] == 'right' else inside_green
        bottom_line_color = hover_yellow if shared_state['hovering_on'] == 'bottom' else inside_green
        
        # "Inside" zone lines (vertical)
        cv2.rectangle(frame, (side_margin, 0), (side_margin + line_thickness - 1, frame_height - bottom_margin), left_line_color, -1)
        cv2.rectangle(frame, (frame_width - side_margin - line_thickness, 0), (frame_width - side_margin - 1, frame_height - bottom_margin), right_line_color, -1)
        # "Inside" zone line (horizontal)
        cv2.rectangle(frame, (side_margin, frame_height - bottom_margin), (frame_width - side_margin, frame_height - bottom_margin + line_thickness - 1), bottom_line_color, -1)
        
        # --- Draw shadow lines when dragging ---
        if shared_state['dragging_line'] and shared_state['shadow_position'] is not None:
            overlay = frame.copy()
            alpha = 0.5
            
            if shared_state['dragging_line'] in ['left', 'right']:
                shadow_x = shared_state['shadow_position']
                mirrored_shadow_x = frame_width - shadow_x
                # Primary shadow line
                cv2.rectangle(overlay, (shadow_x, 0), (shadow_x + line_thickness - 1, frame_height), shadow_line_gray, -1)
                # Mirrored shadow line
                cv2.rectangle(overlay, (mirrored_shadow_x, 0), (mirrored_shadow_x + line_thickness - 1, frame_height), shadow_line_gray, -1)
            
            elif shared_state['dragging_line'] == 'bottom':
                shadow_y = shared_state['shadow_position']
                cv2.rectangle(overlay, (0, shadow_y), (frame_width, shadow_y + line_thickness - 1), shadow_line_gray, -1)

            frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
            
        # Outer boundaries of exit zones
        cv2.rectangle(frame, (0, 0), (line_thickness - 1, frame_height), exit_red, -1)
        cv2.rectangle(frame, (frame_width - line_thickness, 0), (frame_width - 1, frame_height), exit_red, -1)
        cv2.rectangle(frame, (0, frame_height - line_thickness), (frame_width, frame_height), exit_red, -1)


        # --- Zone Labels ---
        font = cv2.FONT_HERSHEY_SIMPLEX
        # Smaller label font for on-screen text
        label_font_scale = 0.6
        label_font_thickness = 1
        exit_text = "Exit"
        text_size = cv2.getTextSize(exit_text, font, label_font_scale, label_font_thickness)[0]

        # Center "Exit" in left zone
        left_text_x = (side_margin - text_size[0]) // 2
        cv2.putText(frame, exit_text, (left_text_x, 30), font, label_font_scale, exit_red, label_font_thickness)

        # Center "Exit" in right zone
        right_text_x = (frame_width - side_margin) + ((side_margin - text_size[0]) // 2)
        cv2.putText(frame, exit_text, (right_text_x, 30), font, label_font_scale, exit_red, label_font_thickness)
        
        # Center "Exit" in bottom zone
        bottom_text_x = (frame_width - text_size[0]) // 2
        bottom_text_y = frame_height - (bottom_margin - text_size[1]) // 2
        cv2.putText(frame, exit_text, (bottom_text_x, bottom_text_y), font, label_font_scale, exit_red, label_font_thickness)

        cv2.putText(frame, "Inside E-Trike", (inside_zone[0] + 10, 30), font, label_font_scale, inside_green, label_font_thickness)

        # Display clock and counters (smaller font)
        current_time_str = datetime.datetime.now().strftime("%m-%d-%y %H:%M")
        cv2.putText(frame, current_time_str, (side_margin + 10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, info_text_white, 1, cv2.LINE_AA)
        display_count = passengers_in_trike_count if did_infer else last_passengers_in_trike_count
        cv2.putText(frame, f"Passengers Inside: {display_count}", (side_margin + 10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, info_text_white, 1, cv2.LINE_AA)
        # FPS display
        cv2.putText(frame, f"FPS: {smoothed_fps:.1f}", (side_margin + 10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, info_text_white, 1, cv2.LINE_AA)
        
        # Add instruction or feedback text
        if shared_state['feedback_message']:
            # Display centered feedback message
            feedback_text = shared_state['feedback_message']
            font_face = cv2.FONT_HERSHEY_DUPLEX
            font_scale_feedback = 1.2
            font_thickness_feedback = 2

            # Center text
            text_size = cv2.getTextSize(feedback_text, font_face, font_scale_feedback, font_thickness_feedback)[0]
            text_x = (frame_width - text_size[0]) // 2
            text_y = (frame_height + text_size[1]) // 2
            
            # Add semi-transparent background
            box_padding = 20
            box_coords = ((text_x - box_padding, text_y - text_size[1] - box_padding), (text_x + text_size[0] + box_padding, text_y + box_padding))
            overlay = frame.copy()
            cv2.rectangle(overlay, box_coords[0], box_coords[1], (0, 0, 0), -1)
            alpha = 0.6 # Transparency
            frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
            
            # Draw centered text
            cv2.putText(frame, feedback_text, (text_x, text_y), font_face, font_scale_feedback, info_text_white, font_thickness_feedback, cv2.LINE_AA)
        
        else:
            # Display adjustment instructions
            if shared_state['dragging_line']:
                drag_text = f"Dragging {shared_state['dragging_line']} zone..."
            else:
                drag_text = "Hover over a zone line, then click and drag to adjust."
            cv2.putText(frame, drag_text, (side_margin + 10, frame_height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, info_text_white, 1, cv2.LINE_AA)


        # Display the frame
        window_name = 'E-Trike Passenger Counter'
        cv2.imshow(window_name, frame)
        cv2.setMouseCallback(window_name, adjust_zones_callback)


        # Press 'q' to exit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    if use_picamera2 and picam2 is not None:
        try:
            picam2.stop()
        except Exception:
            pass
    elif cap is not None:
        cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    # Load the YOLOv8 pose estimation model
    model = YOLO('yolov8n-pose.pt')
    run_detection(model) 