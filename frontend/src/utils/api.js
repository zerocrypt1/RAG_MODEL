import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// ── Auth token injection ──────────────────────────────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Global 401 handler ────────────────────────────────────────────────────────
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ─────────────────────────────────────────────
// AUTH
// ─────────────────────────────────────────────
export const authAPI = {
  register:       (data)             => api.post('/auth/register', data),
  login:          (data)             => api.post('/auth/login', data),
  googleAuth:     (credential)       => api.post('/auth/google', { credential }),
  verifyEmail:    (token)            => api.post('/auth/verify-email', { token }),
  forgotPassword: (email)            => api.post('/auth/forgot-password', { email }),
  resetPassword:  (token, password)  => api.post('/auth/reset-password', { token, password }),
  getMe:          ()                 => api.get('/auth/me'),
  logout:         ()                 => api.post('/auth/logout'),
};

// ─────────────────────────────────────────────
// FILE UPLOAD  (PDF / Image / Word / Excel)
// ─────────────────────────────────────────────
export const fileAPI = {
  /**
   * Upload any supported file.
   * @param {FormData} formData  — must contain field 'file'
   */
  upload: (formData) =>
    api.post('/file/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  getStatus:      (id) => api.get(`/file/status/${id}`),
  list:           ()   => api.get('/file/list'),
  delete:         (id) => api.delete(`/file/${id}`),
  getDownloadUrl: (id) => api.get(`/file/${id}/download-url`),
};

// ── Backward-compat alias ─────────────────────────────────────────────────────
export const pdfAPI = {
  upload:         fileAPI.upload,
  getStatus:      fileAPI.getStatus,
  list:           fileAPI.list,
  delete:         fileAPI.delete,
  getDownloadUrl: fileAPI.getDownloadUrl,
};

// ─────────────────────────────────────────────
// CHAT  (document Q&A + free chat + web search)
// ─────────────────────────────────────────────
export const chatAPI = {
  /**
   * Create a new chat session tied to a document.
   */
  createSession: (fileId) =>
    api.post('/chat/session', { file_id: fileId }),

  /**
   * Send a message in a document session.
   * mode: "document" | "web"
   */
  sendMessage: (sessionId, question, mode = 'document') =>
    api.post('/chat/message', { session_id: sessionId, question, mode }),

  /**
   * Send a free-chat message (no document required).
   * Supports Hindi / Hinglish / English automatically.
   */
  freeChat: (question, history = []) =>
    api.post('/chat/free', { question, history }),

  /**
   * Send a voice transcript as a message (same as sendMessage but labeled).
   */
  voiceMessage: (sessionId, transcript, mode = 'document') =>
    api.post('/chat/message', {
      session_id: sessionId,
      question:   transcript,
      mode,
      input_type: 'voice',
    }),

  /**
   * Free-chat voice message (no document).
   */
  voiceFreeChat: (transcript, history = []) =>
    api.post('/chat/free', {
      question:   transcript,
      history,
      input_type: 'voice',
    }),

  getMessages:   (sessionId) => api.get(`/chat/session/${sessionId}/messages`),
  getSessions:   ()           => api.get('/chat/sessions'),
  deleteSession: (id)         => api.delete(`/chat/session/${id}`),
};

// ─────────────────────────────────────────────
// WEB SEARCH  (standalone)
// ─────────────────────────────────────────────
export const searchAPI = {
  /**
   * Search the web and get an AI-summarized answer.
   */
  webSearch: (query) => api.post('/search/web', { query }),
};

// ─────────────────────────────────────────────
// VOICE  (Speech → Text via browser + helpers)
// ─────────────────────────────────────────────

/**
 * Start browser-native Speech Recognition.
 *
 * @param {Function} onResult   Called with the transcript string
 * @param {Function} onError    Called with error message
 * @param {string}   lang       BCP-47 language code, e.g. 'hi-IN', 'en-US', 'hi-IN'
 * @returns {SpeechRecognition}  Call .stop() to end recording
 */
export function startVoiceRecognition(
  onResult,
  onError,
  lang = 'hi-IN'   // defaults to Hindi for Hinglish friendliness
) {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    onError('Speech recognition is not supported in this browser. Try Chrome.');
    return null;
  }

  const recognition        = new SpeechRecognition();
  recognition.lang         = lang;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    onResult(transcript);
  };

  recognition.onerror = (event) => {
    onError(`Voice error: ${event.error}`);
  };

  recognition.start();
  return recognition;
}

/**
 * Speak text aloud using the browser's Text-to-Speech.
 *
 * @param {string} text
 * @param {string} lang  BCP-47 code, e.g. 'hi-IN', 'en-US'
 */
export function speakText(text, lang = 'en-US') {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance  = new SpeechSynthesisUtterance(text);
  utterance.lang   = lang;
  utterance.rate   = 1.0;
  utterance.pitch  = 1.0;
  window.speechSynthesis.speak(utterance);
}

/**
 * Detect BCP-47 language code from a detected language name.
 */
export function langToBCP47(lang) {
  if (lang === 'hindi')    return 'hi-IN';
  if (lang === 'hinglish') return 'hi-IN';
  return 'en-US';
}

// ─────────────────────────────────────────────
// HISTORY
// ─────────────────────────────────────────────
export const historyAPI = {
  getHistory: (page = 1) => api.get(`/history/?page=${page}`),
  search:     (q)         => api.get(`/history/search?q=${q}`),
  getStats:   ()          => api.get('/history/stats'),
};

// ─────────────────────────────────────────────
// MEMORY RAG  (search across ALL docs + chats)
// ─────────────────────────────────────────────
export const memoryAPI = {
  /** Ask a question searched across every file + every past chat. */
  query:        (question, lang)                      => api.post('/memory/query', { question, lang }),
  /** { documents: [...], chats: [...] } */
  getSources:   ()                                    => api.get('/memory/sources'),
  /** Persist a chat session into the memory index. */
  indexSession: (sessionId, title, messages)          => api.post('/memory/index-session', { session_id: sessionId, title, messages }),
  /** Force a full rebuild of the merged memory index. */
  rebuildIndex: ()                                    => api.post('/memory/rebuild'),
};

// ─────────────────────────────────────────────
// TRAINING  (build dataset + Ollama fine-tune)
// ─────────────────────────────────────────────
export const trainingAPI = {
  /** Build JSONL dataset from all docs, chats & custom Q&A. */
  buildDataset: ()                             => api.post('/training/build-dataset'),
  /** Dataset stats without rebuilding. */
  getStats:     ()                             => api.get('/training/stats'),
  /** Create a custom Ollama model with your knowledge injected. */
  createModel:  (modelName, description = '')  => api.post('/training/create-model', { model_name: modelName, description }),
  listModels:   ()                             => api.get('/training/models'),
  deleteModel:  (modelName)                    => api.delete(`/training/models/${modelName}`),
  /** Export HuggingFace-ready JSONL (prompt/completion + alpaca). */
  exportHF:     ()                             => api.post('/training/export-hf'),
  // Custom Q&A
  addCustomQA:    (question, answer, source = 'manual') => api.post('/training/custom-qa', { question, answer, source }),
  listCustomQA:   ()    => api.get('/training/custom-qa'),
  deleteCustomQA: (idx) => api.delete(`/training/custom-qa/${idx}`),
};

export default api;