"""
Opus Tuition - Tutor Pipeline Web Application
FastAPI + PostgreSQL + Jinja2 templates

Local development:
- Uses SQLite automatically when no PostgreSQL URL is configured.

Railway production:
- Uses PostgreSQL when DATABASE_URL, POSTGRES_URL, or DATABASE_PRIVATE_URL is set.
"""

import os
import shutil
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:
    import psycopg2
    import psycopg2.extras

    HAS_PG = True
except ImportError:
    HAS_PG = False


DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("DATABASE_PRIVATE_URL")
    or ""
)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = HAS_PG and bool(DATABASE_URL)

app = FastAPI(title="Opus Tuition - Tutor Pipeline")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "data" / "tutor_pipeline.db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


STAGES = [
    (1, "Applied", "Tutor Applies"),
    (2, "Screening", "Auto Screening"),
    (3, "Interview", "Interview"),
    (4, "Contract Signing", "Contract Signing"),
    (5, "Training", "Training"),
    (6, "Active", "Activation -> Profile Live"),
]

STAGE_COLORS = {
    1: "#2E86AB",
    2: "#2E86AB",
    3: "#2E86AB",
    4: "#2E86AB",
    5: "#2E86AB",
    6: "#1B6B4A",
}


class AttrDict(dict):
    """Plain dict with attribute access for existing Jinja templates."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


def normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return value


def normalize_row(row: Any) -> Optional[AttrDict]:
    if row is None:
        return None

    data = dict(row)
    return AttrDict({key: normalize_value(value) for key, value in data.items()})


class DB:
    @staticmethod
    def _connect():
        if USE_POSTGRES:
            conn = psycopg2.connect(DATABASE_URL)
            return conn, "%s"

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "?"

    @staticmethod
    def _prepare_sql(sql: str, placeholder: str) -> str:
        return sql.replace("?", placeholder)

    @classmethod
    def execute(cls, sql: str, params: tuple = ()) -> None:
        conn, placeholder = cls._connect()
        sql = cls._prepare_sql(sql, placeholder)

        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def fetchone(cls, sql: str, params: tuple = ()) -> Optional[AttrDict]:
        conn, placeholder = cls._connect()
        sql = cls._prepare_sql(sql, placeholder)

        try:
            if USE_POSTGRES:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            else:
                cur = conn.cursor()

            cur.execute(sql, params)
            return normalize_row(cur.fetchone())
        finally:
            conn.close()

    @classmethod
    def fetchall(cls, sql: str, params: tuple = ()) -> list[AttrDict]:
        conn, placeholder = cls._connect()
        sql = cls._prepare_sql(sql, placeholder)

        try:
            if USE_POSTGRES:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            else:
                cur = conn.cursor()

            cur.execute(sql, params)
            return [normalize_row(row) for row in cur.fetchall()]
        finally:
            conn.close()

    @classmethod
    def executescript(cls, sql: str) -> None:
        conn, _ = cls._connect()

        try:
            if USE_POSTGRES:
                cur = conn.cursor()
                cur.execute(sql)
            else:
                conn.executescript(sql)

            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
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
print(f"DB backend: {'PostgreSQL' if USE_POSTGRES else 'SQLite (local dev)'}")


def render_template(
    request: Request,
    template_name: str,
    context: Optional[dict[str, Any]] = None,
) -> HTMLResponse:
    template_context = {"request": request}
    if context:
        template_context.update(context)

    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context=template_context,
    )


def log_activity(tutor_id: str, action: str, detail: str = "") -> None:
    DB.execute(
        "INSERT INTO activity_log (tutor_id, action, detail) VALUES (?, ?, ?)",
        (tutor_id, action, detail),
    )


def auto_screen(tutor: dict[str, Any]) -> tuple[str, str]:
    subject = str(tutor["subject"]).lower()
    experience = str(tutor["experience"]).lower()

    valid_subjects = [
        "mathematics",
        "english",
        "science",
        "chemistry",
        "physics",
        "biology",
    ]

    if not any(valid_subject in subject for valid_subject in valid_subjects):
        return (
            "Failed",
            f"Subject '{tutor['subject']}' is not currently offered by Opus Tuition.",
        )

    low_exp = ["no experience", "0 year", "none", "fresher"]
    if any(keyword in experience for keyword in low_exp):
        return "Failed", "Minimum 1 year tutoring experience required."

    return "Passed", "All automatic checks passed."


def get_stage_label(stage: int) -> str:
    for stage_number, label, _ in STAGES:
        if stage_number == stage:
            return label

    return "Unknown"


def updated_at_sql() -> str:
    return "NOW()" if USE_POSTGRES else "CURRENT_TIMESTAMP"


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, stage: str = "all", search: str = ""):
    query = "SELECT * FROM tutors WHERE 1=1"
    params: list[Any] = []

    if stage != "all":
        query += " AND stage_label = ?"
        params.append(stage)

    if search:
        if USE_POSTGRES:
            query += " AND (name ILIKE ? OR email ILIKE ? OR subject ILIKE ?)"
        else:
            query += " AND (name LIKE ? OR email LIKE ? OR subject LIKE ?)"

        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    query += " ORDER BY updated_at DESC"

    tutors = DB.fetchall(query, tuple(params))

    counts = {}
    for _, label, _ in STAGES:
        row = DB.fetchone(
            "SELECT COUNT(*) AS c FROM tutors WHERE stage_label = ?",
            (label,),
        )
        counts[label] = row["c"] if row else 0

    row = DB.fetchone("SELECT COUNT(*) AS c FROM tutors")
    counts["all"] = row["c"] if row else 0

    return render_template(
        request,
        "dashboard.html",
        {
            "tutors": tutors,
            "stages": STAGES,
            "counts": counts,
            "current_stage": stage,
            "search": search,
            "stage_colors": STAGE_COLORS,
        },
    )


@app.get("/apply", response_class=HTMLResponse)
async def apply_form(request: Request):
    return render_template(request, "apply.html")


@app.post("/apply")
async def apply_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    subject: str = Form(...),
    level: str = Form(...),
    experience: str = Form(""),
    about: str = Form(""),
    cv: Optional[UploadFile] = File(None),
):
    tutor_id = str(uuid.uuid4())[:8].upper()
    cv_filename = None

    if cv and cv.filename:
        ext = Path(cv.filename).suffix
        cv_filename = f"{tutor_id}{ext}"

        with open(UPLOAD_DIR / cv_filename, "wb") as destination:
            shutil.copyfileobj(cv.file, destination)

    screen_result, screen_notes = auto_screen(
        {"subject": subject, "experience": experience}
    )

    DB.execute(
        """
        INSERT INTO tutors
          (id, name, email, phone, subject, level, experience, about,
           cv_filename, stage, stage_label, screening_result, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tutor_id,
            name,
            email,
            phone,
            subject,
            level,
            experience,
            about,
            cv_filename,
            2,
            "Screening",
            screen_result,
            f"Auto-screening: {screen_notes}",
        ),
    )

    log_activity(
        tutor_id,
        "Application received",
        f"Subject: {subject}, Level: {level}",
    )
    log_activity(tutor_id, f"Auto-screening: {screen_result}", screen_notes)

    return RedirectResponse(
        f"/apply/success?id={tutor_id}&result={screen_result}",
        status_code=303,
    )


