# Mini Project

This repository is the parent workspace for Serenra, a smart study planning system.

It includes:

- A Flask web app for planning and tracking study sessions
- A Chrome focus extension that enforces study-time browsing rules

## Repository Layout

```text
Mini Project/
	README.md
	smartStudyPlanner/
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

The core app lives in `smartStudyPlanner`.

Features include:

- Modern landing page (`/`) with Login/Sign Up actions
- User login/signup (`/login`, `/signup`)
- Post-login dashboard (`/dashboard`)
- Study plan generation based on subjects and available time
- Pomodoro modes (light, standard, deep)
- Progress tracking and undo
- Focus mode controls
- Analytics and accountability pages
- Protected routes for planner pages (session-based)

## Local Setup

### 1) Create and activate a Python virtual environment

```bash
cd smartStudyPlanner
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

Extension source is in `smartStudyPlanner/focus-extension`.

To load it:

1. Open Chrome and go to `chrome://extensions`
2. Enable Developer Mode
3. Click Load unpacked
4. Select `smartStudyPlanner/focus-extension`
5. Reload after extension code changes

Note: Local development hosts (`127.0.0.1` / `localhost`) are exempt from extension blocking.

## Data Files

The app stores local data in JSON files:

- `smartStudyPlanner/data/users.json`
- `smartStudyPlanner/data/plans.json`
- `smartStudyPlanner/data/user_stats.json` (created automatically when needed)

## Deploy On Render

This repository includes a root-level `render.yaml` configured for the Flask app in `smartStudyPlanner`.

1. Push changes to GitHub.
2. In Render, click **New +** > **Blueprint**.
3. Connect this repository (`rachelbrathab/mini-project`).
4. Render reads `render.yaml` and creates the web service automatically.

Configured service details:

- `rootDir: smartStudyPlanner`
- `buildCommand: pip install -r requirements.txt`
- `startCommand: gunicorn app:app`
- `FLASK_SECRET_KEY` generated automatically by Render

## Notes

- Keep `.venv` out of version control.
- This project currently uses local JSON storage, so it is best for local/demo use unless migrated to a database.
- The detailed app-specific documentation is in `smartStudyPlanner/README.md`.
