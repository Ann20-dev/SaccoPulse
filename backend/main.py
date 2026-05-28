import logging
import os
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from typing import Annotated, Literal
from uuid import uuid4

try:
    import africastalking
except ImportError:
    africastalking = None

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
SmsActionStatus = Literal["New", "In Review", "Actioned", "Dismissed"]


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
settings.africastalking_api_key = (
    settings.africastalking_api_key
    or os.getenv("SANDBOX_API_KEY")
    or os.getenv("AT_API_KEY")
    or os.getenv("API_KEY")
)
settings.africastalking_username = (
    os.getenv("SANDBOX_USERNAME")
    or os.getenv("AT_USERNAME")
    or settings.africastalking_username
)

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
    status: str = "New"
    confirmation_status: str = "Not queued"


class Alert(BaseModel):
    id: str
    report_id: str
    message: str
    created_at: str
    routed_to: str


class AtsSmsMessage(BaseModel):
    id: int
    at_message_id: str
    sender: str
    recipient: str | None = None
    text: str
    received_at: str | None = None
    fetched_at: str
    status: SmsActionStatus = "New"
    raw_payload: str


class SmsStatusUpdate(BaseModel):
    status: SmsActionStatus


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

reports: list[Report] = [
    Report(
        id="RPT-DEMO1",
        category="reckless_driving",
        route="CBD - Rongai",
        vehicle_plate="KDA 421P",
        description="Driver was overspeeding near Bomas stage.",
        severity="high",
        reporter_phone="+254700000000",
        created_at=datetime.now(timezone.utc).isoformat(),
        confirmation_status="Demo only",
    )
]

alerts: list[Alert] = [
    Alert(
        id="ALT-DEMO1",
        report_id="RPT-DEMO1",
        message="HIGH alert: reckless_driving on CBD - Rongai, vehicle KDA 421P.",
        created_at=datetime.now(timezone.utc).isoformat(),
        routed_to="+254711000999",
    )
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
            CREATE TABLE IF NOT EXISTS ats_sms_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at_message_id TEXT UNIQUE NOT NULL,
                sender TEXT NOT NULL,
                recipient TEXT,
                text TEXT NOT NULL,
                received_at TEXT,
                fetched_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                raw_payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


def get_app_state(key: str, default: str = "0") -> str:
    with get_connection() as connection:
        row = connection.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_app_state(key: str, value: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO app_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def row_to_ats_sms(row: sqlite3.Row) -> AtsSmsMessage:
    return AtsSmsMessage(**dict(row))


def save_ats_sms_message(message: dict) -> bool:
    at_message_id = str(message.get("id") or uuid4().hex)
    sender = str(message.get("from") or message.get("sender") or "Unknown")
    recipient = message.get("to") or message.get("recipient")
    text = str(message.get("text") or message.get("message") or "")
    received_at = message.get("date") or message.get("receivedAt") or message.get("createdAt")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO ats_sms_messages (
                at_message_id, sender, recipient, text, received_at, fetched_at, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                at_message_id,
                sender,
                recipient,
                text,
                str(received_at) if received_at else None,
                now_iso(),
                json.dumps(message, default=str),
            ),
        )
    return cursor.rowcount > 0


def fetch_ats_sms_messages() -> dict[str, int | str]:
    if africastalking is None:
        raise HTTPException(
            status_code=500,
            detail="Install africastalking with: pip install -r requirements.txt",
        )
    if not settings.africastalking_api_key:
        raise HTTPException(status_code=400, detail="Missing Africa's Talking API key")
    if settings.africastalking_environment == "sandbox" and settings.africastalking_username != "sandbox":
        raise HTTPException(status_code=400, detail="Sandbox fetch requires AFRICASTALKING_USERNAME=sandbox")

    africastalking.initialize(settings.africastalking_username, settings.africastalking_api_key)
    sms_service = africastalking.SMS

    last_received_id = int(get_app_state("ats_last_received_id", "0"))
    fetched_count = 0
    saved_count = 0

    try:
        while True:
            message_data = sms_service.fetch_messages(last_received_id)
            messages = message_data.get("SMSMessageData", {}).get("Messages", [])
            if not messages:
                break

            fetched_count += len(messages)
            for message in messages:
                if save_ats_sms_message(message):
                    saved_count += 1
                if message.get("id") is not None:
                    last_received_id = max(last_received_id, int(message["id"]))

            set_app_state("ats_last_received_id", str(last_received_id))
    except Exception as exc:
        logger.error("Failed to fetch Africa's Talking SMS inbox: %s", exc)
        raise HTTPException(status_code=502, detail=f"Failed to fetch SMS inbox: {exc}") from exc

    return {
        "status": "ok",
        "fetched": fetched_count,
        "saved": saved_count,
        "last_received_id": last_received_id,
    }


init_database()


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

    if settings.africastalking_environment == "sandbox" and settings.africastalking_username != "sandbox":
        logger.error("Sandbox SMS requires AFRICASTALKING_USERNAME=sandbox")
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
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        response_text = exc.response.text[:500] if exc.response is not None else ""
        if status_code == 401:
            logger.error(
                "Africa's Talking rejected SMS credentials. Check that username=%s matches environment=%s "
                "and that the API key came from the same Africa's Talking dashboard. Response: %s",
                settings.africastalking_username,
                settings.africastalking_environment,
                response_text,
            )
        else:
            logger.error("Failed to send SMS to %s: %s. Response: %s", data["to"], exc, response_text)
        return False
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
        logger.warning("Confirmation SMS for %s was not queued because the API key is missing", report.id)
        return

    send_sms_async(report.reporter_phone, message)
    report.confirmation_status = "SMS queued"


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
    alerts.insert(0, alert)
    send_sms_async(settings.manager_phone_number, alert.message)
    return alert


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
def list_reports() -> list[Report]:
    return reports


@app.post("/api/reports", response_model=Report, status_code=201)
def create_report(payload: ReportCreate) -> Report:
    report = Report(
        id=f"RPT-{uuid4().hex[:8].upper()}",
        created_at=now_iso(),
        **payload.model_dump(),
    )
    reports.insert(0, report)
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


@app.get("/api/alerts", response_model=list[Alert])
def list_alerts() -> list[Alert]:
    return alerts


@app.post("/api/ats-sms/fetch")
def fetch_ats_sms() -> dict[str, int | str]:
    return fetch_ats_sms_messages()


@app.get("/api/ats-sms/messages", response_model=list[AtsSmsMessage])
def list_ats_sms_messages(status: SmsActionStatus | None = None) -> list[AtsSmsMessage]:
    with get_connection() as connection:
        if status:
            rows = connection.execute(
                "SELECT * FROM ats_sms_messages WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM ats_sms_messages ORDER BY id DESC").fetchall()
    return [row_to_ats_sms(row) for row in rows]


@app.patch("/api/ats-sms/messages/{message_id}/status", response_model=AtsSmsMessage)
def update_ats_sms_status(message_id: int, payload: SmsStatusUpdate) -> AtsSmsMessage:
    with get_connection() as connection:
        connection.execute(
            "UPDATE ats_sms_messages SET status = ? WHERE id = ?",
            (payload.status, message_id),
        )
        row = connection.execute("SELECT * FROM ats_sms_messages WHERE id = ?", (message_id,)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="SMS report not found")

    return row_to_ats_sms(row)


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
