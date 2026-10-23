import React, { useState, useEffect, useRef } from 'react';
import './index.css';

// In production builds, VITE_API_URL comes from .env.production (Railway API).
// In local/preview dev, empty string routes /api/* through Vite's proxy.
const API_URL = import.meta.env.VITE_API_URL || '';

const PENDING_PREVIEW_KEY = 'dreamdecode_pending_preview';
const SUBSCRIBER_EMAIL_KEY = 'dreamdecode_subscriber_email';
const HAS_REFLECTED_KEY = 'dreamdecode_has_reflected';

// Transparent sample showing both what's in the free preview and what unlocks
// in the full $4.99/mo report — without claiming one symbol always means one thing.
const SAMPLE = {
  dream: '“I was walking through a dark valley at night and felt afraid. Then I saw a warm light over the hills ahead, and I started walking toward it. I woke up feeling peaceful.”',
  freePreview: {
    summary: 'Moving from darkness toward warm light — especially with fear giving way to peace — may invite reflection on walking through an uncertain season while looking for God’s comfort and direction.',
    scripture: {
      reference: 'Psalm 23:4',
      text: 'Even though I walk through the darkest valley, I will fear no evil, for you are with me; your rod and your staff, they comfort me.'
    },
    question: 'Is there an uncertain “valley” season in your life right now where you are asking God for peace and steady guidance?'
  },
  fullThemes: [
    {
      title: 'A Theme to Reflect On — Presence in Uncertain Seasons',
      body: 'In Scripture, valleys can picture testing, grief, or waiting rather than defeat. Because you woke with peace rather than dread, the shift in emotion may be worth weighing in prayer alongside Psalm 23.'
    },
    {
      title: 'Another Angle to Weigh — Direction One Step at a Time',
      body: 'Light ahead on the hills may suggest clarity that grows as you walk rather than having every answer at once (Psalm 119:105). Consider whether you are waiting for certainty before taking a faithful small step.'
    }
  ],
  symbolExamples: [
    {
      symbol: 'Dark valley',
      meaning: 'In Scripture, a valley may suggest a season of testing or shadow (Psalm 23:4), a place of decision (Joel 3:14), or humble dependence where God restores strength (Psalm 84:5–7) — context and fruit matter more than any single fixed code.',
      scripture: 'Psalm 23:4; Psalm 84:5–7'
    },
    {
      symbol: 'Warm light ahead',
      meaning: 'Light often pictures God’s Word guiding the next step (Psalm 119:105), hope dawning after heaviness (Isaiah 9:2), or wisdom tested in the light of truth (Ephesians 5:8–10).',
      scripture: 'Psalm 119:105'
    }
  ],
  questions: [
    'Which part of the dream lingered most when you woke — the dark valley, the warm light ahead, or the shift from fear to peace?',
    'What would “walking toward the light” look like practically and faithfully for you this week?',
    'Who is a trusted pastor, counselor, or mature believer you could pray through this with?'
  ]
};

