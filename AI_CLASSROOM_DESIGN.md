# AIEdu Application Design

## 1. Overview
The AI Classroom is a modern, intelligent learning management system (LMS) designed to enhance the educational experience for both teachers and students. It integrates traditional classroom management with advanced Generative AI capabilities powered by the **Groq API** for ultra-fast, cloud-hosted inference.

## 2. Core Features

### For Teachers
* **Course Management:** Create and manage courses, upload syllabus, and share learning materials (PDFs, text).
* **Assignment Creation:** Generate and distribute assignments with custom rubrics.
* **AI-Assisted Grading:** Automatically grade student submissions and generate constructive feedback using Groq-powered AI.
* **Analytics Dashboard:** View student progress, identify common knowledge gaps, and track engagement.

### For Students
* **Course Enrollment:** Browse and enroll in available courses.
* **Smart AI Tutor (RAG Chat):** Ask questions about course materials. The AI retrieves relevant context from uploaded course documents and uses Groq to answer accurately without hallucinations.
* **Assignment Submission:** Upload completed assignments and view grades/AI feedback.
* **Personalized Learning Paths:** AI suggests topics to review based on past performance.

## 3. Technology Stack

### Frontend
* **Framework:** React + Vite
* **Styling:** Tailwind CSS (or similar UI library)
* **API Communication:** Axios/Fetch

### Backend
* **Framework:** Django & Django REST Framework (DRF)
* **Database:** SQLite (development) / PostgreSQL (production)
* **Vector Database:** ChromaDB (for storing document embeddings)
* **AI Integration:** **Groq API** (using models like Llama 3 or Mixtral for blazing-fast inference without local GPU requirements)
* **Document Processing:** PyPDF2 / LangChain (for chunking and extracting text from uploaded PDFs)

## 4. How It Works (Core Workflows)

### A. Document Upload & RAG Setup (Teacher)
1. Teacher uploads a course syllabus or reading material (PDF).
2. The backend extracts text from the PDF.
3. The text is split into smaller chunks (e.g., 500 tokens each).
4. Embeddings are generated for these chunks and stored in **ChromaDB**.

### B. Smart AI Tutoring (Student)
1. Student asks a question in the course chat (e.g., "What is the formula for standard deviation covered in week 2?").
2. The backend converts the query to an embedding and searches ChromaDB for the most relevant document chunks.
3. The retrieved chunks are combined with the student's question into a prompt.
4. The prompt is sent to the **Groq API**.
5. Groq processes the context instantly and streams the response back to the student's chat interface.

### C. AI Auto-Grading
1. Student submits an assignment.
2. The backend retrieves the submission text, the assignment prompt, and the teacher's rubric.
3. A structured prompt is sent to the **Groq API** asking it to evaluate the submission against the rubric.
4. Groq returns a suggested score and detailed feedback, which is saved to the database for the teacher to review or automatically released to the student.

## 5. Standout Features To Help AIEdu Compete
1. **Instant Study Actions:** Every AI response should support quick follow-ups like "simplify this", "give examples", "make flashcards", and "turn this into a test".
2. **Weak Topic Radar:** Detect repeated student confusion from chat, assignment mistakes, and quiz performance, then surface the top weak concepts for both teacher and student.
3. **Smart Revision Mode:** Generate a fast revision pack from course material with summary, key terms, likely exam questions, and flashcards in one flow.
4. **Evidence-First Chat:** Show short supporting snippets with each answer so the AI feels trustworthy and classroom-grounded.
5. **Fast Teacher Insights:** Highlight which topic is slowing the class down, which students may need help, and which materials are actually being used.
6. **Actionable Feedback:** Make grading outputs specific, with "what you did well", "what to fix", and "what to study next".
7. **Graceful Fallbacks:** If AI is slow or unavailable, return the best matching course notes instead of a dead-end error.

## 6. Next Steps
1. **Configure Groq API:** Add `GROQ_API_KEY` to the backend `.env` file.
2. **Update AI Service:** Refactor the existing local LLM integration to use the `groq` Python client or LangChain's Groq integration.
3. **Database Migrations:** Ensure the database schema reflects the Users, Courses, Assignments, and Chat models.
4. **Frontend Wiring:** Connect the React frontend to the new Groq-powered streaming endpoints.
