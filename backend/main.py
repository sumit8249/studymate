import logging, os, re, json, sqlite3, uuid
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pypdf import PdfReader
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "study_companion.db"
load_dotenv(BASE_DIR / ".env")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Study Companion API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    session_id: str
    message: str
    subject: str = "General"

class ActionRequest(BaseModel):
    session_id: str
    subject: str = "General"
    topic: str
    difficulty: str = "Beginner"

SYSTEM_PROMPT = """You are StudyMate, a friendly, patient AI study tutor. Help students learn, not just copy answers. Explain concepts clearly, use examples, ask clarifying questions if the request is vague, and preserve conversational context. If study notes are provided, prioritize them and say when the answer uses them. Do not pretend uploaded notes contain something they do not. Format answers with clear headings and bullet points. For exam answers, be concise and structured."""

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        con.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
init_db()

def get_model():
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key or key == "your_google_api_key_here":
        raise HTTPException(status_code=503, detail="Gemini API key is missing. Add GOOGLE_API_KEY to backend/.env and restart the backend.")
    return ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), google_api_key=key, temperature=0.4)

def ensure_session(session_id: str, title: str = "New study chat"):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO sessions (id, title) VALUES (?, ?)", (session_id, title[:80]))

def read_history(session_id: str):
    with db() as con:
        rows = con.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT 16", (session_id,)).fetchall()
    return list(reversed(rows))

def extract_text_content(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        block_type = value.get("type")
        if block_type is not None and block_type not in {"text", "output_text"}:
            return ""
        for key in ("text", "content", "answer", "result"):
            if key in value:
                return extract_text_content(value[key])
        return ""
    if isinstance(value, (list, tuple)):
        parts = [extract_text_content(part) for part in value]
        return "\n".join(part for part in parts if part)
    return ""

def extract_response_text(response) -> str:
    content = getattr(response, "content", response)
    text = extract_text_content(content).strip()
    if not text:
        raise ValueError("Gemini returned an empty text response.")
    return text

def add_message(session_id: str, role: str, content: str):
    with db() as con:
        con.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, role, content))
        con.execute("UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))

def document_context(session_id: str, query: str) -> str:
    path = UPLOAD_DIR / f"{session_id}.txt"
    if not path.exists(): return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    chunks = [text[i:i+1200] for i in range(0, len(text), 900)]
    words = set(re.findall(r"[a-zA-Z0-9]{3,}", query.lower()))
    def score(chunk):
        cw = set(re.findall(r"[a-zA-Z0-9]{3,}", chunk.lower()))
        return len(words & cw)
    ranked = sorted(chunks, key=score, reverse=True)[:3]
    selected = [c for c in ranked if score(c) > 0]
    if not selected: selected = chunks[:2]
    return "\n\n".join(selected)[:3500]

@app.get("/api/health")
def health():
    return {"status": "ok", "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), "api_key_configured": bool(os.getenv("GOOGLE_API_KEY", "").strip() and os.getenv("GOOGLE_API_KEY") != "your_google_api_key_here")}

@app.get("/api/sessions")
def list_sessions():
    with db() as con:
        rows = con.execute("SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/sessions")
def create_session():
    sid = str(uuid.uuid4())
    ensure_session(sid)
    return {"id": sid, "title": "New study chat"}

@app.get("/api/history/{session_id}")
def history(session_id: str):
    ensure_session(session_id)
    with db() as con:
        rows = con.execute("SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    return [dict(r) for r in rows]

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    with db() as con:
        con.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        con.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    (UPLOAD_DIR / f"{session_id}.txt").unlink(missing_ok=True)
    return {"ok": True}

@app.post("/api/upload/{session_id}")
async def upload_pdf(session_id: str, file: UploadFile = File(...)):
    ensure_session(session_id)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    raw = await file.read()
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF must be smaller than 12 MB.")
    try:
        import io
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read this PDF: {e}")
    if not text.strip():
        raise HTTPException(status_code=400, detail="No selectable text found. Scanned PDFs need OCR, which this simple version does not include.")
    (UPLOAD_DIR / f"{session_id}.txt").write_text(text[:300000], encoding="utf-8")
    return {"ok": True, "filename": file.filename, "pages": len(reader.pages), "characters": len(text), "message": "PDF uploaded. You can now ask questions about these notes."}

@app.post("/api/chat")
def chat(req: ChatRequest):
    ensure_session(req.session_id, req.message[:60])
    model = get_model()
    history_rows = read_history(req.session_id)
    context = document_context(req.session_id, req.message)
    system = SYSTEM_PROMPT + f"\nStudent's selected subject: {req.subject}."
    if context:
        system += "\nRelevant excerpts from the student's uploaded PDF (may be incomplete):\n" + context + "\nUse these excerpts when relevant, and distinguish them from general knowledge."
    messages = [SystemMessage(content=system)]
    for row in history_rows:
        messages.append(HumanMessage(content=row["content"]) if row["role"] == "user" else AIMessage(content=row["content"]))
    messages.append(HumanMessage(content=req.message))
    try:
        answer = extract_response_text(model.invoke(messages))
    except Exception as exc:
        logger.error("Gemini chat request failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Gemini couldn't complete this response. Check the backend API key, internet connection, or usage quota, then try again.") from None
    add_message(req.session_id, "user", req.message)
    add_message(req.session_id, "assistant", answer)
    with db() as con:
        con.execute("UPDATE sessions SET title=CASE WHEN title='New study chat' THEN ? ELSE title END WHERE id=?", (req.message[:55], req.session_id))
    return {"answer": answer, "session_id": req.session_id, "used_uploaded_notes": bool(context)}

@app.post("/api/summary")
def summary(req: ActionRequest):
    model = get_model()
    context = document_context(req.session_id, req.topic)
    prompt = f"Create a useful study summary for subject {req.subject}, topic {req.topic}. Include: 1) simple explanation, 2) key points, 3) important terms/formulas if relevant, 4) a short exam-ready summary. Difficulty: {req.difficulty}. If provided, prioritize this uploaded study material:\n{context or 'No uploaded PDF context available; use general knowledge.'}"
    try:
        result = extract_response_text(model.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]))
    except Exception as exc:
        logger.error("Gemini summary request failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Gemini couldn't create this summary. Check the backend API key, internet connection, or usage quota, then try again.") from None
    return {"result": result}

@app.post("/api/quiz")
def quiz(req: ActionRequest):
    model = get_model()
    context = document_context(req.session_id, req.topic)
    prompt = f"Create 5 practice questions for {req.subject}, topic {req.topic}, difficulty {req.difficulty}. Include a mix of question types where appropriate. Put questions first, then an Answer Key with short explanations at the end so the learner can try first. Use uploaded notes if relevant:\n{context or 'No uploaded PDF context available; use general knowledge.'}"
    try:
        result = extract_response_text(model.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]))
    except Exception as exc:
        logger.error("Gemini practice-question request failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Gemini couldn't create these practice questions. Check the backend API key, internet connection, or usage quota, then try again.") from None
    return {"result": result}
