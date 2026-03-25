# Setup & Running Guide

Complete instructions for setting up and running the AI Classroom backend.

## Prerequisites

- Python 3.10+
- pip or conda
- Ollama (for LLM inference)
- SQLite (included with Python) or PostgreSQL
- Redis (optional, for caching)

## Installation

### 1. Clone/Setup Project

```bash
cd ai-classroom-backend
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

Key packages:
- Django 5.0
- djangorestframework
- pdfplumber & pypdfium2 (PDF extraction)
- rapidocr-onnxruntime (OCR for scanned PDFs)
- chromadb (vector database)
- sentence-transformers (embeddings)
- ollama (LLM client)
- requests & httpx (HTTP clients)

### 4. Configure Environment

Copy and edit `.env`:

```bash
cp .env.example .env
```

Key variables:
```bash
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

# Ollama (LLM)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_PRIMARY=qwen2.5:7b

# Email
INSTITUTE_EMAIL_DOMAIN=your-domain.com

# Cache
CACHE_TIMEOUT=300
ANSWER_CACHE_TIMEOUT=300
SEARCH_CACHE_TIMEOUT=1800
```

### 5. Initialize Database

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser (admin account)
python manage.py createsuperuser
# Follow prompts to create admin user
```

## Running Ollama

Ollama is required for LLM-based features (chat, grading, etc.).

### Download & Install Ollama

