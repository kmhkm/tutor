"""
Opus Tuition — Tutor Pipeline Web Application
FastAPI + PostgreSQL + Jinja2 templates

Local dev:  uses SQLite automatically if DATABASE_URL is not set
Production: set DATABASE_URL environment variable (Railway provides this automatically)
"""

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os, shutil, uuid, sqlite3
from types import SimpleNamespace
from datetime import datetime
from pathlib import Path

# ── Try to import psycopg2 (PostgreSQL). Fall back to SQLite if not available.
try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except ImportError:
    HAS_PG = False

DATABASE_URL = os.environ.get("DATABASE_URL", "")   # Railway sets this automatically

# If DATABASE_URL starts with postgres:// Railway uses that format — psycopg2 needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = HAS_PG and bool(DATABASE_URL)

app = FastAPI(title="Opus Tuition — Tutor Pipeline")

BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH    = BASE_DIR / "data" / "tutor_pipeline.db"
UPLOAD_DIR.mkdir(exist_ok=True)

app.mount("/static",  StaticFiles(directory=BASE_DIR / "static"),  name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR),           name="uploads")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ── Pipeline stages ────────────────────────────────────────────
STAGES = [
    (1, "Applied",          "Tutor Applies"),
    (2, "Screening",        "Auto Screening"),
    (3, "Interview",        "Interview"),
    (4, "Contract Signing", "Contract Signing"),
    (5, "Training",         "Training"),
    (6, "Active",           "Activation → Profile Live"),
]

STAGE_COLORS = {
    1: "#2E86AB", 2: "#2E86AB", 3: "#2E86AB",
    4: "#2E86AB", 5: "#2E86AB", 6: "#1B6B4A",
}


# ══════════════════════════════════════════════════════════════
# DATABASE LAYER — works with both PostgreSQL and SQLite
# ══════════════════════════════════════════════════════════════

class DB:
    """
    Thin wrapper so the rest of the code doesn't care whether
    it's talking to PostgreSQL or SQLite.

    PostgreSQL uses %s placeholders; SQLite uses ?.
    PostgreSQL rows are dicts; SQLite rows are sqlite3.Row objects.
    This class normalises both into plain dicts.
    """

    @staticmethod
    def _connect():
        if USE_POSTGRES:
            conn = psycopg2.connect(DATABASE_URL)
            return conn, "%s"        # PG placeholder
        else:
            DB_PATH.parent.mkdir(exist_ok=True)
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn, "?"         # SQLite placeholder

    @staticmethod
    def _to_dict(row):
        if row is None:
            return None
        if isinstance(row, dict):
            return SimpleNamespace(**row)
        return SimpleNamespace(**dict(row))   # sqlite3.Row → dot-accessible object

    @classmethod
    def execute(cls, sql: str, params: tuple = ()):
        """Run INSERT / UPDATE / DELETE."""
        conn, ph = cls._connect()
        sql = sql.replace("?", ph)
        try:
            if USE_POSTGRES:
                cur = conn.cursor()
                cur.execute(sql, params)
                conn.commit()
            else:
                conn.execute(sql, params)
                conn.commit()
        finally:
            conn.close()

    @classmethod
    def fetchone(cls, sql: str, params: tuple = ()):
        """Run SELECT and return one row as a dict."""
        conn, ph = cls._connect()
        sql = sql.replace("?", ph)
        try:
            if USE_POSTGRES:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(sql, params)
                row = cur.fetchone()
                return SimpleNamespace(**dict(row)) if row else None
            else:
                row = conn.execute(sql, params).fetchone()
                return cls._to_dict(row)
        finally:
            conn.close()

    @classmethod
    def fetchall(cls, sql: str, params: tuple = ()):
        """Run SELECT and return all rows as a list of dicts."""
        conn, ph = cls._connect()
        sql = sql.replace("?", ph)
        try:
            if USE_POSTGRES:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(sql, params)
                return [SimpleNamespace(**dict(r)) for r in cur.fetchall()]
            else:
                rows = conn.execute(sql, params).fetchall()
                return [cls._to_dict(r) for r in rows]  # returns SimpleNamespace list
        finally:
            conn.close()

    @classmethod
    def executescript(cls, sql: str):
        """Run multiple statements (init only)."""
        conn, _ = cls._connect()
        try:
            if USE_POSTGRES:
                cur = conn.cursor()
                cur.execute(sql)
                conn.commit()
            else:
                conn.executescript(sql)
                conn.commit()
        finally:
            conn.close()


