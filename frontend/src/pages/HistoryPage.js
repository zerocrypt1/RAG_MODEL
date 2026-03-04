import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { historyAPI, chatAPI } from '../utils/api';
import toast from 'react-hot-toast';

export default function HistoryPage() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    if (!searchQuery) { setSearchResults(null); return; }
    const t = setTimeout(async () => {
      try {
        const res = await historyAPI.search(searchQuery);
        setSearchResults(res.data.results);
      } catch {}
    }, 400);
    return () => clearTimeout(t);
  }, [searchQuery]);

  const loadHistory = async () => {
    try {
      const res = await historyAPI.getHistory();
      setHistory(res.data.history);
    } catch {
      toast.error('Failed to load history');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (e, id) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await chatAPI.deleteSession(id);
      setHistory(prev => prev.filter(h => h.id !== id));
      toast.success('Deleted');
    } catch {
      toast.error('Delete failed');
    }
  };

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
      <div className="spinner" />
    </div>
  );

  const displayList = searchResults !== null ? [] : history;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">History</h1>
        <p className="page-subtitle">// All your past PDF conversations</p>
      </div>

      <div style={{ marginBottom: 24 }}>
        <div style={{ position: 'relative' }}>
          <svg style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
            width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            className="form-input"
            style={{ paddingLeft: 42 }}
            placeholder="Search messages..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {searchResults !== null ? (
        <div>
          <div className="section-title">Search Results ({searchResults.length})</div>
          {searchResults.length === 0 ? (
            <div className="empty-state">
              <div className="empty-title">No results</div>
              <div className="empty-text">No messages match "{searchQuery}"</div>
            </div>
          ) : (
            <div className="history-list">
              {searchResults.map(msg => (
                <div key={msg.id} className="history-item"
                  onClick={() => navigate(`/chat/${msg.session_id}`)}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: 6,
                      background: msg.role === 'user' ? 'rgba(99,102,241,0.15)' : 'rgba(34,197,94,0.15)',
                      color: msg.role === 'user' ? 'var(--accent-light)' : 'var(--success)',
                      fontSize: 11, fontFamily: 'Space Mono'
                    }}>
                      {msg.role}
                    </span>
                  </div>
                  <div className="history-title">{msg.content}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : history.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <div className="empty-title">No history yet</div>
          <div className="empty-text">Your chat sessions will appear here after you start talking to your PDFs</div>
        </div>
      ) : (
        <div className="history-list">
          {history.map(item => (
            <div key={item.id} className="history-item" onClick={() => navigate(`/chat/${item.id}`)}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div className="history-title">{item.title}</div>
                  <div className="history-meta" style={{ marginTop: 4 }}>
                    📄 {item.pdf_name} · {item.message_count} messages · {formatDistanceToNow(new Date(item.updated_at), { addSuffix: true })}
                  </div>
                  {item.last_message && (
                    <div style={{
                      marginTop: 8, fontSize: 13, color: 'var(--text-secondary)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                    }}>
                      {item.last_message_role === 'assistant' ? '🤖 ' : '👤 '}{item.last_message}
                    </div>
                  )}
                </div>
                <button className="btn btn-danger" style={{ fontSize: 12, padding: '6px 10px', flexShrink: 0 }}
                  onClick={(e) => handleDelete(e, item.id)}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}