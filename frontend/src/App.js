import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';

// Pages
import LoginPage          from './pages/LoginPage';
import RegisterPage       from './pages/RegisterPage';
import VerifyEmailPage    from './pages/VerifyEmailPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage  from './pages/ResetPasswordPage';
import DashboardPage      from './pages/DashboardPage';
import ChatPage           from './pages/ChatPage';
import HistoryPage        from './pages/HistoryPage';
import HomePage           from './Homepage/Homepage';      // ← updated path
import TrainingPage       from './pages/TrainingPage';  // ← new

// Layout
import Layout from './components/Layout';

const GOOGLE_CLIENT_ID = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

// ── Route Guards ──────────────────────────────────────────────────────────────

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-screen"><div className="spinner" /></div>;
  return user ? children : <Navigate to="/login" replace />;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-screen"><div className="spinner" /></div>;
  return !user ? children : <Navigate to="/dashboard" replace />;
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <AuthProvider>
        <BrowserRouter>
          <Toaster
            position="top-right"
            toastOptions={{
              style: {
                background: '#0D0C0A',
                color: '#F5F0E8',
                border: '1px solid rgba(255,185,90,0.4)',
                borderRadius: '12px',
                fontFamily: "'DM Sans', sans-serif",
              },
            }}
          />

          <Routes>
            {/* ── Public landing ───────────────────────────────────────── */}
            <Route path="/"         element={<HomePage />} />
            <Route path="/home"     element={<HomePage />} />

            {/* ── Auth routes (redirect to dashboard if already logged in) */}
            <Route path="/login"           element={<PublicRoute><LoginPage /></PublicRoute>} />
            <Route path="/register"        element={<PublicRoute><RegisterPage /></PublicRoute>} />
            <Route path="/forgot-password" element={<PublicRoute><ForgotPasswordPage /></PublicRoute>} />
            <Route path="/reset-password"  element={<PublicRoute><ResetPasswordPage /></PublicRoute>} />

            {/* ── Email verification (no auth guard needed) ──────────── */}
            <Route path="/verify-email" element={<VerifyEmailPage />} />

            {/* ── Protected app routes ─────────────────────────────────── */}
            <Route
              path="/dashboard"
              element={
                <PrivateRoute>
                  <Layout><DashboardPage /></Layout>
                </PrivateRoute>
              }
            />
            <Route
              path="/chat"
              element={
                <PrivateRoute>
                  <Layout><ChatPage /></Layout>
                </PrivateRoute>
              }
            />
            <Route
              path="/chat/:sessionId"
              element={
                <PrivateRoute>
                  <Layout><ChatPage /></Layout>
                </PrivateRoute>
              }
            />
            <Route
              path="/history"
              element={
                <PrivateRoute>
                  <Layout><HistoryPage /></Layout>
                </PrivateRoute>
              }
            />
            <Route
              path="/training"
              element={
                <PrivateRoute>
                  <Layout><TrainingPage /></Layout>
                </PrivateRoute>
              }
            />

            {/* ── Catch-all fallback ────────────────────────────────────── */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>

        </BrowserRouter>
      </AuthProvider>
    </GoogleOAuthProvider>
  );
}