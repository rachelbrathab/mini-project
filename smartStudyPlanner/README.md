# Serenra

Serenra is a Flask web app that helps students build study schedules, protect focus time, and track learning progress.

## Features

- Landing page at `/` with modern hero + feature highlights
- User signup/login/logout with session-based auth
- Dedicated auth routes: `/login`, `/signup`
- Post-login dashboard route: `/dashboard`
- Protected planner routes for authenticated users
- Custom study-plan generation from:
	- Subjects and topic counts
	- Available time slots
	- Pomodoro tiers (`light`, `standard`, `deep`)
- Auto-generated schedule with study and break sessions
- Progress tracking with:
	- Complete session
	- Undo last completed session
	- Percent complete and next session
- Study history dashboard with subject distribution chart
- Browser extension integration for distraction blocking

## Tech Stack

- Python 3.11+
- Flask
- Gunicorn (production server)
- Server-side rendered HTML templates
- JSON file storage for users/plans

## Project Structure

```text
smartStudyPlanner/
	app.py                    # Flask app and routes
	src/planner.py            # Schedule generation logic
	templates/                # Jinja templates (pages)
	static/                   # CSS and client-side JS
	data/                     # JSON storage (users/plans)
	requirements.txt
	pyproject.toml
```

## Quick Start (Local)

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## How to Use

1. Open `/` to access the Serenra landing page.
2. Sign up at `/signup` or log in at `/login`.
3. After login, you are redirected to `/dashboard`.
4. Continue to planner input (`/input`) and generate a schedule.
5. View schedule at `/schedule` and track completion at `/progress`.
6. Review history at `/history` and insights at `/analytics`.

## Deployment

### Can this be deployed on GitHub Pages?

No. GitHub Pages only serves static files, while this app needs a Python server.

### Recommended deployment: Render

This repo includes a root-level `render.yaml` with:

- `buildCommand: pip install -r requirements.txt`
- `startCommand: gunicorn app:app`
- `rootDir: smartStudyPlanner`
- Python version pinning (`PYTHON_VERSION`)

Deploy steps:

1. Push this repository to GitHub.
2. In Render, create a new Web Service from that repo.
3. Render auto-detects `render.yaml` from the repository root.
4. Deploy.

## Environment Variables

- `FLASK_SECRET_KEY`: recommended for production session security.

Note: the current app sets a hardcoded secret in `app.py`. For production, update the app to read the secret from environment variables.

## Data Storage Notes

Current persistence uses local JSON files:

- `data/users.json`
- `data/plans.json`
- `data/user_stats.json`

On free/ephemeral hosting, local disk can reset on redeploy/restart. For durable production data, migrate to a database (for example SQLite or Postgres).

## Troubleshooting

- If `ModuleNotFoundError` appears, re-activate your venv and reinstall dependencies.
- If port conflicts occur locally, stop the conflicting process or set `PORT` before running.
- If login/session behavior is inconsistent in production, verify secret key configuration.

## Future Improvements

- Replace JSON storage with a real database
- Hash passwords instead of storing plain text
- Add automated tests for route and planner logic
- Move secret key handling fully to environment variables