def init_db():
    """Create tables if they don't exist yet."""
    if USE_POSTGRES:
        sql = """
            CREATE TABLE IF NOT EXISTS tutors (
                id               TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                email            TEXT NOT NULL,
                phone            TEXT,
                subject          TEXT NOT NULL,
                level            TEXT NOT NULL,
                experience       TEXT,
                about            TEXT,
                cv_filename      TEXT,
                stage            INTEGER DEFAULT 1,
                stage_label      TEXT DEFAULT 'Applied',
                screening_result TEXT,
                interview_date   TEXT,
                interview_notes  TEXT,
                interview_result TEXT,
                contract_sent    INTEGER DEFAULT 0,
                contract_signed  INTEGER DEFAULT 0,
                training_done    INTEGER DEFAULT 0,
                profile_live     INTEGER DEFAULT 0,
                created_at       TIMESTAMP DEFAULT NOW(),
                updated_at       TIMESTAMP DEFAULT NOW(),
                notes            TEXT
            );
            CREATE TABLE IF NOT EXISTS activity_log (
                id         SERIAL PRIMARY KEY,
                tutor_id   TEXT,
                action     TEXT,
                detail     TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """
    else:
        sql = """
            CREATE TABLE IF NOT EXISTS tutors (
                id               TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                email            TEXT NOT NULL,
                phone            TEXT,
                subject          TEXT NOT NULL,
                level            TEXT NOT NULL,
                experience       TEXT,
                about            TEXT,
                cv_filename      TEXT,
                stage            INTEGER DEFAULT 1,
                stage_label      TEXT DEFAULT 'Applied',
                screening_result TEXT,
                interview_date   TEXT,
                interview_notes  TEXT,
                interview_result TEXT,
                contract_sent    INTEGER DEFAULT 0,
                contract_signed  INTEGER DEFAULT 0,
                training_done    INTEGER DEFAULT 0,
                profile_live     INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                notes            TEXT
            );
            CREATE TABLE IF NOT EXISTS activity_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tutor_id   TEXT,
                action     TEXT,
                detail     TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """
    DB.executescript(sql)

init_db()
print(f"  DB backend: {'PostgreSQL' if USE_POSTGRES else 'SQLite (local dev)'}")


# ── Helpers ────────────────────────────────────────────────────

def log_activity(tutor_id: str, action: str, detail: str = ""):
    DB.execute(
        "INSERT INTO activity_log (tutor_id, action, detail) VALUES (?,?,?)",
        (tutor_id, action, detail)
    )

def auto_screen(tutor: dict):
    subject    = str(tutor["subject"]).lower()
    experience = str(tutor["experience"]).lower()

    valid_subjects = ["mathematics", "english", "science", "chemistry", "physics", "biology"]
    if not any(s in subject for s in valid_subjects):
        return "Failed", f"Subject '{tutor['subject']}' is not currently offered by Opus Tuition."

    low_exp = ["no experience", "0 year", "none", "fresher"]
    if any(k in experience for k in low_exp):
        return "Failed", "Minimum 1 year tutoring experience required."

    return "Passed", "All automatic checks passed."

def get_stage_label(stage: int) -> str:
    for s, label, _ in STAGES:
        if s == stage:
            return label
    return "Unknown"

def updated_at_sql() -> str:
    """NOW() for PG, CURRENT_TIMESTAMP for SQLite."""
    return "NOW()" if USE_POSTGRES else "CURRENT_TIMESTAMP"


# ══════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, stage: str = "all", search: str = ""):
    query  = "SELECT * FROM tutors WHERE 1=1"
    params = []

    if stage != "all":
        query += " AND stage_label = ?"
        params.append(stage)
    if search:
        query += " AND (name ILIKE ? OR email ILIKE ? OR subject ILIKE ?)" if USE_POSTGRES \
             else " AND (name LIKE ? OR email LIKE ? OR subject LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    query += " ORDER BY updated_at DESC"

    tutors = DB.fetchall(query, tuple(params))

    counts = {}
    for _, label, _ in STAGES:
        row = DB.fetchone("SELECT COUNT(*) AS c FROM tutors WHERE stage_label=?", (label,))
        counts[label] = row.c if row else 0
    row = DB.fetchone("SELECT COUNT(*) AS c FROM tutors", ())
    counts["all"] = row.c if row else 0

    return templates.TemplateResponse("dashboard.html", {
        "request":       request,
        "tutors":        tutors,
        "stages":        STAGES,
        "counts":        counts,
        "current_stage": stage,
        "search":        search,
        "stage_colors":  STAGE_COLORS,
    })


@app.get("/apply", response_class=HTMLResponse)
async def apply_form(request: Request):
    return templates.TemplateResponse("apply.html", {"request": request})


