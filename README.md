# Banking PII Protection (FastAPI + React + Local HF Models)

This app serves two local Hugging Face models with a modern React frontend:

- `bert-base-multilingual-cased_100k_v1`: extract PII entities
- `llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1`: anonymize PII in text

The React UI provides two separate panels, one for each model, plus metrics and data schema display.

## Prerequisites

- Python 3.10+
- Node.js 16+
- Internet not required at runtime (models are local). First install may download Python wheels.

## Backend Setup (Python)

### 1. Create and activate virtual environment

```powershell
cd "C:\Users\rahil\OneDrive\Desktop\models"
python -m venv .venv
. .venv\Scripts\Activate.ps1
```

### 2. Install Python dependencies

```powershell
pip install -r backend\requirements.txt
```

### 3. Run Python backend

```powershell
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## Frontend Setup (React)

### 1. Install Node.js dependencies

```powershell
cd frontend
npm install
```

### 2. Start React development server

```powershell
npm start
```

This will open `http://localhost:3000` in your browser.

### 3. Build for production (optional)

```powershell
npm run build
```

## Running the Full Application

### Development Mode

1. Start the Python backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`
2. Start the React frontend: `cd frontend && npm start`
3. Open `http://localhost:3000` in your browser

### Production Mode

1. Build the React app: `cd frontend && npm run build`
2. Start the Python backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
3. Open `http://localhost:8000` in your browser

## API Endpoints

- POST `/api/bert/extract` { text }
- POST `/api/llama/anonymize` { text, replacement="[REDACTED]" }
- GET `/api/metrics`
- GET `/api/data_schema`

## Features

- Modern React UI with dark theme
- Real-time PII extraction and anonymization
- System metrics and data schema display
- Responsive design for mobile and desktop
- Error handling and loading states

## Notes

- Uses GPU if available (`torch.cuda.is_available()`), otherwise CPU
- Models are loaded from the existing folders at workspace root
- React frontend proxies API calls to Python backend in development
