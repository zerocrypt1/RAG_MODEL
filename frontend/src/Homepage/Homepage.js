import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

// ─── Animated counter ────────────────────────────────────────────────────────
function Counter({ target, suffix = '' }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let start = 0;
    const step = target / 60;
    const timer = setInterval(() => {
      start += step;
      if (start >= target) { setCount(target); clearInterval(timer); }
      else setCount(Math.floor(start));
    }, 16);
    return () => clearInterval(timer);
  }, [target]);
  return <>{count.toLocaleString()}{suffix}</>;
}

// ─── Floating orb ────────────────────────────────────────────────────────────
function Orb({ style }) {
  return <div style={{ position: 'absolute', borderRadius: '50%', filter: 'blur(80px)', opacity: 0.18, pointerEvents: 'none', ...style }} />;
}

// ─── Feature card ─────────────────────────────────────────────────────────────
function FeatureCard({ icon, title, desc, accent }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.03)',
        border: `1px solid ${hov ? accent + '60' : 'rgba(255,255,255,0.08)'}`,
        borderRadius: 20,
        padding: '28px 24px',
        transition: 'all 0.3s ease',
        transform: hov ? 'translateY(-4px)' : 'none',
        cursor: 'default',
        boxShadow: hov ? `0 20px 40px ${accent}20` : 'none',
      }}
    >
      <div style={{
        width: 48, height: 48, borderRadius: 14, background: accent + '22',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 22, marginBottom: 16,
        border: `1px solid ${accent}40`,
      }}>{icon}</div>
      <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 17, fontWeight: 700, color: '#F5F0E8', marginBottom: 8 }}>{title}</div>
      <div style={{ fontSize: 14, color: '#8A8478', lineHeight: 1.6 }}>{desc}</div>
    </div>
  );
}

// ─── Language badge ───────────────────────────────────────────────────────────
function LangBadge({ label, emoji }) {
  return (
    <span style={{
      background: 'rgba(255,185,90,0.12)',
      border: '1px solid rgba(255,185,90,0.3)',
      borderRadius: 100,
      padding: '6px 16px',
      fontSize: 13,
      color: '#FFB95A',
      fontWeight: 600,
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
    }}>
      {emoji} {label}
    </span>
  );
}

