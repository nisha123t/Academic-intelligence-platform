# Academic Intelligence Platform

Academic Intelligence Platform analyzes uploaded research-paper PDFs, extracts metadata and structured claims, and supports cross-paper comparisons and research-gap exploration.

## Requirements

- Python 3.10 or later
- Node.js 20.19+ or 22.12+
- npm

## Run locally

Run the backend and frontend in separate terminals from the repository root.

### 1. Set up and start the backend

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

The API is available at <http://127.0.0.1:8001>, and its interactive documentation is at <http://127.0.0.1:8001/docs>.

The backend runs without external credentials using in-memory paper storage. Papers stored this way are lost when the backend restarts. To use Supabase storage, set `SUPABASE_URL` and `SUPABASE_KEY` in `.env` in the `backend` directory before starting the backend. Do not commit credentials.

### 2. Set up and start the frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite (normally <http://localhost:5173>). The frontend defaults to the API at `http://127.0.0.1:8001`. To use another backend URL, set `VITE_API_URL` in the frontend environment before starting or building the app.

Port `8001` is used because `8000` may already be occupied by another local service. If you choose a different API port, update `VITE_API_URL`; if you change the frontend's host or port, set `FRONTEND_ORIGIN` in `backend\.env` to the frontend's origin, for example `http://localhost:5173`.

## Run tests and checks

From the repository root, with the Python virtual environment activated:

```powershell
python -m pip install pytest
python -m pytest backend\tests -q
```

Frontend checks:

```powershell
cd frontend
npm run lint
npm run build
```

## API endpoints

- `POST /papers/upload` — upload and analyze a PDF (multipart form field: `file`)
- `GET /papers/{paper_id}` — retrieve an uploaded paper
- `POST /papers/compare` — compare selected papers
- `POST /papers/gaps` — identify research gaps in selected papers
