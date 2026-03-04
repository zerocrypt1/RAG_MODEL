import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import toast from 'react-hot-toast';
import { chatAPI, startVoiceRecognition, speakText, langToBCP47 } from '../utils/api';

// ─────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────

const LANG_META = {
  hindi:    { label: '🇮🇳 Hindi',    color: '#4CAF82' },
  hinglish: { label: '🤝 Hinglish',  color: '#FFB95A' },
  english:  { label: '🇬🇧 English',  color: '#7C9EFF' },
};

const MODE_META = {
  document: { icon: '📄', label: 'Document',  color: '#7C9EFF' },
  web:      { icon: '🌐', label: 'Web Search', color: '#4CAF82' },
  chat:     { icon: '💬', label: 'Free Chat',  color: '#E879A0' },
};

// ─────────────────────────────────────────────
// TYPING INDICATOR
// ─────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', padding: '4px 0' }}>
      <Avatar role="assistant" />
      <div style={{
        background: 'rgba(255,255,255,0.05)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '18px 18px 18px 4px',
        padding: '14px 18px',
        display: 'flex', alignItems: 'center', gap: 5,
      }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            width: 7, height: 7, borderRadius: '50%',
            background: '#FFB95A',
            animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// AVATAR
// ─────────────────────────────────────────────

function Avatar({ role }) {
  const isAI = role === 'assistant';
  return (
    <div style={{
      width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
      background: isAI ? 'rgba(255,185,90,0.15)' : 'rgba(124,158,255,0.15)',
      border: `1px solid ${isAI ? 'rgba(255,185,90,0.3)' : 'rgba(124,158,255,0.3)'}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 14,
    }}>
      {isAI ? '🤖' : '👤'}
    </div>
  );
}

// ─────────────────────────────────────────────
// MESSAGE BUBBLE
// ─────────────────────────────────────────────

function MessageBubble({ message, onSpeak }) {
  const isUser = message.role === 'user';
  const lang   = message.language;
  const mode   = message.mode;
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: isUser ? 'row-reverse' : 'row',
      gap: 10, alignItems: 'flex-end',
      padding: '2px 0',
    }}>
      <Avatar role={message.role} />

      <div style={{ maxWidth: '72%', display: 'flex', flexDirection: 'column', gap: 4, alignItems: isUser ? 'flex-end' : 'flex-start' }}>

        {/* Meta row */}
        {(lang || mode || message.input_type === 'voice') && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', paddingLeft: isUser ? 0 : 2, paddingRight: isUser ? 2 : 0 }}>
            {message.input_type === 'voice' && (
              <span style={{ fontSize: 10, color: '#A78BFA', fontWeight: 600 }}>🎙️ VOICE</span>
            )}
            {lang && LANG_META[lang] && (
              <span style={{ fontSize: 10, color: LANG_META[lang].color, fontWeight: 600, letterSpacing: 0.5 }}>
                {LANG_META[lang].label}
              </span>
            )}
            {mode && MODE_META[mode] && (
              <span style={{
                fontSize: 10, fontWeight: 600,
                color: MODE_META[mode].color,
                background: `${MODE_META[mode].color}15`,
                border: `1px solid ${MODE_META[mode].color}30`,
                borderRadius: 100, padding: '1px 7px',
              }}>
                {MODE_META[mode].icon} {MODE_META[mode].label}
              </span>
            )}
          </div>
        )}

        {/* Bubble */}
        <div style={{
          background: isUser ? 'rgba(255,185,90,0.1)' : 'rgba(255,255,255,0.04)',
          border: `1px solid ${isUser ? 'rgba(255,185,90,0.22)' : 'rgba(255,255,255,0.08)'}`,
          borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
          padding: '12px 16px',
          color: isUser ? '#FFD49A' : '#D4CEC6',
          fontSize: 14.5, lineHeight: 1.7,
          wordBreak: 'break-word',
        }}>
          {message.role === 'assistant' ? (
            <div className="markdown-body">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          ) : message.content}
        </div>

        {/* Sources */}
        {message.sources?.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', paddingLeft: 2 }}>
            {message.sources.map((s, i) => (
              <span key={i} title={s.content} style={{
                fontSize: 11, borderRadius: 8,
                background: 'rgba(124,158,255,0.08)',
                border: '1px solid rgba(124,158,255,0.2)',
                color: '#7C9EFF', padding: '3px 10px',
                cursor: 'default',
              }}>
                {s.page === 'web' ? '🌐 Web' : `📄 pg ${s.page}`}
              </span>
            ))}
          </div>
        )}

        {/* Action row */}
        {!isUser && (
          <div style={{ display: 'flex', gap: 8, paddingLeft: 2 }}>
            <button onClick={copy} style={{ fontSize: 11, color: '#5A5650', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              {copied ? '✓ Copied' : '⎘ Copy'}
            </button>
            {onSpeak && (
              <button onClick={() => onSpeak(message.content, lang)} style={{ fontSize: 11, color: '#5A5650', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                🔊 Speak
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// SUGGESTION CHIPS
// ─────────────────────────────────────────────

function SuggestionChips({ onSelect, mode }) {
  const suggestions = {
    document: [
      'Summarize this document',
      'What are the key points?',
      'Is sabka summary bata do',
      'Koi important clause hai?',
    ],
    web: [
      'Latest AI news today',
      'Aaj ka weather kya hai?',
      'What is machine learning?',
    ],
    chat: [
      'Kya haal hai yaar? 😄',
      'Tell me a fun fact',
      'Ek joke sunao!',
      'Help me think through something',
    ],
  };

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center', marginTop: 16 }}>
      {(suggestions[mode] || suggestions.document).map(s => (
        <button
          key={s}
          onClick={() => onSelect(s)}
          style={{
            background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 100, padding: '7px 16px', fontSize: 13, color: '#8A8478',
            cursor: 'pointer', transition: 'all 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(255,185,90,0.4)'; e.currentTarget.style.color = '#FFB95A'; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = '#8A8478'; }}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────

export default function ChatPage() {
  const { sessionId }                     = useParams();
  const navigate                          = useNavigate();
  const [messages,     setMessages]       = useState([]);
  const [session,      setSession]        = useState(null);
  const [input,        setInput]          = useState('');
  const [loading,      setLoading]        = useState(false);
  const [initializing, setInitializing]   = useState(true);
  const [mode,         setMode]           = useState('document'); // document | web | chat
  const [listening,    setListening]      = useState(false);
  const [isFreeChat,   setIsFreeChat]     = useState(false);   // true when no sessionId

  const messagesEndRef  = useRef(null);
  const textareaRef     = useRef(null);
  const recognitionRef  = useRef(null);

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (sessionId) {
      loadSession();
    } else {
      // Free chat mode — no document needed
      setIsFreeChat(true);
      setMode('chat');
      setInitializing(false);
    }
  }, [sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
  }, [input]);

  const loadSession = async () => {
    try {
      const res = await chatAPI.getMessages(sessionId);
      setSession(res.data.session);
      setMessages(res.data.messages || []);
    } catch {
      toast.error('Session not found');
      navigate('/dashboard');
    } finally {
      setInitializing(false);
    }
  };

  // ── Send message ──────────────────────────────────────────────────────────
  const handleSend = async (overrideText, isVoice = false) => {
    const question = (overrideText ?? input).trim();
    if (!question || loading) return;

    setInput('');
    const tempId = Date.now();

    setMessages(prev => [...prev, {
      id:         tempId,
      role:       'user',
      content:    question,
      input_type: isVoice ? 'voice' : 'text',
    }]);
    setLoading(true);

    try {
      let res;

      if (isFreeChat || mode === 'chat') {
        const history = messages.map(m => ({ role: m.role, content: m.content }));
        res = await chatAPI.freeChat(question, history);
      } else {
        res = await chatAPI.sendMessage(sessionId, question, mode);
      }

      const d = res.data;
      setMessages(prev => [...prev, {
        id:       d.message_id || Date.now() + 1,
        role:     'assistant',
        content:  d.answer,
        sources:  d.sources  || [],
        language: d.language || 'english',
        mode:     d.mode     || mode,
      }]);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to get answer');
      setMessages(prev => prev.filter(m => m.id !== tempId));
    } finally {
      setLoading(false);
    }
  };

  // ── Voice input ───────────────────────────────────────────────────────────
  const toggleVoice = useCallback(() => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    setListening(true);
    recognitionRef.current = startVoiceRecognition(
      (transcript) => {
        setListening(false);
        toast.success(`🎙️ "${transcript.slice(0, 50)}${transcript.length > 50 ? '…' : ''}"`);
        handleSend(transcript, true);
      },
      (err) => { toast.error(err); setListening(false); },
      'hi-IN'   // Hindi + English mixed works well with hi-IN
    );

    if (!recognitionRef.current) setListening(false);
  }, [listening, messages, mode, isFreeChat]);

  // ── TTS ───────────────────────────────────────────────────────────────────
  const handleSpeak = (text, lang) => {
    speakText(text, langToBCP47(lang));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ─────────────────────────────────────────────
  if (initializing) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0D0C0A' }}>
        <div style={{ textAlign: 'center', color: '#4A4640' }}>
          <div style={{ fontSize: 36, marginBottom: 16 }}>🤖</div>
          <div style={{ width: 24, height: 24, border: '2px solid rgba(255,185,90,0.2)', borderTopColor: '#FFB95A', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto' }} />
        </div>
      </div>
    );
  }

  const isEmpty = messages.length === 0;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; }

        @keyframes bounce {
          0%,60%,100% { transform: translateY(0); }
          30% { transform: translateY(-6px); }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse-ring {
          0%   { box-shadow: 0 0 0 0 rgba(232,121,160,0.4); }
          70%  { box-shadow: 0 0 0 10px rgba(232,121,160,0); }
          100% { box-shadow: 0 0 0 0 rgba(232,121,160,0); }
        }

        .chat-wrap {
          height: calc(100vh - 64px);
          display: flex;
          flex-direction: column;
          background: #0D0C0A;
          font-family: 'DM Sans', sans-serif;
          color: #F5F0E8;
        }

        /* Scrollbar */
        .msg-scroll::-webkit-scrollbar { width: 5px; }
        .msg-scroll::-webkit-scrollbar-track { background: transparent; }
        .msg-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }

        /* Markdown */
        .markdown-body p  { margin: 0 0 10px; }
        .markdown-body p:last-child { margin-bottom: 0; }
        .markdown-body ul, .markdown-body ol { padding-left: 20px; margin: 8px 0; }
        .markdown-body li { margin-bottom: 4px; }
        .markdown-body code {
          font-family: 'JetBrains Mono', monospace;
          font-size: 12.5px;
          background: rgba(255,255,255,0.08);
          padding: 2px 6px; border-radius: 4px;
          color: #FFB95A;
        }
        .markdown-body pre {
          background: rgba(0,0,0,0.4);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 10px; padding: 14px;
          overflow-x: auto; margin: 10px 0;
        }
        .markdown-body pre code {
          background: none; padding: 0; color: #C8C0B4;
        }
        .markdown-body strong { color: #F5F0E8; font-weight: 600; }
        .markdown-body h1,.markdown-body h2,.markdown-body h3 {
          font-family: 'Syne', sans-serif;
          color: #F5F0E8; margin: 12px 0 6px;
        }
        .markdown-body blockquote {
          border-left: 3px solid #FFB95A;
          padding-left: 14px; margin: 8px 0;
          color: #8A8478;
        }

        .mode-btn { transition: all 0.15s; }
        .mode-btn:hover { opacity: 0.85; transform: translateY(-1px); }

        .send-btn:disabled { opacity: 0.35; cursor: not-allowed; }
        .send-btn:not(:disabled):hover { background: #ffc96e !important; transform: scale(1.05); }

        .msg-item { animation: fadeIn 0.25s ease both; }
      `}</style>

      <div className="chat-wrap">

        {/* ── HEADER ─────────────────────────────────────────────────────── */}
        <div style={{
          padding: '0 20px',
          height: 60,
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', alignItems: 'center', gap: 12,
          background: 'rgba(255,255,255,0.02)',
          flexShrink: 0,
        }}>
          {/* Back */}
          <button
            onClick={() => navigate('/dashboard')}
            style={{
              width: 36, height: 36, borderRadius: '50%',
              background: 'rgba(255,255,255,0.06)', border: 'none',
              color: '#8A8478', cursor: 'pointer', flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16, transition: 'all 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.06)'}
            title="Back to Dashboard"
          >
            ←
          </button>

          {/* Title */}
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {isFreeChat ? '💬 Free Chat' : (session?.title || 'Document Chat')}
            </div>
            <div style={{ fontSize: 11, color: '#4A4640', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>{messages.length} message{messages.length !== 1 ? 's' : ''}</span>
              <span>·</span>
              <span>Hindi · Hinglish · English 🎙️</span>
            </div>
          </div>

          {/* Mode switcher */}
          <div style={{
            display: 'flex', gap: 4, background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 100, padding: 4,
          }}>
            {Object.entries(MODE_META).map(([key, meta]) => {
              if (key === 'chat' && !isFreeChat) return null; // only show chat mode in free chat
              const active = mode === key;
              return (
                <button
                  key={key}
                  className="mode-btn"
                  onClick={() => setMode(key)}
                  title={meta.label}
                  style={{
                    padding: '5px 12px', borderRadius: 100, border: 'none', cursor: 'pointer',
                    fontSize: 12, fontWeight: 600,
                    background: active ? `${meta.color}22` : 'transparent',
                    color:      active ? meta.color : '#5A5650',
                    border:     active ? `1px solid ${meta.color}40` : '1px solid transparent',
                  }}
                >
                  {meta.icon} {meta.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── MESSAGES ───────────────────────────────────────────────────── */}
        <div className="msg-scroll" style={{ flex: 1, overflowY: 'auto', padding: '24px 20px' }}>
          <div style={{ maxWidth: 760, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* Empty state */}
            {isEmpty && !loading && (
              <div style={{ textAlign: 'center', padding: '48px 20px' }}>
                <div style={{ fontSize: 52, marginBottom: 14 }}>
                  {MODE_META[mode].icon}
                </div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 20, fontWeight: 800, marginBottom: 8 }}>
                  {isFreeChat ? 'Yaar, kuch bhi pooch!' : 'Ask anything about your document'}
                </div>
                <div style={{ color: '#5A5650', fontSize: 14, lineHeight: 1.7, maxWidth: 400, margin: '0 auto' }}>
                  {isFreeChat
                    ? 'Type, speak, or pick a suggestion below. I understand Hindi, Hinglish, and English. 🇮🇳'
                    : 'Type or speak your question — in Hindi, Hinglish, or English. I\'ll find the answer in the document.'}
                </div>
                <SuggestionChips mode={mode} onSelect={(s) => { setInput(s); textareaRef.current?.focus(); }} />
              </div>
            )}

            {/* Message list */}
            {messages.map(msg => (
              <div key={msg.id} className="msg-item">
                <MessageBubble message={msg} onSpeak={handleSpeak} />
              </div>
            ))}

            {loading && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* ── INPUT AREA ──────────────────────────────────────────────────── */}
        <div style={{
          borderTop: '1px solid rgba(255,255,255,0.06)',
          padding: '14px 20px 18px',
          background: 'rgba(255,255,255,0.02)',
          flexShrink: 0,
        }}>
          <div style={{ maxWidth: 760, margin: '0 auto' }}>

            {/* Listening banner */}
            {listening && (
              <div style={{
                marginBottom: 10,
                background: 'rgba(232,121,160,0.08)',
                border: '1px solid rgba(232,121,160,0.3)',
                borderRadius: 12, padding: '8px 16px',
                display: 'flex', alignItems: 'center', gap: 10,
                fontSize: 13, color: '#E879A0',
              }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#E879A0', animation: 'pulse-ring 1s infinite' }} />
                Listening... Hindi, English, ya Hinglish mein bolo 🎙️
                <button onClick={toggleVoice} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#E879A0', cursor: 'pointer', fontSize: 12 }}>
                  Stop ✕
                </button>
              </div>
            )}

            {/* Input row */}
            <div style={{
              display: 'flex', gap: 10, alignItems: 'flex-end',
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 18, padding: '8px 8px 8px 16px',
              transition: 'border-color 0.2s',
            }}
              onFocus={e => e.currentTarget.style.borderColor = 'rgba(255,185,90,0.35)'}
              onBlur={e => e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'}
            >
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                rows={1}
                placeholder={
                  mode === 'web'
                    ? '🌐 Kuch bhi search karo — Hindi ya English mein...'
                    : mode === 'chat'
                    ? '💬 Kuch bhi pooch yaar — type karo ya bolke pooch 🎙️'
                    : '📄 Document ke baare mein kuch bhi pooch...'
                }
                style={{
                  flex: 1, background: 'none', border: 'none', outline: 'none',
                  color: '#F5F0E8', fontSize: 14.5, lineHeight: 1.5,
                  resize: 'none', fontFamily: "'DM Sans', sans-serif",
                  maxHeight: 140, overflowY: 'auto',
                }}
              />

              {/* Voice button */}
              <button
                onClick={toggleVoice}
                title="Speak your question (Hindi/Hinglish/English)"
                style={{
                  width: 38, height: 38, borderRadius: '50%', border: 'none', flexShrink: 0,
                  background: listening ? 'rgba(232,121,160,0.25)' : 'rgba(255,255,255,0.06)',
                  color: listening ? '#E879A0' : '#6B6660',
                  cursor: 'pointer', fontSize: 16,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.2s',
                  animation: listening ? 'pulse-ring 1s infinite' : 'none',
                }}
              >
                🎙️
              </button>

              {/* Send button */}
              <button
                className="send-btn"
                onClick={() => handleSend()}
                disabled={!input.trim() || loading}
                style={{
                  width: 38, height: 38, borderRadius: '50%', border: 'none', flexShrink: 0,
                  background: '#FFB95A', color: '#0D0C0A',
                  cursor: 'pointer', fontSize: 16,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.15s',
                }}
              >
                {loading
                  ? <div style={{ width: 16, height: 16, border: '2px solid rgba(13,12,10,0.3)', borderTopColor: '#0D0C0A', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                  : '↑'}
              </button>
            </div>

            {/* Footer hint */}
            <div style={{ fontSize: 11, color: '#3A3632', marginTop: 8, textAlign: 'center' }}>
              Enter to send · Shift+Enter for newline · 🎙️ click mic to speak · Replies in your language
            </div>
          </div>
        </div>
      </div>
    </>
  );
}