# AI Classroom

AI Classroom is a local-demo classroom management system inspired by Google Classroom, with AI-assisted syllabus parsing, class planning, assignment generation, grading, and student Q&A.

This repository is organized as a monorepo with:

- `ai-classroom-backend/` for the Django REST API
- `ai-classroom-frontend/` for the React app
- `docs/` for architecture, delivery plan, and AI design notes

## Product Goals

- Single-course demo for one teacher and multiple students
- Google OAuth restricted to `@iiitdwd.ac.in`
- Local-first AI using Ollama
- Reliable JSON-based AI workflows for planning, assignments, grading, and chat
- Clean Google Classroom-like teacher and student experience

## Recommended Scope

This is the right MVP scope for a solo 2-4 week build:

- 1 teacher demo account flow
- 1 course with syllabus upload
- Auto-generated class schedule
- Assignment generation limited by syllabus metadata and completed classes
- Submission flow for students
- AI grading for essay/coding, deterministic grading for MCQ
- Course-aware Q&A chatbot with guardrails

## Repo Layout

```text
.
|-- README.md
|-- docs/
|   |-- ai-strategy.md
|   |-- architecture.md
|   `-- implementation-plan.md
|-- ai-classroom-backend/
|   |-- README.md
|   `-- requirements.txt
`-- ai-classroom-frontend/
    |-- README.md
    `-- package.json
```

## What To Build First

1. Backend models, serializers, and REST APIs
2. Syllabus upload and parsing pipeline
3. Schedule generation with teacher approval
4. Assignment creation constraints and publishing flow
5. Submission + grading pipeline
6. Student chat with syllabus/schedule context
7. Frontend polish for the demo script

## Best Model Recommendation

Your original `qwen2.5:4b` pick is okay for a low-resource laptop demo, but it is not the best default if you want higher-quality grading and syllabus understanding.

- Best balanced local default: `qwen2.5:7b-instruct`
- Best stronger local option if hardware allows: `qwen2.5:14b-instruct`
- Best coding-specific secondary model: `qwen2.5-coder:7b`
- Fast fallback for weaker machines: `qwen2.5:4b`

More detailed model guidance is in [docs/ai-strategy.md](/C:/Users/mayur/Desktop/LLMZK/docs/ai-strategy.md).

## Local Setup

### Backend

```bash
cd ai-classroom-backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd ai-classroom-frontend
npm install
npm run dev
```

### Ollama

```bash
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5-coder:7b
```

## Current State

The repository now includes:

- Django project scaffold with domain apps and API endpoints
- React frontend scaffold with login, dashboard, and course pages
- AI service abstraction for syllabus parsing, schedule generation, assignment generation, grading, and chat

The AI service is currently a local scaffold layer with deterministic fallback behavior. Replace those functions with validated Ollama JSON calls to move from demo scaffold to full AI execution.