export default function HomePage() {
  const navigate = useNavigate();
  const heroRef  = useRef(null);
  const [scrollY, setScrollY] = useState(0);

  useEffect(() => {
    const onScroll = () => setScrollY(window.scrollY);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const features = [
    { icon: '🧠', title: 'Ask Your Documents', desc: 'Upload PDFs, Word docs, Excel sheets or images — then have a real conversation with the content inside.', accent: '#7C9EFF' },
    { icon: '🎙️', title: 'Voice Search', desc: 'Just speak your question — in Hindi, English, or Hinglish. No typing needed. It understands you.', accent: '#FF8A65' },
    { icon: '🌐', title: 'Live Web Search', desc: "Can't find it in the doc? It hits the web automatically and brings back a human-friendly answer.", accent: '#4CAF82' },
    { icon: '💬', title: 'Free Chat Mode', desc: 'No document? No problem. Chat freely — ask anything, get real answers from your AI buddy.', accent: '#E879A0' },
    { icon: '🇮🇳', title: 'Hindi & Hinglish', desc: 'Bol do Hindi mein, Hinglish mein, ya English mein — samajhta hai sab. Replies naturally in your language.', accent: '#FFB95A' },
    { icon: '⚡', title: 'Blazing Fast', desc: 'Local Mistral model via Ollama — no API keys, no data leaving your machine, sub-second responses.', accent: '#A78BFA' },
  ];

  const steps = [
    { n: '01', title: 'Upload', desc: 'Drop any PDF, image, Word, or Excel file', icon: '📎' },
    { n: '02', title: 'Ask',    desc: 'Type or speak your question — any language', icon: '❓' },
    { n: '03', title: 'Get',    desc: 'Instant, human-like answers with page refs', icon: '✨' },
  ];

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0D0C0A',
      fontFamily: "'DM Sans', sans-serif",
      overflowX: 'hidden',
      color: '#F5F0E8',
    }}>

      {/* Google Fonts */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::selection { background: #FFB95A40; color: #FFB95A; }

        @keyframes float {
          0%,100% { transform: translateY(0px) rotate(0deg); }
          33% { transform: translateY(-12px) rotate(1deg); }
          66% { transform: translateY(-6px) rotate(-1deg); }
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(30px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes glow {
          0%,100% { box-shadow: 0 0 20px #FFB95A40; }
          50% { box-shadow: 0 0 50px #FFB95A80; }
        }
        @keyframes shimmer {
          0% { background-position: -200% center; }
          100% { background-position: 200% center; }
        }
        .hero-title {
          animation: fadeUp 0.8s ease both;
        }
        .hero-sub {
          animation: fadeUp 0.8s 0.15s ease both;
        }
        .hero-btns {
          animation: fadeUp 0.8s 0.3s ease both;
        }
        .hero-badges {
          animation: fadeUp 0.8s 0.45s ease both;
        }
        .float-card {
          animation: float 6s ease-in-out infinite;
        }
        .cta-btn {
          animation: glow 3s ease-in-out infinite;
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .cta-btn:hover {
          transform: scale(1.04);
        }
        .shimmer-text {
          background: linear-gradient(90deg, #FFB95A, #FF8A65, #FFB95A, #FF8A65);
          background-size: 200% auto;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
          animation: shimmer 3s linear infinite;
        }
        .stat-num {
          font-family: 'Syne', sans-serif;
          font-size: 42px;
          font-weight: 800;
          color: #FFB95A;
        }
        .step-line::after {
          content: '';
          position: absolute;
          top: 24px;
          left: calc(100% + 16px);
          width: calc(100% - 0px);
          height: 1px;
          background: linear-gradient(to right, rgba(255,185,90,0.5), transparent);
        }
      `}</style>

      {/* ── NAV ─────────────────────────────────────────────────────────────── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
        padding: '0 40px',
        height: 64,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: scrollY > 20 ? 'rgba(13,12,10,0.92)' : 'transparent',
        backdropFilter: scrollY > 20 ? 'blur(16px)' : 'none',
        borderBottom: scrollY > 20 ? '1px solid rgba(255,255,255,0.06)' : 'none',
        transition: 'all 0.3s ease',
      }}>
        <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 20, fontWeight: 800, color: '#F5F0E8', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 22 }}>🤖</span>
          <span className="shimmer-text">QUBISA</span>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <button
            onClick={() => navigate('/login')}
            style={{ padding: '9px 22px', borderRadius: 100, border: '1px solid rgba(255,255,255,0.15)', background: 'transparent', color: '#C8C0B4', fontSize: 14, fontWeight: 500, cursor: 'pointer', transition: 'all 0.2s' }}
            onMouseEnter={e => { e.target.style.borderColor = 'rgba(255,185,90,0.5)'; e.target.style.color = '#FFB95A'; }}
            onMouseLeave={e => { e.target.style.borderColor = 'rgba(255,255,255,0.15)'; e.target.style.color = '#C8C0B4'; }}
          >Sign In</button>
          <button
            onClick={() => navigate('/dashboard')}
            style={{ padding: '9px 22px', borderRadius: 100, border: 'none', background: '#FFB95A', color: '#0D0C0A', fontSize: 14, fontWeight: 700, cursor: 'pointer' }}
          >Get Started →</button>
        </div>
      </nav>

      {/* ── HERO ────────────────────────────────────────────────────────────── */}
      <section ref={heroRef} style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '120px 24px 80px', position: 'relative', textAlign: 'center' }}>
        {/* Background orbs */}
        <Orb style={{ width: 600, height: 600, background: '#FFB95A', top: -100, left: -150 }} />
        <Orb style={{ width: 500, height: 500, background: '#7C9EFF', bottom: -50, right: -100 }} />
        <Orb style={{ width: 300, height: 300, background: '#E879A0', top: '40%', left: '60%' }} />

        {/* Floating chat bubble decoration */}
        <div className="float-card" style={{
          position: 'absolute', top: 130, right: 'max(5%, 40px)',
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: 16, padding: '12px 18px',
          fontSize: 13, color: '#C8C0B4',
          backdropFilter: 'blur(10px)',
          maxWidth: 220,
          animationDelay: '0s',
          display: window.innerWidth < 768 ? 'none' : 'block',
        }}>
          <span style={{ color: '#4CAF82', marginRight: 8 }}>●</span>
          "Yaar, page 12 pe kya likha hai?"
        </div>
        <div className="float-card" style={{
          position: 'absolute', bottom: 180, left: 'max(4%, 30px)',
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.12)',
          borderRadius: 16, padding: '12px 18px',
          fontSize: 13, color: '#C8C0B4',
          backdropFilter: 'blur(10px)',
          maxWidth: 230,
          animationDelay: '2s',
          display: window.innerWidth < 768 ? 'none' : 'block',
        }}>
          <span style={{ color: '#FFB95A', marginRight: 8 }}>●</span>
          "What's the summary of this contract?"
        </div>

        {/* Badge */}
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'rgba(255,185,90,0.1)', border: '1px solid rgba(255,185,90,0.3)', borderRadius: 100, padding: '6px 18px', marginBottom: 32, fontSize: 13, color: '#FFB95A', fontWeight: 600 }}>
          <span>✨</span> Your AI dost — now multilingual
        </div>

        {/* Main title */}
        <h1 className="hero-title" style={{ fontFamily: "'Syne', sans-serif", fontSize: 'clamp(40px, 7vw, 88px)', fontWeight: 800, lineHeight: 1.05, letterSpacing: '-2px', marginBottom: 24, maxWidth: 900 }}>
          Chat with your docs<br />
          <span className="shimmer-text">like a best friend.</span>
        </h1>

        <p className="hero-sub" style={{ fontSize: 'clamp(16px, 2.5vw, 20px)', color: '#8A8478', maxWidth: 600, lineHeight: 1.7, marginBottom: 40 }}>
          Upload PDFs, images, or documents. Ask questions in Hindi, English, or Hinglish — by typing or speaking. Get human answers instantly.
        </p>

        {/* CTA Buttons */}
        <div className="hero-btns" style={{ display: 'flex', gap: 14, flexWrap: 'wrap', justifyContent: 'center', marginBottom: 40 }}>
          <button
            className="cta-btn"
            onClick={() => navigate('/dashboard')}
            style={{
              padding: '16px 36px', borderRadius: 100,
              background: '#FFB95A', color: '#0D0C0A',
              fontSize: 16, fontWeight: 700, border: 'none',
              cursor: 'pointer',
            }}
          >
            Start for Free →
          </button>
          <button
            onClick={() => navigate('/chat')}
            style={{
              padding: '16px 36px', borderRadius: 100,
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.12)',
              color: '#F5F0E8', fontSize: 16, fontWeight: 600,
              cursor: 'pointer', transition: 'all 0.2s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.06)'}
          >
            💬 Just Chat
          </button>
        </div>

        {/* Language badges */}
        <div className="hero-badges" style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center' }}>
          <LangBadge label="Hindi"    emoji="🇮🇳" />
          <LangBadge label="English"  emoji="🇬🇧" />
          <LangBadge label="Hinglish" emoji="🤝" />
          <LangBadge label="Voice Input" emoji="🎙️" />
        </div>
      </section>

      {/* ── STATS ──────────────────────────────────────────────────────────── */}
      <section style={{ padding: '60px 24px', borderTop: '1px solid rgba(255,255,255,0.06)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ maxWidth: 900, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 40, textAlign: 'center' }}>
          {[
            { n: 100, suffix: '%', label: 'Local & Private', sub: 'No data leaves your machine' },
            { n: 3,   suffix: '',  label: 'Languages',       sub: 'Hindi · English · Hinglish' },
            { n: 4,   suffix: '+', label: 'File Types',      sub: 'PDF · Image · Word · Excel' },
            { n: 0,   suffix: '$', label: 'API Cost',        sub: 'Powered by Ollama + Mistral' },
          ].map(s => (
            <div key={s.label}>
              <div className="stat-num"><Counter target={s.n} suffix={s.suffix} /></div>
              <div style={{ fontWeight: 600, color: '#F5F0E8', marginTop: 4, marginBottom: 4 }}>{s.label}</div>
              <div style={{ fontSize: 13, color: '#6B6660' }}>{s.sub}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── HOW IT WORKS ─────────────────────────────────────────────────── */}
      <section style={{ padding: '100px 24px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: 60 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#FFB95A', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 12 }}>How it works</div>
            <h2 style={{ fontFamily: "'Syne', sans-serif", fontSize: 'clamp(28px, 4vw, 44px)', fontWeight: 800 }}>Three steps to genius answers</h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 32, position: 'relative' }}>
            {steps.map((s, i) => (
              <div key={s.n} style={{ textAlign: 'center', position: 'relative' }}>
                <div style={{
                  width: 72, height: 72, borderRadius: '50%',
                  background: 'rgba(255,185,90,0.1)',
                  border: '1px solid rgba(255,185,90,0.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 28, margin: '0 auto 20px',
                }}>{s.icon}</div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 36, fontWeight: 800, color: 'rgba(255,185,90,0.15)', marginBottom: -12 }}>{s.n}</div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 20, fontWeight: 700, marginBottom: 10 }}>{s.title}</div>
                <div style={{ color: '#8A8478', lineHeight: 1.6, fontSize: 15 }}>{s.desc}</div>
                {i < steps.length - 1 && (
                  <div style={{
                    position: 'absolute', top: 36, left: 'calc(50% + 50px)',
                    right: -16, height: 1,
                    background: 'linear-gradient(to right, rgba(255,185,90,0.4), transparent)',
                    display: 'none',
                  }} />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FEATURES GRID ─────────────────────────────────────────────────── */}
      <section style={{ padding: '60px 24px 100px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <div style={{ textAlign: 'center', marginBottom: 60 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#7C9EFF', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 12 }}>Features</div>
            <h2 style={{ fontFamily: "'Syne', sans-serif", fontSize: 'clamp(28px, 4vw, 44px)', fontWeight: 800 }}>Everything you need</h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 20 }}>
            {features.map(f => <FeatureCard key={f.title} {...f} />)}
          </div>
        </div>
      </section>

      {/* ── DEMO SNIPPET ──────────────────────────────────────────────────── */}
      <section style={{ padding: '60px 24px 100px' }}>
        <div style={{ maxWidth: 800, margin: '0 auto', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 24, overflow: 'hidden' }}>
          {/* Terminal header */}
          <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', gap: 8 }}>
            {['#FF5F57','#FEBC2E','#28C840'].map(c => <div key={c} style={{ width: 12, height: 12, borderRadius: '50%', background: c }} />)}
            <span style={{ marginLeft: 8, fontSize: 13, color: '#6B6660' }}>QUBISA — Live demo</span>
          </div>
          {/* Chat messages */}
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[
              { role: 'user',  text: '🎙️ Yaar, is contract mein kya dikkat ho sakti hai?',    lang: 'Hinglish' },
              { role: 'ai',    text: 'Bhai sun! Page 4 pe ek clause hai jo slightly tricky hai — termination notice sirf 7 days ka hai, jo pretty short hai. Aur page 11 pe intellectual property waala section thoda broad hai tere liye. Double-check karna chahiye! 👀', lang: '' },
              { role: 'user',  text: 'What does section 3.2 say about payment terms?',         lang: 'English' },
              { role: 'ai',    text: 'Great question! Section 3.2 (page 6) says payment is due within 30 days of invoice. Late payments attract 2% monthly interest. There\'s also a clause allowing them to pause delivery if payment is overdue by more than 15 days — heads up! 💸', lang: '' },
            ].map((m, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', gap: 10, alignItems: 'flex-end' }}>
                {m.role === 'ai' && <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(255,185,90,0.15)', border: '1px solid rgba(255,185,90,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>🤖</div>}
                <div style={{
                  maxWidth: '72%',
                  background: m.role === 'user' ? 'rgba(255,185,90,0.12)' : 'rgba(255,255,255,0.05)',
                  border: `1px solid ${m.role === 'user' ? 'rgba(255,185,90,0.25)' : 'rgba(255,255,255,0.08)'}`,
                  borderRadius: m.role === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                  padding: '12px 16px', fontSize: 14, lineHeight: 1.6,
                  color: m.role === 'user' ? '#FFD49A' : '#C8C0B4',
                }}>
                  {m.lang && <div style={{ fontSize: 10, color: '#FFB95A', fontWeight: 600, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>{m.lang}</div>}
                  {m.text}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA BANNER ────────────────────────────────────────────────────── */}
      <section style={{ padding: '80px 24px 120px' }}>
        <div style={{
          maxWidth: 700, margin: '0 auto', textAlign: 'center',
          background: 'linear-gradient(135deg, rgba(255,185,90,0.08), rgba(124,158,255,0.08))',
          border: '1px solid rgba(255,185,90,0.2)',
          borderRadius: 28, padding: '60px 40px',
          position: 'relative', overflow: 'hidden',
        }}>
          <Orb style={{ width: 300, height: 300, background: '#FFB95A', top: -100, right: -50 }} />
          <div style={{ fontSize: 48, marginBottom: 20 }}>🚀</div>
          <h2 style={{ fontFamily: "'Syne', sans-serif", fontSize: 'clamp(26px, 4vw, 40px)', fontWeight: 800, marginBottom: 16, position: 'relative' }}>
            Ready to meet your<br /><span className="shimmer-text">AI dost?</span>
          </h2>
          <p style={{ color: '#8A8478', marginBottom: 32, fontSize: 16, lineHeight: 1.7, position: 'relative' }}>
            No sign-up fees. No cloud. 100% private. Just you and your documents.
          </p>
          <button
            className="cta-btn"
            onClick={() => navigate('/dashboard')}
            style={{
              padding: '18px 44px', borderRadius: 100,
              background: '#FFB95A', color: '#0D0C0A',
              fontSize: 17, fontWeight: 700, border: 'none',
              cursor: 'pointer', position: 'relative',
            }}
          >
            Start Chatting — It's Free
          </button>
        </div>
      </section>

      {/* ── FOOTER ──────────────────────────────────────────────────────────── */}
      <footer style={{ padding: '32px 40px', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>🤖</span> <span className="shimmer-text">QUBISA</span>
        </div>
        <div style={{ fontSize: 13, color: '#4A4640' }}>
          Powered by Ollama + Mistral · 100% Local · Made with ❤️ by Shivansh
        </div>
      </footer>
    </div>
  );
}