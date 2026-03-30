# AI Classroom

AI Classroom is a local-first full-stack learning platform that turns uploaded course material into an interactive study workspace. It lets a user create classrooms, upload PDFs or pasted notes, generate a structured learning path, ask retrieval-grounded questions, create AI-generated assignments, and receive automated grading with per-question feedback.

The repository is organized as a monorepo with:

- `ai-classroom-frontend`: React + Vite single-page app
- `ai-classroom-backend`: Django + Django REST Framework API with local RAG, PDF extraction, OCR, assignment generation, and grading

## What The Project Does

At a high level, the application supports this flow:

1. Sign in with development-only demo login.
2. Create a classroom.
3. Upload a PDF or paste raw study text.
4. Extract text from materials, run OCR when needed, and index the content into a local retrieval store.
5. Auto-build a learning path from extracted topics.
6. Ask questions in the classroom chat and get answers grounded in uploaded material.
7. Generate assignments from the covered course content.
8. Submit answers and receive AI grading plus detailed answer review.
9. Track classroom progress through schedule completion and analytics endpoints.

## Core Features

### 1. Classroom Management

- Create, list, view, update, and delete classrooms
- Sidebar-based classroom navigation in the frontend
- Per-classroom materials, schedule, assignments, submissions, and chat history

### 2. Demo Authentication

- Token-based authentication using Django REST Framework tokens
- Simple demo login flow for local development
- `/api/auth/demo-login/` creates or reuses a user and returns an auth token
- `/api/auth/me/` restores the active session in the frontend

Important:

- Demo login is only enabled when `DEBUG=True`
- The current UI always logs in through the demo auth flow

### 3. Material Upload And Analysis

- Upload PDF files
- Paste plain text directly instead of uploading a file
- Extract text from native PDFs
- OCR scanned or image-heavy PDFs using `rapidocr-onnxruntime`
- Store extracted content in the backend database
- Extract topics from the material
- Rebuild the classroom summary and learning path after every upload

### 4. Local RAG Pipeline

- Chunk extracted material into retrieval-friendly blocks
- Index chunks into ChromaDB
- Use hybrid retrieval:
  - vector search when embeddings are available
  - lexical fallback when vector search is unavailable
- Support deterministic offline fallback embeddings
- Support Ollama embeddings when configured
- Return evidence snippets with answers
- Prefer answering from retrieved course evidence instead of generic model knowledge

### 5. AI Chat

- Course-specific chat panel
- Server-Sent Events streaming endpoint for token-by-token responses
- Stored chat history on the backend
- Frontend also keeps local per-course chat history in `localStorage`
- Evidence snippets shown under AI messages when available
- Chat feedback endpoint for recording helpful or unhelpful responses

### 6. Learning Path Generation

- Automatically builds a class schedule from extracted topics and material structure
- Tracks planned vs completed sessions
- Shows progress percentage, next topic, and material count
- Supports regenerating schedule using a more AI-heavy mode

### 7. Assignment Generation

- Generate assignments from covered topics
- Supported types in the backend:
  - `MCQ`
  - `ESSAY`
  - `CODING`
- Current frontend exposes:
  - MCQ generation
  - Essay generation
- Assignment payloads include:
  - title
  - description
  - questions
  - rubric
  - answer key
  - marks
  - due date

### 8. AI Grading

- Auto-grade MCQ submissions
- AI-assisted grading for essay and coding-style answers
- Per-question score breakdown
- Overall feedback
- Retake flow by deleting a previous submission
- Regrade endpoint available in backend

### 9. Analytics And Advanced AI Endpoints

The backend also includes endpoints for:

- course analytics
- student analytics
- topic analytics
- conversation summaries
- conversation export
- adaptive difficulty recommendations
- feedback quality analysis
- dashboard metrics

Some of these capabilities are backend-ready but not yet wired into the current frontend screens.

## Tech Stack

### Frontend