@app.post("/apply")
async def apply_submit(
    request:    Request,
    name:       str        = Form(...),
    email:      str        = Form(...),
    phone:      str        = Form(""),
    subject:    str        = Form(...),
    level:      str        = Form(...),
    experience: str        = Form(""),
    about:      str        = Form(""),
    cv:         UploadFile = File(None),
):
    tutor_id    = str(uuid.uuid4())[:8].upper()
    cv_filename = None

    if cv and cv.filename:
        ext         = Path(cv.filename).suffix
        cv_filename = f"{tutor_id}{ext}"
        with open(UPLOAD_DIR / cv_filename, "wb") as f:
            shutil.copyfileobj(cv.file, f)

    screen_result, screen_notes = auto_screen({"subject": subject, "experience": experience})

    DB.execute("""
        INSERT INTO tutors
          (id, name, email, phone, subject, level, experience, about,
           cv_filename, stage, stage_label, screening_result, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (tutor_id, name, email, phone, subject, level, experience, about,
          cv_filename, 2, "Screening", screen_result,
          f"Auto-screening: {screen_notes}"))

    log_activity(tutor_id, "Application received",         f"Subject: {subject}, Level: {level}")
    log_activity(tutor_id, f"Auto-screening: {screen_result}", screen_notes)

    return RedirectResponse(f"/apply/success?id={tutor_id}&result={screen_result}", status_code=303)


@app.get("/apply/success", response_class=HTMLResponse)
async def apply_success(request: Request, id: str, result: str):
    return templates.TemplateResponse("apply_success.html", {
        "request": request, "tutor_id": id, "result": result
    })


@app.get("/tutor/{tutor_id}", response_class=HTMLResponse)
async def tutor_detail(request: Request, tutor_id: str):
    tutor = DB.fetchone("SELECT * FROM tutors WHERE id=?", (tutor_id,))
    if not tutor:
        raise HTTPException(404, "Tutor not found")
    activity = DB.fetchall(
        "SELECT * FROM activity_log WHERE tutor_id=? ORDER BY created_at DESC", (tutor_id,)
    )
    return templates.TemplateResponse("tutor_detail.html", {
        "request":  request,
        "tutor":    tutor,
        "activity": activity,
        "stages":   STAGES,
    })


@app.post("/tutor/{tutor_id}/interview")
async def set_interview(
    tutor_id:         str,
    interview_date:   str = Form(...),
    interview_notes:  str = Form(""),
    interview_result: str = Form(...),
):
    stage = 4 if interview_result == "Passed" else 3
    label = get_stage_label(stage) if interview_result == "Passed" else "Interview"
    ts    = updated_at_sql()

    DB.execute(f"""
        UPDATE tutors SET
            interview_date=?, interview_notes=?, interview_result=?,
            stage=?, stage_label=?, updated_at={ts}
        WHERE id=?
    """, (interview_date, interview_notes, interview_result, stage, label, tutor_id))
    log_activity(tutor_id, f"Interview: {interview_result}", interview_notes)
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.post("/tutor/{tutor_id}/contract")
async def set_contract(tutor_id: str, action: str = Form(...)):
    ts = updated_at_sql()
    if action == "sent":
        DB.execute(f"UPDATE tutors SET contract_sent=1, updated_at={ts} WHERE id=?", (tutor_id,))
        log_activity(tutor_id, "Contract sent to tutor")
    elif action == "signed":
        DB.execute(f"""
            UPDATE tutors SET contract_signed=1, stage=5, stage_label='Training',
            updated_at={ts} WHERE id=?
        """, (tutor_id,))
        log_activity(tutor_id, "Contract signed — moved to Training")
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.post("/tutor/{tutor_id}/training")
async def set_training(tutor_id: str, action: str = Form(...)):
    ts = updated_at_sql()
    DB.execute(f"""
        UPDATE tutors SET training_done=1, stage=6, stage_label='Active',
        updated_at={ts} WHERE id=?
    """, (tutor_id,))
    log_activity(tutor_id, "Training completed — moved to Activation")
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.post("/tutor/{tutor_id}/activate")
async def activate_tutor(tutor_id: str):
    ts = updated_at_sql()
    DB.execute(f"""
        UPDATE tutors SET profile_live=1, stage=6, stage_label='Active',
        updated_at={ts} WHERE id=?
    """, (tutor_id,))
    log_activity(tutor_id, "Profile activated — tutor is now LIVE")
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.post("/tutor/{tutor_id}/notes")
async def update_notes(tutor_id: str, notes: str = Form(...)):
    ts = updated_at_sql()
    DB.execute(f"UPDATE tutors SET notes=?, updated_at={ts} WHERE id=?", (notes, tutor_id))
    log_activity(tutor_id, "Notes updated")
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.get("/cv/{filename}")
async def download_cv(filename: str):
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=filename)