@app.get("/apply/success", response_class=HTMLResponse)
async def apply_success(request: Request, id: str, result: str):
    return render_template(
        request,
        "apply_success.html",
        {
            "tutor_id": id,
            "result": result,
        },
    )


@app.get("/tutor/{tutor_id}", response_class=HTMLResponse)
async def tutor_detail(request: Request, tutor_id: str):
    tutor = DB.fetchone("SELECT * FROM tutors WHERE id = ?", (tutor_id,))

    if not tutor:
        raise HTTPException(status_code=404, detail="Tutor not found")

    activity = DB.fetchall(
        "SELECT * FROM activity_log WHERE tutor_id = ? ORDER BY created_at DESC",
        (tutor_id,),
    )

    return render_template(
        request,
        "tutor_detail.html",
        {
            "tutor": tutor,
            "activity": activity,
            "stages": STAGES,
        },
    )


@app.post("/tutor/{tutor_id}/interview")
async def set_interview(
    tutor_id: str,
    interview_date: str = Form(...),
    interview_notes: str = Form(""),
    interview_result: str = Form(...),
):
    stage = 4 if interview_result == "Passed" else 3
    label = get_stage_label(stage) if interview_result == "Passed" else "Interview"
    ts = updated_at_sql()

    DB.execute(
        f"""
        UPDATE tutors SET
            interview_date = ?,
            interview_notes = ?,
            interview_result = ?,
            stage = ?,
            stage_label = ?,
            updated_at = {ts}
        WHERE id = ?
        """,
        (interview_date, interview_notes, interview_result, stage, label, tutor_id),
    )

    log_activity(tutor_id, f"Interview: {interview_result}", interview_notes)
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.post("/tutor/{tutor_id}/contract")
async def set_contract(tutor_id: str, action: str = Form(...)):
    ts = updated_at_sql()

    if action == "sent":
        DB.execute(
            f"UPDATE tutors SET contract_sent = 1, updated_at = {ts} WHERE id = ?",
            (tutor_id,),
        )
        log_activity(tutor_id, "Contract sent to tutor")

    elif action == "signed":
        DB.execute(
            f"""
            UPDATE tutors SET
                contract_signed = 1,
                stage = 5,
                stage_label = 'Training',
                updated_at = {ts}
            WHERE id = ?
            """,
            (tutor_id,),
        )
        log_activity(tutor_id, "Contract signed - moved to Training")

    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.post("/tutor/{tutor_id}/training")
async def set_training(tutor_id: str, action: str = Form(...)):
    ts = updated_at_sql()

    DB.execute(
        f"""
        UPDATE tutors SET
            training_done = 1,
            stage = 6,
            stage_label = 'Active',
            updated_at = {ts}
        WHERE id = ?
        """,
        (tutor_id,),
    )

    log_activity(tutor_id, "Training completed - moved to Activation")
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.post("/tutor/{tutor_id}/activate")
async def activate_tutor(tutor_id: str):
    ts = updated_at_sql()

    DB.execute(
        f"""
        UPDATE tutors SET
            profile_live = 1,
            stage = 6,
            stage_label = 'Active',
            updated_at = {ts}
        WHERE id = ?
        """,
        (tutor_id,),
    )

    log_activity(tutor_id, "Profile activated - tutor is now LIVE")
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.post("/tutor/{tutor_id}/notes")
async def update_notes(tutor_id: str, notes: str = Form(...)):
    ts = updated_at_sql()

    DB.execute(
        f"UPDATE tutors SET notes = ?, updated_at = {ts} WHERE id = ?",
        (notes, tutor_id),
    )

    log_activity(tutor_id, "Notes updated")
    return RedirectResponse(f"/tutor/{tutor_id}", status_code=303)


@app.get("/cv/{filename}")
async def download_cv(filename: str):
    path = UPLOAD_DIR / filename

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, filename=filename)
