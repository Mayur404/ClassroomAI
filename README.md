# 🎓 AI Classroom Tutor (100% Local & Free)

A complete, production-ready AI tutoring system that allows students to upload their coursework and interact with an AI Teacher. This project uses a **100% local, offline hybrid architecture**:
1. **Local RAG (Retrieval-Augmented Generation)** for lightning-fast vector search over your documents.
2. **Local LLM (Ollama / Llama 3.2)** for high-quality, private conversational answers and assignment generation without API costs.

![AI Classroom Screenshot](https://raw.githubusercontent.com/mayur/ai-classroom/main/docs/screenshot.png) *(Place your screenshot here)*

## ✨ Features

- **🌐 100% Offline & Private:** Your data never leaves your machine. No API keys, no subscriptions, no rate limits.
- **📚 Multi-Course Management:** Create isolated classrooms. Upload multiple PDFs or paste raw text per class.
- **📄 Local Document Parsing:** Extracts and chunks PDF text entirely locally using `pdfplumber`. 
- **🧠 Local Vector Search (RAG):** Uses `ChromaDB` and `sentence-transformers` (`all-MiniLM-L6-v2`) to embed chunks and perform vector similarity search instantly.
- **💬 Conversational AI Teacher:** Powered by `Ollama` (`llama3.2`), the AI tutor answers questions strictly using your uploaded syllabus/materials. Chat history is preserved per classroom!
- **🗺️ Auto-Learning Paths:** Automatically extracts topics from your materials and generates a class-by-class schedule.
- **📝 Interactive Assignments:** Generates custom MCQ and Essay assignments based on your materials. Includes inline AI grading with personalized feedback.
- **🎨 Premium UI:** A stunning, modern dark theme with glassmorphism effects, micro-animations, and a fully responsive tabbed interface.

---

## 🏗️ Architecture

1. **Frontend:** React + Vite (`@tanstack/react-query`, `react-router-dom`, `react-markdown`)
2. **Backend:** Django Rest Framework
3. **Database:** SQLite (Relational) + ChromaDB (Vector Store)
4. **AI Models (All Local):**
   - Embeddings: `all-MiniLM-L6-v2` (`sentence-transformers`)
   - Generation: `llama3.2` (via `Ollama`)

---

## 🚀 Quick Start

### 1. Prerequisites (Ollama)
Because this app runs powerful AI models entirely on your hardware, you must install Ollama.
1. Download and install [Ollama](https://ollama.com/).
2. Open a terminal and download the required model (we use the blazing-fast 3B parameter Llama model):
   ```bash
   ollama run llama3.2
   ```
*(Keep Ollama running in the background while using the app).*

### 2. Backend Setup

Navigate to the backend directory and set up your Python environment:

```bash
cd ai-classroom-backend
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Run the backend server (this will auto-create the database):
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

### 3. Frontend Setup

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

1. **Login:** Enter any name and email address. The demo uses passwordless local auth.
2. **Create a Classroom:** Use the left sidebar to add a new course (e.g., "History 101").
3. **Upload Materials:** Go to the "Materials" tab and upload a PDF or paste text. The system will extract topics and store vector embeddings locally.
4. **Chat:** Ask the AI Teacher a question in the right-hand Chat sidebar. It performs a local vector search in ChromaDB and answers based strictly on your PDF! Switch between classrooms and your chat history persists.
5. **Assignments:** Navigate to the "Assignments" tab to generate and take interactive quizzes graded by the local AI.

---

## 🤝 Contributing

Feel free to fork this project, submit pull requests, or open issues. It's designed to be a premier starting point for private, offline EdTech applications!
