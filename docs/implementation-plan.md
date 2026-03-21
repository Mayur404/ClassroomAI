# Implementation Plan

## Final MVP Definition

Build a robust local-demo product, not a half-working prototype. The MVP should support one polished end-to-end story:

1. Teacher logs in with institute email
2. Teacher creates a course and uploads syllabus PDF
3. System extracts syllabus text and parses assignment count, weightages, and topic outline
4. System generates a draft class schedule
5. Teacher approves the schedule and marks classes complete over time
6. Teacher generates an assignment only from covered topics
7. Student submits answers
8. System grades and returns feedback
9. Student asks course-aware questions
10. Teacher views analytics

## Build Order

### Phase 1: Foundation

- Set up Django project with modular apps
- Set up React app with routing, auth shell, and API client
- Configure SQLite, media uploads, CORS, env files
- Add institute-email access restriction in backend auth logic

### Phase 2: Core Data Model

- Implement `User`
- Implement `Course`
- Implement `Enrollment`
- Implement `ClassSchedule`
- Implement `Assignment`
- Implement `Submission`
- Implement `ChatMessage`

### Phase 3: Syllabus Pipeline

- Upload PDF
- Extract text with `pdfplumber`
- Parse structured metadata via Ollama
- Validate extracted JSON
- Store both raw text and cleaned structured fields
- Let teacher correct extracted metadata before final save

### Phase 4: Schedule Generator

- Use syllabus topics + number of classes
- Generate class-by-class breakdown
- Save draft schedule
- Add teacher approval and manual edit
- Add endpoint to mark classes complete

### Phase 5: Assignment Flow

- Enforce assignment count limit in backend
- Compute covered topics from completed classes
- Generate assignment draft with question metadata
- Let teacher edit and publish

### Phase 6: Submission and Grading

- Student submission API
- MCQ autograding
- Essay rubric-based grading
- Coding rubric-based grading
- Grade visibility in student UI

### Phase 7: Chatbot

- Course-scoped chat endpoint
- Prompt with syllabus, covered topics, assignment context
- Refusal behavior for uncovered topics
- Persist chat history

### Phase 8: Demo Polish

- Teacher analytics cards
- Better loading/error states
- Seed data for demo
- Scripted demo path

## Recommended Model/Data Changes

Your original schema is good, but these additions make it safer:

### User

Add:

- `is_active`
- `avatar_url`
- `last_login_at`

### Course

Add:

- `status` (`DRAFT`, `ACTIVE`, `ARCHIVED`)
- `syllabus_parse_status` (`PENDING`, `SUCCESS`, `FAILED`)
- `schedule_approved_at`

### ClassSchedule

Add:

- `order_index`
- `learning_objectives` as JSON
- `is_ai_generated`

### Assignment

Add:

- `status` (`DRAFT`, `PUBLISHED`, `CLOSED`)
- `rubric` as JSON
- `answer_key` as JSON for MCQ and guided evaluation
- `published_at`

### Submission

Add:

- `status` (`DRAFT`, `SUBMITTED`, `GRADED`)
- `score_breakdown` as JSON
- `graded_at`
- `grading_version`

### ChatMessage

Add:

- `role` (`STUDENT`, `ASSISTANT`, `SYSTEM`)
- `sources` as JSON for explainability

## Non-Negotiable Backend Validations

- Only `@iiitdwd.ac.in` emails may authenticate
- Only the course teacher may upload syllabus, approve schedule, and publish assignments
- Only enrolled students may view course content
- Students cannot submit after assignment due date unless explicitly allowed
- Assignments cannot exceed syllabus assignment count
- Assignments cannot use uncovered topics

## Risks And How To Avoid Them

### Risk: AI returns malformed JSON

Mitigation:

- use strict JSON prompts
- validate with serializers/pydantic
- retry once with repair prompt
- fall back to manual teacher review

### Risk: Small local model gives weak grading

Mitigation:

- use structured rubrics
- limit grading scope
- show feedback as draft/AI-assisted, not absolute truth

### Risk: PDF extraction quality is messy

Mitigation:

- store raw extracted text
- allow teacher edits before approval
- support plain text fallback paste later if needed

### Risk: Coding evaluation becomes too ambitious

Mitigation:

- keep coding assignments small
- accept code text input
- use rubric-based review instead of full sandboxed execution in MVP

## Suggested 3-Week Delivery

### Week 1

- Backend auth, models, course APIs
- Frontend login shell, dashboards, course setup
- Syllabus upload and parse

### Week 2

- Schedule generation and teacher approval
- Assignment generation and publishing
- Submission flow and MCQ grading

### Week 3

- Essay/coding grading
- Chatbot
- Analytics and demo polish

## Suggested 4-Week Delivery

If you have four weeks, spend the extra week on:

- better grading rubrics
- better teacher editing flows
- seed/demo fixtures
- mobile responsiveness
- error handling and retry UX