- React 18
- Vite 5
- React Router 6
- TanStack Query 5
- Axios
- React Markdown
- Remark GFM
- Custom CSS

### Backend

- Django 5
- Django REST Framework
- Django token authentication
- `django-cors-headers`
- `django-allauth`
- `drf-spectacular` for OpenAPI schema support
- Pydantic + `pydantic-settings` for validated configuration

### AI / Retrieval / Document Processing

- Ollama for local LLM generation
- ChromaDB for vector storage
- sentence-transformers or Ollama embeddings when available
- deterministic hash embeddings fallback
- `pdfplumber` for PDF extraction
- `pypdfium2` for PDF rendering and extraction support
- `rapidocr-onnxruntime` for OCR
- Pillow
- NumPy

### Infra / Supporting Services

- SQLite in development
- PostgreSQL referenced for production in `docker-compose.yml`
- Redis for caching / Celery broker configuration, with in-memory cache fallback if Redis is unavailable
- Celery settings present, but local development is configured to run tasks eagerly/synchronously
- Optional Sentry integration

## Repository Structure

```text
LLMZK/
|-- ai-classroom-backend/
|   |-- apps/
|   |   |-- ai_service/
|   |   |-- analytics/
|   |   |-- assignments/
|   |   |-- chat/
|   |   |-- courses/
|   |   |-- submissions/
|   |   `-- users/
|   |-- config/
|   |-- manage.py
|   `-- requirements.txt
|-- ai-classroom-frontend/
|   |-- src/
|   |   |-- api/
|   |   |-- components/
|   |   |-- contexts/
|   |   |-- hooks/
|   |   `-- pages/
|   |-- package.json
|   `-- vite.config.js
`-- docker-compose.yml
```

## Frontend Overview

The current frontend flow is centered around three main screens:

- `LoginPage`: demo sign-in
- `DashboardPage`: project landing and course overview
- `CoursePage`: classroom workspace

Inside `CoursePage`, the UI is split into:

- Materials tab
- Learning Path tab
- Assignments tab
- persistent AI chat sidebar

### Frontend Capabilities

- Auth state stored via React context
- Token persisted in `localStorage`
- API communication through shared Axios client
- Data fetching and mutations handled with TanStack Query
- Streaming chat implemented with direct `fetch()` to the SSE endpoint
- Markdown rendering for AI answers
- Upload progress and processing states during PDF ingestion

## Backend Overview

### Main Django Apps

#### `users`

- custom user model using email as the login identifier
- roles: `TEACHER`, `STUDENT`
- demo login and current-user endpoints

#### `courses`

- course model
- course materials
- enrollments
- class schedule generation and completion tracking
- syllabus/material upload workflow

#### `assignments`

- assignment creation, retrieval, publishing, deletion
- assignment generation from extracted course content

#### `submissions`

- submission creation
- grading
- regrading
- submission delete / retake flow

#### `chat`

- chat history
- grounded Q&A
- streaming responses
- feedback on response quality

#### `analytics`

- course-level analytics
- student-level analytics
- topic analytics
- frontend error logging endpoint

#### `ai_service`

- PDF extraction
- OCR fallback
- retrieval and ranking
- answer generation
- grading logic
- streaming logic
- adaptive difficulty
- feedback analysis
- advanced views

## Data Model Summary

### User

- email-based custom auth model
- stores `name`, `email`, `role`, optional social fields, and last login timestamp

### Course

- belongs to a teacher
- stores name, description, extracted topics, policies, summary metadata, status, and schedule approval state

### CourseMaterial

- belongs to a course
- stores uploaded file or pasted text
- stores parse status and extracted topics

### ClassSchedule

- belongs to a course
- tracks generated topic sequence, subtopics, learning objectives, session duration, and completion status

### Assignment

- belongs to a course
- stores generated questions, rubric, answer key, total marks, type, due date, and publish state

### Submission

- belongs to an assignment and a student
- stores answers, AI grade, feedback, grading breakdown, and timestamps

### ChatMessage

- belongs to a course and optionally a student
- stores question, AI response, sources, timestamps, and feedback metadata

## API Overview

Base URL in local frontend development:

```text
http://127.0.0.1:8000/api
```

### Auth

- `POST /api/auth/demo-login/`
- `GET /api/auth/me/`

### Courses

- `GET /api/courses/`
- `POST /api/courses/`
- `GET /api/courses/{id}/`
- `PATCH /api/courses/{id}/`
- `DELETE /api/courses/{id}/`
- `POST /api/courses/{course_id}/syllabus/`
- `DELETE /api/materials/{material_id}/delete/`
- `POST /api/courses/{course_id}/schedule/generate/`
- `POST /api/courses/{course_id}/schedule/approve/`
- `POST /api/schedule/{schedule_id}/complete/`
- `POST /api/enrollments/`
- `GET /api/teacher/dashboard/`

### Assignments

- `GET /api/courses/{course_id}/assignments/`
- `POST /api/courses/{course_id}/assignments/generate/`
- `GET /api/assignments/{id}/`
- `DELETE /api/assignments/{id}/`
- `POST /api/assignments/{assignment_id}/publish/`

### Submissions

- `POST /api/assignments/{assignment_id}/submissions/`
- `GET /api/submissions/{id}/`
- `DELETE /api/submissions/{id}/`
- `POST /api/submissions/{submission_id}/regrade/`

### Chat

- `GET /api/courses/{course_id}/chat/`
- `POST /api/courses/{course_id}/chat/ask/`
- `POST /api/courses/{course_id}/chat/stream/`
- `POST /api/chat/{message_id}/feedback/`

### Analytics

- `GET /api/courses/{course_id}/analytics/`
- `GET /api/students/{student_id}/analytics/`
- `GET /api/topics/analytics/`
- `POST /api/errors/log`

### Advanced AI Service Endpoints

- `GET /api/courses/{course_id}/students/{student_id}/difficulty/`
- `GET /api/conversations/{student_id}/courses/{course_id}/summary/`
- `GET /api/conversations/{student_id}/courses/{course_id}/export/`
- `GET /api/courses/{course_id}/feedback-analysis/`
- `GET /api/dashboard/metrics/`

## How The AI Pipeline Works

### Material Ingestion

1. User uploads a PDF or pastes text.
2. Backend stores a `CourseMaterial` record.
3. If a PDF is uploaded, the backend extracts text using PDF-native extraction first.
4. If pages are image-heavy or text-poor, OCR is used.
5. Extracted text is stored in the material record.
6. Text is chunked and indexed in ChromaDB.
7. Topics are extracted from the chunks and source text.
8. The course summary and schedule are rebuilt.

### Question Answering

1. User asks a question in the classroom chat.
2. Backend performs intelligent search and fallback hybrid retrieval.
3. Relevant passages are ranked.
4. For fact-like questions, the system may respond directly from evidence snippets.
5. Otherwise it prompts Ollama to answer only from retrieved evidence.
6. Sources are returned with the answer.
7. Streaming mode emits tokens to the frontend through SSE.

### Assignment Generation

1. Backend collects completed schedule items or early covered topics.
2. These topics are passed to assignment generation logic.
3. LLM produces questions, rubric, answer key, and description.
4. Assignment is created and immediately published.

### Grading

1. Student submits answers.
2. MCQs are auto-checked against answer keys.
3. Essays/coding answers use AI grading with a structured schema.
4. If grading output is poor, fallback grading logic is used.
5. Detailed question-level review is stored and returned.

## Local Development Setup

### Prerequisites

- Node.js 18+
- npm
- Python 3.11+ recommended
- `pip`
- Ollama installed and running locally
- At least one Ollama model pulled locally
- Redis optional for best parity, but not strictly required for basic local use

### 1. Clone And Enter The Repo

```bash
git clone <your-repo-url>
cd LLMZK
```

### 2. Backend Setup

```bash
cd ai-classroom-backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Backend runs by default at:

