import React, { useState, useEffect } from 'react';
import './index.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Static sample so visitors can see what a reflection looks like
// before entering their own dream or subscribing.
const SAMPLE = {
  dream: '“I was walking through a dark valley at night and felt afraid. Then I saw a warm light over the hills ahead, and I started walking toward it. I woke up feeling peaceful.”',
  themes: [
    {
      title: 'From fear to peace — presence in dark seasons',
      body: 'Moving from darkness toward light is a recurring biblical picture of God’s guidance and comfort in difficult times. The shift in feeling — fear giving way to peace — may be the part most worth reflecting on.',
      verse: 'Psalm 23:4 — “Even though I walk through the darkest valley, I will fear no evil, for you are with me.”'
    },
    {
      title: 'Light as guidance and hope',
      body: 'Light in Scripture often pictures God’s direction and truth. Walking toward the light could prompt reflection on where you are currently looking for guidance.',
      verse: 'Psalm 119:105 — “Your word is a lamp for my feet, a light on my path.”'
    }
  ],
  questions: [
    'Is there a “dark valley” situation in your life right now where you need to remember God’s presence?',
    'What would “walking toward the light” look like practically for you this week?',
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
  const [trialDays, setTrialDays] = useState(0);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Email is collected only at subscribe time (receipt + report delivery).
  const [subscribeEmail, setSubscribeEmail] = useState('');

  const [giftMode, setGiftMode] = useState(false);
  const [giftInfo, setGiftInfo] = useState(null);

  const feelings = ['Fear', 'Peace', 'Urgency', 'Joy', 'Confusion', 'Awe', 'Warning', 'Love'];

  // Handle URL parameters
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const dId = params.get('dream_id');
    const sessionId = params.get('session_id');

    if (code) {
      setGiftMode(true);
      setFormData(prev => ({...prev, referral_code: code}));
      fetchGiftInfo(code);
    }

    if (dId) {
      setDreamId(dId);
    }

    // Returning from Stripe Checkout — verify subscription and unlock the report
    if (sessionId && dId) {
      verifySubscription(sessionId, dId);
    } else if (dId) {
      // Returning visitor with a dream link — unlock if already paid
      tryAutoReveal(dId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const verifySubscription = async (sessionId, dId) => {
    setStep('verifying');
    setError(null);
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
        setReport(data.report);
        setStep('reveal');
        window.history.replaceState({}, '', window.location.pathname);
      } else {
        setError('Subscription not confirmed yet — if you just subscribed, wait a few seconds and refresh.');
        setStep('input');
      }
    } catch (error) {
      console.error('Verify error:', error);
      setError(error.message || 'Error confirming your subscription');
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
    } catch (error) {
      console.error('Gift info error:', error);
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

    try {
      const res = await fetch(`${API_URL}/api/analyze-teaser`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to analyze dream');
      }

      const data = await res.json();

      if (!data.dream_id) {
        throw new Error('No dream ID received from server');
      }

      setDreamId(data.dream_id);
      setReferralCode(data.referral_code);
      setTeaser(data.teaser);
      setTrialDays(data.trial_days || 0);
      setStep('teaser');

    } catch (error) {
      console.error('Teaser error:', error);
      setError(error.message || 'Error analyzing dream');
    } finally {
      setLoading(false);
    }
  };

  const handleSubscribe = async () => {
    if (!dreamId) {
      setError('Dream ID is missing. Please refresh and try again.');
      return;
    }
    if (!subscribeEmail.trim() || !subscribeEmail.includes('@')) {
      setError('Please enter your email — it’s needed for your receipt and to deliver your report.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/create-checkout-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ dream_id: dreamId, email: subscribeEmail.trim() })
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || `Checkout failed (${res.status})`);
      }

      if (data.already_subscribed) {
        // Active subscriber — unlock this dream without charging again
        await handleReveal();
        return;
      }

      if (data.url) {
        window.location.href = data.url;
      } else {
        throw new Error('No checkout URL received');
      }

    } catch (error) {
      console.error('Subscribe error:', error);
      setError(error.message || 'Error starting checkout');
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
      } else {
        throw new Error('No report received');
      }

    } catch (error) {
      console.error('Reveal error:', error);
      setError(error.message || 'Error generating your reflection report');
    } finally {
      setLoading(false);
    }
  };

  const manageSubscription = async () => {
    const email = window.prompt('Enter the email you subscribed with:');
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
    } catch (error) {
      console.error('Portal error:', error);
      setError(error.message || 'Error opening billing portal');
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
    setReport(null);
    setTeaser('');
    setSubscribeEmail('');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const shareLink = `${window.location.origin}/gift?code=${referralCode}`;

  const copyToClipboard = () => {
    navigator.clipboard.writeText(shareLink).then(() => {
      alert('Blessing link copied! Share it with someone who would appreciate biblical reflection.');
    }).catch(err => {
      console.error('Copy failed:', err);
      alert('Failed to copy link');
    });
  };

  // Error display component
  const ErrorMessage = () => error ? (
    <div className="bg-red-900/30 border border-red-600/50 text-red-200 p-4 rounded-lg mb-4 text-center">
      <p className="font-bold">Error</p>
      <p className="text-sm">{error}</p>
      <button
        onClick={() => setError(null)}
        className="mt-2 text-xs underline hover:text-red-100"
      >
        Dismiss
      </button>
    </div>
  ) : null;

  return (
    <div className="min-h-screen bg-slate-950 text-amber-50 font-cormorant selection:bg-amber-500/30">
      {/* Header */}
      <div className="border-b border-amber-900/30 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-2xl mx-auto px-6 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-amber-400 font-cinzel tracking-wider">
            DreamDecode
          </h1>
          <div className="text-xs text-amber-200/60 tracking-widest uppercase">
            Free preview · Full report $4.99/mo
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-6 py-12">
        <ErrorMessage />

        {/* Gift Mode Banner */}
        {giftMode && giftInfo && (
          <div className="bg-gradient-to-r from-amber-900/30 to-amber-600/20 border border-amber-500/50 p-6 rounded-lg mb-8 text-center animate-pulse">
            <div className="text-3xl mb-2">🕊️</div>
            <h3 className="text-amber-400 font-cinzel text-xl mb-2">
              A Blessing from {giftInfo.referrer_name || 'A Friend'}
            </h3>
            <p className="text-amber-200/80 text-sm mb-4">
              "{giftInfo.message}"
            </p>
            <div className="bg-slate-950/50 inline-block px-4 py-2 rounded border border-amber-600/30">
              <span className="text-amber-500 font-bold">$4.99/mo</span>
              <span className="text-amber-200/60 text-sm ml-2">Full reflection reports</span>
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
            <div className="text-center space-y-4">
              <h2 className="text-3xl text-amber-100 font-cinzel">Reflect on your dreams through a biblical lens</h2>
              <p className="text-amber-200/80 text-lg">
                DreamDecode helps you explore <span className="text-amber-100 font-semibold">possible themes, Scripture references, and questions</span> for personal reflection.
              </p>
              <p className="text-amber-200/60 text-sm italic max-w-xl mx-auto">
                Reflections are prompts for discernment — not a guaranteed message from God, and not a substitute for Scripture, prayer, or pastoral counsel.
              </p>
              <div className="pt-2">
                <p className="text-amber-200/70 italic text-lg">
                  "In the last days, God says, I will pour out my Spirit on all people..."
                </p>
                <p className="text-sm text-amber-600 font-cinzel">— Acts 2:17</p>
                <p className="text-xs text-amber-200/50 italic max-w-xl mx-auto mt-2">
                  Scripture shows God has spoken through dreams. We help you reflect on yours prayerfully — without claiming His definitive meaning.
                </p>
              </div>
              <p className="text-sm text-amber-200/70">
                <span className="text-amber-400 font-semibold">Free preview</span> · Full report and symbol guide: <span className="text-amber-400 font-semibold">$4.99/month</span>. Renews monthly; cancel anytime.
              </p>
              <div>
                <button
                  onClick={() => { setStep('sample'); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                  className="text-amber-400 text-sm underline hover:text-amber-300 transition-colors font-cinzel tracking-wide"
                >
                  See a sample reflection first →
                </button>
              </div>
            </div>

            <form onSubmit={handleSubmitTeaser} className="space-y-6 bg-slate-900/30 p-8 rounded-lg border border-amber-900/20 shadow-2xl shadow-black/50">
              <div>
                <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Describe your dream</label>
                <textarea
                  required
                  rows={4}
                  className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none transition-colors placeholder:text-amber-900/50"
                  value={formData.dream_text}
                  onChange={(e) => setFormData({...formData, dream_text: e.target.value})}
                  placeholder="What did you see? Write it in your own words — even a few sentences is enough..."
                />
                <p className="text-xs text-amber-200/50 mt-2 leading-relaxed">
                  🔒 <span className="font-semibold text-amber-200/70">Privacy:</span> your dream is sent securely to generate your preview and is never sold or used for ads. No email needed for the free preview. Please don’t include full names, addresses, or other sensitive details.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">What feeling stood out most? <span className="text-amber-200/40">(optional)</span></label>
                  <select
                    className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none"
                    value={formData.emotion}
                    onChange={(e) => setFormData({...formData, emotion: e.target.value})}
                  >
                    <option value="">Prefer not to say</option>
                    {feelings.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Colors you remember <span className="text-amber-200/40">(optional)</span></label>
                  <input
                    type="text"
                    className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none placeholder:text-amber-900/50"
                    value={formData.colors}
                    onChange={(e) => setFormData({...formData, colors: e.target.value})}
                    placeholder="Crimson, gold..."
                  />
                </div>
              </div>

              <div>
                <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Symbols or objects that stood out <span className="text-amber-200/40">(optional)</span></label>
                <input
                  type="text"
                  className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none placeholder:text-amber-900/50"
                  value={formData.symbols}
                  onChange={(e) => setFormData({...formData, symbols: e.target.value})}
                  placeholder="River, ladder, keys, dove..."
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-gradient-to-r from-amber-700 to-amber-600 hover:from-amber-600 hover:to-amber-500 text-white font-bold py-4 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed font-cinzel tracking-wider"
              >
                {loading ? 'Preparing your preview...' : 'Explore possible themes — free preview'}
              </button>

              <p className="text-center text-xs text-amber-200/40">
                Free preview · No email needed · Full report + symbol guide with $4.99/mo subscription · Cancel anytime
              </p>
            </form>
          </div>
        )}

        {/* Sample Step */}
        {step === 'sample' && (
          <div className="space-y-8 animate-fade-in">
            <div className="text-center space-y-3">
              <h2 className="text-3xl text-amber-100 font-cinzel">A sample reflection</h2>
              <p className="text-amber-200/70">
                Here’s the kind of preview reflection DreamDecode produces — so you know exactly what to expect before subscribing.
              </p>
            </div>

            <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40">
              <h3 className="text-amber-400 font-cinzel mb-2">💭 The sample dream</h3>
              <p className="text-amber-100/90 italic leading-relaxed">{SAMPLE.dream}</p>
            </div>

            <div className="space-y-4">
              <h3 className="text-amber-400 font-cinzel text-center">🌿 Possible themes for reflection</h3>
              {SAMPLE.themes.map((t, idx) => (
                <div key={idx} className="bg-slate-900/30 p-6 rounded-lg border-l-4 border-amber-600 shadow-lg">
                  <h4 className="text-lg text-amber-300 font-cinzel mb-2">{t.title}</h4>
                  <p className="text-amber-100/90 leading-relaxed">{t.body}</p>
                  <p className="text-amber-600 font-bold text-sm font-cinzel mt-2">{t.verse}</p>
                </div>
              ))}
            </div>

            <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40">
              <h3 className="text-amber-400 font-cinzel mb-3">🤔 Sample reflection questions</h3>
              <ol className="list-decimal list-inside space-y-2 text-amber-100/90">
                {SAMPLE.questions.map((q, idx) => <li key={idx}>{q}</li>)}
              </ol>
            </div>

            <div className="bg-amber-950/20 p-5 rounded-lg border border-amber-700/30 text-center">
              <p className="text-amber-200/70 text-sm italic">
                A sample, not a verdict. Real reflections vary with each dream — and every reflection is a starting point for prayer, not a final answer. “Test everything; hold fast what is good.” — 1 Thessalonians 5:21
              </p>
            </div>

            <button
              onClick={() => { setStep('input'); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
              className="w-full bg-gradient-to-r from-amber-700 to-amber-600 hover:from-amber-600 hover:to-amber-500 text-white font-bold py-4 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all transform hover:scale-[1.02] font-cinzel tracking-wider"
            >
              Try it with your own dream — free
            </button>
          </div>
        )}

        {/* Teaser Step */}
        {step === 'teaser' && (
          <div className="space-y-8 text-center animate-fade-in">
            <div className="bg-slate-900/50 p-8 rounded-lg border border-amber-600/30 shadow-2xl shadow-amber-900/10 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-amber-600 to-transparent"></div>
              <div className="text-amber-500 text-sm tracking-widest mb-4 uppercase font-cinzel">Your free preview</div>
              <p className="text-2xl text-amber-100 italic leading-relaxed font-cormorant">
                "{teaser}"
              </p>
            </div>

            <div className="bg-amber-950/20 p-5 rounded-lg border border-amber-700/30 text-left">
              <p className="text-amber-200/70 text-sm leading-relaxed">
                <span className="font-semibold text-amber-300">A note on discernment:</span> this preview suggests <span className="font-semibold">possible themes to prayerfully consider</span> — not a definitive meaning for your dream. Symbols in Scripture carry different meanings in different contexts. Test everything against God’s Word, prayer, and wise counsel (1 Thessalonians 5:21).
              </p>
            </div>

            <div className="space-y-4">
              <p className="text-amber-200/70 text-lg">
                Want to go deeper? The complete reflection report awaits...
              </p>

              <div className="bg-slate-900/30 p-6 rounded-lg border border-amber-900/20 space-y-3 text-left">
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">✨ In-depth theme reflections</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">🔍 Dream Symbol Dictionary</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">🕊️ Discernment guidance</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">📖 Scriptural Anchor</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">🌾 Joseph & Daniel Anchor</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">🙏 A prayer for reflection</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">📜 Beautiful PDF Report</span>
                  <span className="text-amber-400">✓</span>
                </div>
              </div>

              {/* Billing clarity — the full picture before anyone pays */}
              <div className="bg-slate-900/50 p-6 rounded-lg border border-amber-900/40 text-left space-y-3">
                <h3 className="text-amber-400 font-cinzel text-center mb-1">Before you subscribe — the full picture</h3>
                <p className="text-sm text-amber-200/70"><span className="font-semibold text-amber-300">What’s free?</span> This preview — possible themes and a first taste of your report. Always free, no card required.</p>
                <p className="text-sm text-amber-200/70"><span className="font-semibold text-amber-300">What requires payment?</span> Only the full report, symbol guide, and PDF — $4.99/month.</p>
                <p className="text-sm text-amber-200/70">
                  <span className="font-semibold text-amber-300">When am I charged?</span>{' '}
                  {trialDays > 0
                    ? `$0 today — your first $4.99 bill lands on day ${trialDays + 1} unless you cancel.`
                    : 'Only when you click Subscribe and confirm checkout — $4.99 today, then monthly. Nothing before that moment.'}
                </p>
                <p className="text-sm text-amber-200/70"><span className="font-semibold text-amber-300">How do I cancel?</span> One click from the “Manage subscription” link below — anytime, no emails or calls needed.</p>
              </div>

              <div className="pt-4">
                {trialDays > 0 ? (
                  <>
                    <div className="text-3xl font-cinzel text-amber-400 mb-2">{trialDays} Days FREE</div>
                    <p className="text-xs text-amber-200/50 mb-3">then $4.99/month • Full reflection reports • Cancel anytime</p>
                  </>
                ) : (
                  <>
                    <div className="text-3xl font-cinzel text-amber-400 mb-2">$4.99<span className="text-lg text-amber-200/60">/month</span></div>
                    <p className="text-xs text-amber-200/50 mb-3">Full reflection reports • Cancel anytime</p>
                  </>
                )}

                {!dreamId && (
                  <div className="mb-4 p-2 bg-red-900/20 text-red-400 text-xs rounded">
                    ⚠️ Error: Dream ID missing. Please refresh page.
                  </div>
                )}

                <div className="text-left mb-4">
                  <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Email for your report & receipt</label>
                  <input
                    type="email"
                    className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none placeholder:text-amber-900/50"
                    value={subscribeEmail}
                    onChange={(e) => setSubscribeEmail(e.target.value)}
                    placeholder="your@email.com"
                  />
                  <p className="text-xs text-amber-200/50 mt-2">
                    Required only to subscribe — used for your receipt and to deliver your report. Never sold, never used for ads.
                  </p>
                </div>

                <button
                  onClick={handleSubscribe}
                  disabled={loading || !dreamId}
                  className="w-full bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-white font-bold py-4 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed font-cinzel tracking-wider text-lg"
                >
                  {loading ? 'Opening Secure Checkout...' : (trialDays > 0 ? `Start ${trialDays}-Day Free Trial` : 'Subscribe — $4.99/month')}
                </button>

                {dreamId && (
                  <p className="text-xs text-amber-600/50 mt-2 font-mono">
                    ID: {dreamId.substring(0, 8)}...
                  </p>
                )}

                <p className="text-xs text-amber-200/40 mt-3">
                  {trialDays > 0
                    ? `Card required • $0 charged today • First bill $4.99 on day ${trialDays + 1} unless you cancel • Cancel anytime`
                    : 'Secure checkout by Stripe • Charged $4.99 today • Renews monthly • Cancel anytime • Report emailed instantly'}
                </p>

                <button
                  onClick={startOver}
                  className="mt-4 text-amber-200/50 text-sm underline hover:text-amber-200/80 transition-colors"
                >
                  ← Reflect on a different dream
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
                <p className="text-amber-200/70 text-sm leading-relaxed">
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
                <p className="text-amber-200/70 text-sm italic">
                  Hold these reflections lightly and prayerfully. If this dream troubles you — especially around fear, grief, or a major decision — please bring it to your pastor, a trusted counselor, or a mature believer.
                </p>
              </div>

              <div className="flex gap-4">
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
                  Share Blessing
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
                <p className="text-xs text-amber-200/40 mt-2">
                  Share the gift of reflection with friends
                </p>
              </div>

              <button
                onClick={startOver}
                className="w-full text-amber-200/50 text-sm underline hover:text-amber-200/80 transition-colors"
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
          <p className="text-xs text-amber-200/30">
            DreamDecode — Biblical dream reflection • $4.99/month, cancel anytime
          </p>
          <p className="text-xs text-amber-200/30 italic">
            Reflections are prompts for discernment — test everything against Scripture, prayer, and pastoral counsel (1 Thess. 5:21).
          </p>
          <button
            onClick={manageSubscription}
            className="text-amber-200/40 text-xs underline hover:text-amber-200/70 transition-colors"
          >
            Manage or cancel your subscription
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;
