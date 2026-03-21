# Architecture

## High-Level Design

The system should use a standard three-service local architecture:

1. React frontend for teacher and student flows
2. Django REST backend for domain logic and persistence
3. Ollama for local LLM inference

```text
React App
   |
   v
Django REST API
   | \
   |  \-> SQLite
   |
   \----> Ollama
```

## Recommended Backend App Split

Use domain-based Django apps instead of one large app:

- `apps.users`
- `apps.courses`
- `apps.assignments`
- `apps.submissions`
- `apps.chat`
- `apps.ai_service`
- `apps.analytics`

This keeps boundaries clean and makes serializers, permissions, and tests easier to manage.

## Core Entity Relationships

- A `User` has one role: `TEACHER` or `STUDENT`
- A `Course` belongs to one teacher
- A `Course` has many `Enrollment`
- A `Course` has many `ClassSchedule` items
- A `Course` has many `Assignment`
- An `Assignment` has many `Submission`
- A `Course` has many `ChatMessage`

## Key Backend Rules

### Syllabus Parsing

The upload flow should:

1. Store the original PDF
2. Extract raw text
3. Ask AI for structured syllabus metadata in JSON
4. Validate parsed fields before saving
5. Allow teacher edits before final approval

Do not treat AI output as source-of-truth without validation.

### Schedule Generation

Schedule generation should be idempotent per course version:

- Generate a draft schedule from syllabus text
- Save as `PLANNED`
- Let the teacher approve or regenerate
- Track whether the syllabus changed after schedule generation

### Assignment Constraints

Assignment creation must enforce both:

- `existing_assignments < course.num_assignments`
- covered topics are limited to classes with `status = COMPLETED`

These rules must live in the backend, not only the UI.

### Grading

- MCQ grading should be fully deterministic
- Essay grading should use rubric + structured JSON feedback
- Coding grading should run simple static checks plus AI review

Avoid pure free-form AI grades. Always store the rubric, score breakdown, and rationale.

### Chatbot Guardrails

The chatbot should:

- answer from syllabus, schedule, and published assignments
- refuse or soften answers for uncovered topics
- state when information is inferred rather than explicit
- avoid fabricating policies not present in course data

## Suggested API Surface

### Auth

- `POST /api/auth/google/`
- `GET /api/auth/me/`
- `POST /api/auth/logout/`

### Courses

- `GET /api/courses/`
- `POST /api/courses/`
- `GET /api/courses/:id/`
- `POST /api/courses/:id/syllabus/`
- `POST /api/courses/:id/schedule/generate/`
- `POST /api/courses/:id/schedule/approve/`
- `POST /api/courses/:id/schedule/:schedule_id/complete/`

### Assignments

- `GET /api/courses/:id/assignments/`
- `POST /api/courses/:id/assignments/generate/`
- `POST /api/assignments/:id/publish/`
- `GET /api/assignments/:id/`

### Submissions

- `POST /api/assignments/:id/submissions/`
- `GET /api/assignments/:id/submissions/`
- `GET /api/submissions/:id/`
- `POST /api/submissions/:id/regrade/`

### Chat

- `GET /api/courses/:id/chat/`
- `POST /api/courses/:id/chat/`

### Analytics

- `GET /api/courses/:id/analytics/`

## Frontend Route Plan

- `/login`
- `/teacher/dashboard`
- `/teacher/courses/:id`
- `/teacher/courses/:id/schedule`
- `/teacher/courses/:id/assignments`
- `/student/dashboard`
- `/student/courses/:id`
- `/student/assignments/:id`
- `/student/chat/:courseId`

## UI Notes

To feel like a Google Classroom-inspired product without being a copy:

- use a soft, card-based layout
- keep assignment state obvious
- make grades visible from list and detail views
- highlight schedule progress using completed/planned chips
- show AI-generated content with review/edit affordances
