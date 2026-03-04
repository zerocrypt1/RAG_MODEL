import React, { useEffect, useState } from 'react';
import { useSearchParams, Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { authAPI } from '../utils/api';
import { useAuth } from '../context/AuthContext';

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const [status, setStatus] = useState('verifying');
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const token = params.get('token');
    if (!token) { setStatus('error'); return; }
    authAPI.verifyEmail(token)
      .then(res => {
        login(res.data.token, res.data.user);
        setStatus('success');
        setTimeout(() => navigate('/dashboard'), 2000);
      })
      .catch(() => setStatus('error'));
  }, []);

  return (
    <div className="auth-wrapper">
      <div className="auth-card" style={{ textAlign: 'center' }}>
        {status === 'verifying' && (
          <>
            <div className="spinner" style={{ margin: '0 auto 24px' }} />
            <h2 className="auth-title">Verifying your email...</h2>
          </>
        )}
        {status === 'success' && (
          <>
            <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
            <h2 className="auth-title">Email Verified!</h2>
            <p style={{ color: 'var(--text-secondary)', fontFamily: 'Space Mono' }}>Redirecting to dashboard...</p>
          </>
        )}
        {status === 'error' && (
          <>
            <div style={{ fontSize: 48, marginBottom: 16 }}>❌</div>
            <h2 className="auth-title">Invalid Link</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: 24, fontFamily: 'Space Mono' }}>
              This verification link is invalid or expired.
            </p>
            <Link to="/login" className="btn btn-primary" style={{ display: 'inline-flex' }}>Back to Login</Link>
          </>
        )}
      </div>
    </div>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await authAPI.forgotPassword(email);
      setSent(true);
    } catch {
      toast.error('Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-card">
        <h1 className="auth-title">Reset Password</h1>
        <p className="auth-subtitle">// Enter your email to receive a reset link</p>
        {sent ? (
          <div style={{ textAlign: 'center' }}>
            <p style={{ color: 'var(--success)', marginBottom: 24, fontFamily: 'Space Mono' }}>
              ✓ Reset email sent (if account exists)
            </p>
            <Link to="/login" className="btn btn-secondary" style={{ display: 'inline-flex' }}>Back to Login</Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input type="email" className="form-input" placeholder="you@example.com"
                value={email} onChange={e => setEmail(e.target.value)} required />
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? 'Sending...' : 'Send Reset Link'}
            </button>
          </form>
        )}
        <p className="auth-link"><Link to="/login">Back to Login</Link></p>
      </div>
    </div>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    const token = params.get('token');
    setLoading(true);
    try {
      await authAPI.resetPassword(token, password);
      toast.success('Password reset! Please login.');
      navigate('/login');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Reset failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-card">
        <h1 className="auth-title">New Password</h1>
        <p className="auth-subtitle">// Choose a strong password</p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">New Password</label>
            <input type="password" className="form-input" placeholder="••••••••"
              value={password} onChange={e => setPassword(e.target.value)}
              minLength={8} required />
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? 'Resetting...' : 'Reset Password'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default VerifyEmailPage;