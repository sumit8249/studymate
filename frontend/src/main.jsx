import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BookOpen, Plus, Send, Paperclip, GraduationCap, MessageCircle, FileText, Brain, Trash2, Menu, X, Sparkles, LoaderCircle } from 'lucide-react';
import './styles.css';
import './markdown.css';

const API = 'http://127.0.0.1:8000/api';
const subjects = ['General', 'Computer Networks', 'Operating Systems', 'Data Structures & Algorithms', 'Java', 'Python', 'Mathematics', 'Physics', 'Software Engineering'];
const newId = () => crypto.randomUUID();
function App() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(localStorage.getItem('studymate_session') || '');
  const [messages, setMessages] = useState([]);
  const [subject, setSubject] = useState('General');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [uploaded, setUploaded] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [topic, setTopic] = useState('');
  const [difficulty, setDifficulty] = useState('Beginner');
  const [health, setHealth] = useState({ status: 'checking' });

  async function request(path, options = {}) {
    let response;
    try {
      response = await fetch(`${API}${path}`, options);
    } catch {
      throw new Error('Could not connect to the study assistant. Check that the backend is running, then try again.');
    }
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail.trim() : '';
      const message = detail || (response.status === 422
        ? 'Please check the information you entered and try again.'
        : `The request failed (${response.status}). Please try again.`);
      throw new Error(message);
    }
    return data;
  }
  function responseText(data, field, label) {
    const text = data && typeof data[field] === 'string' ? data[field] : '';
    if (!text.trim()) throw new Error(`The study assistant returned an empty ${label}. Please try again.`);
    return text;
  }
  async function refreshSessions() { try { setSessions(await request('/sessions')); } catch (e) { setNotice(`Cannot connect to backend: ${e.message}`); } }
  async function startSession() {
    try {
      const s = await request('/sessions', { method: 'POST' });
      setSessionId(s.id); localStorage.setItem('studymate_session', s.id); setMessages([]); setUploaded(''); setNotice(''); setInput('');
      await refreshSessions(); setSidebarOpen(false);
    } catch (e) { setNotice(e.message); }
  }
  async function openSession(id) {
    try { const data = await request(`/history/${id}`); setSessionId(id); localStorage.setItem('studymate_session', id); setMessages(data.map(m => ({ role: m.role, content: m.content }))); setUploaded(''); setNotice(''); setSidebarOpen(false); }
    catch (e) { setNotice(e.message); }
  }
  useEffect(() => { request('/health').then(setHealth).catch(() => setHealth({ status: 'offline' })); refreshSessions(); }, []);
  useEffect(() => { if (sessionId) openSession(sessionId); else startSession(); }, []);

  async function sendMessage(text = input) {
    const value = text.trim(); if (!value || loading) return;
    let sid = sessionId;
    if (!sid) { try { const s = await request('/sessions', { method: 'POST' }); sid = s.id; setSessionId(sid); localStorage.setItem('studymate_session', sid); } catch (e) { setNotice(e.message); return; } }
    setInput(''); setNotice(''); setMessages(prev => [...prev, { role: 'user', content: value }, { role: 'assistant', content: '', pending: true }]); setLoading(true);
    try {
      const data = await request('/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sid, message: value, subject }) });
      setMessages(prev => [...prev.slice(0, -1), { role: 'assistant', content: responseText(data, 'answer', 'answer') }]); await refreshSessions();
    } catch (e) { setMessages(prev => [...prev.slice(0, -1), { role: 'assistant', content: `**I couldn't answer that yet.**\n\n${e.message}` }]); }
    finally { setLoading(false); }
  }
  async function uploadPdf(file) {
    if (!file) return; if (!sessionId) { setNotice('Start a chat before uploading a PDF.'); return; }
    const form = new FormData(); form.append('file', file); setNotice('Uploading and reading your PDF…');
    try { const data = await request(`/upload/${sessionId}`, { method: 'POST', body: form }); setUploaded(data.filename); setNotice(`${data.filename} uploaded (${data.pages} pages). Ask a question about it!`); }
    catch (e) { setNotice(e.message); }
  }
  async function runStudyAction(kind) {
    if (!topic.trim()) { setNotice('Enter a topic first.'); return; }
    setLoading(true); setNotice('');
    try {
      const data = await request(`/${kind}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sessionId, subject, topic, difficulty }) });
      setMessages(prev => [...prev, { role: 'assistant', content: responseText(data, 'result', 'study result') }]); setTopic(''); await refreshSessions();
    } catch (e) { setNotice(e.message); } finally { setLoading(false); }
  }
  async function removeSession(e, id) { e.stopPropagation(); try { await request(`/sessions/${id}`, { method: 'DELETE' }); if (sessionId === id) { setSessionId(''); localStorage.removeItem('studymate_session'); setMessages([]); setUploaded(''); await startSession(); } await refreshSessions(); } catch (err) { setNotice(err.message); } }

  return <div className="app-shell">
    {sidebarOpen && <button className="mobile-scrim" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar"/>}
    <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-icon"><GraduationCap size={23}/></div><div><strong>StudyMate</strong><small>AI STUDY COMPANION</small></div><button className="icon-button close-sidebar" onClick={() => setSidebarOpen(false)}><X size={18}/></button></div>
      <button className="new-chat" onClick={startSession}><Plus size={17}/> New study session</button>
      <div className="side-label">YOUR WORKSPACE</div>
      <div className="nav-item active"><MessageCircle size={17}/> Study chat</div>
      <div className="side-label recent-label">RECENT CONVERSATIONS</div>
      <div className="session-list">{sessions.map(s => <button key={s.id} className={`session-item ${s.id === sessionId ? 'selected' : ''}`} onClick={() => openSession(s.id)}><MessageCircle size={15}/><span>{s.title || 'New study chat'}</span><span className="delete-wrap" onClick={e => removeSession(e, s.id)}><Trash2 size={14}/></span></button>)}</div>
      <div className="sidebar-bottom"><div className="avatar">S</div><div className="profile-text"><strong>Student workspace</strong><small>Learning at your pace</small></div><span className={`status-dot ${health.status === 'ok' ? 'online' : ''}`}/></div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><button className="icon-button menu-button" onClick={() => setSidebarOpen(true)}><Menu size={20}/></button><div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong>Study assistant</strong></div><div className="top-status"><span className={`status-dot ${health.status === 'ok' ? 'online' : ''}`}/>{health.status === 'ok' ? (health.api_key_configured ? 'Gemini connected' : 'Add Gemini API key') : 'Checking API'}</div></header>
      <div className="content-area">
        <div className="page-heading"><div><div className="eyebrow"><Sparkles size={14}/> YOUR PERSONAL AI TUTOR</div><h1>What are we learning <span>today?</span></h1><p>Ask questions, understand difficult topics, and turn your notes into knowledge.</p></div><div className="heading-art"><div className="art-circle"><BookOpen size={32}/></div><span className="art-spark spark-one">✦</span><span className="art-spark spark-two">✧</span></div></div>
        <section className="settings-row"><label className="select-wrap"><span>SUBJECT</span><select value={subject} onChange={e => setSubject(e.target.value)}>{subjects.map(s => <option key={s}>{s}</option>)}</select></label><label className="select-wrap difficulty"><span>LEVEL</span><select value={difficulty} onChange={e => setDifficulty(e.target.value)}><option>Beginner</option><option>Intermediate</option><option>Advanced</option></select></label><div className="upload-chip"><label className="upload-label"><Paperclip size={16}/><span>{uploaded || 'Upload study PDF'}</span><input type="file" accept="application/pdf,.pdf" onChange={e => uploadPdf(e.target.files?.[0])}/></label>{uploaded && <button className="tiny-x" onClick={() => setUploaded('')} title="Hide filename">×</button>}</div></section>
        {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}
        <section className="chat-card">
          <div className="chat-header"><div className="tutor-avatar"><Brain size={20}/></div><div><strong>StudyMate Tutor</strong><small><span className="status-dot online"/> Ready to help you learn</small></div><span className="powered">POWERED BY GEMINI</span></div>
          <div className="messages" aria-live="polite">
            {messages.length === 0 ? <div className="welcome"><div className="welcome-icon"><GraduationCap size={28}/></div><h2>Hey there, learner! 👋</h2><p>I'm your study partner. Pick a subject and tell me what you're curious about. We'll break it down together.</p><div className="suggestions"><button onClick={() => sendMessage('Explain a difficult concept in '+subject+' in simple language with an example.') }><span className="suggestion-icon purple"><Brain size={17}/></span><span><strong>Clarify a doubt</strong><small>Understand a concept step by step</small></span></button><button onClick={() => {setTopic(''); document.getElementById('topic-input')?.focus();}}><span className="suggestion-icon blue"><FileText size={17}/></span><span><strong>Make a topic summary</strong><small>Get concise notes for revision</small></span></button><button onClick={() => {setTopic(''); document.getElementById('topic-input')?.focus();}}><span className="suggestion-icon amber"><BookOpen size={17}/></span><span><strong>Practise what you learned</strong><small>Generate questions and answers</small></span></button></div></div> : messages.map((m, i) => <div key={i} className={`message-row ${m.role === 'user' ? 'user-row' : ''}`}><div className={`message-avatar ${m.role === 'user' ? 'user-avatar' : ''}`}>{m.role === 'user' ? 'S' : <Brain size={16}/>}</div><div className={`message-bubble ${m.role === 'user' ? 'user-bubble' : ''}`}>{m.pending ? <span className="typing"><i/><i/><i/> Thinking through it…</span> : <ReactMarkdown remarkPlugins={[remarkGfm]} components={{table: ({children}) => <div className="markdown-table-wrap"><table>{children}</table></div>}}>{m.content}</ReactMarkdown>}</div></div>)}
            {messages.length > 0 && !loading && <div className="followups"><span>Continue learning</span><button onClick={() => sendMessage('Explain that more simply with another example.')}>Explain more simply</button><button onClick={() => sendMessage('Give me the key points to remember.')}>Key points</button><button onClick={() => sendMessage('Give me an exam-ready answer for 5 marks.')}>5-mark answer</button></div>}
          </div>
          <div className="composer"><textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey) {e.preventDefault(); sendMessage();}}} placeholder="Ask a doubt, explain a concept, or ask a follow-up…" rows={2}/><div className="composer-footer"><span><kbd>Enter</kbd> to send · <kbd>Shift + Enter</kbd> for new line</span><button className="send-button" disabled={!input.trim() || loading} onClick={() => sendMessage()}>{loading ? <LoaderCircle size={17} className="spin"/> : <Send size={17}/>} <span>Send</span></button></div></div>
        </section>
        <section className="tools-section"><div className="tools-title"><div><h3>Study tools</h3><p>Turn any topic into a focused learning session.</p></div><span className="tools-tag">QUICK ACTIONS</span></div><div className="tool-grid"><div className="tool-card"><div className="tool-card-top"><div className="tool-icon summary-icon"><FileText size={19}/></div><span className="tool-number">01</span></div><h4>Topic summary</h4><p>Get clear notes, key terms, and an exam-ready recap.</p><div className="tool-controls"><input id="topic-input" value={topic} onChange={e => setTopic(e.target.value)} placeholder="Enter a topic…" onKeyDown={e => e.key === 'Enter' && runStudyAction('summary')}/><button disabled={loading} onClick={() => runStudyAction('summary')} aria-label="Generate summary"><Send size={15}/></button></div></div><div className="tool-card"><div className="tool-card-top"><div className="tool-icon quiz-icon"><Brain size={19}/></div><span className="tool-number">02</span></div><h4>Practice questions</h4><p>Test your understanding with five questions and an answer key.</p><div className="tool-controls"><input value={topic} onChange={e => setTopic(e.target.value)} placeholder="Enter a topic…" onKeyDown={e => e.key === 'Enter' && runStudyAction('quiz')}/><button disabled={loading} onClick={() => runStudyAction('quiz')} aria-label="Generate practice questions"><Send size={15}/></button></div></div></div></section>
        <footer>Made for curious minds <span>✦</span> AI can make mistakes, so verify important facts with your course materials.</footer>
      </div>
    </main>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
