import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Handle 401 globally
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

// Auth
export const authAPI = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  googleAuth: (credential) => api.post('/auth/google', { credential }),
  verifyEmail: (token) => api.post('/auth/verify-email', { token }),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }),
  resetPassword: (token, password) => api.post('/auth/reset-password', { token, password }),
  getMe: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
};

// PDF
export const pdfAPI = {
  upload: (formData) => api.post('/pdf/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  getStatus: (id) => api.get(`/pdf/status/${id}`),
  list: () => api.get('/pdf/list'),
  delete: (id) => api.delete(`/pdf/${id}`),
  getDownloadUrl: (id) => api.get(`/pdf/${id}/download-url`),
};

// Chat
export const chatAPI = {
  createSession: (pdfId) => api.post('/chat/session', { pdf_id: pdfId }),
  sendMessage: (sessionId, question) =>
    api.post('/chat/message', { session_id: sessionId, question }),
  getMessages: (sessionId) => api.get(`/chat/session/${sessionId}/messages`),
  getSessions: () => api.get('/chat/sessions'),
  deleteSession: (id) => api.delete(`/chat/session/${id}`),
};

// History
export const historyAPI = {
  getHistory: (page = 1) => api.get(`/history/?page=${page}`),
  search: (q) => api.get(`/history/search?q=${q}`),
  getStats: () => api.get('/history/stats'),
};

export default api;