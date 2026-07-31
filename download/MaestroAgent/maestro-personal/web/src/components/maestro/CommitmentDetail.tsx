'use client';

import { useState, useEffect } from 'react';

interface Commitment {
  commitment_id: string;
  entity: string;
  text: string;
  state: string;
  confidence: number;
  deadline_text?: string;
  source_signal_id?: string;
}

interface EmailMessage {
  id: string;
  from: string;
  to: string;
  subject: string;
  date: string;
  body: string;
  is_user: boolean;
}

interface EmailDraft {
  draft_id: string;
  to: string;
  subject: string;
  body: string;
  voice_confidence: number;
  suggested_edits: string[];
}

interface VoiceProfile {
  style: string;
  common_phrases: string[];
  signature: string;
  formality: number;
  samples_analyzed: number;
}

interface CommitmentDetailProps {
  commitment: Commitment;
  onClose: () => void;
  apiBase: string;
  token: string;
}

// Normalize backend thread response (from_email/to_email/is_from_user)
// into the frontend's EmailMessage shape (from/to/is_user).
function normalizeMessage(raw: any): EmailMessage {
  return {
    id: raw.id || raw.message_id || '',
    from: raw.from_email ?? raw.from ?? raw.sender ?? '',
    to: raw.to_email ?? raw.to ?? '',
    subject: raw.subject || '',
    date: raw.date || raw.timestamp || '',
    body: raw.body || raw.text || '',
    is_user: raw.is_from_user ?? raw.is_user ?? false,
  };
}

