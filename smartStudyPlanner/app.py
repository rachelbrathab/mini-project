from flask import Flask, request, render_template, redirect, url_for, session
from flask import jsonify
from src.planner import generate_schedule, format_time
import json
import copy
import os
from datetime import datetime, timedelta, date
from collections import Counter

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret123")

POMODORO_TIERS = {
    "light": (25, 5),
    "standard": (50, 10),
    "deep": (90, 15)
}

DEFAULT_BLOCKED_DOMAINS = [
    "netflix.com",
    "youtube.com",
    "instagram.com",
    "primevideo.com",
]

REWARD_UNLOCK_MINUTES = 5

SUBJECT_RELAX_RULES = {
    "math": ["netflix.com", "primevideo.com"],
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
}


# ---------- FILE HELPERS ----------
def load_users():
    try:
        with open("data/users.json") as f:
            users = json.load(f)
            return normalize_users(users)
    except:
        return []

def save_users(data):
    with open("data/users.json", "w") as f:
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
        with open("data/plans.json") as f:
            return json.load(f)
    except:
        return []

def save_plans(data):
    with open("data/plans.json", "w") as f:
        json.dump(data, f, indent=4)


def load_user_stats():
    try:
        with open("data/user_stats.json") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except:
        return {}


def save_user_stats(data):
    with open("data/user_stats.json", "w") as f:
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
        **progress,
    }


def convert_time(t):
    h, m = map(int, t.split(":"))
    return h + m / 60


# ---------- AUTH ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users = load_users()
        username = request.form["username"].strip()

        if any(u["username"].lower() == username.lower() for u in users):
            return render_template("signup.html", error="That username already exists.")

        users.append({
            "username": username,
            "password": request.form["password"]
        })
        save_users(users)
        return redirect("/login")
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        users = load_users()
        for u in users:
            if u["username"] == request.form["username"] and u["password"] == request.form["password"]:
                session["user"] = u["username"]
                # Keep buddy email synced to the identity used to log in.
                update_user_stats(session["user"], {"buddy_email": session["user"]})
                return redirect("/")
        return render_template("login.html", error="Invalid username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------- INPUT ----------
@app.route("/", methods=["GET", "POST"])
def input_page():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        count = max(1, int(request.form.get("numSubjects", 1)))
        selected_tier = request.form.get("pomodoroTier", "standard")
        study_minutes, break_minutes = POMODORO_TIERS.get(selected_tier, POMODORO_TIERS["standard"])
        accountability_enabled = request.form.get("accountabilityEnabled") == "on"
        buddy_email = session.get("user", "").strip()
        hard_mode = request.form.get("hardMode") == "on"

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

        schedule = generate_schedule(
            subjects,
            time_slots,
            study_minutes=study_minutes,
            break_minutes=break_minutes
        )
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

        return redirect("/schedule")

    return render_template("input.html", login_email=session.get("user", ""))


# ---------- PAGES ----------
@app.route("/schedule")
def schedule():
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
    current_schedule = session.get("schedule", [])
    payload = request.get_json(silent=True) or {}
    target_subject = payload.get("subject")
    target_start = payload.get("start")
    target_end = payload.get("end")
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
            plan["xp_earned"] = int(plan.get("xp_earned", 0)) + earned_xp
            break
    save_plans(plans)

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
    })


@app.route("/undo-session", methods=["POST"])
def undo_session():
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

    return render_template(
        "history.html",
        plans=history_plans,
        chart_labels=chart_labels,
        chart_data=chart_data,
        streak_stats=streak_stats,
        analytics=analytics,
        user_stats=user_stats,
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
    return render_template("accountability.html", stats=stats, summary=summary)


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
            break
    save_plans(plans)

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)