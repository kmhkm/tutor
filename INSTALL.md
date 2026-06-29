# Installation & Deployment Guide
## Opus Tuition — Tutor Pipeline Web App (PostgreSQL Edition)

---

## How the database works

| Environment | Database used | How |
|---|---|---|
| Your laptop (local) | SQLite — automatic, no setup | No DATABASE_URL set → uses a local file |
| Railway (production) | PostgreSQL — persistent, reliable | Railway sets DATABASE_URL automatically |

You don't have to configure anything. The app detects which one to use.

---

## PART A — Run locally on your laptop

### Step 1 — Make sure you have Python 3.10+
```bash
python --version
```
Should show Python 3.10 or higher.

### Step 2 — Set up the project folder

```
tutor_app/
├── main.py
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── apply.html
│   ├── apply_success.html
│   └── tutor_detail.html
└── static/
    ├── css/
    └── js/
```

### Step 3 — Install packages
Open terminal / Command Prompt and run:
```bash
pip install fastapi uvicorn python-multipart aiofiles jinja2 psycopg2-binary
```

### Step 4 — Start the app
```bash
cd tutor_app
uvicorn main:app --reload
```

You will see:
```
  DB backend: SQLite (local dev)
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Open your browser: **http://localhost:8000**

### Step 5 — Stop the app
Press `Ctrl + C` in the terminal.

---

## PART B — Deploy to Railway (online, PostgreSQL)

Railway is free to start, never sleeps, and provides PostgreSQL automatically.

### Step 1 — Push your code to GitHub

Create a free account at **github.com**, then:
1. Click **New repository** → name it `opus-tuition-pipeline`
2. Upload all your project files (main.py, requirements.txt, templates/, static/)
3. Make sure `requirements.txt` is in the root of the repo

### Step 2 — Sign up at Railway

Go to **railway.app** → click **Login with GitHub**

### Step 3 — Create a new project

1. Click **New Project**
2. Click **Deploy from GitHub repo**
3. Select your `opus-tuition-pipeline` repository
4. Railway will detect it's a Python app automatically

### Step 4 — Add a PostgreSQL database

Inside your Railway project:
1. Click **New** → **Database** → **PostgreSQL**
2. Railway creates the database and adds `DATABASE_URL` to your app automatically
3. No further configuration needed — the app reads it on its own

### Step 5 — Set the start command

In Railway → your web service → **Settings** → **Start Command**:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Step 6 — Deploy

Click **Deploy**. Railway will:
- Install packages from `requirements.txt`
- Start the app
- Give you a public URL like:

```
https://opus-tuition-pipeline.up.railway.app
```

Your app is live. On first visit you will see in the logs:
```
  DB backend: PostgreSQL
```

---

## PART C — What Railway costs

| Plan | Cost | What you get |
|---|---|---|
| Hobby (free trial) | $0 for first 30 days | 512MB RAM, PostgreSQL included |
| Hobby (after trial) | $5/month | Same, ongoing |
| PostgreSQL add-on | Included in the $5 | 1GB storage, persistent |

For a demo or assessment: completely free for 30 days.
For Opus Tuition production use: $5/month total.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: psycopg2` | Run `pip install psycopg2-binary` |
| App starts but shows DB error | Check Railway logs — DATABASE_URL may not be linked |
| `Address already in use` | Run `uvicorn main:app --port 8001` instead |
| CV uploads not persisting on Railway | Expected on free plan — use Railway Volume or S3 for production file storage |
| Database resets | This only happens with SQLite on Railway. PostgreSQL (this setup) persists permanently |

---

## File reference

| File | Purpose |
|---|---|
| `main.py` | All backend logic — auto-detects SQLite vs PostgreSQL |
| `requirements.txt` | Package list — includes psycopg2-binary for PostgreSQL |
| `templates/*.html` | All pages of the app |
| `data/tutor_pipeline.db` | SQLite file — created automatically on local dev only |
| `uploads/` | Uploaded CVs — created automatically |

