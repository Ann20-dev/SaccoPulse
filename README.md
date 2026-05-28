# SaccoPulse

Offline-first fleet governance demo for informal transit networks.

The project includes:

- A FastAPI backend with commuter reporting, manager alerts, driver scores, and airtime reward simulation.
- SQLite persistence for reports, alerts, and inbound SMS queries.
- A plain HTML, CSS, and JavaScript frontend.
- A mock USSD endpoint shaped like Africa's Talking callbacks.

## Project Structure

```text
SaccoPulse/
  backend/
    main.py
  frontend/
    index.html
    styles.css
    app.js
  saccopulse.db
  requirements.txt
```

## Run Locally

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Start the server:

```bash
uvicorn backend.main:app --reload
```

Open the app:

```text
http://127.0.0.1:8000
```

API docs are available at:

```text
http://127.0.0.1:8000/docs
```

## SMS Setup

Copy `.env.example` to `.env`, then add your Africa's Talking API key.

Sandbox example:

```env
AFRICASTALKING_API_KEY=your_sandbox_api_key
AFRICASTALKING_USERNAME=sandbox
AFRICASTALKING_ENVIRONMENT=sandbox
SMS_SHORTCODE=90875
MANAGER_PHONE_NUMBER=+254711000999
```

Production example:

```env
AFRICASTALKING_API_KEY=your_live_api_key
AFRICASTALKING_USERNAME=your_live_username
AFRICASTALKING_ENVIRONMENT=production
SMS_SHORTCODE=your_approved_shortcode_or_sender_id
MANAGER_PHONE_NUMBER=+254711000999
```

When a commuter submits a complaint with a phone number, SaccoPulse queues an SMS confirmation. High-severity complaints also queue an SMS-style alert for the SACCO manager.

## Admin Dashboard

Reports are stored in `saccopulse.db` and shown in the dashboard. SACCO managers can filter by:

- `New`
- `In Review`
- `Actioned`
- `Dismissed`

Use the action buttons on each report to update its status.

## Demo Endpoints

- `POST /api/reports` creates a commuter report.
- `GET /api/reports` lists reports.
- `GET /api/reports?status=Actioned` lists reports by status.
- `PATCH /api/reports/{report_id}/status` updates report action status.
- `GET /api/alerts` lists high-severity manager alerts.
- `POST /sms_callback` accepts Africa's Talking inbound SMS callbacks.
- `GET /api/sms-queries` lists saved inbound SMS queries.
- `GET /api/drivers` lists drivers and compliance scores.
- `POST /api/rewards/run` simulates airtime rewards for high-scoring drivers.
- `POST /ussd` simulates an Africa's Talking USSD callback.
