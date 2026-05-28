import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATABASE_PATH = BASE_DIR / "saccopulse.db"
ReportStatus = Literal["New", "In Review", "Actioned", "Dismissed"]


class Settings(BaseSettings):
    africastalking_api_key: str | None = None
    africastalking_username: str = "sandbox"
    africastalking_environment: Literal["sandbox", "production"] = "sandbox"
    sms_shortcode: str = "90875"
    manager_phone_number: str = "+254711000999"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def messaging_url(self) -> str:
        if self.africastalking_environment == "production":
            return "https://api.africastalking.com/version1/messaging"
        return "https://api.sandbox.africastalking.com/version1/messaging"


load_dotenv(BASE_DIR / ".env")
settings = Settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("saccopulse.sms")


class Driver(BaseModel):
    id: str
    name: str
    route: str
    phone: str
    vehicle_plate: str
    score: int = Field(ge=0, le=100)
    reward_status: str = "Not rewarded"


class ReportCreate(BaseModel):
    category: Literal["overcharging", "reckless_driving", "vehicle_defect", "harassment", "other"]
    route: str = Field(min_length=2, max_length=80)
    vehicle_plate: str = Field(min_length=3, max_length=20)
    description: str = Field(min_length=5, max_length=400)
    severity: Literal["low", "medium", "high"]
    reporter_phone: str = Field(min_length=9, max_length=30)


class Report(ReportCreate):
    id: str
    created_at: str
    status: ReportStatus = "New"
    confirmation_status: str = "Not queued"


class ReportStatusUpdate(BaseModel):
    status: ReportStatus


class Alert(BaseModel):
    id: str
    report_id: str
    message: str
    created_at: str
    routed_to: str


drivers: list[Driver] = [
    Driver(
        id="DRV-001",
        name="Peter Mwangi",
        route="CBD - Rongai",
        phone="+254700111222",
        vehicle_plate="KDA 421P",
        score=94,
    ),
    Driver(
        id="DRV-002",
        name="Amina Odhiambo",
        route="CBD - Umoja",
        phone="+254700333444",
        vehicle_plate="KCB 118L",
        score=88,
    ),
    Driver(
        id="DRV-003",
        name="Brian Otieno",
        route="CBD - Thika",
        phone="+254700555666",
        vehicle_plate="KDD 705Q",
        score=62,
    ),
]

app = FastAPI(
    title="SaccoPulse API",
    description="Offline-first fleet governance and incentive platform demo.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                route TEXT NOT NULL,
                vehicle_plate TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                reporter_phone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                confirmation_status TEXT NOT NULL DEFAULT 'Not queued',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                routed_to TEXT NOT NULL,
                FOREIGN KEY (report_id) REFERENCES reports (id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sms_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'callback'
            )
            """
        )
        seed_count = connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        if seed_count == 0:
            connection.execute(
                """
                INSERT INTO reports (
                    id, category, route, vehicle_plate, description, severity,
                    reporter_phone, status, confirmation_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "RPT-DEMO1",
                    "reckless_driving",
                    "CBD - Rongai",
                    "KDA 421P",
                    "Driver was overspeeding near Bomas stage.",
                    "high",
                    "+254700000000",
                    "New",
                    "Demo only",
                    now_iso(),
                ),
            )
            connection.execute(
                """
                INSERT INTO alerts (id, report_id, message, created_at, routed_to)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "ALT-DEMO1",
                    "RPT-DEMO1",
                    "HIGH alert: reckless_driving on CBD - Rongai, vehicle KDA 421P.",
                    now_iso(),
                    settings.manager_phone_number,
                ),
            )


def row_to_report(row: sqlite3.Row) -> Report:
    return Report(**dict(row))


def row_to_alert(row: sqlite3.Row) -> Alert:
    return Alert(**dict(row))


def save_report(report: Report) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO reports (
                id, category, route, vehicle_plate, description, severity,
                reporter_phone, status, confirmation_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.id,
                report.category,
                report.route,
                report.vehicle_plate,
                report.description,
                report.severity,
                report.reporter_phone,
                report.status,
                report.confirmation_status,
                report.created_at,
            ),
        )


def update_report_confirmation_status(report_id: str, confirmation_status: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE reports SET confirmation_status = ? WHERE id = ?",
            (confirmation_status, report_id),
        )


def save_alert(alert: Alert) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO alerts (id, report_id, message, created_at, routed_to)
            VALUES (?, ?, ?, ?, ?)
            """,
            (alert.id, alert.report_id, alert.message, alert.created_at, alert.routed_to),
        )


def normalize_phone_number(phone_number: str) -> str:
    cleaned = phone_number.strip().replace(" ", "")
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("0"):
        return f"+254{cleaned[1:]}"
    return f"+{cleaned}"


