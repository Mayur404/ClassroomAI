# 🎓 AI Classroom Tutor

A complete, production-ready AI tutoring system that allows students to upload their coursework (PDFs) and interact with an AI Teacher. This project uses a hybrid architecture: **Local RAG (Retrieval-Augmented Generation)** for vector search to eliminate token-heavy document parsing, and the **Gemini API** for high-quality, conversational answers and assignment generation.

![AI Classroom Screenshot](https://raw.githubusercontent.com/mayur/ai-classroom/main/docs/screenshot.png) *(Place your screenshot here)*

## ✨ Features

- **📄 Local PDF Parsing:** Extracts and chunks PDF text entirely locally using `pdfplumber`. No expensive API calls for reading documents.
- **🧠 Local Vector Search (RAG):** Uses `ChromaDB` and `sentence-transformers` (`all-MiniLM-L6-v2`) to embed chunks and perform vector similarity search on your machine.
- **💬 Conversational AI Teacher:** Powered by `gemini-2.5-flash`, the AI tutor answers questions strictly using your uploaded syllabus/materials. Output is beautifully formatted with `react-markdown`.
- **🗺️ Auto-Learning Paths:** Automatically extracts topics from your PDF and generates a class-by-class schedule.
- **📝 Interactive Assignments:** Generates custom MCQ and Essay assignments based on your materials. Includes inline AI grading with personalized feedback.
- **🎨 Premium UI:** A stunning, modern dark theme with glassmorphism effects, micro-animations, and a fully responsive tabbed interface.
- **🛡️ Zero-Setup Robustness:** Auto-creates demo users and courses natively—just spin it up and it instantly works without manual database population.

---

## 🏗️ Architecture

1. **Frontend:** React + Vite + Tailwind/CSS Modules (`@tanstack/react-query`, `react-router-dom`, `react-markdown`)
2. **Backend:** Django Rest Framework
3. **Database:** SQLite (default) + ChromaDB (Local Vector Store)
4. **AI Models:**
   - Embeddings: `all-MiniLM-L6-v2` (Local)
   - Generation: `gemini-2.5-flash` (Google API)

---

## 🚀 Quick Start

### 1. Backend Setup

Navigate to the backend directory and set up your Python environment:

```bash
cd ai-classroom-backend
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies (includes Django, ChromaDB, sentence-transformers)
pip install -r requirements.txt
```

Create a `.env` file in the `ai-classroom-backend` directory and add your Gemini API Key:
```ini
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL_PRIMARY=gemini-2.5-flash
GEMINI_MODEL_CODER=gemini-2.5-flash
```

Run the backend server (this will auto-create the database and demo course):
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

### 2. Frontend Setup

Open a new terminal and navigate to the frontend directory:

```bash
cd ai-classroom-frontend
npm install

# Start the Vite development server
npm run dev
```

The application will be running at `http://localhost:5173`.

---

## 🧑‍🎓 Usage Guide

1. **Login:** Enter any name and email address. The demo does not require passwords.
2. **Upload Materials:** Go to the "Materials" tab and upload a PDF. You will see ChromeDB extract the topics instantly.
3. **Chat:** Ask the AI Teacher a question in the right-hand Chat sidebar. It will perform a local vector search in ChromaDB and answer based on your PDF!
4. **Assignments:** Navigate to the "Assignments" tab to generate and take interactive quizzes graded by the AI.

## 🤝 Contributing

Feel free to fork this project, submit pull requests, or open issues. It's designed to be a starting point for more complex EdTech applications!
