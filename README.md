# StudyMate — AI Study Companion

A beginner-friendly study chatbot built with **React + Vite**, **FastAPI**, **LangChain**, and **Google Gemini**. It supports conversational doubt clarification, summaries, practice questions, saved chat history, and PDF notes.

## Features
- Conversational tutoring with recent chat context
- Subject and difficulty selectors
- Summary and practice-question actions
- PDF upload (text-based PDFs up to 12 MB)
- Simple retrieval from uploaded PDF text, alongside general AI knowledge
- Chat sessions and messages persisted in a local SQLite database
- Responsive interface

## Requirements
- Python 3.10 or newer (Python 3.11 recommended)
- Node.js 20 or newer and npm
- A Gemini API key: https://aistudio.google.com/apikey

## Run in VS Code (Windows PowerShell)

### 1. Open the project
Extract the ZIP, open the `ai-study-companion` folder in VS Code.

### 2. Configure the backend
Open a VS Code terminal:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `backend/.env` and replace `your_google_api_key_here` with your real key. Keep this file private; do not commit it to GitHub.

If PowerShell blocks environment activation, run this once in the terminal and retry activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Start the API (keep this terminal open):

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/docs` for the FastAPI API page. The health endpoint is `http://127.0.0.1:8000/api/health`.

### 3. Start the React frontend
Open a **second** VS Code terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL Vite prints, usually `http://localhost:5173`.

## First test
1. Check that the top-right status says Gemini connected. If not, confirm the key in `backend/.env`, save, and restart Uvicorn.
2. Select a subject and ask a question.
3. Use Topic summary or Practice questions by entering a topic.
4. Upload a text-based PDF and ask questions about the uploaded notes.
5. Create another study session; conversations persist in `backend/data/study_companion.db`.

## Notes and limitations
- The first run needs internet access to call Gemini and install packages.
- Gemini API usage may be subject to quotas or charges depending on your Google AI account.
- PDF support extracts selectable text. Scanned/image-only PDFs need OCR and are not supported in this starter version.
- PDF text is stored locally in `backend/uploads/` and chat history in SQLite. Delete a session in the sidebar to remove its chat and uploaded PDF text.
- Retrieval is intentionally lightweight keyword matching to keep the project easy to understand. For a larger knowledge base, replace it with embeddings and a vector database.
- This is a local student project, not a hardened public deployment. Add authentication, stricter upload controls, and production CORS settings before hosting it publicly.

## Project structure

```text
ai-study-companion/
├── README.md
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── .gitignore
│   ├── data/       # created at runtime; SQLite history
│   └── uploads/    # created at runtime; extracted PDF text
└── frontend/
    ├── index.html
    ├── package.json
    └── src/
        ├── main.jsx
        └── styles.css
```
