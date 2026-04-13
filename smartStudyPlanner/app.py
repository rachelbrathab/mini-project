from flask import Flask, request, render_template, redirect, url_for, session, send_file, send_from_directory
from flask import jsonify
from src.planner import generate_schedule, format_time
import json
import copy
import os
import re
import io
import zipfile
from datetime import datetime, timedelta, date
from collections import Counter

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret123")

PUBLIC_PATHS = {
    "/",
    "/login",
    "/signup",
    "/logout",
    "/manifest.webmanifest",
    "/service-worker.js",
    "/pwa-icon.png",
}

PUBLIC_PREFIXES = (
    "/static/",
)

DATA_DIR = os.path.join(app.root_path, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PLANS_FILE = os.path.join(DATA_DIR, "plans.json")
USER_STATS_FILE = os.path.join(DATA_DIR, "user_stats.json")

POMODORO_TIERS = {
    "light": (25, 5),
    "standard": (50, 10),
    "deep": (90, 15)
}

DEFAULT_BLOCKED_DOMAINS = [
    "netflix.com",
    "youtube.com",
    "instagram.com",
    "hotstar.com",
]

REWARD_UNLOCK_MINUTES = 5

SUBJECT_RELAX_RULES = {
    "math": ["netflix.com"],
    "reading": ["youtube.com"],
    "english": ["youtube.com"],
    "literature": ["youtube.com"],
}

SUBJECT_POLICY_LIBRARY = {
    "math": {
        "name": "Math Drill",
        "allow_domains": ["khanacademy.org", "desmos.com"],
        "remove_from_block": ["youtube.com"],
    },
    "coding": {
        "name": "Coding Sprint",
        "allow_domains": ["stackoverflow.com", "github.com", "developer.mozilla.org"],
        "remove_from_block": [],
    },
    "programming": {
        "name": "Coding Sprint",
        "allow_domains": ["stackoverflow.com", "github.com", "developer.mozilla.org"],
        "remove_from_block": [],
    },
    "physics": {
        "name": "STEM Solve",
        "allow_domains": ["khanacademy.org", "wikipedia.org"],
        "remove_from_block": [],
    },
    "chemistry": {
        "name": "STEM Solve",
        "allow_domains": ["khanacademy.org", "wikipedia.org"],
        "remove_from_block": [],
    },
    "biology": {
        "name": "STEM Solve",
        "allow_domains": ["khanacademy.org", "wikipedia.org"],
        "remove_from_block": [],
    },
    "history": {
        "name": "Theory Review",
        "allow_domains": ["wikipedia.org", "youtube.com"],
        "remove_from_block": ["youtube.com"],
    },
    "english": {
        "name": "Language Practice",
        "allow_domains": ["dictionary.com", "grammarly.com", "youtube.com"],
        "remove_from_block": ["youtube.com"],
    },
}

XP_PER_COMPLETED_SESSION = 10
XP_STREAK_BONUS_MULTIPLIER = 3
HARD_MODE_EMERGENCY_LIMIT = 1

DEFAULT_USER_STATS = {
    "xp": 0,
    "level": 1,
    "buddy_email": "",
    "accountability_enabled": False,
    "energy_map": {},
}


# ---------- FILE HELPERS ----------
def load_users():
    try:
        with open(USERS_FILE) as f:
            users = json.load(f)
            return normalize_users(users)
    except:
        return []

def save_users(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(normalize_users(data), f, indent=4)


def normalize_users(users):
    unique_users = []
    seen_usernames = set()

    for user in users:
        username = user.get("username", "").strip()
        if not username:
            continue

        username_key = username.lower()
        if username_key in seen_usernames:
            continue

        seen_usernames.add(username_key)
        unique_users.append({
            "username": username,
            "password": user.get("password", "")
        })

    return unique_users

def load_plans():
    try:
        with open(PLANS_FILE) as f:
            return json.load(f)
    except:
        return []

def save_plans(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PLANS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_user_stats():
    try:
        with open(USER_STATS_FILE) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except:
        return {}


def save_user_stats(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USER_STATS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_user_stats(username):
    all_stats = load_user_stats()
    key = (username or "").strip().lower()
    login_identity = (username or "").strip()
    current = all_stats.get(key, {}) if isinstance(all_stats, dict) else {}

    normalized = {
        **DEFAULT_USER_STATS,
        **current,
    }
    normalized["xp"] = int(normalized.get("xp", 0))
    normalized["level"] = max(1, int(normalized.get("level", 1)))
    normalized["accountability_enabled"] = bool(normalized.get("accountability_enabled", False))
    normalized["buddy_email"] = str(normalized.get("buddy_email", "")).strip() or login_identity
    return normalized


def update_user_stats(username, patch):
    all_stats = load_user_stats()
    key = (username or "").strip().lower()
    login_identity = (username or "").strip()
    existing = get_user_stats(username)
    merged = {**existing, **(patch or {})}
    merged["xp"] = int(merged.get("xp", 0))
    merged["level"] = max(1, int(merged.get("level", 1)))
    merged["buddy_email"] = str(merged.get("buddy_email", "")).strip() or login_identity
    all_stats[key] = merged
    save_user_stats(all_stats)
    return merged


def level_from_xp(xp):
    # Linear progression keeps leveling predictable for MVP.
    return max(1, int(xp // 120) + 1)


def update_current_plan_progress():
    plan_date = session.get("current_plan_date")
    user = session.get("user")

    if not user:
        return

    completed_sessions = session.get("completed_study_sessions", 0)
    total_sessions = session.get("total_study_sessions", 0)
    percent = 0 if total_sessions == 0 else round((completed_sessions / total_sessions) * 100)

    plans = load_plans()
    target_plan = None

    if plan_date:
        for plan in reversed(plans):
            if plan.get("user") == user and plan.get("date") == plan_date:
                target_plan = plan
                break

    if target_plan is None:
        for plan in reversed(plans):
            if plan.get("user") == user:
                target_plan = plan
                session["current_plan_date"] = plan.get("date")
                break

    if target_plan is None:
        return

    target_plan["completed_study_sessions"] = completed_sessions
    target_plan["total_study_sessions"] = total_sessions
    target_plan["progress_percent"] = percent
    save_plans(plans)


def get_progress_snapshot():
    total_sessions = session.get("total_study_sessions", 0)
    completed_sessions = session.get("completed_study_sessions", 0)
    percent = 0 if total_sessions == 0 else round((completed_sessions / total_sessions) * 100)
    return {
        "completed_sessions": completed_sessions,
        "total_sessions": total_sessions,
        "percent": percent,
    }


def parse_iso_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_time_to_hour(value, fallback=23):
    if not value or ":" not in str(value):
        return fallback

    try:
        hour = int(str(value).split(":", 1)[0])
        return max(0, min(23, hour))
    except (TypeError, ValueError):
        return fallback


def get_current_plan_for_user(username):
    plans = load_plans()
    plan_date = session.get("current_plan_date")

    if plan_date:
        for plan in reversed(plans):
            if plan.get("user") == username and plan.get("date") == plan_date:
                return plan

    for plan in reversed(plans):
        if plan.get("user") == username:
            return plan

    return None


def update_energy_map_for_user(username, energy_level):
    if not username:
        return

    try:
        level = int(energy_level)
    except (TypeError, ValueError):
        return

    if level < 1 or level > 5:
        return

    now_hour = datetime.now().hour
    stats = get_user_stats(username)
    energy_map = stats.get("energy_map", {}) if isinstance(stats, dict) else {}
    bucket = energy_map.get(str(now_hour), {"sum": 0, "count": 0})
    bucket_sum = int(bucket.get("sum", 0)) + level
    bucket_count = int(bucket.get("count", 0)) + 1
    energy_map[str(now_hour)] = {"sum": bucket_sum, "count": bucket_count}
    update_user_stats(username, {"energy_map": energy_map})


def get_energy_peak_hour(username):
    stats = get_user_stats(username)
    energy_map = stats.get("energy_map", {}) if isinstance(stats, dict) else {}

    peak_hour = None
    peak_avg = 0
    for hour_key, bucket in energy_map.items():
        bucket_sum = int((bucket or {}).get("sum", 0))
        bucket_count = int((bucket or {}).get("count", 0))
        if bucket_count <= 0:
            continue

        avg = bucket_sum / bucket_count
        if avg > peak_avg:
            peak_avg = avg
            peak_hour = int(hour_key)

    return peak_hour, round(peak_avg, 2)


def build_focus_genome(username):
    plans = load_plans()
    user_plans = [p for p in plans if p.get("user") == username]

    hourly_pressure = Counter()
    weekday_pressure = Counter()
    domain_pressure = Counter()
    subject_pressure = Counter()

    for plan in user_plans:
        for event in plan.get("focus_genome_events", []) or []:
            domain = str(event.get("domain", "")).strip().lower()
            subject = str(event.get("subject", "")).strip()
            hour = int(event.get("hour", -1))
            weekday = str(event.get("weekday", "")).strip()

            if domain:
                domain_pressure[domain] += 1
            if subject:
                subject_pressure[subject] += 1
            if 0 <= hour <= 23:
                hourly_pressure[hour] += 1
            if weekday:
                weekday_pressure[weekday] += 1

    top_hour = hourly_pressure.most_common(1)[0][0] if hourly_pressure else None
    top_day = weekday_pressure.most_common(1)[0][0] if weekday_pressure else "N/A"
    top_domains = domain_pressure.most_common(5)
    top_subjects = subject_pressure.most_common(3)

    strategy_cards = []
    if top_hour is not None:
        strategy_cards.append(
            f"High-risk distraction window is around {top_hour:02d}:00. Start a deep-focus block 15 minutes earlier."
        )
    if top_day != "N/A":
        strategy_cards.append(
            f"Most distraction-heavy day is {top_day}. Pre-schedule lighter review tasks there to keep momentum."
        )
    if top_domains:
        strategy_cards.append(
            f"Top trigger domain: {top_domains[0][0]}. Keep it blocked until at least 80% plan completion."
        )

    return {
        "top_hour": top_hour,
        "top_day": top_day,
        "top_domains": [{"domain": d, "count": c} for d, c in top_domains],
        "top_subjects": [{"subject": s, "count": c} for s, c in top_subjects],
        "strategy_cards": strategy_cards,
    }


def build_recovery_plan(username, sleep_start, sleep_end):
    plans = load_plans()
    user_plans = [p for p in plans if p.get("user") == username]
    if not user_plans:
        return {"extra_blocks": 0, "note": "No previous plan. Fresh start today."}

    previous = user_plans[-1]
    remaining = max(0, int(previous.get("total_study_sessions", 0)) - int(previous.get("completed_study_sessions", 0)))
    if remaining == 0:
        return {"extra_blocks": 0, "note": "No recovery needed. Last plan was completed."}

    sleep_start_hour = parse_time_to_hour(sleep_start, fallback=23)
    sleep_end_hour = parse_time_to_hour(sleep_end, fallback=7)
    if sleep_end_hour <= sleep_start_hour:
        sleep_hours = (24 - sleep_start_hour) + sleep_end_hour
    else:
        sleep_hours = sleep_end_hour - sleep_start_hour

    # Preserve rest quality by never adding more than 2 catch-up blocks per day.
    extra_blocks = min(2, remaining)
    note = f"Recovery mode: carry {remaining} unfinished block(s), add {extra_blocks} smart catch-up block(s), keep ~{sleep_hours}h sleep window."
    return {"extra_blocks": extra_blocks, "note": note}


def build_live_room_snapshot(username):
    stats = get_user_stats(username)
    buddy_email = str(stats.get("buddy_email", "")).strip()
    current_plan = get_current_plan_for_user(username)

    me_payload = {
        "user": username,
        "progress_percent": int((current_plan or {}).get("progress_percent", 0)),
        "completed": int((current_plan or {}).get("completed_study_sessions", 0)),
        "total": int((current_plan or {}).get("total_study_sessions", 0)),
        "level": int(stats.get("level", 1)),
    }

    buddy_payload = None
    if buddy_email:
        buddy_plan = None
        plans = load_plans()
        for plan in reversed(plans):
            if str(plan.get("user", "")).strip().lower() == buddy_email.lower():
                buddy_plan = plan
                break

        if buddy_plan:
            buddy_payload = {
                "user": buddy_email,
                "progress_percent": int(buddy_plan.get("progress_percent", 0)),
                "completed": int(buddy_plan.get("completed_study_sessions", 0)),
                "total": int(buddy_plan.get("total_study_sessions", 0)),
            }

    return {
        "me": me_payload,
        "buddy": buddy_payload,
    }


def get_active_subject_name():
    for item in session.get("schedule", []):
        if item.get("type", "study") != "break":
            return item.get("subject", "").strip()

    return ""


def get_domain_policy_for_subject(active_subject):
    blocked_domains = list(DEFAULT_BLOCKED_DOMAINS)
    allowed_domains = []
    policy_tag = "General Focus"

    subject_value = (active_subject or "").strip().lower()
    if not subject_value:
        return blocked_domains, allowed_domains, policy_tag

    for keyword, domains_to_allow in SUBJECT_RELAX_RULES.items():
        if keyword not in subject_value:
            continue

        for domain in domains_to_allow:
            if domain in blocked_domains:
                blocked_domains.remove(domain)
                allowed_domains.append(domain)

    for keyword, policy in SUBJECT_POLICY_LIBRARY.items():
        if keyword not in subject_value:
            continue

        policy_tag = policy.get("name", policy_tag)

        for domain in policy.get("remove_from_block", []):
            if domain in blocked_domains:
                blocked_domains.remove(domain)

        for domain in policy.get("allow_domains", []):
            if domain not in allowed_domains:
                allowed_domains.append(domain)

    return blocked_domains, allowed_domains, policy_tag


def parse_plan_date(value):
    if not value:
        return None

    parsed = parse_iso_datetime(value)
    if parsed:
        return parsed.date()

    return None


def build_streak_stats(plans):
    completion_dates = []
    for plan in plans:
        if int(plan.get("progress_percent", 0)) < 100:
            continue

        parsed_date = parse_plan_date(plan.get("date"))
        if parsed_date:
            completion_dates.append(parsed_date)

    completion_set = set(completion_dates)

    current_streak = 0
    cursor = date.today()
    while cursor in completion_set:
        current_streak += 1
        cursor = cursor - timedelta(days=1)

    sorted_dates = sorted(completion_set)
    best_streak = 0
    running = 0
    prev = None

    for day in sorted_dates:
        if prev and day == prev + timedelta(days=1):
            running += 1
        else:
            running = 1

        best_streak = max(best_streak, running)
        prev = day

    today = date.today()
    week_start = today - timedelta(days=6)
    weekly_plans = []

    for plan in plans:
        parsed_date = parse_plan_date(plan.get("date"))
        if not parsed_date:
            continue

        if week_start <= parsed_date <= today:
            weekly_plans.append(int(plan.get("progress_percent", 0)))

    weekly_consistency = round(sum(weekly_plans) / len(weekly_plans)) if weekly_plans else 0

    return {
        "current_streak": current_streak,
        "best_streak": best_streak,
        "weekly_consistency": weekly_consistency,
    }


def build_reflection(plan):
    study_sessions = int(plan.get("study_sessions", 0))
    completed = int(plan.get("completed_study_sessions", 0))
    percent = int(plan.get("progress_percent", 0))

    if study_sessions == 0:
        return "No study blocks were scheduled that day. Create a short plan to build momentum."

    if percent >= 100:
        return "Excellent finish. You completed every planned study block."

    remaining = max(0, study_sessions - completed)
    if percent >= 70:
        return f"Strong effort. {remaining} block{'s' if remaining != 1 else ''} remained for full completion."

    return f"You started the day. {remaining} block{'s' if remaining != 1 else ''} are still available to recover tomorrow."


def build_accountability_summary(username):
    plans = load_plans()
    user_plans = [p for p in plans if p.get("user") == username]
    if not user_plans:
        return "No study history yet. Create your first study plan and complete one block today."

    latest = user_plans[-1]
    completed = int(latest.get("completed_study_sessions", 0))
    total = int(latest.get("total_study_sessions", 0))
    progress = int(latest.get("progress_percent", 0))
    minutes = int(latest.get("productive_minutes", 0))
    distractions = int(latest.get("distraction_attempts", 0))

    stats = get_user_stats(username)
    return (
        f"Study accountability update for {username}: "
        f"{completed}/{total} blocks completed ({progress}%), "
        f"{minutes} productive minutes, "
        f"{distractions} distraction attempts, "
        f"XP {stats.get('xp', 0)} (Level {stats.get('level', 1)})."
    )


def build_analytics_snapshot(username):
    plans = load_plans()
    user_plans = [p for p in plans if p.get("user") == username]

    total_productive_minutes = sum(int(p.get("productive_minutes", 0)) for p in user_plans)
    total_focus_starts = sum(int(p.get("focus_start_count", 0)) for p in user_plans)
    total_distractions = sum(int(p.get("distraction_attempts", 0)) for p in user_plans)
    total_completed = sum(int(p.get("completed_study_sessions", 0)) for p in user_plans)
    total_planned = sum(int(p.get("total_study_sessions", 0)) for p in user_plans)

    completion_rate = 0 if total_planned == 0 else round((total_completed / total_planned) * 100)
    focus_efficiency = 0 if total_focus_starts == 0 else round((total_completed / total_focus_starts) * 100)

    daily_labels = []
    daily_productive = []
    daily_completion = []
    for plan in user_plans[-10:]:
        day = parse_plan_date(plan.get("date"))
        daily_labels.append(day.isoformat() if day else "Unknown")
        daily_productive.append(int(plan.get("productive_minutes", 0)))
        daily_completion.append(int(plan.get("progress_percent", 0)))

    top_domains = Counter()
    for plan in user_plans:
        for domain, count in (plan.get("blocked_domain_hits") or {}).items():
            top_domains[domain] += int(count)

    top_domains_data = [{"domain": domain, "count": count} for domain, count in top_domains.most_common(5)]
    weak_topic_counter = Counter()
    for plan in user_plans:
        for weak in plan.get("weak_topics", []) or []:
            subject = str(weak.get("subject", "")).strip()
            if subject:
                weak_topic_counter[subject] += 1

    focus_genome = build_focus_genome(username)

    return {
        "total_productive_minutes": total_productive_minutes,
        "total_focus_starts": total_focus_starts,
        "total_distractions": total_distractions,
        "completion_rate": completion_rate,
        "focus_efficiency": focus_efficiency,
        "daily_labels": daily_labels,
        "daily_productive": daily_productive,
        "daily_completion": daily_completion,
        "top_domains": top_domains_data,
        "weak_topics": [{"subject": s, "count": c} for s, c in weak_topic_counter.most_common(5)],
        "focus_genome": focus_genome,
    }


def get_focus_state_snapshot():
    progress = get_progress_snapshot()
    requested_focus = bool(session.get("focus_mode_requested", False))
    has_schedule = progress["total_sessions"] > 0
    active_subject = get_active_subject_name()
    hard_mode = bool(session.get("hard_mode", False))
    break_mode_active = bool(session.get("pomodoro_break_mode", False))
    emergency_remaining = int(session.get("hard_mode_emergency_remaining", HARD_MODE_EMERGENCY_LIMIT))

    reward_until_value = session.get("reward_unlock_until")
    reward_until = parse_iso_datetime(reward_until_value)
    now = datetime.now()
    reward_active = bool(reward_until and reward_until > now)
    reward_remaining_seconds = 0
    if reward_active and reward_until:
        reward_remaining_seconds = max(0, int((reward_until - now).total_seconds()))

    # Disable focus mode only when no schedule exists.
    focus_mode = requested_focus and has_schedule
    blocked_domains = []
    allowed_domains = []
    policy_tag = "General Focus"

    if focus_mode:
        if reward_active:
            blocked_domains = []
            allowed_domains = ["reward-window"]
        elif break_mode_active:
            blocked_domains = []
            allowed_domains = ["pomodoro-break-window"]
        else:
            blocked_domains, allowed_domains, policy_tag = get_domain_policy_for_subject(active_subject)

            # Extra context-aware restrictions based on subject and weak-topic pressure.
            subject_value = (active_subject or "").strip().lower()
            if "coding" in subject_value or "program" in subject_value:
                if "reddit.com" not in blocked_domains:
                    blocked_domains.append("reddit.com")
                if "x.com" not in blocked_domains:
                    blocked_domains.append("x.com")

            current_plan = get_current_plan_for_user(session.get("user"))
            weak_topics = [w for w in (current_plan or {}).get("weak_topics", []) if str(w.get("subject", "")).strip().lower() == subject_value]
            if weak_topics and "facebook.com" not in blocked_domains:
                blocked_domains.append("facebook.com")

            # Automatically unlock YouTube at 80%.
            if progress["percent"] >= 80 and "youtube.com" in blocked_domains:
                blocked_domains.remove("youtube.com")
                if "youtube.com" not in allowed_domains:
                    allowed_domains.append("youtube.com")
    return {
        "focus_mode": focus_mode,
        "session_active": focus_mode,
        "blocked_domains": blocked_domains,
        "allowed_domains": allowed_domains,
        "has_schedule": has_schedule,
        "active_subject": active_subject,
        "reward_active": reward_active,
        "reward_remaining_seconds": reward_remaining_seconds,
        "reward_unlock_until": reward_until_value if reward_active else None,
        "break_mode_active": break_mode_active,
        "hard_mode": hard_mode,
        "emergency_break_remaining": emergency_remaining,
        "policy_tag": policy_tag,
        "active_context": {
            "subject": active_subject,
            "weak_subject_pressure": len((get_current_plan_for_user(session.get("user")) or {}).get("weak_topics", [])),
        },
        **progress,
    }


def convert_time(t):
    h, m = map(int, t.split(":"))
    return h + m / 60


def is_valid_email(value):
    if not value:
        return False

    # Lightweight email validation for auth input.
    return bool(re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value.strip()))


# ---------- AUTH ----------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user" in session:
        return redirect("/dashboard")

    if request.method == "POST":
        print("[DEBUG] Received POST to /signup")
        print("[DEBUG] Form data:", dict(request.form))
        users = load_users()
        username = request.form["username"].strip().lower()

        if not is_valid_email(username):
            print("[DEBUG] Invalid email format:", username)
            return render_template("signup.html", error="Please enter a valid email address.")

        if any(u["username"].lower() == username.lower() for u in users):
            print("[DEBUG] Email already registered:", username)
            return render_template("signup.html", error="That email is already registered.")

        users.append({
            "username": username,
            "password": request.form["password"]
        })
        print("[DEBUG] Adding new user:", username)
        save_users(users)
        print("[DEBUG] Users after save:", users)
        return redirect("/login")
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect("/dashboard")

    if request.method == "POST":
        users = load_users()
        login_email = request.form.get("username", "").strip().lower()
        for u in users:
            if u["username"].strip().lower() == login_email and u["password"] == request.form["password"]:
                session["user"] = u["username"]
                # Keep buddy email synced to the identity used to log in.
                update_user_stats(session["user"], {"buddy_email": session["user"]})
                return redirect(url_for("dashboard", auth="1"))
        return render_template("login.html", error="Invalid username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return render_template("logout.html")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    return render_template("dashboard.html", login_email=session.get("user", ""))


@app.before_request
def enforce_auth_for_protected_routes():
    path = request.path or "/"

    if path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return None

    if "user" not in session:
        return redirect("/login")

    return None


# ---------- INPUT ----------
@app.route("/input", methods=["GET", "POST"])
def input_page():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        count = max(1, int(request.form.get("numSubjects", 1)))
        selected_tier = request.form.get("pomodoroTier", "standard")
        study_minutes, break_minutes = POMODORO_TIERS.get(selected_tier, POMODORO_TIERS["standard"])
        accountability_enabled = request.form.get("accountabilityEnabled") == "on"
        buddy_email = str(request.form.get("buddyEmail", "")).strip() or session.get("user", "").strip()
        hard_mode = request.form.get("hardMode") == "on"
        baseline_energy = int(request.form.get("baselineEnergy", 3))
        sleep_start = request.form.get("sleepStart", "23:00")
        sleep_end = request.form.get("sleepEnd", "07:00")

        subjects = []
        for i in range(1, count + 1):
            subjects.append({
                "name": request.form.get(f"sub{i}", ""),
                "difficulty": request.form.get(f"diff{i}", "easy"),
                "topics": int(request.form.get(f"topics{i}", 1))
            })

        time_slots = []
        for key in request.form:
            if key.startswith("start"):
                index = key.replace("start", "")
                start = convert_time(request.form[f"start{index}"])
                end = convert_time(request.form[f"end{index}"])
                if end < start:
                    end += 24
                time_slots.append((start, end))

        time_slots.sort(key=lambda slot: slot[0])

        # Put harder subjects earlier when historical energy signal suggests better focus.
        subjects.sort(
            key=lambda s: {"hard": 0, "medium": 1, "easy": 2}.get(str(s.get("difficulty", "easy")).lower(), 2)
        )

        schedule = generate_schedule(
            subjects,
            time_slots,
            study_minutes=study_minutes,
            break_minutes=break_minutes
        )

        recovery = build_recovery_plan(session.get("user"), sleep_start, sleep_end)
        extra_blocks = int(recovery.get("extra_blocks", 0))
        if extra_blocks > 0:
            first_subject = next((s.get("name", "Recovery") for s in subjects if s.get("name")), "Recovery")
            current_recovery_start = time_slots[-1][1] if time_slots else 20
            for _ in range(extra_blocks):
                current_recovery_end = current_recovery_start + (study_minutes / 60)
                schedule.append({
                    "type": "study",
                    "subject": f"Recovery: {first_subject}",
                    "start": current_recovery_start,
                    "end": current_recovery_end,
                })
                current_recovery_start = current_recovery_end

        schedule.sort(key=lambda item: item["start"])

        for item in schedule:
            item["duration_minutes"] = round((item["end"] - item["start"]) * 60)

        session["pomodoro"] = {
            "tier": selected_tier,
            "study_minutes": study_minutes,
            "break_minutes": break_minutes
        }

        for s in schedule:
            s["start"] = format_time(s["start"])
            s["end"] = format_time(s["end"])

        session["raw_schedule"] = copy.deepcopy(schedule)
        session["schedule"] = copy.deepcopy(schedule)
        session["total_study_sessions"] = sum(1 for item in schedule if item.get("type", "study") != "break")
        session["completed_study_sessions"] = 0
        session["completed_history"] = []
        session["focus_mode_requested"] = False
        session["reward_unlock_until"] = None
        session["pomodoro_break_mode"] = False
        session["hard_mode"] = hard_mode
        session["hard_mode_emergency_remaining"] = 0 if hard_mode else HARD_MODE_EMERGENCY_LIMIT
        session["goal_confirmations"] = []
        session["adaptive_revision_queue"] = []
        session["recovery_note"] = recovery.get("note", "")
        session["energy_baseline"] = baseline_energy

        # SAVE PLAN
        plans = load_plans()
        plan_date = str(datetime.now())
        plans.append({
            "user": session["user"],
            "date": plan_date,
            "pomodoro": session.get("pomodoro", {}),
            "schedule": schedule,
            "completed_study_sessions": 0,
            "total_study_sessions": session.get("total_study_sessions", 0),
            "progress_percent": 0,
            "productive_minutes": 0,
            "focus_start_count": 0,
            "focus_stop_count": 0,
            "distraction_attempts": 0,
            "blocked_domain_hits": {},
            "goal_confirmations": [],
            "hard_mode": hard_mode,
            "accountability_enabled": accountability_enabled,
            "buddy_email": buddy_email,
            "energy_baseline": baseline_energy,
            "sleep_window": {"start": sleep_start, "end": sleep_end},
            "confidence_log": [],
            "weak_topics": [],
            "focus_genome_events": [],
            "recovery_note": recovery.get("note", ""),
        })
        save_plans(plans)
        session["current_plan_date"] = plan_date
        update_user_stats(
            session["user"],
            {
                "accountability_enabled": accountability_enabled,
                "buddy_email": buddy_email,
            }
        )
        update_energy_map_for_user(session["user"], baseline_energy)

        return redirect("/schedule")

    return render_template("input.html", login_email=session.get("user", ""))


# ---------- PAGES ----------
@app.route("/schedule")
def schedule():
    if "user" not in session:
        return redirect("/login")

    pomodoro = session.get("pomodoro", {"tier": "standard", "study_minutes": 50, "break_minutes": 10})
    return render_template("schedule.html", schedule=session.get("raw_schedule", session.get("schedule", [])), pomodoro=pomodoro)

@app.route("/progress")
def progress():
    if "user" not in session:
        return redirect("/login")

    study_only = [
        item for item in session.get("schedule", [])
        if item.get("type", "study") != "break"
    ]
    pomodoro = session.get("pomodoro", {"tier": "standard", "study_minutes": 50, "break_minutes": 10})
    next_session = study_only[0] if study_only else None
    current_study_minutes = (
        next_session.get("duration_minutes", pomodoro["study_minutes"]) if next_session else pomodoro["study_minutes"]
    )
    total_sessions = session.get("total_study_sessions", len(study_only))
    completed_sessions = session.get("completed_study_sessions", 0)
    percent = 0 if total_sessions == 0 else round((completed_sessions / total_sessions) * 100)
    focus_state = get_focus_state_snapshot()
    plans = load_plans()
    user_plans = [p for p in plans if p.get("user") == session.get("user")]
    streak_stats = build_streak_stats(user_plans)
    user_stats = get_user_stats(session.get("user"))
    accountability_summary = build_accountability_summary(session.get("user"))
    xp_to_next_level = max(0, (user_stats["level"] * 120) - user_stats["xp"])
    energy_peak_hour, energy_peak_score = get_energy_peak_hour(session.get("user"))
    current_plan = get_current_plan_for_user(session.get("user"))
    adaptive_queue = (current_plan or {}).get("weak_topics", [])[-3:]

    return render_template(
        "progress.html",
        schedule=study_only,
        pomodoro=pomodoro,
        next_session=next_session,
        current_study_minutes=current_study_minutes,
        completed_sessions=completed_sessions,
        total_sessions=total_sessions,
        percent=percent,
        focus_state=focus_state,
        streak_stats=streak_stats,
        user_stats=user_stats,
        xp_to_next_level=xp_to_next_level,
        accountability_summary=accountability_summary,
        energy_peak_hour=energy_peak_hour,
        energy_peak_score=energy_peak_score,
        recovery_note=(current_plan or {}).get("recovery_note", ""),
        adaptive_queue=adaptive_queue,
    )


@app.route("/focus-mode/start", methods=["POST"])
def start_focus_mode():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    session["focus_mode_requested"] = True
    session["pomodoro_break_mode"] = False

    plans = load_plans()
    for plan in reversed(plans):
        if plan.get("user") == session.get("user") and plan.get("date") == session.get("current_plan_date"):
            plan["focus_start_count"] = int(plan.get("focus_start_count", 0)) + 1
            break
    save_plans(plans)

    return jsonify(get_focus_state_snapshot())


@app.route("/focus-mode/stop", methods=["POST"])
def stop_focus_mode():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    reflection = (payload.get("reflection") or "").strip()

    if not reflection:
        return jsonify({"error": "Goal confirmation required", "requires_confirmation": True}), 400

    session["focus_mode_requested"] = False
    session["pomodoro_break_mode"] = False

    goal_confirmations = session.get("goal_confirmations", [])
    goal_confirmations.append({"time": datetime.now().isoformat(), "reflection": reflection})
    session["goal_confirmations"] = goal_confirmations

    plans = load_plans()
    for plan in reversed(plans):
        if plan.get("user") == session.get("user") and plan.get("date") == session.get("current_plan_date"):
            plan["focus_stop_count"] = int(plan.get("focus_stop_count", 0)) + 1
            plan["distraction_attempts"] = int(plan.get("distraction_attempts", 0)) + 1
            confirmations = plan.get("goal_confirmations", [])
            confirmations.append({"time": datetime.now().isoformat(), "reflection": reflection})
            plan["goal_confirmations"] = confirmations
            break
    save_plans(plans)

    return jsonify(get_focus_state_snapshot())


@app.route("/focus-mode/break-start", methods=["POST"])
def start_break_mode():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    session["pomodoro_break_mode"] = True
    return jsonify(get_focus_state_snapshot())


@app.route("/focus-mode/break-end", methods=["POST"])
def end_break_mode():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    session["pomodoro_break_mode"] = False
    return jsonify(get_focus_state_snapshot())


@app.route("/focus-mode/emergency-use", methods=["POST"])
def use_emergency_break():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    hard_mode = bool(session.get("hard_mode", False))
    remaining = int(session.get("hard_mode_emergency_remaining", HARD_MODE_EMERGENCY_LIMIT))

    if hard_mode and remaining <= 0:
        return jsonify({"ok": False, "error": "Hard mode: emergency breaks exhausted"}), 403

    session["hard_mode_emergency_remaining"] = max(0, remaining - 1)
    return jsonify({
        "ok": True,
        "hard_mode": hard_mode,
        "emergency_break_remaining": session["hard_mode_emergency_remaining"],
    })


@app.route("/focus-state", methods=["GET"])
def focus_state():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify(get_focus_state_snapshot())


@app.route("/complete-session", methods=["POST"])
def complete_session():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    current_schedule = session.get("schedule", [])
    payload = request.get_json(silent=True) or {}
    target_subject = payload.get("subject")
    target_start = payload.get("start")
    target_end = payload.get("end")
    energy_level = payload.get("energy_level")
    confidence_level = payload.get("confidence_level")
    completed_item = None

    for index, item in enumerate(current_schedule):
        if item.get("type", "study") != "break":
            if target_subject and target_start and target_end:
                if (
                    item.get("subject") != target_subject or
                    item.get("start") != target_start or
                    item.get("end") != target_end
                ):
                    continue

            current_schedule.pop(index)
            completed_item = item
            session["completed_study_sessions"] = session.get("completed_study_sessions", 0) + 1
            completed_history = session.get("completed_history", [])
            completed_history.append({"item": item, "index": index})
            session["completed_history"] = completed_history
            session["reward_unlock_until"] = (datetime.now() + timedelta(minutes=REWARD_UNLOCK_MINUTES)).isoformat()
            break

    session["schedule"] = current_schedule
    update_current_plan_progress()

    plans = load_plans()
    earned_xp = 0
    completion_bonus = 0
    for plan in reversed(plans):
        if plan.get("user") == session.get("user") and plan.get("date") == session.get("current_plan_date"):
            if completed_item:
                plan["productive_minutes"] = int(plan.get("productive_minutes", 0)) + int(completed_item.get("duration_minutes", session.get("pomodoro", {}).get("study_minutes", 0)))
                earned_xp = XP_PER_COMPLETED_SESSION

                completed = int(plan.get("completed_study_sessions", 0))
                total = int(plan.get("total_study_sessions", 0))
                if total > 0 and completed >= total and not plan.get("completion_bonus_awarded"):
                    completion_bonus = XP_PER_COMPLETED_SESSION * XP_STREAK_BONUS_MULTIPLIER
                    plan["completion_bonus_awarded"] = True

                earned_xp += completion_bonus

                try:
                    confidence_int = int(str(confidence_level or "3"))
                except (TypeError, ValueError):
                    confidence_int = 3

                confidence_int = max(1, min(5, confidence_int))
                confidence_log = plan.get("confidence_log", [])
                confidence_log.append({
                    "subject": completed_item.get("subject", ""),
                    "confidence": confidence_int,
                    "time": datetime.now().isoformat(),
                })
                plan["confidence_log"] = confidence_log

                if confidence_int <= 2:
                    weak_topics = plan.get("weak_topics", [])
                    weak_topics.append({
                        "subject": completed_item.get("subject", ""),
                        "confidence": confidence_int,
                        "next_revision": (datetime.now() + timedelta(days=2)).isoformat(),
                    })
                    plan["weak_topics"] = weak_topics

            plan["xp_earned"] = int(plan.get("xp_earned", 0)) + earned_xp
            break
    save_plans(plans)

    update_energy_map_for_user(session.get("user"), energy_level)

    user_stats = get_user_stats(session.get("user"))
    new_xp = user_stats["xp"] + earned_xp
    new_level = level_from_xp(new_xp)
    update_user_stats(session.get("user"), {"xp": new_xp, "level": new_level})

    study_only = [item for item in current_schedule if item.get("type", "study") != "break"]
    total_sessions = session.get("total_study_sessions", len(study_only))
    completed_sessions = session.get("completed_study_sessions", 0)
    percent = 0 if total_sessions == 0 else round((completed_sessions / total_sessions) * 100)
    next_session = study_only[0] if study_only else None

    if next_session and "duration_minutes" not in next_session:
        next_session["duration_minutes"] = session.get("pomodoro", {}).get("study_minutes", 50)

    current_pomodoro = session.get("pomodoro", {})
    current_study_minutes = next_session.get("duration_minutes", current_pomodoro.get("study_minutes", 50)) if next_session else current_pomodoro.get("study_minutes", 50)

    return jsonify({
        "completed_sessions": completed_sessions,
        "total_sessions": total_sessions,
        "percent": percent,
        "next_session": next_session,
        "current_study_minutes": current_study_minutes,
        "can_undo": bool(session.get("completed_history")),
        "remaining_subjects": [item.get("subject", "") for item in study_only],
        "focus_state": get_focus_state_snapshot(),
        "xp_earned": earned_xp,
        "completion_bonus": completion_bonus,
        "xp_total": new_xp,
        "level": new_level,
        "adaptive_hint": "Low-confidence topic added to 48h revision loop." if str(confidence_level) in ["1", "2"] else "Great momentum. Keep going.",
    })


@app.route("/undo-session", methods=["POST"])
def undo_session():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    current_schedule = session.get("schedule", [])
    completed_history = session.get("completed_history", [])

    if not completed_history:
        total_sessions = session.get("total_study_sessions", len(current_schedule))
        completed_sessions = session.get("completed_study_sessions", 0)
        percent = 0 if total_sessions == 0 else round((completed_sessions / total_sessions) * 100)
        next_session = next((item for item in current_schedule if item.get("type", "study") != "break"), None)
        current_pomodoro = session.get("pomodoro", {})
        current_study_minutes = next_session.get("duration_minutes", current_pomodoro.get("study_minutes", 50)) if next_session else current_pomodoro.get("study_minutes", 50)

        return jsonify({
            "completed_sessions": completed_sessions,
            "total_sessions": total_sessions,
            "percent": percent,
            "next_session": next_session,
            "current_study_minutes": current_study_minutes,
            "can_undo": False,
            "restored_item": None,
            "remaining_subjects": [item.get("subject", "") for item in current_schedule if item.get("type", "study") != "break"],
            "focus_state": get_focus_state_snapshot(),
        })

    last_completed = completed_history.pop()
    restored_item = last_completed.get("item")
    restore_index = last_completed.get("index", 0)

    if restored_item:
        restore_index = max(0, min(restore_index, len(current_schedule)))
        current_schedule.insert(restore_index, restored_item)
        session["completed_study_sessions"] = max(0, session.get("completed_study_sessions", 0) - 1)

    session["schedule"] = current_schedule
    session["completed_history"] = completed_history
    update_current_plan_progress()

    plans = load_plans()
    xp_removed = 0
    removed_minutes = 0
    if restored_item:
        removed_minutes = int(restored_item.get("duration_minutes", session.get("pomodoro", {}).get("study_minutes", 0)))

    for plan in reversed(plans):
        if plan.get("user") == session.get("user") and plan.get("date") == session.get("current_plan_date"):
            if restored_item:
                plan["productive_minutes"] = max(0, int(plan.get("productive_minutes", 0)) - removed_minutes)
                xp_removed = XP_PER_COMPLETED_SESSION
                plan["xp_earned"] = max(0, int(plan.get("xp_earned", 0)) - xp_removed)
            break
    save_plans(plans)

    user_stats = get_user_stats(session.get("user"))
    next_xp = max(0, user_stats["xp"] - xp_removed)
    next_level = level_from_xp(next_xp)
    update_user_stats(session.get("user"), {"xp": next_xp, "level": next_level})

    study_only = [item for item in current_schedule if item.get("type", "study") != "break"]
    total_sessions = session.get("total_study_sessions", len(study_only))
    completed_sessions = session.get("completed_study_sessions", 0)
    percent = 0 if total_sessions == 0 else round((completed_sessions / total_sessions) * 100)
    next_session = study_only[0] if study_only else None

    if next_session and "duration_minutes" not in next_session:
        next_session["duration_minutes"] = session.get("pomodoro", {}).get("study_minutes", 50)

    current_pomodoro = session.get("pomodoro", {})
    current_study_minutes = next_session.get("duration_minutes", current_pomodoro.get("study_minutes", 50)) if next_session else current_pomodoro.get("study_minutes", 50)

    return jsonify({
        "completed_sessions": completed_sessions,
        "total_sessions": total_sessions,
        "percent": percent,
        "next_session": next_session,
        "current_study_minutes": current_study_minutes,
        "can_undo": bool(completed_history),
        "restored_item": restored_item,
        "remaining_subjects": [item.get("subject", "") for item in study_only],
        "focus_state": get_focus_state_snapshot(),
        "xp_total": next_xp,
        "level": next_level,
    })

@app.route("/history")
def history():
    if "user" not in session:
        return redirect("/login")

    plans = load_plans()
    user_plans = [p for p in plans if p["user"] == session["user"]]

    history_plans = []
    for plan in user_plans:
        pomodoro = plan.get("pomodoro", {})
        study_minutes = 0
        break_minutes = 0
        study_sessions = 0
        break_sessions = 0

        for item in plan.get("schedule", []):
            item_type = item.get("type", "study")
            duration_minutes = item.get("duration_minutes")

            if duration_minutes is None:
                if item_type == "break" or item.get("subject") == "Break":
                    duration_minutes = pomodoro.get("break_minutes", 0)
                else:
                    duration_minutes = pomodoro.get("study_minutes", 0)

            duration_minutes = int(duration_minutes)

            if item_type == "break" or item.get("subject") == "Break":
                break_minutes += duration_minutes
                break_sessions += 1
            else:
                study_minutes += duration_minutes
                study_sessions += 1

        normalized_plan = {
            **plan,
            "study_minutes": study_minutes,
            "break_minutes": break_minutes,
            "study_sessions": study_sessions,
            "break_sessions": break_sessions,
            "completed_study_sessions": min(max(int(plan.get("completed_study_sessions", 0)), 0), study_sessions),
            "total_study_sessions": int(plan.get("total_study_sessions", study_sessions)),
            "progress_percent": int(
                plan.get(
                    "progress_percent",
                    0 if study_sessions == 0 else round((min(max(int(plan.get("completed_study_sessions", 0)), 0), study_sessions) / study_sessions) * 100)
                )
            ),
        }
        normalized_plan["reflection"] = build_reflection(normalized_plan)
        history_plans.append(normalized_plan)

    subject_counter = Counter()
    for plan in user_plans:
        for item in plan.get("schedule", []):
            if item.get("type") == "break":
                continue
            subject = item.get("subject", "").strip()
            if subject:
                subject_counter[subject] += 1

    chart_labels = list(subject_counter.keys())
    chart_data = list(subject_counter.values())
    streak_stats = build_streak_stats(history_plans)
    analytics = build_analytics_snapshot(session.get("user"))
    user_stats = get_user_stats(session.get("user"))
    focus_genome = build_focus_genome(session.get("user"))

    return render_template(
        "history.html",
        plans=history_plans,
        chart_labels=chart_labels,
        chart_data=chart_data,
        streak_stats=streak_stats,
        analytics=analytics,
        user_stats=user_stats,
        focus_genome=focus_genome,
    )


@app.route("/analytics")
def analytics():
    if "user" not in session:
        return redirect("/login")

    analytics_data = build_analytics_snapshot(session.get("user"))
    return render_template("analytics.html", analytics=analytics_data)


@app.route("/accountability")
def accountability():
    if "user" not in session:
        return redirect("/login")

    stats = get_user_stats(session.get("user"))
    summary = build_accountability_summary(session.get("user"))
    live_room = build_live_room_snapshot(session.get("user"))
    return render_template("accountability.html", stats=stats, summary=summary, live_room=live_room)


@app.route("/live-room/status")
def live_room_status():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify(build_live_room_snapshot(session.get("user")))


@app.route("/extension-setup")
def extension_setup():
    if "user" not in session:
        return redirect("/login")

    return render_template("extension_setup.html")


@app.route("/download-extension")
def download_extension():
    if "user" not in session:
        return redirect("/login")

    extension_dir = os.path.join(app.root_path, "focus-extension")
    if not os.path.isdir(extension_dir):
        return jsonify({"error": "Extension package not found"}), 404

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(extension_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(file_path, extension_dir)
                archive.write(file_path, arcname=os.path.join("focus-extension", relative_path))

    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="smart-study-focus-extension.zip",
    )


@app.route("/manifest.webmanifest")
def web_manifest():
    return send_from_directory(os.path.join(app.root_path, "static"), "manifest.webmanifest", mimetype="application/manifest+json")


@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory(os.path.join(app.root_path, "static"), "service-worker.js", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/pwa-icon.png")
def pwa_icon():
    return send_from_directory(os.path.join(app.root_path, "focus-extension", "icons"), "icon.png", mimetype="image/png")


@app.route("/analytics/domain-hit", methods=["POST"])
def analytics_domain_hit():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    domain = str(payload.get("domain", "")).strip().lower()
    if not domain:
        return jsonify({"ok": False, "error": "Missing domain"}), 400

    plans = load_plans()
    for plan in reversed(plans):
        if plan.get("user") == session.get("user") and plan.get("date") == session.get("current_plan_date"):
            hits = plan.get("blocked_domain_hits", {})
            hits[domain] = int(hits.get(domain, 0)) + 1
            plan["blocked_domain_hits"] = hits
            events = plan.get("focus_genome_events", [])
            events.append({
                "domain": domain,
                "subject": get_active_subject_name(),
                "hour": datetime.now().hour,
                "weekday": datetime.now().strftime("%A"),
                "time": datetime.now().isoformat(),
            })
            plan["focus_genome_events"] = events
            break
    save_plans(plans)

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)