# Mini Project

This repository is the parent project workspace for the Smart Study Planner system.

It includes:

- A Flask web app for planning and tracking study sessions
- A Chrome focus extension that enforces study-time browsing rules

## Repository Layout

```text
Mini Project/
	README.md
	smart_study_planner/
		app.py
		requirements.txt
		pyproject.toml
		data/
		src/
		static/
		templates/
		focus-extension/
```

## Main Application

The core app lives in `smart_study_planner`.

Features include:

- User login/signup
- Study plan generation based on subjects and available time
- Pomodoro modes (light, standard, deep)
- Progress tracking and undo
- Focus mode controls
- Analytics and accountability pages

## Local Setup

### 1) Create and activate a Python virtual environment

```bash
cd smart_study_planner
python3 -m venv ../.venv
source ../.venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Run the app

```bash
python app.py
```

If port `5000` is busy:

```bash
PORT=5001 python app.py
```

Open in browser:

`http://127.0.0.1:5000` (or the port you chose)

## Chrome Focus Extension (Local)

Extension source is in `smart_study_planner/focus-extension`.

To load it:

1. Open Chrome and go to `chrome://extensions`
2. Enable Developer Mode
3. Click Load unpacked
4. Select `smart_study_planner/focus-extension`
5. Reload after extension code changes

## Data Files

The app stores local data in JSON files:

- `smart_study_planner/data/users.json`
- `smart_study_planner/data/plans.json`
- `smart_study_planner/data/user_stats.json` (created automatically when needed)

## Notes

- Keep `.venv` out of version control.
- This project currently uses local JSON storage, so it is best for local/demo use unless migrated to a database.
- The detailed app-specific documentation is in `smart_study_planner/README.md`.