function App() {
  const [step, setStep] = useState('input');
  // No name or email up front: visitors get a free preview with just their dream.
  const [formData, setFormData] = useState({
    dream_text: '',
    emotion: '',
    colors: '',
    symbols: '',
    referral_code: ''
  });

  const [dreamId, setDreamId] = useState(null);
  const [referralCode, setReferralCode] = useState('');
  const [teaser, setTeaser] = useState('');
  const [preview, setPreview] = useState(null);
  const [trialDays, setTrialDays] = useState(0);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [infoNotice, setInfoNotice] = useState(null);

  // Email is collected only at subscribe time (receipt + report delivery).
  const [subscribeEmail, setSubscribeEmail] = useState(() => {
    try {
      return localStorage.getItem(SUBSCRIBER_EMAIL_KEY) || '';
    } catch {
      return '';
    }
  });
  const [hasSavedSubscriberEmail, setHasSavedSubscriberEmail] = useState(() => {
    try {
      return Boolean(localStorage.getItem(SUBSCRIBER_EMAIL_KEY));
    } catch {
      return false;
    }
  });

  const [giftMode, setGiftMode] = useState(false);
  const [giftInfo, setGiftInfo] = useState(null);

  const dreamTextareaRef = useRef(null);
  const dreamFormRef = useRef(null);

  const feelings = ['Peace', 'Fear', 'Urgency', 'Joy', 'Confusion', 'Awe', 'Hope', 'Grief', 'Unease', 'Love'];

  // Handle URL parameters & initial config check
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const dId = params.get('dream_id');
    const sessionId = params.get('session_id');
    const cancelled = params.get('cancelled');

    if (code) {
      setGiftMode(true);
      setFormData(prev => ({ ...prev, referral_code: code }));
      fetchGiftInfo(code);
    }

    if (dId) {
      setDreamId(dId);
    }

    // Returning from cancelled Stripe Checkout — restore their preview & reassure no charge
    if (cancelled) {
      try {
        const raw = sessionStorage.getItem(PENDING_PREVIEW_KEY);
        if (raw) {
          const saved = JSON.parse(raw);
          if (saved.dreamId) setDreamId(saved.dreamId);
          if (saved.referralCode) setReferralCode(saved.referralCode);
          if (saved.teaser) setTeaser(saved.teaser);
          if (saved.preview) setPreview(saved.preview);
          if (typeof saved.trialDays === 'number') setTrialDays(saved.trialDays);
          setStep('teaser');
        }
      } catch (e) {
        console.error('Could not restore pending preview:', e);
      }
      setInfoNotice('Checkout cancelled — you were not charged. Your free preview is still here whenever you’re ready.');
      window.history.replaceState({}, '', window.location.pathname);
      return;
    }

    // Returning from Stripe Checkout — verify subscription and unlock the report
    if (sessionId && dId) {
      verifySubscription(sessionId, dId);
    } else if (dId) {
      // Returning visitor with a dream link — unlock if already paid
      tryAutoReveal(dId);
    }

    // Light check for trial_days so hero pricing matches backend config
    fetch(`${API_URL}/health`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (data && typeof data.trial_days === 'number') {
          setTrialDays(data.trial_days);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const focusDreamForm = () => {
    if (dreamFormRef.current) {
      dreamFormRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    setTimeout(() => {
      if (dreamTextareaRef.current) {
        dreamTextareaRef.current.focus({ preventScroll: true });
      }
    }, 350);
  };

  const rememberSubscriberEmail = (email) => {
    if (!email) return;
    try {
      localStorage.setItem(SUBSCRIBER_EMAIL_KEY, email.trim());
      setHasSavedSubscriberEmail(true);
    } catch {
      // ignore storage errors in private browsing
    }
  };

  const verifySubscription = async (sessionId, dId) => {
    setStep('verifying');
    setError(null);
    setInfoNotice(null);
    try {
      const res = await fetch(`${API_URL}/api/verify-payment`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ session_id: sessionId, dream_id: dId })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Verification failed');
      if (data.status === 'paid' && data.report) {
        if (subscribeEmail) rememberSubscriberEmail(subscribeEmail);
        try {
          sessionStorage.removeItem(PENDING_PREVIEW_KEY);
        } catch {}
        setReport(data.report);
        setStep('reveal');
        window.history.replaceState({}, '', window.location.pathname);
      } else {
        setError('Subscription not confirmed yet — if you just subscribed, wait a few seconds and refresh.');
        setStep('input');
      }
    } catch (err) {
      console.error('Verify error:', err);
      setError(err.message || 'Error confirming your subscription');
      setStep('input');
    }
  };

  const tryAutoReveal = async (dId) => {
    try {
      const res = await fetch(`${API_URL}/api/get-full-report`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ dream_id: dId })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.report) {
          setReport(data.report);
          setStep('reveal');
        }
      }
    } catch (e) {
      console.error('Auto-reveal skipped:', e);
    }
  };

  const fetchGiftInfo = async (code) => {
    try {
      const res = await fetch(`${API_URL}/api/referral/${code}`);
      if (!res.ok) throw new Error('Invalid referral code');
      const data = await res.json();
      setGiftInfo(data);
    } catch (err) {
      console.error('Gift info error:', err);
      setError('Invalid blessing code');
    }
  };

  const handleSubmitTeaser = async (e) => {
    e.preventDefault();
    if (!formData.dream_text.trim()) {
      setError('Please describe your dream first — even a few sentences is enough.');
      return;
    }
    setLoading(true);
    setError(null);
    setInfoNotice(null);

    let isReturning = false;
    try {
      isReturning = localStorage.getItem(HAS_REFLECTED_KEY) === '1';
    } catch {}

    try {
      const res = await fetch(`${API_URL}/api/analyze-teaser`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({
          ...formData,
          is_returning: isReturning
        })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to prepare reflection preview');
      }

      const data = await res.json();

      if (!data.dream_id) {
        throw new Error('No dream ID received from server');
      }

      try {
        localStorage.setItem(HAS_REFLECTED_KEY, '1');
      } catch {}

      setDreamId(data.dream_id);
      setReferralCode(data.referral_code);
      setTeaser(data.teaser);
      setPreview(data.preview || null);
      if (typeof data.trial_days === 'number') {
        setTrialDays(data.trial_days);
      }
      setStep('teaser');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      console.error('Preview error:', err);
      setError(err.message || 'Error preparing your reflection preview');
    } finally {
      setLoading(false);
    }
  };

  const handleSubscribe = async () => {
    if (!dreamId) {
      setError('Dream ID is missing. Please refresh and try again.');
      return;
    }
    const cleanEmail = subscribeEmail.trim();
    if (!cleanEmail || !cleanEmail.includes('@')) {
      setError('Please enter your email — it’s needed for your receipt and to deliver your report.');
      return;
    }

    setLoading(true);
    setError(null);
    setInfoNotice(null);

    try {
      const res = await fetch(`${API_URL}/api/create-checkout-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ dream_id: dreamId, email: cleanEmail })
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || `Checkout failed (${res.status})`);
      }

      if (data.already_subscribed) {
        // Active subscriber — unlock this dream without charging again
        rememberSubscriberEmail(cleanEmail);
        await handleReveal();
        return;
      }

      if (data.url) {
        try {
          sessionStorage.setItem(
            PENDING_PREVIEW_KEY,
            JSON.stringify({ dreamId, referralCode, teaser, preview, trialDays })
          );
          localStorage.setItem(SUBSCRIBER_EMAIL_KEY, cleanEmail);
        } catch {}
        window.location.href = data.url;
      } else {
        throw new Error('No checkout URL received');
      }
    } catch (err) {
      console.error('Subscribe error:', err);
      setError(err.message || 'Error starting checkout');
      setLoading(false);
    }
  };

  const handleReveal = async () => {
    if (!dreamId) {
      setError('Dream ID is missing. Please refresh and try again.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/get-full-report`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ dream_id: dreamId })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || `Report failed (${res.status})`);
      }

      const data = await res.json();

      if (data.report) {
        setReport(data.report);
        setStep('reveal');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        throw new Error('No report received');
      }
    } catch (err) {
      console.error('Reveal error:', err);
      setError(err.message || 'Error generating your reflection report');
    } finally {
      setLoading(false);
    }
  };

  const manageSubscription = async () => {
    const email = window.prompt('Enter the email you subscribed with:', subscribeEmail || '');
    if (!email) return;
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/create-portal-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ email: email.trim() })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Could not open billing portal');
      window.location.href = data.url;
    } catch (err) {
      console.error('Portal error:', err);
      setError(err.message || 'Error opening billing portal');
    }
  };

  const downloadPDF = () => {
    if (!dreamId) {
      setError('Dream ID missing for download');
      return;
    }
    window.open(`${API_URL}/api/download-pdf/${dreamId}`);
  };

  const startOver = () => {
    setStep('input');
    setError(null);
    setInfoNotice(null);
    setReport(null);
    setTeaser('');
    setPreview(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const shareLink = `${window.location.origin}/gift?code=${referralCode}`;

  const copyToClipboard = () => {
    navigator.clipboard.writeText(shareLink).then(() => {
      alert('Blessing link copied! Share a free reflection preview with someone who would appreciate it.');
    }).catch(err => {
      console.error('Copy failed:', err);
      alert('Failed to copy link');
    });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-amber-50 font-cormorant selection:bg-amber-500/30">
      {/* Header */}
      <div className="border-b border-amber-900/30 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-2xl mx-auto px-6 py-4 flex justify-between items-center gap-3">
          <button
            type="button"
            onClick={startOver}
            className="text-2xl font-bold text-amber-400 font-cinzel tracking-wider text-left hover:text-amber-300 transition-colors"
          >
            DreamDecode
          </button>
          <div className="text-xs text-amber-200/70 tracking-wider uppercase text-right">
            Free preview · Full report $4.99/mo
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-6 py-10 sm:py-12">
        {error && (
          <div className="bg-red-900/30 border border-red-600/50 text-red-200 p-4 rounded-lg mb-6 text-center">
            <p className="font-bold">Notice</p>
            <p className="text-sm">{error}</p>
            <button
              onClick={() => setError(null)}
              className="mt-2 text-xs underline hover:text-red-100"
            >
              Dismiss
            </button>
          </div>
        )}

        {infoNotice && (
          <div className="bg-amber-950/40 border border-amber-600/40 text-amber-100 p-4 rounded-lg mb-6 text-center">
            <p className="text-sm">{infoNotice}</p>
            <button
              onClick={() => setInfoNotice(null)}
              className="mt-2 text-xs text-amber-300 underline hover:text-amber-200"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Gift Mode Banner */}
        {giftMode && giftInfo && (
          <div className="bg-gradient-to-r from-amber-900/30 to-amber-600/20 border border-amber-500/50 p-6 rounded-lg mb-8 text-center">
            <div className="text-3xl mb-2">🕊️</div>
            <h3 className="text-amber-400 font-cinzel text-xl mb-2">
              A Blessing from {giftInfo.referrer_name || 'A Friend'}
            </h3>
            <p className="text-amber-200/80 text-sm mb-4">
              "{giftInfo.message}"
            </p>
            <div className="bg-slate-950/50 inline-block px-4 py-2 rounded border border-amber-600/30 text-sm">
              <span className="text-amber-400 font-semibold">Free preview included</span>
              <span className="text-amber-200/60 ml-2">· Full report & symbol guide $4.99/mo</span>
            </div>
          </div>
        )}

        {/* Verifying Step */}
        {step === 'verifying' && (
          <div className="text-center space-y-6 py-16 animate-fade-in">
            <div className="text-5xl animate-pulse">🕊️</div>
            <h2 className="text-2xl text-amber-100 font-cinzel">Confirming Your Subscription...</h2>
            <p className="text-amber-200/60 italic">Preparing your full reflection report.</p>
          </div>
        )}

        {/* Input Step */}
        {step === 'input' && (
          <div className="space-y-8 animate-fade-in">
            {/* First-screen hero */}
            <div className="text-center space-y-4">
              <h2 className="text-3xl sm:text-4xl text-amber-100 font-cinzel leading-snug">
                Reflect on your dreams through a biblical lens
              </h2>
              <p className="text-amber-200/85 text-lg max-w-xl mx-auto leading-relaxed">
                DreamDecode helps you explore <span className="text-amber-100 font-semibold">possible themes, Scripture references, and questions</span> for personal reflection.
              </p>
              <p className="text-amber-200/65 text-sm italic max-w-xl mx-auto leading-relaxed">
                Reflections are prompts for discernment — not a guaranteed message from God, and not a substitute for Scripture, prayer, or pastoral counsel.
              </p>

              {/* Paired first-screen CTAs */}
              <div className="flex flex-col sm:flex-row justify-center items-stretch sm:items-center gap-3 pt-2 max-w-md mx-auto">
                <button
                  type="button"
                  onClick={focusDreamForm}
                  className="flex-1 bg-gradient-to-r from-amber-700 to-amber-600 hover:from-amber-600 hover:to-amber-500 text-white font-bold py-3 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all font-cinzel tracking-wide text-sm"
                >
                  Explore a dream
                </button>
                <button
                  type="button"
                  onClick={() => { setStep('sample'); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                  className="flex-1 bg-slate-900/70 hover:bg-slate-800/80 text-amber-300 font-semibold py-3 px-6 rounded-lg border border-amber-700/40 transition-all font-cinzel tracking-wide text-sm"
                >
                  See a sample
                </button>
              </div>

              <p className="text-sm text-amber-200/75 pt-1">
                {trialDays > 0 ? (
                  <>
                    <span className="text-amber-400 font-semibold">Free preview</span> · Full report and symbol guide: <span className="text-amber-400 font-semibold">{trialDays}-day free trial, then $4.99/month</span>. Renews monthly; cancel anytime.
                  </>
                ) : (
                  <>
                    <span className="text-amber-400 font-semibold">Free preview</span> · Full report and symbol guide: <span className="text-amber-400 font-semibold">$4.99/month</span>. Renews monthly; cancel anytime.
                  </>
                )}
              </p>

              <div className="pt-2 border-t border-amber-900/20 max-w-lg mx-auto">
                <p className="text-amber-200/70 italic text-base">
                  "In the last days, God says, I will pour out my Spirit on all people..."
                </p>
                <p className="text-xs text-amber-600 font-cinzel mt-0.5">— Acts 2:17</p>
                <p className="text-xs text-amber-200/50 italic mt-1.5 leading-relaxed">
                  Scripture shows God has spoken through dreams, yet no app can speak for Him. Use these reflections to pray and search the Word — never as a definitive verdict.
                </p>
              </div>
            </div>

            <form
              ref={dreamFormRef}
              id="dream-form"
              onSubmit={handleSubmitTeaser}
              className="space-y-6 bg-slate-900/30 p-6 sm:p-8 rounded-lg border border-amber-900/20 shadow-2xl shadow-black/50 scroll-mt-24"
            >
              <div>
                <label htmlFor="dream-textarea" className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">
                  Describe your dream
                </label>
                <textarea
                  id="dream-textarea"
                  ref={dreamTextareaRef}
                  required
                  rows={4}
                  className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none transition-colors placeholder:text-amber-900/50"
                  value={formData.dream_text}
                  onChange={(e) => setFormData({ ...formData, dream_text: e.target.value })}
                  placeholder="What happened in your dream? Write it in your own words — even a few sentences is enough..."
                />
                <p className="text-xs text-amber-200/55 mt-2 leading-relaxed">
                  🔒 <span className="font-semibold text-amber-200/75">Privacy:</span> your dream is sent securely to generate your reflection preview and is never sold or used for ads. No name or email is needed for the free preview. Please avoid including full names, addresses, or other sensitive personal details.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="dream-feeling" className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">
                    What feeling stood out most? <span className="text-amber-200/40">(optional)</span>
                  </label>
                  <select
                    id="dream-feeling"
                    className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none"
                    value={formData.emotion}
                    onChange={(e) => setFormData({ ...formData, emotion: e.target.value })}
                  >
                    <option value="">Prefer not to say</option>
                    {feelings.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="dream-colors" className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">
                    Colors you remember <span className="text-amber-200/40">(optional)</span>
                  </label>
                  <input
                    id="dream-colors"
                    type="text"
                    className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none placeholder:text-amber-900/50"
                    value={formData.colors}
                    onChange={(e) => setFormData({ ...formData, colors: e.target.value })}
                    placeholder="Gold, deep blue, white..."
                  />
                </div>
              </div>

              <div>
                <label htmlFor="dream-symbols" className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">
                  Symbols or objects that stood out <span className="text-amber-200/40">(optional)</span>
                </label>
                <input
                  id="dream-symbols"
                  type="text"
                  className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none placeholder:text-amber-900/50"
                  value={formData.symbols}
                  onChange={(e) => setFormData({ ...formData, symbols: e.target.value })}
                  placeholder="River, ladder, keys, dove..."
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-gradient-to-r from-amber-700 to-amber-600 hover:from-amber-600 hover:to-amber-500 text-white font-bold py-4 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all transform hover:scale-[1.01] disabled:opacity-50 disabled:cursor-not-allowed font-cinzel tracking-wider"
              >
                {loading ? 'Preparing your free preview...' : 'Explore possible themes — free preview'}
              </button>

              <p className="text-center text-xs text-amber-200/45">
                Free preview · No email or card required · Full report & symbol guide $4.99/month (cancel anytime)
              </p>
            </form>
          </div>
        )}

        {/* Sample Step */}
        {step === 'sample' && (
          <div className="space-y-8 animate-fade-in">
            <div className="text-center space-y-3">
              <h2 className="text-3xl text-amber-100 font-cinzel">Sample dream reflection</h2>
              <p className="text-amber-200/75">
                See both what’s included in your <span className="text-amber-300 font-semibold">free preview</span> and what unlocks in the <span className="text-amber-300 font-semibold">$4.99/month full report</span>.
              </p>
            </div>

            <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40">
              <h3 className="text-amber-400 font-cinzel mb-2">💭 Sample dream</h3>
              <p className="text-amber-100/90 italic leading-relaxed">{SAMPLE.dream}</p>
            </div>

            {/* Free preview sample */}
            <div className="bg-slate-900/60 p-6 rounded-lg border border-amber-600/40 space-y-4">
              <div className="flex items-center justify-between border-b border-amber-900/30 pb-2">
                <h3 className="text-amber-400 font-cinzel text-sm uppercase tracking-wider">Included in your Free Preview</h3>
                <span className="text-xs bg-amber-900/40 text-amber-300 px-2.5 py-0.5 rounded font-cinzel">$0 · No email</span>
              </div>
              <p className="text-amber-100/95 italic text-lg leading-relaxed">
                “{SAMPLE.freePreview.summary}”
              </p>
              <div className="bg-slate-950/60 p-4 rounded border-l-4 border-amber-600">
                <p className="text-xs uppercase tracking-wider text-amber-400 font-cinzel mb-1">Scripture to read in context</p>
                <p className="text-amber-100 italic">“{SAMPLE.freePreview.scripture.text}”</p>
                <p className="text-amber-500 font-cinzel text-xs font-bold mt-1">{SAMPLE.freePreview.scripture.reference}</p>
              </div>
              <div className="bg-slate-950/60 p-4 rounded border-l-4 border-amber-700/70">
                <p className="text-xs uppercase tracking-wider text-amber-400 font-cinzel mb-1">Question for reflection</p>
                <p className="text-amber-100/90">{SAMPLE.freePreview.question}</p>
              </div>
            </div>

            {/* Paid report sample */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-amber-400 font-cinzel text-sm uppercase tracking-wider">Added in the Full Report & Symbol Guide</h3>
                <span className="text-xs bg-slate-900 text-amber-300/90 border border-amber-800/40 px-2.5 py-0.5 rounded font-cinzel">$4.99/mo · Cancel anytime</span>
              </div>

              {SAMPLE.fullThemes.map((t, idx) => (
                <div key={idx} className="bg-slate-900/30 p-6 rounded-lg border-l-4 border-amber-600 shadow-lg">
                  <h4 className="text-lg text-amber-300 font-cinzel mb-2">{t.title}</h4>
                  <p className="text-amber-100/90 leading-relaxed">{t.body}</p>
                </div>
              ))}

              <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40 space-y-4">
                <div>
                  <h4 className="text-amber-400 font-cinzel">🔍 Dream Symbol Dictionary (context-sensitive, never fixed codes)</h4>
                  <p className="text-xs text-amber-200/55 italic mt-1">
                    In Scripture, the same image can carry different meanings in different contexts:
                  </p>
                </div>
                {SAMPLE.symbolExamples.map((s, idx) => (
                  <div key={idx} className="border-l-4 border-amber-700 pl-4 space-y-1">
                    <div className="text-amber-300 font-cinzel">{s.symbol}</div>
                    <p className="text-amber-100/90 text-sm leading-relaxed">{s.meaning}</p>
                    <p className="text-amber-600 font-bold text-xs font-cinzel">{s.scripture}</p>
                  </div>
                ))}
              </div>

              <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40">
                <h4 className="text-amber-400 font-cinzel mb-3">🤔 Personal reflection questions</h4>
                <ol className="list-decimal list-inside space-y-2 text-amber-100/90">
                  {SAMPLE.questions.map((q, idx) => <li key={idx}>{q}</li>)}
                </ol>
              </div>
            </div>

            <div className="bg-amber-950/20 p-5 rounded-lg border border-amber-700/30 text-center">
              <p className="text-amber-200/70 text-sm italic">
                A sample, not a formula. Every reflection is a starting point for prayer and Scripture study — never a final verdict. “Test everything; hold fast what is good.” — 1 Thessalonians 5:21
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => { setStep('input'); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                className="flex-1 bg-gradient-to-r from-amber-700 to-amber-600 hover:from-amber-600 hover:to-amber-500 text-white font-bold py-4 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all font-cinzel tracking-wider"
              >
                Try a free preview with your dream
              </button>
            </div>
          </div>
        )}

        {/* Teaser / Free Preview Step */}
        {step === 'teaser' && (
          <div className="space-y-8 text-center animate-fade-in">
            <div className="bg-slate-900/50 p-6 sm:p-8 rounded-lg border border-amber-600/30 shadow-2xl shadow-amber-900/10 relative overflow-hidden text-left space-y-5">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-amber-600 to-transparent"></div>
              <div className="text-amber-500 text-sm tracking-widest uppercase font-cinzel text-center">
                Your free reflection preview
              </div>
              <p className="text-xl sm:text-2xl text-amber-100 italic leading-relaxed font-cormorant text-center">
                “{preview?.summary || teaser}”
              </p>

              {preview?.scripture?.reference && (
                <div className="bg-slate-950/60 p-4 rounded border-l-4 border-amber-600">
                  <div className="text-xs uppercase tracking-wider text-amber-400 font-cinzel mb-1">
                    Scripture to read in context
                  </div>
                  {preview.scripture.text && (
                    <p className="text-amber-100 italic leading-relaxed">“{preview.scripture.text}”</p>
                  )}
                  <p className="text-amber-500 font-cinzel text-xs font-bold mt-1">{preview.scripture.reference}</p>
                </div>
              )}

              {preview?.reflection_question && (
                <div className="bg-slate-950/60 p-4 rounded border-l-4 border-amber-700/70">
                  <div className="text-xs uppercase tracking-wider text-amber-400 font-cinzel mb-1">
                    Question for personal reflection
                  </div>
                  <p className="text-amber-100/90 leading-relaxed">{preview.reflection_question}</p>
                </div>
              )}
            </div>

            <div className="bg-amber-950/20 p-5 rounded-lg border border-amber-700/30 text-left">
              <p className="text-amber-200/75 text-sm leading-relaxed">
                <span className="font-semibold text-amber-300">A note on discernment:</span> this preview offers <span className="font-semibold">possible themes to weigh prayerfully</span> — not a definitive meaning from God. Symbols in Scripture carry different associations in different contexts. Test everything against God’s Word, prayer, and pastoral counsel (1 Thessalonians 5:21).
              </p>
            </div>

            <div className="space-y-5">
              <p className="text-amber-200/80 text-lg">
                Want to explore every symbol, Scripture parallel, and reflection question?
              </p>

              <div className="bg-slate-900/30 p-6 rounded-lg border border-amber-900/20 space-y-3 text-left">
                <h3 className="text-amber-400 font-cinzel text-sm uppercase tracking-wider mb-2">
                  Included in the Full Report & Symbol Guide
                </h3>
                <div className="flex justify-between text-sm text-amber-200/70 items-center">
                  <span className="flex items-center gap-2">✨ Multi-angle biblical theme reflections</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/70 items-center">
                  <span className="flex items-center gap-2">🤔 Guided personal reflection questions</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/70 items-center">
                  <span className="flex items-center gap-2">🔍 Dream Symbol Dictionary (every symbol, color & number)</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/70 items-center">
                  <span className="flex items-center gap-2">🕊️ Prayerful source discernment guidance</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/70 items-center">
                  <span className="flex items-center gap-2">🌾 Joseph & Daniel biblical parallels</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/70 items-center">
                  <span className="flex items-center gap-2">🙏 Personalized prayer + downloadable & emailed PDF</span>
                  <span className="text-amber-400">✓</span>
                </div>
              </div>

              {/* Billing clarity — the full picture before anyone pays */}
              <div className="bg-slate-900/60 p-6 rounded-lg border border-amber-700/40 text-left space-y-3">
                <h3 className="text-amber-400 font-cinzel text-center mb-1">Before you subscribe — the full picture</h3>
                <p className="text-sm text-amber-200/75">
                  <span className="font-semibold text-amber-300">What’s free?</span> Your preview above (initial theme, Scripture reference, and reflection question) — always $0, no card or email required.
                </p>
                <p className="text-sm text-amber-200/75">
                  <span className="font-semibold text-amber-300">What requires payment?</span> Full reflection reports, the Dream Symbol Dictionary, and PDF + email delivery — <span className="font-semibold text-amber-200">$4.99/month</span> for unlimited dreams while subscribed.
                </p>
                <p className="text-sm text-amber-200/75">
                  <span className="font-semibold text-amber-300">When am I charged?</span>{' '}
                  {trialDays > 0
                    ? `$0 today — your first $4.99 charge happens on day ${trialDays + 1} unless you cancel beforehand.`
                    : '$4.99 today only after you confirm payment on Stripe’s checkout page, then $4.99 monthly. Nothing is charged before that step.'}
                </p>
                <p className="text-sm text-amber-200/75">
                  <span className="font-semibold text-amber-300">How do I cancel?</span> Anytime in two clicks via “Manage or cancel your subscription” in the footer — no phone calls or emails needed.
                </p>
              </div>

              <div className="bg-slate-900/40 p-6 rounded-lg border border-amber-800/30 pt-5">
                {trialDays > 0 ? (
                  <>
                    <div className="text-3xl font-cinzel text-amber-400 mb-1">{trialDays} Days FREE</div>
                    <p className="text-sm text-amber-200/75 mb-4">then <span className="font-semibold text-amber-200">$4.99/month</span> · Renews monthly · Cancel anytime</p>
                  </>
                ) : (
                  <>
                    <div className="text-3xl font-cinzel text-amber-400 mb-1">$4.99<span className="text-lg text-amber-200/70">/month</span></div>
                    <p className="text-sm text-amber-200/70 mb-4">Renews monthly · Unlimited full reports & symbol guides · Cancel anytime</p>
                  </>
                )}

                {!dreamId && (
                  <div className="mb-4 p-2 bg-red-900/20 text-red-400 text-xs rounded">
                    ⚠️ Dream ID missing. Please return to the form and submit your dream again.
                  </div>
                )}

                <div className="text-left mb-4">
                  <label htmlFor="subscribe-email" className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">
                    Email for your report & receipt
                  </label>
                  <input
                    id="subscribe-email"
                    type="email"
                    className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none placeholder:text-amber-900/50"
                    value={subscribeEmail}
                    onChange={(e) => setSubscribeEmail(e.target.value)}
                    placeholder="your@email.com"
                  />
                  <p className="text-xs text-amber-200/55 mt-2">
                    Asked only when unlocking your full report — used for your Stripe receipt, PDF report delivery, and managing your plan. Never sold or used for ads.
                  </p>
                  <p className="text-xs text-amber-300/75 mt-1.5">
                    {hasSavedSubscriberEmail
                      ? 'Welcome back — if your subscription is active on this email, clicking below unlocks this report immediately with no extra charge.'
                      : 'Already subscribed? Enter the email on your plan and click below — active subscribers unlock immediately with no new charge.'}
                  </p>
                </div>

                <button
                  onClick={handleSubscribe}
                  disabled={loading || !dreamId}
                  className="w-full bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-white font-bold py-4 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all transform hover:scale-[1.01] disabled:opacity-50 disabled:cursor-not-allowed font-cinzel tracking-wider text-base sm:text-lg"
                >
                  {loading
                    ? 'Checking plan & opening secure checkout...'
                    : hasSavedSubscriberEmail
                      ? 'Continue — Unlock Report (or $4.99/mo)'
                      : trialDays > 0
                        ? `Start ${trialDays}-Day Free Trial (then $4.99/mo)`
                        : 'Subscribe for Full Report — $4.99/month'}
                </button>

                <p className="text-xs text-amber-200/45 mt-3">
                  {trialDays > 0
                    ? `Secure Stripe checkout • Card required • $0 charged today • $4.99/mo starting day ${trialDays + 1} unless cancelled`
                    : 'Secure checkout by Stripe • Charged $4.99 today, then monthly • Cancel anytime • Report & PDF delivered immediately'}
                </p>

                <button
                  onClick={startOver}
                  className="mt-4 text-amber-200/55 text-sm underline hover:text-amber-200/85 transition-colors"
                >
                  ← Reflect on a different dream (free preview)
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Reveal Step */}
        {step === 'reveal' && report && (
          <div className="space-y-8 animate-fade-in">
            <div className="text-center">
              <h2 className="text-3xl text-amber-100 font-cinzel mb-2">Your reflection report</h2>
              <p className="text-amber-200/60 font-cinzel">Hebrew Year {new Date().getFullYear() + 3760}</p>
            </div>

            {report.discernment_note && (
              <div className="bg-amber-950/20 p-5 rounded-lg border border-amber-700/30">
                <p className="text-amber-200/75 text-sm leading-relaxed">
                  <span className="font-semibold text-amber-300">A note on discernment: </span>{report.discernment_note}
                </p>
              </div>
            )}

            <div className="space-y-6">
              {report.interpretations?.map((interp, idx) => (
                <div key={idx} className="bg-slate-900/30 p-6 rounded-lg border-l-4 border-amber-600 shadow-lg">
                  <h3 className="text-xl text-amber-400 font-cinzel mb-3">{interp.title}</h3>
                  <p className="text-amber-100/90 leading-relaxed text-lg">{interp.meaning}</p>
                </div>
              ))}

              {/* Personal Reflection Questions */}
              {report.reflection_questions?.length > 0 && (
                <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40">
                  <h3 className="text-lg text-amber-400 font-cinzel mb-3">🤔 Questions for Personal Reflection</h3>
                  <ol className="list-decimal list-inside space-y-2.5 text-amber-100/90 leading-relaxed">
                    {report.reflection_questions.map((q, idx) => (
                      <li key={idx}>{q}</li>
                    ))}
                  </ol>
                </div>
              )}

              {/* Dream Symbol Dictionary */}
              {report.symbol_dictionary?.length > 0 && (
                <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40">
                  <h3 className="text-lg text-amber-400 font-cinzel text-center mb-1">Dream Symbol Dictionary</h3>
                  <p className="text-amber-200/50 text-xs text-center mb-5 italic">
                    Possible meanings to weigh through the language of Scripture
                  </p>
                  <div className="space-y-4">
                    {report.symbol_dictionary.map((entry, idx) => (
                      <div key={idx} className="border-l-4 border-amber-700 pl-4 py-1 space-y-1">
                        <h4 className="text-amber-300 font-cinzel capitalize">{entry.symbol}</h4>
                        <p className="text-amber-100/90 leading-relaxed">{entry.biblical_meaning}</p>
                        <p className="text-amber-600 font-bold text-sm font-cinzel">{entry.scripture}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Source Discernment */}
              {report.source_discernment && (
                <div className="bg-amber-950/20 p-6 rounded-lg border border-amber-700/30 space-y-3">
                  <h3 className="text-lg text-amber-400 font-cinzel text-center">🕊️ Source Discernment</h3>
                  <p className="text-center">
                    <span className="text-amber-200/60 text-sm">For prayerful discernment — this dream may flow from: </span>
                    <span className="text-amber-300 font-bold font-cinzel">{report.source_discernment.source}</span>
                  </p>
                  <p className="text-amber-100/90 leading-relaxed">{report.source_discernment.explanation}</p>
                  <p className="text-amber-200/70 italic border-t border-amber-900/30 pt-3">{report.source_discernment.counsel}</p>
                </div>
              )}

              <div className="bg-amber-950/30 p-6 rounded-lg border border-amber-600/30 text-center">
                <h3 className="text-lg text-amber-400 font-cinzel mb-4">Scriptural Anchor</h3>
                <p className="text-amber-100 italic text-lg mb-2">"{report.scripture?.text}"</p>
                <p className="text-amber-600 font-bold font-cinzel">{report.scripture?.reference}</p>
                <p className="text-amber-200/60 text-sm mt-2">{report.scripture?.context}</p>
              </div>

              {/* Joseph & Daniel Anchor */}
              {report.joseph_daniel_anchor && (
                <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40 space-y-6">
                  <h3 className="text-lg text-amber-400 font-cinzel text-center">The Joseph & Daniel Anchor</h3>

                  {report.joseph_daniel_anchor.joseph && (
                    <div className="border-l-4 border-amber-700 pl-4 space-y-2">
                      <h4 className="text-amber-400 font-cinzel">🌾 Joseph — The Interpreter of Pharaoh's Dreams</h4>
                      <p className="text-amber-600 font-bold text-sm font-cinzel">{report.joseph_daniel_anchor.joseph.reference}</p>
                      <p className="text-amber-100/90 leading-relaxed">{report.joseph_daniel_anchor.joseph.connection}</p>
                      <p className="text-amber-200/70 italic">{report.joseph_daniel_anchor.joseph.insight}</p>
                    </div>
                  )}

                  {report.joseph_daniel_anchor.daniel && (
                    <div className="border-l-4 border-amber-700 pl-4 space-y-2">
                      <h4 className="text-amber-400 font-cinzel">🦁 Daniel — The Interpreter of Visions</h4>
                      <p className="text-amber-600 font-bold text-sm font-cinzel">{report.joseph_daniel_anchor.daniel.reference}</p>
                      <p className="text-amber-100/90 leading-relaxed">{report.joseph_daniel_anchor.daniel.connection}</p>
                      <p className="text-amber-200/70 italic">{report.joseph_daniel_anchor.daniel.insight}</p>
                    </div>
                  )}
                </div>
              )}

              <div className="bg-slate-900 p-8 rounded-lg border border-amber-600/30 text-center">
                <h3 className="text-xl text-amber-400 font-cinzel mb-4 border-b border-amber-600/30 pb-2 inline-block">A Prayer for Your Dream</h3>
                <p className="text-amber-100 italic text-lg leading-relaxed">{report.prayer}</p>
              </div>

              <div className="bg-amber-950/20 p-5 rounded-lg border border-amber-700/30 text-center">
                <p className="text-amber-200/75 text-sm italic">
                  Hold these reflections lightly and prayerfully. If this dream troubles you — especially around fear, grief, or a major life decision — please share it with your pastor, a trusted counselor, or a mature believer.
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-4">
                <button
                  onClick={downloadPDF}
                  disabled={!dreamId}
                  className="flex-1 bg-gradient-to-r from-slate-800 to-slate-700 hover:from-slate-700 hover:to-slate-600 text-amber-400 font-bold py-4 px-6 rounded-lg border border-amber-600/30 transition-all font-cinzel disabled:opacity-50"
                >
                  Download PDF
                </button>
                <button
                  onClick={copyToClipboard}
                  disabled={!referralCode}
                  className="flex-1 bg-gradient-to-r from-amber-800 to-amber-700 hover:from-amber-700 hover:to-amber-600 text-white font-bold py-4 px-6 rounded-lg border border-amber-600/30 transition-all font-cinzel disabled:opacity-50"
                >
                  Share Blessing Link
                </button>
              </div>

              <div className="bg-gradient-to-br from-amber-900/20 to-slate-900/50 p-6 rounded-lg border border-amber-600/30 text-center">
                <h4 className="text-amber-400 font-cinzel mb-2">🕊️ Pass the Blessing Forward</h4>
                <p className="text-amber-200/70 text-sm mb-3">
                  "Freely you have received, freely give." — Matthew 10:8
                </p>
                <div className="bg-slate-950 p-3 rounded text-xs text-amber-600/80 font-mono break-all">
                  {shareLink}
                </div>
                <p className="text-xs text-amber-200/45 mt-2">
                  Invite a friend to try a free biblical reflection preview
                </p>
              </div>

              <button
                onClick={startOver}
                className="w-full text-amber-200/55 text-sm underline hover:text-amber-200/85 transition-colors"
              >
                Reflect on another dream
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-amber-900/30 mt-12">
        <div className="max-w-2xl mx-auto px-6 py-6 text-center space-y-2">
          <p className="text-xs text-amber-200/35">
            DreamDecode — Biblical dream reflection • Free preview • Full report $4.99/month, cancel anytime
          </p>
          <p className="text-xs text-amber-200/35 italic">
            Reflections are prompts for discernment — test everything against Scripture, prayer, and pastoral counsel (1 Thess. 5:21).
          </p>
          <button
            onClick={manageSubscription}
            className="text-amber-200/50 text-xs underline hover:text-amber-200/80 transition-colors"
          >
            Manage or cancel your subscription
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;
