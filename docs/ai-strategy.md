# AI Strategy

## Model Recommendation

Your original plan uses `qwen2.5:4b`. That is usable, but not the strongest choice for this product if you want believable outputs.

## Best Setup By Task

### Option A: One-Model Simplicity

Use `qwen2.5:7b-instruct` for everything.

Why:

- noticeably better structure and reasoning than 4B
- still practical for local demos
- simpler ops than managing multiple models

### Option B: Best Practical Local Setup

Use:

- `qwen2.5:7b-instruct` for syllabus parsing, scheduling, essay grading, and chat
- `qwen2.5-coder:7b` for coding assignment generation and coding feedback

Why:

- cleaner coding analysis
- better separation of general pedagogy vs code review

### Option C: Highest Quality If Hardware Allows

Use:

- `qwen2.5:14b-instruct` for parsing, planning, essay grading, and chat
- `qwen2.5-coder:7b` or stronger coder model for code tasks

Use this only if your machine can handle it smoothly during the demo.

## What I Recommend

For a solo project and reliable local demo:

- Primary model: `qwen2.5:7b-instruct`
- Secondary coding model: `qwen2.5-coder:7b`
- Emergency fallback: `qwen2.5:4b`

That gives the best quality-to-speed tradeoff for this use case.

## Why 4B Is Not Ideal As Default

`qwen2.5:4b` is fast, but the weak points matter here:

- worse syllabus parsing consistency
- weaker rubric-based grading
- higher chance of shallow or generic feedback
- more prompt brittleness for JSON-heavy workflows

It is fine as a fallback, not as the main demo model.

## Inference Strategy

Use low temperature for structure-heavy flows:

- syllabus parse: `0.1`
- schedule generation: `0.3`
- assignment generation: `0.5`
- essay/coding grading: `0.2`
- chatbot: `0.4`

The original blanket `0.7` is too high for grading and JSON extraction.

## Prompting Rules

Every AI feature should:

- ask for strict JSON only
- include the schema inline
- give one short example
- tell the model to return empty arrays instead of invented fields
- include explicit refusal guidance for missing context

## Recommended Prompt Contracts

### Syllabus Parse Output

```json
{
  "course_title": "string",
  "topics": ["string"],
  "num_assignments": 2,
  "assignment_weightage": "string",
  "other_weightages": [
    {"label": "Midsem", "weight": "20%"}
  ],
  "policies": ["string"],
  "assumptions": ["string"]
}
```

### Schedule Output

```json
{
  "classes": [
    {
      "class_number": 1,
      "topic": "Introduction to ML",
      "subtopics": ["History", "Applications"],
      "learning_objectives": ["Explain core terms"],
      "duration_minutes": 90
    }
  ]
}
```

### Assignment Output

```json
{
  "title": "Assignment 1",
  "type": "ESSAY",
  "total_marks": 20,
  "questions": [
    {
      "question_number": 1,
      "prompt": "Explain supervised learning.",
      "marks": 10,
      "rubric": ["Definition", "Examples", "Clarity"]
    }
  ]
}
```

### Grading Output

```json
{
  "total_score": 16,
  "max_score": 20,
  "score_breakdown": [
    {
      "question_number": 1,
      "score": 8,
      "max_score": 10,
      "feedback": "Good definition, missing example."
    }
  ],
  "overall_feedback": "Strong fundamentals with minor gaps."
}
```

## Retrieval Context Rules For Chat

The chatbot prompt should include:

- syllabus text summary
- approved schedule
- completed classes only
- published assignments only
- refusal rule for uncovered topics

This is enough for MVP. Full vector search is optional and not necessary yet.

## Best Libraries

- `ollama` or `ollama-python` for inference
- `pydantic` for AI output validation
- `pdfplumber` for PDF extraction

## Golden Rule

The AI should propose, not silently decide. Any action that affects grading, syllabus interpretation, or teaching scope should remain reviewable by the teacher.