Go to [ollama.ai](https://ollama.ai) and download for your OS.

### Start Ollama Server

```bash
# On Windows (in new terminal)
ollama serve

# On macOS/Linux
ollama serve
```

Default URL: `http://localhost:11434`

### Pull Model

In another terminal (while ollama serve is running):

```bash
# Pull qwen2.5:7b (recommended - good quality, 7GB RAM)
ollama pull qwen2.5:7b

# Or try other models:
ollama pull llama2              # Smaller, faster
ollama pull mistral             # Larger, slower
ollama pull neural-chat         # Optimized for chat
```

Check available models:
```bash
ollama list
```

## Running Django Development Server

### Start Server

```bash
python manage.py runserver
```

Output:
```
Starting development server at http://127.0.0.1:8000/
```

The server runs on `http://localhost:8000`

### Stop Server

Press `Ctrl+C` in terminal

### Common Issues

**Port 8000 already in use:**
```bash
python manage.py runserver 8001  # Use different port
```

**Module not found errors:**
```bash
# Reinstall dependencies
pip install -r requirements.txt -U

# Or reinstall specific package
pip install --upgrade pdfplumber
```

## Testing

### Run All Tests

```bash
python manage.py test
```

### Run Specific App Tests

```bash
python manage.py test apps.chat
python manage.py test apps.assignments
python manage.py test apps.analytics
```

### Run With Verbosity

```bash
python manage.py test -v 2
```

## Using the API

### With cURL

```bash
# Get CSRF token first
curl -X GET http://localhost:8000/api/courses/

# Ask a question
curl -X POST http://localhost:8000/api/chat/courses/1/ask/ \
  -H "Content-Type: application/json" \
  -d '{"message": "What is machine learning?"}'
```

### With Python Requests

```python
import requests

# Ask a question
response = requests.post(
    'http://localhost:8000/api/chat/courses/1/ask/',
    json={'message': 'What is photosynthesis?'},
    headers={'Authorization': 'Bearer YOUR_TOKEN'}
)

print(response.json())
```

### With Postman

1. Open Postman
2. Create new request
3. Method: POST
4. URL: `http://localhost:8000/api/chat/courses/1/ask/`
5. Headers:
   - Content-Type: application/json
   - Authorization: Bearer YOUR_TOKEN
6. Body (JSON):
   ```json
   {
     "message": "Your question here"
   }
   ```

## First Time Setup Checklist

- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file configured with correct settings
- [ ] Database migrated (`python manage.py migrate`)
- [ ] Superuser created (`python manage.py createsuperuser`)
- [ ] Ollama installed and running (`ollama serve`)
- [ ] Model pulled (`ollama pull qwen2.5:7b`)
- [ ] Django server started (`python manage.py runserver`)
- [ ] Can access admin at `http://localhost:8000/admin/`

## Admin Interface

Access admin at: `http://localhost:8000/admin/`

Login with superuser credentials created above.

In admin you can:
- Create courses
- Add materials
- Manage users
- Create assignments
- View submissions

## Development Workflow

### 1. Make Changes

Edit code in `apps/` directory.

### 2. Test Locally

```bash
python manage.py test
```

### 3. Check Server

Server auto-reloads on code changes (with `runserver`).

### 4. Check API

Test endpoints with cURL, Postman, or Python.

## Production Deployment

For production, you'll want:

1. **Use PostgreSQL** instead of SQLite
2. **Enable DEBUG=false** in `.env`
3. **Use strong SECRET_KEY**
4. **Setup Redis** for caching
5. **Use Gunicorn** or similar WSGI server
6. **Setup SSL/TLS** (HTTPS)
7. **Use environment variables** for secrets
8. **Setup proper logging**

Example Docker setup (advanced):
```dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "config.wsgi"]
```

## Performance Tips

### Enable Caching

In `.env`:
```bash
CACHE_TIMEOUT=3600
ANSWER_CACHE_TIMEOUT=300
SEARCH_CACHE_TIMEOUT=1800
```

### Use Premium Answer Engine

```python
from apps.ai_service.services import answer_course_question_premium

response = answer_course_question_premium(
    course=course,
    question=question,
    user=user,
    use_cache=True,  # Enable caching
)
```

### Batch Processing

For bulk operations:
```python
from apps.ai_service.premium_answer_engine import batch_optimizer

# Process multiple items
for item in items:
    optimizer.cache_answer(item['question'], item['course_id'], item['answer'])
```

## Troubleshooting

### "Connection refused" for Ollama

**Problem:** Can't connect to LLM
**Solution:**
- Make sure Ollama is running: `ollama serve`
- Check URL in `.env` matches `OLLAMA_BASE_URL`
- Default: `http://localhost:11434`

### "ModuleNotFoundError"

**Problem:** Python can't find a package
**Solution:**
```bash
pip install -r requirements.txt -U
```

### Database locked (SQLite)

**Problem:** "database is locked" error
**Solution:**
- Only one process can write to SQLite at a time
- For concurrent access, use PostgreSQL
- For development, this usually resolves itself

### Ollama model too large

**Problem:** Model uses too much RAM
**Solution:**
```bash
# Use smaller model
ollama pull llama2
```

Then update `.env`:
```bash
OLLAMA_MODEL_PRIMARY=llama2
```

### Slow responses

**Problem:** Answers take >2 seconds
**Solution:**
1. Check Ollama is running with decent hardware
2. Try smaller model: `ollama pull llama2`
3. Enable caching in `.env`
4. Check network latency

## Common Commands Reference

```bash
# Virtual environment
source venv/bin/activate          # Activate (macOS/Linux)
venv\Scripts\activate             # Activate (Windows)

# Database
python manage.py migrate          # Apply migrations
python manage.py makemigrations   # Create migrations
python manage.py createsuperuser  # Create admin user
python manage.py flush            # Clear database

# Server
python manage.py runserver        # Start dev server
python manage.py runserver 8001   # Start on port 8001

# Testing
python manage.py test             # Run all tests
python manage.py test apps.chat   # Test specific app

# Management
python manage.py shell            # Django shell
python manage.py dbshell          # Database shell

# Ollama
ollama serve                       # Start Ollama server
ollama pull qwen2.5:7b            # Download model
ollama list                        # List downloaded models
```

## Next Steps

1. **Upload course materials** through admin
2. **Create a course** through API
3. **Test chat endpoint** with a question
4. **Monitor performance** and adjust settings

## Support

For detailed API usage, see `README.md`.

For module-specific documentation, check inline docstrings in code.

Happy coding! 🚀