def send_sms(phone_number: str, message: str) -> bool:
    if not settings.africastalking_api_key:
        logger.warning("SMS not sent to %s because AFRICASTALKING_API_KEY is missing", phone_number)
        return False

    data = {
        "username": settings.africastalking_username,
        "to": normalize_phone_number(phone_number),
        "message": message,
        "from": settings.sms_shortcode,
    }
    headers = {
        "apiKey": settings.africastalking_api_key,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        response = requests.post(
            settings.messaging_url,
            headers=headers,
            data=data,
            timeout=10,
        )
        response.raise_for_status()
        logger.info("SMS sent to %s with status %s", data["to"], response.status_code)
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send SMS to %s: %s", data["to"], exc)
        return False


def send_sms_async(phone_number: str, message: str) -> None:
    thread = Thread(target=send_sms, args=(phone_number, message), daemon=True)
    thread.start()


def queue_report_confirmation(report: Report) -> None:
    message = (
        f"SaccoPulse has received your complaint {report.id}. "
        "Thank you for helping improve commuter safety."
    )
    if not settings.africastalking_api_key:
        report.confirmation_status = "SMS disabled: missing API key"
        update_report_confirmation_status(report.id, report.confirmation_status)
        logger.warning("Confirmation SMS for %s was not queued because the API key is missing", report.id)
        return

    send_sms_async(report.reporter_phone, message)
    report.confirmation_status = "SMS queued"
    update_report_confirmation_status(report.id, report.confirmation_status)


def create_manager_alert(report: Report) -> Alert:
    alert = Alert(
        id=f"ALT-{uuid4().hex[:8].upper()}",
        report_id=report.id,
        message=(
            f"HIGH alert: {report.category.replace('_', ' ')} on {report.route}, "
            f"vehicle {report.vehicle_plate}."
        ),
        created_at=now_iso(),
        routed_to="+254711000999",
    )
    save_alert(alert)
    send_sms_async(settings.manager_phone_number, alert.message)
    return alert


def save_sms_query(sender: str, message: str, source: str = "callback") -> None:
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO sms_queries (sender, message, created_at, source) VALUES (?, ?, ?, ?)",
            (sender, message, now_iso(), source),
        )


init_database()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "SaccoPulse API"}


@app.get("/api/drivers", response_model=list[Driver])
def list_drivers() -> list[Driver]:
    return drivers


@app.get("/api/reports", response_model=list[Report])
def list_reports(status: ReportStatus | None = None) -> list[Report]:
    with get_connection() as connection:
        if status:
            rows = connection.execute(
                "SELECT * FROM reports WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
    return [row_to_report(row) for row in rows]


@app.post("/api/reports", response_model=Report, status_code=201)
def create_report(payload: ReportCreate) -> Report:
    report = Report(
        id=f"RPT-{uuid4().hex[:8].upper()}",
        created_at=now_iso(),
        **payload.model_dump(),
    )
    save_report(report)
    queue_report_confirmation(report)

    matching_driver = next(
        (driver for driver in drivers if driver.vehicle_plate.upper() == report.vehicle_plate.upper()),
        None,
    )
    if matching_driver:
        penalty = {"low": 3, "medium": 7, "high": 14}[report.severity]
        matching_driver.score = max(0, matching_driver.score - penalty)

    if report.severity == "high":
        create_manager_alert(report)

    return report


@app.patch("/api/reports/{report_id}/status", response_model=Report)
def update_report_status(report_id: str, payload: ReportStatusUpdate) -> Report:
    with get_connection() as connection:
        connection.execute(
            "UPDATE reports SET status = ? WHERE id = ?",
            (payload.status, report_id),
        )
        row = connection.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    return row_to_report(row)


@app.get("/api/alerts", response_model=list[Alert])
def list_alerts() -> list[Alert]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM alerts ORDER BY created_at DESC").fetchall()
    return [row_to_alert(row) for row in rows]


@app.post("/sms_callback")
def sms_callback(
    sender: Annotated[str | None, Form(alias="from")] = None,
    text: Annotated[str | None, Form()] = None,
) -> dict[str, str]:
    if not sender or not text:
        raise HTTPException(status_code=400, detail="Missing sender or text")

    normalized_sender = normalize_phone_number(sender)
    save_sms_query(normalized_sender, text)

    confirmation = "SaccoPulse has received your message. A SACCO manager will review it."
    send_sms_async(normalized_sender, confirmation)
    return {"status": "accepted"}


@app.get("/api/sms-queries")
def list_sms_queries() -> list[dict[str, str]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, sender, message, created_at, source FROM sms_queries ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/rewards/run", response_model=list[Driver])
def run_rewards() -> list[Driver]:
    for driver in drivers:
        if driver.score >= 85:
            driver.reward_status = "Airtime reward queued"
        else:
            driver.reward_status = "Needs improvement"
    return drivers


@app.post("/ussd", response_class=PlainTextResponse)
def ussd_callback(
    sessionId: Annotated[str, Form()],
    serviceCode: Annotated[str, Form()],
    phoneNumber: Annotated[str, Form()],
    text: Annotated[str, Form()] = "",
) -> str:
    selections = text.split("*") if text else []

    if text == "":
        return (
            "CON Welcome to SaccoPulse\n"
            "1. Report overcharging\n"
            "2. Report reckless driving\n"
            "3. Report vehicle defect"
        )

    if len(selections) == 1:
        return "CON Enter vehicle plate number"

    if len(selections) == 2:
        return "CON Enter route, for example CBD-Rongai"

    if len(selections) == 3:
        return "CON Severity\n1. Low\n2. Medium\n3. High"

    if len(selections) >= 4:
        category_map = {
            "1": "overcharging",
            "2": "reckless_driving",
            "3": "vehicle_defect",
        }
        severity_map = {"1": "low", "2": "medium", "3": "high"}
        category = category_map.get(selections[0])
        severity = severity_map.get(selections[3])

        if not category or not severity:
            raise HTTPException(status_code=400, detail="Invalid USSD selection")

        report = create_report(
            ReportCreate(
                category=category,
                vehicle_plate=selections[1],
                route=selections[2],
                description=f"USSD report submitted by {phoneNumber}",
                severity=severity,
                reporter_phone=phoneNumber,
            )
        )
        return f"END Thank you. Your anonymous report ID is {report.id}."

    return "END Invalid request"