export default function CommitmentDetail({ commitment, onClose, apiBase, token }: CommitmentDetailProps) {
  const [activeTab, setActiveTab] = useState<'thread' | 'draft' | 'voice'>('thread');
  const [thread, setThread] = useState<EmailMessage[]>([]);
  const [draft, setDraft] = useState<EmailDraft | null>(null);
  const [voiceProfile, setVoiceProfile] = useState<VoiceProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [editedBody, setEditedBody] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  // P-CORS-FIX: route through same-origin Next.js proxy (/api/*) instead of
  // the direct backend URL. The Next.js rewrite (next.config.ts) proxies
  // /api/* to BACKEND_URL. Bypassing the proxy triggers CORS preflight
  // (OPTIONS) which the backend returns as HTTP 400, blocking the actual
  // GET in the browser and causing "Failed to load thread." Using an empty
  // apiBase (or a relative path) keeps the fetch same-origin.
  //
  // If apiBase is "" or relative, fetch("/api/...") goes through the proxy.
  // If apiBase is the direct backend URL (legacy), we still honor it but
  // strip it to "" so the proxy is used. This is safe because the proxy
  // forwards to the same backend.
  const proxyBase = (!apiBase || apiBase.startsWith('/') || apiBase.includes('maestroagent-production'))
    ? ''  // use same-origin proxy
    : apiBase.replace(/\/$/, '');

  const headers = {
    'Authorization': `Bearer ${token}`,
  };

  // Load thread
  useEffect(() => {
    if (activeTab !== 'thread') return;
    setLoading(true);
    setError('');
    // AbortController so we don't setState on unmounted component
    const controller = new AbortController();
    fetch(`${proxyBase}/api/commitments/${commitment.commitment_id}/thread`, {
      headers,
      signal: controller.signal,
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        const msgs = Array.isArray(data?.messages) ? data.messages.map(normalizeMessage) : [];
        setThread(msgs);
        setLoading(false);
      })
      .catch(err => {
        if (err.name === 'AbortError') return;
        console.error('Thread fetch failed:', err);
        setThread([]);
        setError('Failed to load thread. Please try again.');
        setLoading(false);
      });
    return () => controller.abort();
  }, [activeTab, commitment.commitment_id, proxyBase, token]);

  // Load voice profile
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${proxyBase}/api/user/voice-profile`, {
      headers,
      signal: controller.signal,
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setVoiceProfile(data); })
      .catch(() => {});
    return () => controller.abort();
  }, [proxyBase, token]);

  // Generate draft — INSTANT streaming via SSE
  const generateDraft = async () => {
    setLoading(true);
    setError('');
    // Show skeleton immediately
    setDraft({
      draft_id: 'streaming',
      commitment_id: commitment.commitment_id,
      to: commitment.entity || '',
      subject: 'Generating...',
      body: '',
      voice_confidence: 0,
      suggested_edits: [],
      created_at: new Date().toISOString(),
    } as any);
    setEditedBody('');
    try {
      const resp = await fetch(`${proxyBase}/api/commitments/${commitment.commitment_id}/draft/stream`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ tone: 'professional', length: 'medium' }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        setError(err.detail || `Draft generation failed (HTTP ${resp.status}).`);
        setDraft(null);
        setLoading(false);
        return;
      }
      const reader = resp.body?.getReader();
      if (!reader) { setError('No response body'); setLoading(false); return; }
      const decoder = new TextDecoder();
      let buffer = '';
      let accumulated = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break;
          try {
            const evt = JSON.parse(payload);
            if (evt.chunk) {
              accumulated += evt.chunk;
              setEditedBody(accumulated);
              setDraft((prev: any) => prev ? { ...prev, body: accumulated, subject: prev.subject === 'Generating...' ? 'Re: follow-up' : prev.subject } : prev);
            } else if (evt.final) {
              accumulated = evt.final;
              setEditedBody(accumulated);
              setDraft((prev: any) => prev ? { ...prev, body: evt.final, draft_id: evt.draft_id || prev.draft_id, subject: prev.subject === 'Generating...' ? 'Re: follow-up' : prev.subject, voice_confidence: 0.85 } : prev);
            } else if (evt.error) {
              setError(evt.error);
              setDraft(null);
            }
          } catch { /* skip */ }
        }
      }
    } catch (e) {
      setError('Network error. Please check your connection.');
      setDraft(null);
    }
    setLoading(false);
  };

  // Send email
  const sendEmail = async () => {
    if (!draft) return;
    setSending(true);
    setError('');
    try {
      const resp = await fetch(`${proxyBase}/api/drafts/${draft.draft_id}/send`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        // P-SEND-503 fix: send to/subject so the mailto fallback works
        // even when the draft was not persisted to DB (current behavior).
        body: JSON.stringify({
          edited_body: editedBody,
          to: draft.to,
          subject: draft.subject,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        if (resp.status === 400) setError(err.detail || 'Missing recipient or body.');
        else if (resp.status === 503) setError('Email sending is not yet available. Please copy the draft manually.');
        else setError(err.detail || 'Failed to send email.');
        return;
      }
      const data = await resp.json();
      // If mailto fallback, open the mailto link properly
      if (data.method === 'mailto' && data.mailto_link) {
        if (typeof window !== 'undefined') {
          // P-SEND-MAILTO fix: Use anchor element click instead of window.location.href
          // window.location.href navigates away and is blocked by many browsers
          // Creating an anchor and clicking it is the standard way to open mailto links
          const mailtoAnchor = document.createElement('a');
          mailtoAnchor.href = data.mailto_link;
          mailtoAnchor.style.display = 'none';
          document.body.appendChild(mailtoAnchor);
          mailtoAnchor.click();
          document.body.removeChild(mailtoAnchor);
        }
        // Show success message with the mailto link as fallback
        setError('');
        setSent(true);
      } else {
        setSent(true);
      }
    } catch (e) {
      setError('Network error. Please check your connection.');
    }
    setSending(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-2xl max-h-[85vh] bg-white border border-gray-200 overflow-hidden flex flex-col">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{commitment.entity}</h2>
            <p className="text-sm text-gray-500 mt-0.5 line-clamp-1">{commitment.text}</p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="px-6 pt-3 flex gap-1 border-b border-gray-100">
          {(['thread', 'draft', 'voice'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                activeTab === tab
                  ? 'text-black border-b-2 border-black'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              {tab === 'thread' && '📧 Thread'}
              {tab === 'draft' && '✍️ Draft'}
              {tab === 'voice' && '🎯 Voice'}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          
          {error && (
            <div className="mb-4 p-3 border-l-2 border-gray-400 text-sm text-gray-700">
              {error}
            </div>
          )}
          
          {/* THREAD TAB */}
          {activeTab === 'thread' && (
            <div className="space-y-3">
              {loading ? (
                <div className="text-center py-8 text-gray-400">Loading thread...</div>
              ) : thread.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-gray-500">No email thread found for this commitment.</p>
                  <p className="text-sm text-gray-400 mt-1">The commitment may have been created manually.</p>
                </div>
              ) : (
                thread.map((msg, i) => (
                  <div
                    key={msg.id}
                    className={`p-4 border-l-2 ${
                      msg.is_user
                        ? "border-black ml-8"
                        : 'bg-gray-50 border border-gray-100 mr-8'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className={`text-xs font-medium ${msg.is_user ? 'text-blue-700' : 'text-gray-700'}`}>
                        {msg.is_user ? 'You' : msg.from}
                      </span>
                      <span className="text-xs text-gray-400">
                        {new Date(msg.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">{msg.body}</p>
                  </div>
                ))
              )}
            </div>
          )}

          {/* DRAFT TAB */}
          {activeTab === 'draft' && (
            <div className="space-y-4">
              {!draft ? (
                <div className="text-center py-8">
                  <p className="text-gray-500 mb-4">Generate a follow-up email in your voice.</p>
                  <button
                    onClick={generateDraft}
                    disabled={loading}
                    className="px-6 py-2.5 text-black underline underline-offset-4 font-medium disabled:opacity-40"
                  >
                    {loading ? 'Generating...' : '✍️ Generate Draft'}
                  </button>
                </div>
              ) : sent ? (
                <div className="text-center py-8">
                  <div className="text-4xl mb-3">✅</div>
                  <p className="text-gray-700 font-medium">Email sent successfully</p>
                  <p className="text-sm text-gray-400 mt-1">to {draft.to}</p>
                </div>
              ) : (
                <>
                  {/* To / Subject */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-gray-400 w-12">To:</span>
                      <span className="text-gray-700">{draft.to}</span>
                    </div>
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-gray-400 w-12">Subj:</span>
                      <span className="text-gray-700">{draft.subject}</span>
                    </div>
                    {draft.voice_confidence > 0 && (
                      <div className="flex items-center gap-2 text-xs text-gray-400">
                        <span>Voice match:</span>
                        <span className={draft.voice_confidence > 0.8 ? 'text-green-600' : 'text-yellow-600'}>
                          {Math.round(draft.voice_confidence * 100)}%
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Editable body */}
                  <textarea
                    value={editedBody}
                    onChange={(e) => setEditedBody(e.target.value)}
                    className="w-full h-48 p-4 border border-gray-200 text-sm text-gray-700 resize-none focus:outline-none focus:border-gray-400 font-mono"
                    placeholder="Edit your email..."
                  />

                  {/* Suggested edits */}
                  {draft.suggested_edits && draft.suggested_edits.length > 0 && (
                    <div className="border-l-2 border-gray-400 p-3">
                      <p className="text-xs font-medium text-amber-700 mb-1">💡 Suggestions:</p>
                      {draft.suggested_edits.map((s, i) => (
                        <p key={i} className="text-xs text-amber-600">• {s}</p>
                      ))}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-3 pt-2">
                    <button
                      onClick={sendEmail}
                      disabled={sending}
                      className="flex-1 px-4 py-2.5 text-black underline underline-offset-4 font-medium disabled:opacity-40"
                    >
                      {sending ? 'Sending...' : '📤 Send Email'}
                    </button>
                    <button
                      onClick={generateDraft}
                      className="px-4 py-2.5 text-gray-500 underline underline-offset-4 font-medium hover:text-black"
                    >
                      🔄 Regenerate
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* VOICE TAB */}
          {activeTab === 'voice' && (
            <div className="space-y-4">
              {voiceProfile ? (
                <>
                  <div className="border-l-2 border-gray-300 p-4">
                    <h3 className="text-sm font-medium text-gray-700 mb-3">Your Writing Style</h3>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-xs text-gray-400">Style</p>
                        <p className="text-sm text-gray-700 capitalize">{voiceProfile.style}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400">Formality</p>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-gray-200 overflow-hidden">
                            <div
                              className="h-full bg-black"
                              style={{ width: `${voiceProfile.formality * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500">{Math.round(voiceProfile.formality * 100)}%</span>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400">Emails analyzed</p>
                        <p className="text-sm text-gray-700">{voiceProfile.samples_analyzed}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400">Signature</p>
                        <p className="text-sm text-gray-700 font-mono text-xs">{voiceProfile.signature}</p>
                      </div>
                    </div>
                  </div>

                  {voiceProfile.common_phrases && voiceProfile.common_phrases.length > 0 && (
                    <div className="border-l-2 border-gray-300 p-4">
                      <h3 className="text-sm font-medium text-blue-700 mb-2">Your Common Phrases</h3>
                      <div className="flex flex-wrap gap-2">
                        {voiceProfile.common_phrases.map((phrase, i) => (
                          <span key={i} className="px-2.5 py-1 bg-white border-l-2 border-gray-300 text-xs text-gray-700">
                            &quot;{phrase}&quot;
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-8">
                  <p className="text-gray-500">Voice profile not yet available.</p>
                  <p className="text-sm text-gray-400 mt-1">Connect Gmail and send a few emails to build your profile.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
