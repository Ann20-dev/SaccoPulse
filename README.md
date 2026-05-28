# SaccoPulse

Offline-first fleet governance demo for informal transit networks.

The project includes:

- A FastAPI backend with commuter reporting, manager alerts, driver scores, and airtime reward simulation.
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

## Demo Endpoints

- `POST /api/reports` creates a commuter report.
- `GET /api/reports` lists reports.
- `GET /api/alerts` lists high-severity manager alerts.
- `GET /api/drivers` lists drivers and compliance scores.
- `POST /api/rewards/run` simulates airtime rewards for high-scoring drivers.
- `POST /ussd` simulates an Africa's Talking USSD callback.

