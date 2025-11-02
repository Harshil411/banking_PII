# React Frontend for Banking PII Protection

This is the React frontend for the Banking PII Protection application.

## Development Setup

### Prerequisites

- Node.js 16+
- npm or yarn

### Installation

```bash
cd frontend
npm install
```

### Development Server

```bash
npm start
```

Runs the app in development mode. Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

### Production Build

```bash
npm run build
```

Builds the app for production to the `build` folder.

## Backend Integration

The frontend expects the Python backend to be running on `http://localhost:8000`.

### API Endpoints Used

- `POST /api/bert/extract` - Extract PII using BERT model
- `POST /api/llama/anonymize` - Anonymize PII using LLaMA model
- `GET /api/metrics` - Get system metrics
- `GET /api/data_schema` - Get data schema

## Components

- **BertPanel**: Interface for PII extraction using BERT model
- **LlamaPanel**: Interface for PII anonymization using LLaMA model
- **MetricsPanel**: Displays system metrics and data schema
- **App**: Main application component

## Styling

Uses CSS modules with a modern dark theme optimized for banking applications.
