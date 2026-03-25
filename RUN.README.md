# Run Guide

This project has 3 parts:

1. Ollama
2. Django backend
3. React frontend

Use Windows PowerShell commands below.

## Project Paths

- Backend: `C:\Users\mayur\Desktop\LLMZK\ai-classroom-backend`
- Frontend: `C:\Users\mayur\Desktop\LLMZK\ai-classroom-frontend`

## Current Model Setup

Backend `.env` is already configured for:

- Primary model: `qwen2.5:7b`
- Coder model: `qwen2.5-coder:7b`
- Ollama URL: `http://localhost:11434`

You do not need to keep `qwen2.5-coder:7b` running in a terminal.

## One-Time Setup

### 1. Install Ollama

Install Ollama on Windows and open it once so it runs in the background.

### 2. Download the Models Once

Open PowerShell and run:

```powershell
ollama run qwen2.5:7b
```

After it opens, type:

```text
/bye
```

Then run:

```powershell
ollama run qwen2.5-coder:7b "hello"
```

That downloads both models.

### 3. Backend Dependencies

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe manage.py migrate
```

### 4. Frontend Dependencies

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-frontend
npm install
```

## Daily Startup

### 1. Make Sure Ollama Is Running

Usually you just need the Ollama desktop app open in the tray/background.

If needed, verify it with:

```powershell
ollama list
```

You should see `qwen2.5:7b` and `qwen2.5-coder:7b`.

### 2. Start Backend

Open a new PowerShell window:

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-backend
.\venv\Scripts\python.exe manage.py runserver
```

Backend runs at:

```text
http://127.0.0.1:8000
```

### 3. Start Frontend

Open another PowerShell window:

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-frontend
npm run dev
```

Frontend runs at:

```text
http://localhost:5173
```

## Exact Order To Run

1. Open Ollama if it is not already running
2. Start backend
3. Start frontend
4. Open `http://localhost:5173`

## How To Test The App

1. Open the frontend
2. Create or open a course
3. Go to `Materials`
4. Upload a PDF or paste text
5. Watch the upload progress bar
6. Check the backend terminal for logs
7. Open the learning path
8. Generate assignments or quizzes
9. Ask chat questions from the uploaded material

## Helpful Backend Logs

While uploading, the backend terminal should show lines like:

- `Material upload started`
- `Extraction finished`
- `Indexing completed`
- `Starting fast schedule rebuild`
- `Material upload completed`

For PDFs, it may also show:

- `PDF extraction progress`
- OCR usage
- extraction duration
- indexing duration

## Useful Commands

### Run Tests

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-backend
.\venv\Scripts\python.exe manage.py test apps.ai_service.tests apps.courses.tests apps.assignments.tests
```

### Compile Check

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-backend
.\venv\Scripts\python.exe -m compileall apps\ai_service apps\courses config
```

### Frontend Build Check

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-frontend
npm run build
```

## If Something Fails

### Ollama not reachable

- Make sure the Ollama app is running
- Make sure `http://localhost:11434` is available
- Run `ollama list`

### Backend not starting

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-backend
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver
```

### Frontend not starting

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-frontend
npm install
npm run dev
```

## Short Version

Terminal 1:

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-backend
.\venv\Scripts\python.exe manage.py runserver
```

Terminal 2:

```powershell
cd C:\Users\mayur\Desktop\LLMZK\ai-classroom-frontend
npm run dev
```

Then open:

```text
http://localhost:5173
```
