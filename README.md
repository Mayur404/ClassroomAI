# AI Classroom Tutor

A local-first AI classroom platform for turning course PDFs into structured learning paths, grounded chat answers, and auto-generated assignments.

The project is designed to run primarily on your own machine with Ollama, Django, React, SQLite, and ChromaDB. Recent work focused on making the pipeline faster, more reliable on scanned PDFs, and more strictly grounded in the uploaded material.

## What It Does

- Upload searchable PDFs, scanned PDFs, or pasted text
- Extract text locally with PDF parsing plus OCR fallback
- Build course topics and a class-by-class learning path
- Answer questions using retrieval over uploaded material
- Return PDF-grounded answers instead of generic LLM filler
- Generate MCQ, essay, and coding assignments from course content
- Grade submissions with structured AI feedback

## Key Highlights

- Local LLM setup using Ollama with `qwen2.5:7b` and `qwen2.5-coder:7b`
- Faster PDF extraction using `pypdfium2`
- OCR support for scanned and image-heavy PDFs using `rapidocr-onnxruntime`
- Hybrid retrieval using vector search plus lexical search
- Structured generation with Pydantic schemas for schedule, assignment, and grading output
- Upload progress UI plus backend extraction/indexing logs
- Grounded chat answers with direct PDF evidence snippets

## Tech Stack

### Frontend

- React 18
- Vite
- React Router
- TanStack Query
- Axios
- React Markdown

### Backend

- Django 5
- Django REST Framework
- django-cors-headers
- django-allauth
- Token authentication

### Data Layer

- SQLite for application data
- ChromaDB for vector storage
- Local filesystem for uploaded materials

### AI and Retrieval

- Ollama for local model inference
- Qwen 2.5 for generation
- Qwen 2.5 Coder for coding-oriented generation and grading
- sentence-transformers (`all-MiniLM-L6-v2`) for embeddings
- Optional Ollama embedding support in the retrieval layer
- Hybrid retrieval: semantic vector search plus lexical fallback/reranking

### Document Processing

- pdfplumber
- pypdfium2
- Pillow
- rapidocr-onnxruntime

## Architecture

### High-Level Flow

1. The frontend uploads a PDF or raw text to the Django API.
2. The backend extracts text, optionally runs OCR, and cleans the content.
3. The backend chunks and indexes the material in ChromaDB.
4. The course summary is rebuilt into topics, policies, and a learning path.
5. Chat, assignment generation, and grading use retrieval plus Ollama.

### Main Backend Apps

- `users`: custom user model and auth endpoints
- `courses`: courses, uploaded materials, enrollments, schedules
- `ai_service`: PDF extraction, OCR, RAG, generation, grading
- `assignments`: assignment creation and publishing
- `submissions`: answers, grading results, feedback
- `chat`: course-grounded Q and A history
- `analytics`: course stats and summary views

## Project Structure

```text
.
|- ai-classroom-backend/
|  |- apps/
|  |- config/
|  |- manage.py
|  |- requirements.txt
|- ai-classroom-frontend/
|  |- src/
|  |- package.json
|- docs/
|- run.readme
|- RUN.README.md
```

## Local AI Setup

The backend is currently configured for:

- `OLLAMA_MODEL_PRIMARY=qwen2.5:7b`
- `OLLAMA_MODEL_CODER=qwen2.5-coder:7b`
- `OLLAMA_BASE_URL=http://localhost:11434`

You only need Ollama running in the background. You do not need to keep a separate terminal open for the coder model.

## Quick Start

For the exact Windows-first run guide, see [run.readme](./run.readme).

### 1. Install and Prepare Ollama

Download Ollama, then download the models once:

```powershell
ollama run qwen2.5:7b
```

Exit the chat with:

```text
/bye
```

Then:

```powershell
ollama run qwen2.5-coder:7b "hello"
```

### 2. Start the Backend

```powershell
cd ai-classroom-backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver
```

Backend URL:

```text
http://127.0.0.1:8000
```

### 3. Start the Frontend

```powershell
cd ai-classroom-frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## Environment Variables

The main backend environment values are:

```env
DJANGO_SECRET_KEY=dev-secret-key-12345
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
INSTITUTE_EMAIL_DOMAIN=iiitdwd.ac.in
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_PRIMARY=qwen2.5:7b
OLLAMA_MODEL_CODER=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=
OLLAMA_EMBED_KEEP_ALIVE=30m
```

## Current Performance and Quality Improvements

- Fast upload path that avoids unnecessary AI schedule generation during upload
- Adaptive OCR so normal text PDFs do not waste time on OCR
- Conditional table extraction to reduce expensive parsing on pages that do not need it
- Adaptive chunk sizing to reduce indexing overhead on larger PDFs
- Cached lexical retrieval for repeated questions
- Cached repeated search results with invalidation on material updates
- Keep-alive and connection pooling for Ollama calls
- Retrieval-first factual chat answers with direct PDF evidence

## Testing

### Backend Tests

```powershell
cd ai-classroom-backend
.\venv\Scripts\python.exe manage.py test apps.chat.tests apps.ai_service.tests apps.courses.tests apps.assignments.tests
```

### Compile Check

```powershell
cd ai-classroom-backend
.\venv\Scripts\python.exe -m compileall apps\ai_service apps\chat apps\courses config
```

### Frontend Build

```powershell
cd ai-classroom-frontend
npm run build
```

## Typical User Flow

1. Create a classroom
2. Upload materials in the Materials tab
3. Let the app extract topics and build the learning path
4. Ask grounded questions in chat
5. Generate assignments from the uploaded material
6. Submit answers and review AI feedback

## Notes for GitHub

- The repo is local-first and optimized for development on Windows
- Uploaded files, SQLite data, and vector storage are created locally during use
- If you want a cleaner public demo, consider adding screenshots or a short demo GIF to `docs/`
- `run.readme` is the simplest handoff file for people who just want to run the app

## Future Directions

- True background jobs plus live processing percentages
- Page-level citations for answers
- Multimodal vision model support for diagram understanding
- Deployment profile for a hosted demo environment

## License

Add your preferred license before publishing the repository publicly.
