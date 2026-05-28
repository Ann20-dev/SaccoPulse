# SaccoPulse

Offline-first fleet governance demo for informal transit networks.

The project includes:

- A FastAPI backend with commuter reporting, manager alerts, driver scores, and airtime reward simulation.
- An Africa's Talking SMS inbox fetcher that saves fetched SMS reports locally.
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

If you see `401 Client Error: Unauthorized`, the API key and username do not match the selected Africa's Talking environment. Use `AFRICASTALKING_USERNAME=sandbox` with a sandbox key, or use your live username with a production key and `AFRICASTALKING_ENVIRONMENT=production`.

## Africa's Talking SMS Inbox

The second admin dashboard fetches inbound SMS messages from Africa's Talking, stores them in local SQLite, and lets a SACCO manager mark each SMS report as:

- `New`
- `In Review`
- `Actioned`
- `Dismissed`

Use the **Fetch SMS Reports** button in the dashboard, or call:

```bash
curl -X POST http://127.0.0.1:8000/api/ats-sms/fetch
```

## Demo Endpoints

- `POST /api/reports` creates a commuter report.
- `GET /api/reports` lists reports.
- `GET /api/alerts` lists high-severity manager alerts.
- `POST /api/ats-sms/fetch` fetches inbound SMS messages from Africa's Talking.
- `GET /api/ats-sms/messages` lists saved SMS reports.
- `GET /api/ats-sms/messages?status=Actioned` filters saved SMS reports by action status.
- `PATCH /api/ats-sms/messages/{message_id}/status` updates a saved SMS report status.
- `GET /api/drivers` lists drivers and compliance scores.
- `POST /api/rewards/run` simulates airtime rewards for high-scoring drivers.
- `POST /ussd` simulates an Africa's Talking USSD callback.
