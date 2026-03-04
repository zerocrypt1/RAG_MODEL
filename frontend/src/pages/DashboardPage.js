import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import toast from 'react-hot-toast';
import { fileAPI, chatAPI, historyAPI, startVoiceRecognition } from '../utils/api';

// ── Helpers ──────────────────────────────────────────────────────────────────
function formatBytes(bytes) {
  if (!bytes) return '—';
  const k = 1024, sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function fileIcon(type) {
  if (!type) return '📄';
  if (type.includes('pdf'))   return '📕';
  if (type.includes('image')) return '🖼️';
  if (type.includes('word') || type.includes('doc')) return '📝';
  if (type.includes('excel') || type.includes('sheet')) return '📊';
  return '📄';
}

const LANG_LABELS = { hindi: '🇮🇳 Hindi', hinglish: '🤝 Hinglish', english: '🇬🇧 English' };

// ── Inline styles ─────────────────────────────────────────────────────────────
const styles = {
  page: { minHeight: '100vh', background: '#0D0C0A', color: '#F5F0E8', fontFamily: "'DM Sans', sans-serif", padding: '88px 24px 60px' },
  maxW: { maxWidth: 1100, margin: '0 auto' },
  title: { fontFamily: "'Syne', sans-serif", fontSize: 32, fontWeight: 800, marginBottom: 6 },
  sub: { color: '#6B6660', marginBottom: 32, fontSize: 15 },
  grid3: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 32 },
  statCard: { background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 14 },
  statIcon: { fontSize: 24 },
  statVal: { fontFamily: "'Syne', sans-serif", fontSize: 26, fontWeight: 800, color: '#FFB95A' },
  statLbl: { fontSize: 13, color: '#6B6660' },
  sectionTitle: { fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 17, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 },
  uploadZone: (active) => ({
    border: `2px dashed ${active ? '#FFB95A' : 'rgba(255,255,255,0.12)'}`,
    borderRadius: 20,
    padding: '40px 24px',
    textAlign: 'center',
    cursor: 'pointer',
    marginBottom: 32,
    background: active ? 'rgba(255,185,90,0.04)' : 'transparent',
    transition: 'all 0.2s',
  }),
  pdfGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, marginBottom: 40 },
  pdfCard: (hov) => ({
    background: hov ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.03)',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 16, padding: '20px',
    transition: 'all 0.2s',
    transform: hov ? 'translateY(-2px)' : 'none',
  }),
  btn: (variant) => ({
    padding: '9px 18px', borderRadius: 100, border: 'none',
    fontSize: 13, fontWeight: 600, cursor: 'pointer',
    background: variant === 'primary' ? '#FFB95A' : variant === 'danger' ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.06)',
    color: variant === 'primary' ? '#0D0C0A' : variant === 'danger' ? '#EF4444' : '#C8C0B4',
    border: variant === 'danger' ? '1px solid rgba(239,68,68,0.3)' : 'none',
    display: 'inline-flex', alignItems: 'center', gap: 6,
  }),
  tag: (color) => ({
    display: 'inline-block', borderRadius: 100,
    padding: '3px 10px', fontSize: 11, fontWeight: 600,
    background: `${color}18`, color: color,
    border: `1px solid ${color}30`,
  }),
  chatBox: {
    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 20, overflow: 'hidden', marginBottom: 40,
  },
  chatHeader: {
    padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    background: 'rgba(255,185,90,0.04)',
  },
  msgArea: { padding: 20, minHeight: 200, maxHeight: 400, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 },
  inputRow: { padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', gap: 8, alignItems: 'center' },
  textInput: {
    flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 100, padding: '10px 18px', color: '#F5F0E8', fontSize: 14,
    outline: 'none',
  },
};

// ── FileCard ──────────────────────────────────────────────────────────────────
function FileCard({ file, onDelete, onChat }) {
  const [hov, setHov] = useState(false);
  const statusColor = { ready: '#4CAF82', processing: '#FFB95A', failed: '#EF4444' }[file.status] || '#6B6660';
  return (
    <div style={styles.pdfCard(hov)} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
      <div style={{ fontSize: 28, marginBottom: 12 }}>{fileIcon(file.file_type)}</div>
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={file.original_name}>{file.original_name}</div>
      <div style={{ fontSize: 12, color: '#6B6660', marginBottom: 10 }}>
        {formatBytes(file.file_size)}{file.page_count ? ` · ${file.page_count}p` : ''}
      </div>
      <div style={{ ...styles.tag(statusColor), marginBottom: 14 }}>
        {file.status === 'ready' && '● '}
        {file.status === 'processing' && '◐ '}
        {file.status === 'failed' && '✕ '}
        {file.status}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        {file.status === 'ready' && (
          <button style={{ ...styles.btn('primary'), flex: 1 }} onClick={() => onChat(file.id)}>
            💬 Chat
          </button>
        )}
        <button style={styles.btn('danger')} onClick={() => onDelete(file.id)}>🗑️</button>
      </div>
    </div>
  );
}

