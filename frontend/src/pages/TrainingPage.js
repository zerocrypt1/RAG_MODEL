import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { trainingAPI, memoryAPI } from '../utils/api';
import { startVoiceRecognition } from '../utils/api';

// ─────────────────────────────────────────────
// STYLES
// ─────────────────────────────────────────────
const C = {
  bg:       '#0D0C0A',
  surface:  'rgba(255,255,255,0.03)',
  border:   'rgba(255,255,255,0.08)',
  gold:     '#FFB95A',
  blue:     '#7C9EFF',
  green:    '#4CAF82',
  pink:     '#E879A0',
  purple:   '#A78BFA',
  text:     '#F5F0E8',
  muted:    '#6B6660',
  dim:      '#3A3632',
};

const pill = (color, active) => ({
  padding: '6px 14px', borderRadius: 100, fontSize: 12, fontWeight: 600,
  cursor: 'pointer', border: 'none', transition: 'all 0.15s',
  background: active ? `${color}22` : 'transparent',
  color:      active ? color : C.muted,
  border:     active ? `1px solid ${color}40` : `1px solid transparent`,
});

const card = (glow) => ({
  background: C.surface,
  border: `1px solid ${glow ? glow + '30' : C.border}`,
  borderRadius: 16, padding: 20,
  boxShadow: glow ? `0 0 24px ${glow}10` : 'none',
  transition: 'all 0.2s',
});

const btn = (variant = 'ghost', size = 'md') => {
  const colors = {
    primary: { bg: C.gold,   color: '#0D0C0A' },
    success: { bg: C.green,  color: '#0D0C0A' },
    danger:  { bg: 'rgba(239,68,68,0.15)', color: '#EF4444', border: '1px solid rgba(239,68,68,0.3)' },
    ghost:   { bg: 'rgba(255,255,255,0.05)', color: C.muted, border: `1px solid ${C.border}` },
    purple:  { bg: 'rgba(167,139,250,0.15)', color: C.purple, border: `1px solid rgba(167,139,250,0.3)` },
  };
  const c = colors[variant] || colors.ghost;
  const pad = size === 'sm' ? '7px 14px' : '10px 20px';
  return {
    padding: pad, borderRadius: 100, border: c.border || 'none',
    background: c.bg, color: c.color,
    fontSize: size === 'sm' ? 12 : 14, fontWeight: 600,
    cursor: 'pointer', transition: 'all 0.15s',
    display: 'inline-flex', alignItems: 'center', gap: 6,
  };
};

// ─────────────────────────────────────────────
// SUB-COMPONENTS
// ─────────────────────────────────────────────

function SectionHeader({ icon, title, sub }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <span style={{ fontSize: 20 }}>{icon}</span>
        <span style={{ fontFamily: "'Syne', sans-serif", fontSize: 18, fontWeight: 800 }}>{title}</span>
      </div>
      {sub && <div style={{ fontSize: 13, color: C.muted, paddingLeft: 30 }}>{sub}</div>}
    </div>
  );
}

function StatBadge({ value, label, color }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 28, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>{label}</div>
    </div>
  );
}

function StatusDot({ active }) {
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: active ? C.green : C.muted,
      boxShadow: active ? `0 0 6px ${C.green}` : 'none',
      marginRight: 6,
    }} />
  );
}

function MemoryChatBubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', gap: 8, alignItems: 'flex-end' }}>
      <div style={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0, fontSize: 13,
        background: isUser ? 'rgba(124,158,255,0.15)' : 'rgba(255,185,90,0.15)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {isUser ? '👤' : '🧠'}
      </div>
      <div style={{
        maxWidth: '75%',
        background: isUser ? 'rgba(124,158,255,0.08)' : 'rgba(255,255,255,0.04)',
        border: `1px solid ${isUser ? 'rgba(124,158,255,0.2)' : C.border}`,
        borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        padding: '10px 14px', fontSize: 14, lineHeight: 1.6,
        color: isUser ? '#B8D4FF' : '#D4CEC6',
      }}>
        {msg.content}
        {msg.sources?.length > 0 && (
          <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${C.border}`, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {msg.sources.slice(0, 4).map((s, i) => (
              <span key={i} style={{
                fontSize: 10, padding: '2px 8px', borderRadius: 6,
                background: s.type === 'chat' ? 'rgba(232,121,160,0.1)' : 'rgba(124,158,255,0.1)',
                color: s.type === 'chat' ? C.pink : C.blue,
                border: `1px solid ${s.type === 'chat' ? 'rgba(232,121,160,0.25)' : 'rgba(124,158,255,0.25)'}`,
              }}>
                {s.type === 'chat' ? '💬' : '📄'} {s.store_id?.slice(0, 16) || 'source'}
                {s.score ? ` (${s.score})` : ''}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────

export default function TrainingPage() {
  const navigate = useNavigate();
  const [tab, setTab]         = useState('memory');  // memory | train | dataset | custom

  // ── Memory state ──────────────────────────────────────────────────────────
  const [memMsgs,       setMemMsgs]       = useState([]);
  const [memInput,      setMemInput]      = useState('');
  const [memLoading,    setMemLoading]    = useState(false);
  const [memorySources, setMemorySources] = useState({ documents: [], chats: [] });
  const [listening,     setListening]     = useState(false);
  const recogRef = useRef(null);

  // ── Training state ────────────────────────────────────────────────────────
  const [dataStats,     setDataStats]     = useState(null);
  const [buildingData,  setBuildingData]  = useState(false);
  const [trainedModels, setTrainedModels] = useState([]);
  const [training,      setTraining]      = useState(false);
  const [modelName,     setModelName]     = useState('my-buddy-ai');
  const [modelDesc,     setModelDesc]     = useState('');
  const [trainLog,      setTrainLog]      = useState('');
  const [exportInfo,    setExportInfo]    = useState(null);

  // ── Custom QA state ───────────────────────────────────────────────────────
  const [customQA,      setCustomQA]      = useState([]);
  const [newQ,          setNewQ]          = useState('');
  const [newA,          setNewA]          = useState('');

  const chatBottomRef = useRef(null);

  // ── Load on mount ──────────────────────────────────────────────────────────
  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [memMsgs]);

  const loadAll = async () => {
    try {
      const [srcRes, statsRes, modelsRes, qaRes] = await Promise.allSettled([
        memoryAPI.getSources(),
        trainingAPI.getStats(),
        trainingAPI.listModels(),
        trainingAPI.listCustomQA(),
      ]);
      if (srcRes.status    === 'fulfilled') setMemorySources(srcRes.value.data);
      if (statsRes.status  === 'fulfilled') setDataStats(statsRes.value.data);
      if (modelsRes.status === 'fulfilled') setTrainedModels(modelsRes.value.data.models || []);
      if (qaRes.status     === 'fulfilled') setCustomQA(qaRes.value.data.pairs || []);
    } catch (e) {
      console.error(e);
    }
  };

  // ── Memory chat ────────────────────────────────────────────────────────────
  const sendMemoryQuery = async (override) => {
    const q = (override ?? memInput).trim();
    if (!q || memLoading) return;
    setMemInput('');
    setMemMsgs(prev => [...prev, { role: 'user', content: q }]);
    setMemLoading(true);
    try {
      const res = await memoryAPI.query(q);
      setMemMsgs(prev => [...prev, {
        role: 'assistant', content: res.data.answer, sources: res.data.sources,
      }]);
    } catch {
      setMemMsgs(prev => [...prev, { role: 'assistant', content: "Memory se connect nahi ho paya. 😕" }]);
    } finally {
      setMemLoading(false);
    }
  };

  const toggleVoice = () => {
    if (listening) { recogRef.current?.stop(); setListening(false); return; }
    setListening(true);
    recogRef.current = startVoiceRecognition(
      (t) => { setListening(false); sendMemoryQuery(t); toast.success(`🎙️ "${t.slice(0,40)}…"`); },
      (e) => { toast.error(e); setListening(false); },
      'hi-IN'
    );
    if (!recogRef.current) setListening(false);
  };

  // ── Build dataset ──────────────────────────────────────────────────────────
  const buildDataset = async () => {
    setBuildingData(true);
    try {
      const res = await trainingAPI.buildDataset();
      setDataStats(res.data);
      toast.success(`Dataset ready! ${res.data.total} examples built 🎉`);
    } catch { toast.error('Dataset build failed'); }
    finally { setBuildingData(false); }
  };

  // ── Train Ollama model ─────────────────────────────────────────────────────
  const trainModel = async () => {
    if (!modelName.trim()) return toast.error('Model name required');
    setTraining(true);
    setTrainLog('Building dataset...\n');
    try {
      const ds = await trainingAPI.buildDataset();
      setTrainLog(p => p + `✓ Dataset: ${ds.data.total} examples\n`);
      setTrainLog(p => p + `Creating Ollama model '${modelName}'...\n`);
      const res = await trainingAPI.createModel(modelName, modelDesc);
      const d = res.data;
      if (d.success) {
        setTrainLog(p => p + `✓ Model '${modelName}' created!\n${d.stdout}\n`);
        toast.success(`Model '${modelName}' trained & ready! 🚀`);
        loadAll();
      } else {
        setTrainLog(p => p + `✗ Error:\n${d.stderr}\n`);
        toast.error('Training failed — check log below');
      }
    } catch (e) {
      setTrainLog(p => p + `✗ ${e.message}\n`);
      toast.error('Training failed');
    } finally {
      setTraining(false);
    }
  };

  // ── Export ─────────────────────────────────────────────────────────────────
  const exportDataset = async () => {
    try {
      const res = await trainingAPI.exportHF();
      setExportInfo(res.data);
      toast.success('Dataset exported!');
    } catch { toast.error('Export failed'); }
  };

  // ── Custom QA ──────────────────────────────────────────────────────────────
  const addQA = async () => {
    if (!newQ.trim() || !newA.trim()) return toast.error('Both question and answer required');
    try {
      await trainingAPI.addCustomQA(newQ, newA);
      setNewQ(''); setNewA('');
      toast.success('Q&A added to training data!');
      loadAll();
    } catch { toast.error('Failed to add Q&A'); }
  };

  const deleteQA = async (i) => {
    try {
      await trainingAPI.deleteCustomQA(i);
      toast.success('Deleted');
      loadAll();
    } catch { toast.error('Delete failed'); }
  };

  // ─────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', background: C.bg, color: C.text, fontFamily: "'DM Sans', sans-serif", padding: '88px 24px 60px' }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400&display=swap');
        * { box-sizing: border-box; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeUp { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
        .tab-btn:hover { opacity: 0.8; }
        textarea { resize: vertical; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
        .log-box { font-family: 'JetBrains Mono', monospace; font-size: 12px; background: rgba(0,0,0,0.5);
          border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px;
          color: #4CAF82; max-height: 200px; overflow-y: auto; white-space: pre-wrap; line-height: 1.6; }
        input, textarea { font-family: 'DM Sans', sans-serif; }
        input:focus, textarea:focus { outline: none; border-color: rgba(255,185,90,0.4) !important; }
      `}</style>

      <div style={{ maxWidth: 980, margin: '0 auto' }}>

        {/* ── Header ──────────────────────────────────────────────────── */}
        <div style={{ marginBottom: 32, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <button onClick={() => navigate('/dashboard')} style={{ ...btn('ghost', 'sm'), borderRadius: 100 }}>← Back</button>
            </div>
            <h1 style={{ fontFamily: "'Syne', sans-serif", fontSize: 30, fontWeight: 800, marginBottom: 4 }}>🧠 Memory & Training</h1>
            <p style={{ color: C.muted, fontSize: 14 }}>Search across all your docs + chats · Train your own model · Export dataset</p>
          </div>

          {/* Stats row */}
          <div style={{ display: 'flex', gap: 24, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 16, padding: '14px 24px' }}>
            <StatBadge value={memorySources.documents?.length || 0} label="Documents"  color={C.blue} />
            <div style={{ width: 1, background: C.border }} />
            <StatBadge value={memorySources.chats?.length || 0}     label="Chat Sessions" color={C.pink} />
            <div style={{ width: 1, background: C.border }} />
            <StatBadge value={dataStats?.total || 0}                label="Train Examples" color={C.green} />
          </div>
        </div>

        {/* ── Tabs ────────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 28, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 100, padding: 5, width: 'fit-content' }}>
          {[
            { id: 'memory',  icon: '🧠', label: 'Memory Chat' },
            { id: 'train',   icon: '🚀', label: 'Train Model' },
            { id: 'dataset', icon: '📊', label: 'Dataset' },
            { id: 'custom',  icon: '✍️',  label: 'Custom Q&A' },
          ].map(t => (
            <button key={t.id} className="tab-btn" onClick={() => setTab(t.id)} style={pill(C.gold, tab === t.id)}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* ══════════════════════════════════════════════════════════════
            TAB: MEMORY CHAT
        ══════════════════════════════════════════════════════════════ */}
        {tab === 'memory' && (
          <div style={{ animation: 'fadeUp 0.3s ease both', display: 'grid', gridTemplateColumns: '1fr 260px', gap: 20 }}>

            {/* Chat panel */}
            <div style={{ ...card(C.blue), display: 'flex', flexDirection: 'column', height: 560 }}>
              <SectionHeader icon="🧠" title="Ask Across All Memory"
                sub="Searches every uploaded PDF, image, doc & past chat history at once" />

              {/* Messages */}
              <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 14, paddingRight: 4 }}>
                {memMsgs.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '32px 0', color: C.muted }}>
                    <div style={{ fontSize: 40, marginBottom: 10 }}>🧠</div>
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>Kuch bhi pooch — sab yaad hai!</div>
                    <div style={{ fontSize: 13 }}>Purani PDFs, images, chats — sab search ho jaega</div>
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap', marginTop: 16 }}>
                      {[
                        'Pichli PDF mein kya tha?',
                        'Summarize all my documents',
                        'What did I ask yesterday?',
                      ].map(s => (
                        <button key={s} onClick={() => setMemInput(s)} style={{ ...btn('ghost', 'sm'), borderRadius: 8, fontSize: 12 }}>{s}</button>
                      ))}
                    </div>
                  </div>
                )}
                {memMsgs.map((m, i) => <MemoryChatBubble key={i} msg={m} />)}
                {memLoading && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'rgba(255,185,90,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>🧠</div>
                    <div style={{ ...card(), padding: '10px 14px', fontSize: 13, color: C.muted }}>
                      Memory search chal raha hai…
                      {[0,1,2].map(i => <span key={i} style={{ display: 'inline-block', width: 5, height: 5, borderRadius: '50%', background: C.gold, margin: '0 2px', animation: `pulse 1s ${i*0.2}s infinite` }} />)}
                    </div>
                  </div>
                )}
                <div ref={chatBottomRef} />
              </div>

              {/* Input */}
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', background: 'rgba(255,255,255,0.04)', border: `1px solid ${C.border}`, borderRadius: 14, padding: '6px 8px 6px 14px' }}>
                <input
                  value={memInput}
                  onChange={e => setMemInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && sendMemoryQuery()}
                  placeholder="Kuch bhi pooch — sab yaad hai 🧠"
                  style={{ flex: 1, background: 'none', border: 'none', color: C.text, fontSize: 14, outline: 'none' }}
                />
                <button onClick={toggleVoice} style={{
                  width: 34, height: 34, borderRadius: '50%', border: 'none', cursor: 'pointer', fontSize: 15,
                  background: listening ? 'rgba(232,121,160,0.2)' : 'rgba(255,255,255,0.06)',
                  color: listening ? C.pink : C.muted,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>🎙️</button>
                <button onClick={() => sendMemoryQuery()} disabled={!memInput.trim() || memLoading} style={{
                  ...btn('primary', 'sm'), borderRadius: '50%', width: 34, height: 34, padding: 0, justifyContent: 'center',
                }}>↑</button>
              </div>
            </div>

            {/* Sources panel */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={card()}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: C.blue }}>📄 Documents ({memorySources.documents?.length || 0})</div>
                {(memorySources.documents || []).length === 0
                  ? <div style={{ fontSize: 12, color: C.muted }}>No docs yet</div>
                  : (memorySources.documents || []).map((d, i) => (
                    <div key={i} style={{ fontSize: 12, color: '#C8C0B4', padding: '5px 0', borderBottom: `1px solid ${C.border}` }}>
                      <StatusDot active />
                      {d.store_id || d.source_file || 'Document'}
                      {d.chunk_count && <span style={{ color: C.muted, marginLeft: 6 }}>{d.chunk_count} chunks</span>}
                    </div>
                  ))
                }
              </div>
              <div style={card()}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: C.pink }}>💬 Chat Sessions ({memorySources.chats?.length || 0})</div>
                {(memorySources.chats || []).length === 0
                  ? <div style={{ fontSize: 12, color: C.muted }}>No chat history yet</div>
                  : (memorySources.chats || []).map((c, i) => (
                    <div key={i} style={{ fontSize: 12, color: '#C8C0B4', padding: '5px 0', borderBottom: `1px solid ${C.border}` }}>
                      <StatusDot active />
                      {c.title?.slice(0, 22) || c.session_id?.slice(0, 16)}
                      <span style={{ color: C.muted, marginLeft: 6 }}>{c.msg_count} msgs</span>
                    </div>
                  ))
                }
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            TAB: TRAIN MODEL
        ══════════════════════════════════════════════════════════════ */}
        {tab === 'train' && (
          <div style={{ animation: 'fadeUp 0.3s ease both', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

            {/* Left: Create model */}
            <div style={card(C.gold)}>
              <SectionHeader icon="🚀" title="Train Ollama Model"
                sub="Creates a custom model with your docs + chats injected into its memory. No GPU needed." />

              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div>
                  <label style={{ fontSize: 12, color: C.muted, fontWeight: 600, display: 'block', marginBottom: 6 }}>MODEL NAME</label>
                  <input
                    value={modelName}
                    onChange={e => setModelName(e.target.value.replace(/[^a-z0-9-_]/gi, '-').toLowerCase())}
                    placeholder="my-buddy-ai"
                    style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: `1px solid ${C.border}`, borderRadius: 10, padding: '10px 14px', color: C.text, fontSize: 14 }}
                  />
                  <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>Usable as: ollama run {modelName || 'my-buddy-ai'}</div>
                </div>

                <div>
                  <label style={{ fontSize: 12, color: C.muted, fontWeight: 600, display: 'block', marginBottom: 6 }}>DESCRIPTION (optional)</label>
                  <textarea
                    value={modelDesc}
                    onChange={e => setModelDesc(e.target.value)}
                    placeholder="e.g. My personal AI that knows all my work documents and chat history"
                    rows={3}
                    style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: `1px solid ${C.border}`, borderRadius: 10, padding: '10px 14px', color: C.text, fontSize: 13, lineHeight: 1.5 }}
                  />
                </div>

                {/* How it works */}
                <div style={{ background: 'rgba(255,185,90,0.05)', border: `1px solid rgba(255,185,90,0.15)`, borderRadius: 10, padding: '12px 14px' }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: C.gold, marginBottom: 6 }}>⚡ What happens:</div>
                  {['Builds dataset from all your PDFs, images, chats',
                    'Extracts key knowledge into a system prompt',
                    'Creates a custom Ollama Modelfile',
                    'Registers the model locally (ollama create)',
                    'Model is instantly usable in chat!'].map((s, i) => (
                    <div key={i} style={{ fontSize: 12, color: C.muted, marginBottom: 3 }}>
                      <span style={{ color: C.green, marginRight: 6 }}>✓</span>{s}
                    </div>
                  ))}
                </div>

                <button
                  onClick={trainModel}
                  disabled={training}
                  style={{ ...btn('primary'), justifyContent: 'center', width: '100%', padding: '12px' }}
                >
                  {training
                    ? <><div style={{ width: 16, height: 16, border: '2px solid rgba(0,0,0,0.3)', borderTopColor: '#0D0C0A', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} /> Training…</>
                    : '🚀 Build & Train Model'}
                </button>
              </div>

              {trainLog && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 11, color: C.muted, marginBottom: 6, fontWeight: 600 }}>TRAINING LOG</div>
                  <div className="log-box">{trainLog}</div>
                </div>
              )}
            </div>

            {/* Right: Trained models */}
            <div style={card()}>
              <SectionHeader icon="🤖" title="Your Models"
                sub={`${trainedModels.length} trained model${trainedModels.length !== 1 ? 's' : ''}`} />

              {trainedModels.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '30px 0', color: C.muted }}>
                  <div style={{ fontSize: 36, marginBottom: 10 }}>🤖</div>
                  <div style={{ fontSize: 14 }}>Train your first model to see it here</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {trainedModels.map((m, i) => (
                    <div key={i} style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${C.border}`, borderRadius: 12, padding: '14px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                          <StatusDot active={m.has_knowledge} />
                          {m.name}
                        </div>
                        <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>
                          {new Date(m.created_at).toLocaleDateString()} · {m.has_knowledge ? '✓ Custom knowledge' : 'Base model'}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button style={btn('ghost', 'sm')} onClick={() => { navigator.clipboard.writeText(`ollama run ${m.name}`); toast.success('Command copied!'); }}>
                          Copy
                        </button>
                        <button style={btn('danger', 'sm')} onClick={async () => {
                          if (!window.confirm(`Delete model '${m.name}'?`)) return;
                          await trainingAPI.deleteModel(m.name);
                          toast.success('Deleted'); loadAll();
                        }}>Del</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Ollama usage hint */}
              <div style={{ marginTop: 16, background: 'rgba(167,139,250,0.05)', border: `1px solid rgba(167,139,250,0.15)`, borderRadius: 10, padding: 12 }}>
                <div style={{ fontSize: 11, color: C.purple, fontWeight: 600, marginBottom: 6 }}>USE IN CHAT</div>
                <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.6 }}>
                  Set <code style={{ color: C.purple, background: 'rgba(167,139,250,0.1)', padding: '1px 5px', borderRadius: 4 }}>OLLAMA_MODEL={modelName}</code> in your <code style={{ color: C.purple, background: 'rgba(167,139,250,0.1)', padding: '1px 5px', borderRadius: 4 }}>.env</code> and restart the server to use your custom model everywhere.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            TAB: DATASET
        ══════════════════════════════════════════════════════════════ */}
        {tab === 'dataset' && (
          <div style={{ animation: 'fadeUp 0.3s ease both', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

            <div style={card(C.green)}>
              <SectionHeader icon="📊" title="Dataset Overview"
                sub="Training data collected from all your sources" />

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
                {[
                  { label: 'Total Examples', value: dataStats?.total        || 0, color: C.gold },
                  { label: 'From Documents', value: dataStats?.from_docs    || 0, color: C.blue },
                  { label: 'From Chats',     value: dataStats?.from_chat    || 0, color: C.pink },
                  { label: 'Custom Q&A',     value: dataStats?.from_custom  || 0, color: C.purple },
                ].map(s => (
                  <div key={s.label} style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${C.border}`, borderRadius: 12, padding: '14px', textAlign: 'center' }}>
                    <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 28, fontWeight: 800, color: s.color }}>{s.value}</div>
                    <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{s.label}</div>
                  </div>
                ))}
              </div>

              {dataStats?.built_at && (
                <div style={{ fontSize: 12, color: C.muted, marginBottom: 16 }}>
                  Last built: {new Date(dataStats.built_at).toLocaleString()}
                </div>
              )}

              <button onClick={buildDataset} disabled={buildingData} style={{ ...btn('success'), width: '100%', justifyContent: 'center', padding: '12px' }}>
                {buildingData
                  ? <><div style={{ width: 15, height: 15, border: '2px solid rgba(0,0,0,0.3)', borderTopColor: '#0D0C0A', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} /> Building…</>
                  : '⚡ Rebuild Dataset'}
              </button>
            </div>

            <div style={card(C.purple)}>
              <SectionHeader icon="📤" title="Export for HuggingFace"
                sub="Export JSONL for LoRA / QLoRA fine-tuning on any GPU machine" />

              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
                {[
                  { fmt: 'HuggingFace prompt/completion', file: 'hf_dataset.jsonl', color: C.gold },
                  { fmt: 'Alpaca instruction format',      file: 'alpaca_dataset.jsonl', color: C.blue },
                ].map(f => (
                  <div key={f.fmt} style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${C.border}`, borderRadius: 10, padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{f.fmt}</div>
                      <div style={{ fontSize: 11, color: C.muted }}>{f.file}</div>
                    </div>
                    <span style={{ fontSize: 11, color: f.color, background: `${f.color}15`, border: `1px solid ${f.color}30`, borderRadius: 100, padding: '2px 8px' }}>JSONL</span>
                  </div>
                ))}
              </div>

              <button onClick={exportDataset} style={{ ...btn('purple'), width: '100%', justifyContent: 'center', padding: '12px' }}>
                📤 Export Dataset
              </button>

              {exportInfo && (
                <div style={{ marginTop: 14 }}>
                  <div style={{ fontSize: 11, color: C.green, marginBottom: 6 }}>✓ Exported {exportInfo.total_examples} examples</div>
                  <div style={{ fontSize: 11, color: C.muted, marginBottom: 8 }}>Fine-tune command:</div>
                  <div className="log-box" style={{ color: C.purple }}>
                    {exportInfo.train_command}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            TAB: CUSTOM Q&A
        ══════════════════════════════════════════════════════════════ */}
        {tab === 'custom' && (
          <div style={{ animation: 'fadeUp 0.3s ease both', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

            {/* Add form */}
            <div style={card(C.pink)}>
              <SectionHeader icon="✍️" title="Add Custom Q&A"
                sub="Teach the model specific things — highest quality training signal" />

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, color: C.muted, fontWeight: 600, display: 'block', marginBottom: 6 }}>QUESTION / INSTRUCTION</label>
                  <textarea
                    value={newQ}
                    onChange={e => setNewQ(e.target.value)}
                    placeholder="e.g. Mera naam kya hai? / What is this company's refund policy?"
                    rows={3}
                    style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: `1px solid ${C.border}`, borderRadius: 10, padding: '10px 14px', color: C.text, fontSize: 13 }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: C.muted, fontWeight: 600, display: 'block', marginBottom: 6 }}>IDEAL ANSWER</label>
                  <textarea
                    value={newA}
                    onChange={e => setNewA(e.target.value)}
                    placeholder="Write the exact answer you want the model to give..."
                    rows={5}
                    style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: `1px solid ${C.border}`, borderRadius: 10, padding: '10px 14px', color: C.text, fontSize: 13 }}
                  />
                </div>
                <button onClick={addQA} style={{ ...btn('primary'), justifyContent: 'center', padding: '11px' }}>
                  ✓ Add to Training Data
                </button>
              </div>

              <div style={{ marginTop: 16, background: 'rgba(232,121,160,0.05)', border: `1px solid rgba(232,121,160,0.15)`, borderRadius: 10, padding: '10px 14px' }}>
                <div style={{ fontSize: 11, color: C.pink, fontWeight: 600, marginBottom: 4 }}>💡 PRO TIP</div>
                <div style={{ fontSize: 12, color: C.muted, lineHeight: 1.6 }}>
                  Custom Q&A has the highest weight in training. Use it to teach your exact name, personality, domain knowledge, and preferred response style.
                </div>
              </div>
            </div>

            {/* List */}
            <div style={card()}>
              <SectionHeader icon="📋" title={`Saved Q&A (${customQA.length})`}
                sub="These will be included in every model training run" />

              {customQA.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '30px 0', color: C.muted }}>
                  <div style={{ fontSize: 36, marginBottom: 10 }}>📋</div>
                  <div style={{ fontSize: 14 }}>No custom Q&A yet — add some on the left!</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 440, overflowY: 'auto', paddingRight: 4 }}>
                  {customQA.map((qa, i) => (
                    <div key={i} style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${C.border}`, borderRadius: 12, padding: '12px 14px' }}>
                      <div style={{ fontSize: 12, color: C.gold, fontWeight: 600, marginBottom: 4 }}>Q: {qa.question?.slice(0, 80)}{qa.question?.length > 80 ? '…' : ''}</div>
                      <div style={{ fontSize: 12, color: C.muted, marginBottom: 8, lineHeight: 1.5 }}>A: {qa.answer?.slice(0, 100)}{qa.answer?.length > 100 ? '…' : ''}</div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: 10, color: C.dim }}>{qa.added_at ? new Date(qa.added_at).toLocaleDateString() : ''}</span>
                        <button style={btn('danger', 'sm')} onClick={() => deleteQA(i)}>Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}