```text
http://127.0.0.1:8000
```

### 3. Frontend Setup

Open a second terminal:

```bash
cd ai-classroom-frontend
npm install
npm run dev
```

Frontend runs by default at:

```text
http://127.0.0.1:5173
```

### 4. Start Ollama

Run Ollama separately and ensure the configured models exist.

Example:

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull qwen2.5-coder:7b
```

If you want embedding support through Ollama as well, set `OLLAMA_EMBED_MODEL` and pull that model too.

## Environment Variables

The backend loads environment values from `.env` at the repo root level expected by Django settings.

Important backend settings currently supported:

```env
SECRET_KEY=dev-secret-key
DEBUG=True
ENVIRONMENT=development
ALLOWED_HOSTS=127.0.0.1,localhost

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_PRIMARY=qwen2.5:7b
OLLAMA_MODEL_CODER=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=
OLLAMA_EMBED_KEEP_ALIVE=30m
OLLAMA_TIMEOUT=300

GEMINI_API_KEY=
GEMINI_MODEL_PRIMARY=gemini-2.5-flash
GEMINI_MODEL_CODER=gemini-2.5-pro

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
SENTRY_DSN=
INSTITUTE_EMAIL_DOMAIN=iiitdwd.ac.in
```

Frontend variable:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

## Development Notes

- Development uses SQLite by default.
- Production settings switch to `DATABASE_URL`-based database configuration through `dj_database_url`.
- Redis cache is attempted first; if Redis is unavailable, the project falls back to Django local memory cache.
- Celery settings are present, but `CELERY_TASK_ALWAYS_EAGER=True` means local tasks run synchronously in-process.
- Media, logs, SQLite DB files, and vector store artifacts are ignored in `.gitignore`.

## Running Tests

Backend test files exist in several apps:

- `apps/chat/tests.py`
- `apps/courses/tests.py`
- `apps/assignments/tests.py`
- `apps/ai_service/tests.py`

Run backend tests with:

```bash
cd ai-classroom-backend
python manage.py test
```

The frontend currently does not include a test suite in this repository snapshot.

## Current Project Status And Limitations

This section is intentionally honest so contributors know what is implemented versus what is planned or partial.

- The main local development path is the manual frontend + backend + Ollama setup.
- `docker-compose.yml` exists, but the repository snapshot does not currently include the Dockerfiles referenced by that compose stack.
- The current UI is best described as a single-user or developer-focused workflow using demo auth.
- The backend contains more advanced analytics and adaptive-learning endpoints than the frontend currently exposes.
- Redis and Celery are configured, but default local behavior is synchronous rather than true background processing.
- Some auxiliary files, such as `src/router.jsx`, appear to be reference or experimental code rather than the active app entry flow.
- Production auth, deployment hardening, and fully multi-user classroom workflows would need additional work beyond the current demo-oriented setup.

## Why This Project Is Interesting

This codebase goes beyond a basic "chat with PDF" demo. It combines:

- local-first LLM usage with Ollama
- hybrid RAG with fallback strategies
- OCR-aware document ingestion
- schedule generation from course content
- assignment creation and grading
- streaming AI responses
- analytics and quality feedback hooks

That makes it a strong foundation for an offline-capable or privacy-conscious AI learning platform.

## Suggested Next Improvements

- add missing Dockerfiles and document containerized deployment
- add production authentication flow beyond demo login
- wire advanced analytics into the frontend
- add frontend tests and expand backend test coverage
- separate teacher and student workflows more explicitly in the UI and permissions
- move heavy ingestion and grading back to true async workers when desired
- add richer source citations and chunk provenance in the chat UI

## License

No license file is currently present in this repository snapshot. Add one before distributing or publishing the project externally.