// ── ChatBubble ────────────────────────────────────────────────────────────────
function ChatBubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', gap: 8, alignItems: 'flex-end' }}>
      {!isUser && <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'rgba(255,185,90,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>🤖</div>}
      <div style={{
        maxWidth: '75%',
        background: isUser ? 'rgba(255,185,90,0.1)' : 'rgba(255,255,255,0.05)',
        border: `1px solid ${isUser ? 'rgba(255,185,90,0.2)' : 'rgba(255,255,255,0.07)'}`,
        borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        padding: '10px 14px', fontSize: 14, lineHeight: 1.6,
        color: isUser ? '#FFD49A' : '#C8C0B4',
      }}>
        {msg.lang && <span style={{ fontSize: 10, color: '#FFB95A', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1, marginRight: 8 }}>{LANG_LABELS[msg.lang] || ''}</span>}
        {msg.input_type === 'voice' && <span style={{ fontSize: 10, color: '#A78BFA', marginRight: 6 }}>🎙️</span>}
        {msg.content}
        {msg.sources?.length > 0 && (
          <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            {msg.sources.map((s, i) => (
              <div key={i} style={{ fontSize: 11, color: '#6B6660', marginBottom: 2 }}>
                📄 Page {s.page}: {s.content?.slice(0, 80)}…
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── VoiceButton ───────────────────────────────────────────────────────────────
function VoiceButton({ onTranscript, lang = 'hi-IN' }) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);

  const toggle = () => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    setListening(true);
    recognitionRef.current = startVoiceRecognition(
      (transcript) => { onTranscript(transcript); setListening(false); },
      (err)        => { toast.error(err); setListening(false); },
      lang
    );
    if (!recognitionRef.current) setListening(false);
  };

  return (
    <button
      onClick={toggle}
      title={listening ? 'Stop listening' : 'Speak your question (Hindi/English/Hinglish)'}
      style={{
        width: 40, height: 40, borderRadius: '50%', border: 'none',
        background: listening ? 'rgba(232,121,160,0.3)' : 'rgba(255,255,255,0.07)',
        color: listening ? '#E879A0' : '#8A8478',
        cursor: 'pointer', fontSize: 17,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.2s',
        animation: listening ? 'pulse 1s infinite' : 'none',
        flexShrink: 0,
      }}
    >
      {listening ? '⏹' : '🎙️'}
    </button>
  );
}

// ── MAIN COMPONENT ────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const [files,           setFiles]          = useState([]);
  const [stats,           setStats]          = useState({});
  const [uploading,       setUploading]      = useState(false);
  const [uploadProgress,  setUploadProgress] = useState(0);

  // Free chat state
  const [freeChatOpen,    setFreeChatOpen]   = useState(false);
  const [freeMsgs,        setFreeMsgs]       = useState([]);
  const [freeChatInput,   setFreeChatInput]  = useState('');
  const [freeChatLoading, setFreeChatLoading]= useState(false);

  const chatBottomRef = useRef(null);
  const navigate      = useNavigate();

  // ── Load data ──────────────────────────────────────────────────────────────
  useEffect(() => {
    loadFiles();
    historyAPI.getStats().then(r => setStats(r.data)).catch(() => {});
    const interval = setInterval(loadFiles, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [freeMsgs]);

  const loadFiles = async () => {
    try {
      const res = await fileAPI.list();
      setFiles(res.data.files || res.data.pdfs || []);
    } catch {}
  };

  // ── Upload ─────────────────────────────────────────────────────────────────
  const onDrop = useCallback(async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    const allowed = ['application/pdf', 'image/png', 'image/jpeg', 'image/webp', 'image/bmp',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel'];

    if (!allowed.includes(file.type) && !file.name.match(/\.(pdf|png|jpg|jpeg|webp|bmp|doc|docx|xls|xlsx)$/i)) {
      toast.error('Unsupported file type. Use PDF, image, Word, or Excel.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    setUploading(true);
    setUploadProgress(0);

    const progressInterval = setInterval(() => {
      setUploadProgress(p => Math.min(p + 8, 88));
    }, 250);

    try {
      const res = await fileAPI.upload(formData);
      clearInterval(progressInterval);
      setUploadProgress(100);
      toast.success(`${file.name} uploaded! Processing started...`);
      setFiles(prev => [res.data.file || res.data.pdf, ...prev]);
    } catch (err) {
      clearInterval(progressInterval);
      toast.error(err.response?.data?.error || 'Upload failed');
    } finally {
      setTimeout(() => { setUploading(false); setUploadProgress(0); }, 500);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/*':         ['.png', '.jpg', '.jpeg', '.webp', '.bmp'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    maxFiles: 1,
    disabled: uploading,
  });

  // ── Delete ─────────────────────────────────────────────────────────────────
  const handleDelete = async (id) => {
    if (!window.confirm('Delete this file and all its chats?')) return;
    try {
      await fileAPI.delete(id);
      setFiles(prev => prev.filter(f => f.id !== id));
      toast.success('File deleted');
    } catch { toast.error('Delete failed'); }
  };

  // ── Start document chat ────────────────────────────────────────────────────
  const handleChat = async (fileId) => {
    try {
      const res = await chatAPI.createSession(fileId);
      navigate(`/chat/${res.data.session.id}`);
    } catch (err) { toast.error(err.response?.data?.error || 'Failed to start chat'); }
  };

  // ── Free chat ──────────────────────────────────────────────────────────────
  const sendFreeChat = async (text) => {
    const q = (text || freeChatInput).trim();
    if (!q) return;
    setFreeChatInput('');
    const userMsg = { role: 'user', content: q };
    setFreeMsgs(prev => [...prev, userMsg]);
    setFreeChatLoading(true);
    try {
      const res = await chatAPI.freeChat(q, freeMsgs);
      const data = res.data;
      setFreeMsgs(prev => [...prev, {
        role:    'assistant',
        content: data.answer,
        lang:    data.language,
        sources: data.sources,
      }]);
    } catch {
      setFreeMsgs(prev => [...prev, { role: 'assistant', content: "Oops, kuch gadbad ho gayi! 😅 Try again." }]);
    } finally { setFreeChatLoading(false); }
  };

  const handleVoiceTranscript = (transcript) => {
    setFreeChatInput(transcript);
    toast.success(`🎙️ "${transcript}"`);
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div style={styles.page}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&display=swap');
        @keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.12); } }
        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner { width: 20px; height: 20px; border: 2px solid rgba(255,185,90,0.2); border-top-color: #FFB95A; border-radius: 50%; animation: spin 0.8s linear infinite; }
        textarea:focus, input:focus { outline: none !important; border-color: rgba(255,185,90,0.4) !important; }
        ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
      `}</style>

      <div style={styles.maxW}>

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div style={{ marginBottom: 32, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 style={styles.title}>Dashboard</h1>
            <p style={styles.sub}>Apne documents se baat karo — Hindi, Hinglish, ya English mein 🇮🇳</p>
          </div>
          <button
            style={{ ...styles.btn('primary'), padding: '12px 24px', fontSize: 14 }}
            onClick={() => setFreeChatOpen(o => !o)}
          >
            {freeChatOpen ? '✕ Close Chat' : '💬 Free Chat'}
          </button>
        </div>

        {/* ── Stats ──────────────────────────────────────────────────────── */}
        <div style={styles.grid3}>
          {[
            { label: 'Total Files',   value: stats.total_pdfs     || files.length, icon: '📁' },
            { label: 'Chat Sessions', value: stats.total_sessions || 0,            icon: '💬' },
            { label: 'Messages Sent', value: stats.total_messages || 0,            icon: '✉️' },
          ].map(s => (
            <div key={s.label} style={styles.statCard}>
              <div style={styles.statIcon}>{s.icon}</div>
              <div>
                <div style={styles.statVal}>{s.value}</div>
                <div style={styles.statLbl}>{s.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* ── Free Chat Panel ─────────────────────────────────────────────── */}
        {freeChatOpen && (
          <div style={styles.chatBox}>
            <div style={styles.chatHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 20 }}>🤖</span>
                <div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 14 }}>Free Chat Mode</div>
                  <div style={{ fontSize: 11, color: '#6B6660' }}>Hindi · Hinglish · English · 🎙️ Voice</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button style={{ ...styles.tag('#4CAF82'), cursor: 'pointer', border: 'none' }} onClick={() => setFreeMsgs([])}>Clear</button>
              </div>
            </div>

            <div style={styles.msgArea}>
              {freeMsgs.length === 0 && (
                <div style={{ textAlign: 'center', color: '#4A4640', padding: '30px 0' }}>
                  <div style={{ fontSize: 40, marginBottom: 10 }}>👋</div>
                  <div style={{ fontWeight: 600 }}>Kuch bhi pooch sakte ho!</div>
                  <div style={{ fontSize: 13, marginTop: 6 }}>Hindi, English, ya Hinglish — type karo ya 🎙️ bolke pucho</div>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap', marginTop: 16 }}>
                    {['Kya haal hai yaar? 😄', 'What is machine learning?', 'Explain AI in simple terms'].map(s => (
                      <button key={s} style={{ ...styles.btn(''), fontSize: 12, padding: '6px 14px' }} onClick={() => { setFreeChatInput(s); }}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {freeMsgs.map((m, i) => <ChatBubble key={i} msg={m} />)}
              {freeChatLoading && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'rgba(255,185,90,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>🤖</div>
                  <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '16px 16px 16px 4px', padding: '10px 14px', fontSize: 13, color: '#6B6660' }}>
                    Soch raha hun... 🤔
                  </div>
                </div>
              )}
              <div ref={chatBottomRef} />
            </div>

            <div style={styles.inputRow}>
              <VoiceButton onTranscript={handleVoiceTranscript} />
              <input
                style={styles.textInput}
                placeholder="Hindi mein ya English mein kuch bhi pooch... (or speak 🎙️)"
                value={freeChatInput}
                onChange={e => setFreeChatInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendFreeChat()}
              />
              <button
                style={{ ...styles.btn('primary'), padding: '10px 20px' }}
                onClick={() => sendFreeChat()}
                disabled={!freeChatInput.trim() || freeChatLoading}
              >
                {freeChatLoading ? <div className="spinner" /> : '→'}
              </button>
            </div>
          </div>
        )}

        {/* ── Upload Zone ─────────────────────────────────────────────────── */}
        <div style={styles.sectionTitle}>
          <span>📤</span> Upload a File
        </div>

        <div {...getRootProps()} style={styles.uploadZone(isDragActive || uploading)}>
          <input {...getInputProps()} />
          <div style={{ fontSize: 36, marginBottom: 12 }}>
            {uploading ? <div className="spinner" style={{ margin: '0 auto' }} /> : isDragActive ? '🎯' : '📎'}
          </div>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 17, marginBottom: 6 }}>
            {uploading ? 'Uploading...' : isDragActive ? 'Drop it!' : 'Upload a File'}
          </div>
          <div style={{ color: '#6B6660', fontSize: 14 }}>
            {uploading ? 'Please wait...' : 'PDF · PNG/JPG · Word (.docx) · Excel (.xlsx) · Max 50MB'}
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap', marginTop: 14 }}>
            {['📕 PDF', '🖼️ Image', '📝 Word', '📊 Excel'].map(t => (
              <span key={t} style={{ ...styles.tag('#7C9EFF'), fontSize: 12 }}>{t}</span>
            ))}
          </div>
          {uploading && (
            <div style={{ marginTop: 16, background: 'rgba(255,255,255,0.06)', borderRadius: 100, height: 6, maxWidth: 300, margin: '16px auto 0' }}>
              <div style={{ height: '100%', background: '#FFB95A', borderRadius: 100, width: `${uploadProgress}%`, transition: 'width 0.3s ease' }} />
            </div>
          )}
        </div>

        {/* ── File Grid ───────────────────────────────────────────────────── */}
        <div style={styles.sectionTitle}>
          <span>📁</span> Your Files ({files.length})
        </div>

        {files.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#4A4640', background: 'rgba(255,255,255,0.02)', borderRadius: 16, border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📭</div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Koi file nahi hai abhi</div>
            <div style={{ fontSize: 14 }}>Upload karo koi bhi document aur AI se baatein karo!</div>
          </div>
        ) : (
          <div style={styles.pdfGrid}>
            {files.map(f => (
              <FileCard key={f.id} file={f} onDelete={handleDelete} onChat={handleChat} />
            ))}
          </div>
        )}

      </div>
    </div>
  );
}