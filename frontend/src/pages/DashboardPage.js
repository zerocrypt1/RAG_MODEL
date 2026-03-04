import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import toast from 'react-hot-toast';
import { pdfAPI, chatAPI, historyAPI } from '../utils/api';

function formatBytes(bytes) {
  if (!bytes) return '—';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function PDFCard({ pdf, onDelete, onChat }) {
  return (
    <div className="pdf-card">
      <div className="pdf-card-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
      </div>
      <div className="pdf-card-name" title={pdf.original_name}>{pdf.original_name}</div>
      <div className="pdf-card-meta">
        {formatBytes(pdf.file_size)}
        {pdf.page_count ? ` · ${pdf.page_count} pages` : ''}
      </div>
      <div>
        <span className={`pdf-status ${pdf.status}`}>
          {pdf.status === 'ready' && '● '}
          {pdf.status === 'processing' && '◐ '}
          {pdf.status === 'failed' && '✕ '}
          {pdf.status}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        {pdf.status === 'ready' && (
          <button className="btn btn-primary" style={{ flex: 1, fontSize: 13, padding: '8px 12px' }}
            onClick={() => onChat(pdf.id)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
            </svg>
            Chat
          </button>
        )}
        <button className="btn btn-danger" style={{ fontSize: 13, padding: '8px 12px' }}
          onClick={() => onDelete(pdf.id)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [pdfs, setPdfs] = useState([]);
  const [stats, setStats] = useState({});
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    loadPDFs();
    historyAPI.getStats().then(r => setStats(r.data)).catch(() => {});
    // Poll for processing status
    const interval = setInterval(loadPDFs, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadPDFs = async () => {
    try {
      const res = await pdfAPI.list();
      setPdfs(res.data.pdfs);
    } catch {}
  };

  const onDrop = useCallback(async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;
    if (file.type !== 'application/pdf') {
      return toast.error('Only PDF files allowed');
    }

    const formData = new FormData();
    formData.append('file', file);

    setUploading(true);
    setUploadProgress(0);

    const progressInterval = setInterval(() => {
      setUploadProgress(p => Math.min(p + 10, 90));
    }, 300);

    try {
      const res = await pdfAPI.upload(formData);
      clearInterval(progressInterval);
      setUploadProgress(100);
      toast.success('PDF uploaded! Processing started...');
      setPdfs(prev => [res.data.pdf, ...prev]);
    } catch (err) {
      clearInterval(progressInterval);
      toast.error(err.response?.data?.error || 'Upload failed');
    } finally {
      setTimeout(() => {
        setUploading(false);
        setUploadProgress(0);
      }, 500);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1, disabled: uploading
  });

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this PDF and all its chats?')) return;
    try {
      await pdfAPI.delete(id);
      setPdfs(prev => prev.filter(p => p.id !== id));
      toast.success('PDF deleted');
    } catch {
      toast.error('Delete failed');
    }
  };

  const handleChat = async (pdfId) => {
    try {
      const res = await chatAPI.createSession(pdfId);
      navigate(`/chat/${res.data.session.id}`);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to start chat');
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">// Upload PDFs and start querying with AI</p>
      </div>

      <div className="stats-grid">
        {[
          { label: 'Total PDFs', value: stats.total_pdfs || 0, icon: '📄' },
          { label: 'Chat Sessions', value: stats.total_sessions || 0, icon: '💬' },
          { label: 'Messages Sent', value: stats.total_messages || 0, icon: '✉️' },
        ].map(stat => (
          <div className="stat-card" key={stat.label}>
            <div className="stat-icon">{stat.icon}</div>
            <div className="stat-value">{stat.value}</div>
            <div className="stat-label">{stat.label}</div>
          </div>
        ))}
      </div>

      <div {...getRootProps()} className={`upload-zone ${isDragActive ? 'dragging' : ''}`}>
        <input {...getInputProps()} />
        <div className="upload-icon">
          {uploading ? (
            <div className="spinner" />
          ) : (
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
            </svg>
          )}
        </div>
        <div className="upload-title">
          {uploading ? 'Uploading...' : isDragActive ? 'Drop PDF here' : 'Upload a PDF'}
        </div>
        <div className="upload-subtitle">
          {uploading ? 'Please wait' : 'Drag & drop or click to select · Max 50MB'}
        </div>
        {uploading && (
          <div className="upload-progress" style={{ marginTop: 16 }}>
            <div className="upload-progress-bar" style={{ width: `${uploadProgress}%` }} />
          </div>
        )}
      </div>

      <div className="section-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        Your PDFs ({pdfs.length})
      </div>

      {pdfs.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div className="empty-title">No PDFs yet</div>
          <div className="empty-text">Upload your first PDF to start asking questions with AI</div>
        </div>
      ) : (
        <div className="pdf-grid">
          {pdfs.map(pdf => (
            <PDFCard key={pdf.id} pdf={pdf} onDelete={handleDelete} onChat={handleChat} />
          ))}
        </div>
      )}
    </div>
  );
}