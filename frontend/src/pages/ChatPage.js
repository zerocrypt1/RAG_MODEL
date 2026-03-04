import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import toast from 'react-hot-toast';
import { chatAPI } from '../utils/api';

function TypingDots() {
  return (
    <div className="message assistant">
      <div className="message-avatar">AI</div>
      <div className="message-bubble">
        <div className="typing-dots">
          <span/><span/><span/>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }) {
  return (
    <div className={`message ${message.role}`}>
      <div className="message-avatar">
        {message.role === 'user' ? 'U' : 'AI'}
      </div>
      <div className="message-bubble">
        {message.role === 'assistant' ? (
          <ReactMarkdown>{message.content}</ReactMarkdown>
        ) : message.content}

        {message.sources && message.sources.length > 0 && (
          <div className="message-sources">
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontFamily: 'Space Mono' }}>
              SOURCES
            </div>
            {message.sources.map((s, i) => (
              <span key={i} className="source-tag" title={s.content}>
                📄 Page {s.page}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [session, setSession] = useState(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    loadSession();
  }, [sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const loadSession = async () => {
    try {
      const res = await chatAPI.getMessages(sessionId);
      setSession(res.data.session);
      setMessages(res.data.messages);
    } catch (err) {
      toast.error('Session not found');
      navigate('/dashboard');
    } finally {
      setInitializing(false);
    }
  };

  const handleSend = async () => {
    const question = input.trim();
    if (!question || loading) return;

    setInput('');
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', content: question }]);
    setLoading(true);

    try {
      const res = await chatAPI.sendMessage(sessionId, question);
      setMessages(prev => [...prev, {
        id: res.data.message_id,
        role: 'assistant',
        content: res.data.answer,
        sources: res.data.sources
      }]);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to get answer');
      setMessages(prev => prev.filter(m => m.id !== Date.now()));
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (initializing) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div style={{ height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      <div className="chat-main" style={{ flex: 1 }}>
        <div className="chat-header">
          <button className="btn btn-secondary" style={{ padding: '8px 12px', fontSize: 13 }}
            onClick={() => navigate('/dashboard')}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
            Back
          </button>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <div style={{ fontWeight: 700, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {session?.title || 'Chat'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'Space Mono' }}>
              {messages.length} messages
            </div>
          </div>
        </div>

        <div className="chat-messages">
          {messages.length === 0 && !loading && (
            <div className="empty-state" style={{ padding: '32px' }}>
              <div className="empty-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
              </div>
              <div className="empty-title">Start the conversation</div>
              <div className="empty-text">Ask anything about your document. The AI will find answers using RAG.</div>
            </div>
          )}

          {messages.map(msg => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {loading && <TypingDots />}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder="Ask a question about the document... (Enter to send, Shift+Enter for newline)"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={loading}
          />
          <button className="chat-send-btn" onClick={handleSend} disabled={!input.trim() || loading}>
            {loading ? (
              <div className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}