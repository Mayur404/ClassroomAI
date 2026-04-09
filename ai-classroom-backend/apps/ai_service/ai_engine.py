import os
import chromadb
from groq import Groq
from PyPDF2 import PdfReader
from django.conf import settings
import requests

# Initialize ChromaDB Local Client (Persistent)
# Stores embedded vectors into a local sqlite and parquet files inside /media/chromadb/
chroma_client = chromadb.PersistentClient(path=os.path.join(settings.BASE_DIR, 'media', 'chromadb'))

class CustomGroqService:
    @staticmethod
    def get_client():
        return Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

    @staticmethod
    def answer_question(course_id, question):
        """RAG Query using Groq AI and ChromaDB without external servers."""
        groq_client = CustomGroqService.get_client()
        PRIMARY_MODEL = os.environ.get("GROQ_MODEL_PRIMARY", "llama-3.3-70b-versatile")

        collection = chroma_client.get_or_create_collection(name=f"course_{course_id}")
        
        try:
            results = collection.query(query_texts=[question], n_results=3)
            context = " ".join(results["documents"][0]) if results["documents"] else "No context found."
        except Exception:
            context = "No context found."

        system_prompt = (
            "You are an AI Tutor. Use the provided context from course materials to answer."
            "If the context doesn't contain the answer, politely say you don't know based on the materials."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context: {context}\n\nQuestion: {question}"}
        ]

        completion = groq_client.chat.completions.create(
            messages=messages,
            model=PRIMARY_MODEL,
        )
        
        return completion.choices[0].message.content


class CustomSarvamService:
    @staticmethod
    def translate_to_hindi(text):
        """Uses Sarvam API to translate text into Hindi for regional students."""
        sarvam_api_key = os.environ.get("SARVAM_API_KEY", "")
        if not sarvam_api_key:
            return text

        url = "https://api.sarvam.ai/translate"
        payload = {
            "input": text,
            "source_language_code": "en-IN",
            "target_language_code": "hi-IN",
            "speaker_gender": "Male",
            "mode": "formal",
            "model": "sarvam-translate:v1",
            "enable_preprocessing": False
        }
        headers = {
            "api-subscription-key": sarvam_api_key,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                translated_data = response.json()
                return translated_data.get("translated_text", text)
            else:
                return text
        except Exception as e:
            return text

class CourseMaterialProcessor:
    @staticmethod
    def extract_and_store_material(course_id, pdf_path):
        """Extracts text from PDF, chunks it, and stores locally in ChromaDB."""
        reader = PdfReader(pdf_path)
        text = "".join(page.extract_text() for page in reader.pages)
        
        chunk_size = 1000
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        collection = chroma_client.get_or_create_collection(name=f"course_{course_id}")
        
        collection.add(
            documents=chunks,
            metadatas=[{"source": pdf_path, "chunk": i} for i in range(len(chunks))],
            ids=[f"doc_{course_id}_{i}" for i in range(len(chunks))]
        )
        return {"status": "success", "chunks_stored": len(chunks)}
