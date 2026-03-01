import React, { useState, useEffect } from 'react';
import './index.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [step, setStep] = useState('input');
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    dream_text: '',
    emotion: '',
    colors: '',
    symbols: '',
    referral_code: ''
  });
  
  const [dreamId, setDreamId] = useState(null);
  const [referralCode, setReferralCode] = useState('');
  const [teaser, setTeaser] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const [giftMode, setGiftMode] = useState(false);
  const [giftInfo, setGiftInfo] = useState(null);
  const [price, setPrice] = useState(17.00);

  const emotions = ['Fear', 'Peace', 'Urgency', 'Joy', 'Confusion', 'Awe', 'Warning', 'Love'];

  // Handle URL parameters
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const sessionId = params.get('session_id');
    const dId = params.get('dream_id');
    
    if (code) {
      setGiftMode(true);
      setFormData(prev => ({...prev, referral_code: code}));
      fetchGiftInfo(code);
    }
    
    if (sessionId && dId) {
      setStep('reveal');
      setDreamId(dId);
      verifyPayment(sessionId, dId);
    }
  }, []);

  const fetchGiftInfo = async (code) => {
    try {
      const res = await fetch(`${API_URL}/api/referral/${code}`);
      if (!res.ok) throw new Error('Invalid referral code');
      const data = await res.json();
      setGiftInfo(data);
      setPrice(8.50);
    } catch (error) {
      console.error('Gift info error:', error);
      setError('Invalid blessing code');
    }
  };

  const handleSubmitTeaser = async (e) => {
    e.preventDefault();
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
      setPrice(data.price || 17.00);
      setStep('teaser');
      
    } catch (error) {
      console.error('Teaser error:', error);
      setError(error.message || 'Error analyzing dream');
    } finally {
      setLoading(false);
    }
  };

  const handlePayment = async () => {
    if (!dreamId) {
      setError('Dream ID is missing. Please refresh and try again.');
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
        body: JSON.stringify({ dream_id: dreamId })
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || `Payment failed (${res.status})`);
      }
      
      const data = await res.json();
      
      if (!data.url) {
        throw new Error('No checkout URL received');
      }
      
      window.location.href = data.url;
      
    } catch (error) {
      console.error('Payment error:', error);
      setError(error.message || 'Error creating payment session');
      setLoading(false);
    }
  };

  const verifyPayment = async (sessionId, dId) => {
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch(`${API_URL}/api/verify-payment`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ 
          session_id: sessionId, 
          dream_id: dId 
        })
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Payment verification failed');
      }
      
      const data = await res.json();
      
      if (data.status === 'paid' && data.report) {
        setReport(data.report);
      } else {
        setError('Payment not completed');
      }
      
    } catch (error) {
      console.error('Verification error:', error);
      setError(error.message || 'Error verifying payment');
    } finally {
      setLoading(false);
    }
  };

  const downloadPDF = () => {
    if (!dreamId) {
      setError('Dream ID missing for download');
      return;
    }
    window.open(`${API_URL}/api/download-pdf/${dreamId}`);
  };

  const shareLink = `${window.location.origin}/gift?code=${referralCode}&from=${formData.name.replace(/\s+/g, '-')}`;

  const copyToClipboard = () => {
    navigator.clipboard.writeText(shareLink).then(() => {
      alert('Blessing link copied! Share it with someone who needs revelation.');
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
            Biblical Interpretation
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
              A Blessing from {giftInfo.referrer_name}
            </h3>
            <p className="text-amber-200/80 text-sm mb-4">
              "{giftInfo.message}"
            </p>
            <div className="bg-slate-950/50 inline-block px-4 py-2 rounded border border-amber-600/30">
              <span className="text-amber-500 font-bold">50% OFF</span>
              <span className="text-amber-200/60 text-sm ml-2">Applied automatically</span>
            </div>
          </div>
        )}

        {/* Input Step */}
        {step === 'input' && (
          <div className="space-y-8 animate-fade-in">
            <div className="text-center space-y-4">
              <h2 className="text-3xl text-amber-100 font-cinzel">Unlock Your Vision</h2>
              <p className="text-amber-200/70 italic text-lg">
                "In the last days, God says, I will pour out my Spirit on all people..." 
              </p>
              <p className="text-sm text-amber-600 font-cinzel">— Acts 2:17</p>
            </div>

            <form onSubmit={handleSubmitTeaser} className="space-y-6 bg-slate-900/30 p-8 rounded-lg border border-amber-900/20 shadow-2xl shadow-black/50">
              <div>
                <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Your Name</label>
                <input
                  type="text"
                  required
                  className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none transition-colors placeholder:text-amber-900/50"
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                  placeholder="Enter your name..."
                />
              </div>

              <div>
                <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">The Vision</label>
                <textarea
                  required
                  rows={4}
                  className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none transition-colors placeholder:text-amber-900/50"
                  value={formData.dream_text}
                  onChange={(e) => setFormData({...formData, dream_text: e.target.value})}
                  placeholder="Describe what you saw in the vision..."
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Dominant Spirit</label>
                  <select
                    className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none"
                    value={formData.emotion}
                    onChange={(e) => setFormData({...formData, emotion: e.target.value})}
                  >
                    <option value="">Select...</option>
                    {emotions.map(e => <option key={e} value={e}>{e}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Colors Seen</label>
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
                <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Symbols & Objects</label>
                <input
                  type="text"
                  className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none placeholder:text-amber-900/50"
                  value={formData.symbols}
                  onChange={(e) => setFormData({...formData, symbols: e.target.value})}
                  placeholder="Door, serpent, mountain..."
                />
              </div>

              <div>
                <label className="block text-amber-400 mb-2 text-sm tracking-wide font-cinzel">Email for Your Report</label>
                <input
                  type="email"
                  required
                  className="w-full bg-slate-950 border border-amber-900/30 rounded p-3 text-amber-100 focus:border-amber-600 focus:outline-none placeholder:text-amber-900/50"
                  value={formData.email}
                  onChange={(e) => setFormData({...formData, email: e.target.value})}
                  placeholder="your@email.com"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-gradient-to-r from-amber-700 to-amber-600 hover:from-amber-600 hover:to-amber-500 text-white font-bold py-4 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed font-cinzel tracking-wider"
              >
                {loading ? 'Consulting the Scriptures...' : 'Reveal My Dream Meaning'}
              </button>
              
              <p className="text-center text-xs text-amber-200/40">
                Free preview • ${price.toFixed(2)} for full revelation
              </p>
            </form>
          </div>
        )}

        {/* Teaser Step */}
        {step === 'teaser' && (
          <div className="space-y-8 text-center animate-fade-in">
            <div className="bg-slate-900/50 p-8 rounded-lg border border-amber-600/30 shadow-2xl shadow-amber-900/10 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-amber-600 to-transparent"></div>
              <div className="text-amber-500 text-sm tracking-widest mb-4 uppercase font-cinzel">The Spirit is Moving</div>
              <p className="text-2xl text-amber-100 italic leading-relaxed font-cormorant">
                "{teaser}"
              </p>
            </div>

            <div className="space-y-4">
              <p className="text-amber-200/70 text-lg">
                A complete revelation awaits you...
              </p>
              
              <div className="bg-slate-900/30 p-6 rounded-lg border border-amber-900/20 space-y-3">
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">✨ Three Revelations</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">📖 Scriptural Anchor</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">🙏 Personalized Prayer</span>
                  <span className="text-amber-400">✓</span>
                </div>
                <div className="flex justify-between text-sm text-amber-200/60 items-center">
                  <span className="flex items-center gap-2">📜 Beautiful PDF Report</span>
                  <span className="text-amber-400">✓</span>
                </div>
                {price < 17 && (
                  <div className="flex justify-between text-sm text-green-400 items-center border-t border-amber-900/30 pt-2 mt-2">
                    <span className="flex items-center gap-2">🕊️ Blessing Discount Applied</span>
                    <span>-50%</span>
                  </div>
                )}
              </div>

              <div className="pt-4">
                <div className="text-3xl font-cinzel text-amber-400 mb-2">${price.toFixed(2)}</div>
                
                {!dreamId && (
                  <div className="mb-4 p-2 bg-red-900/20 text-red-400 text-xs rounded">
                    ⚠️ Error: Dream ID missing. Please refresh page.
                  </div>
                )}
                
                <button
                  onClick={handlePayment}
                  disabled={loading || !dreamId}
                  className="w-full bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-white font-bold py-4 px-6 rounded-lg shadow-lg shadow-amber-900/20 transition-all transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed font-cinzel tracking-wider text-lg"
                >
                  {loading ? 'Preparing the Revelation...' : 'Unlock Full Report'}
                </button>
                
                {dreamId && (
                  <p className="text-xs text-amber-600/50 mt-2 font-mono">
                    ID: {dreamId.substring(0, 8)}...
                  </p>
                )}
                
                <p className="text-xs text-amber-200/40 mt-3">
                  Secure payment via Stripe • Instant delivery via email
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Reveal Step */}
        {step === 'reveal' && report && (
          <div className="space-y-8 animate-fade-in">
            <div className="text-center">
              <h2 className="text-3xl text-amber-100 font-cinzel mb-2">Your Revelation</h2>
              <p className="text-amber-200/60 font-cinzel">Hebrew Year {new Date().getFullYear() + 3760}</p>
            </div>

            <div className="space-y-6">
              {report.interpretations?.map((interp, idx) => (
                <div key={idx} className="bg-slate-900/30 p-6 rounded-lg border-l-4 border-amber-600 shadow-lg">
                  <h3 className="text-xl text-amber-400 font-cinzel mb-3">{interp.title}</h3>
                  <p className="text-amber-100/90 leading-relaxed text-lg">{interp.meaning}</p>
                </div>
              ))}

              <div className="bg-amber-950/30 p-6 rounded-lg border border-amber-600/30 text-center">
                <h3 className="text-lg text-amber-400 font-cinzel mb-4">Scriptural Anchor</h3>
                <p className="text-amber-100 italic text-lg mb-2">"{report.scripture?.text}"</p>
                <p className="text-amber-600 font-bold font-cinzel">{report.scripture?.reference}</p>
                <p className="text-amber-200/60 text-sm mt-2">{report.scripture?.context}</p>
              </div>

              <div className="bg-slate-900 p-8 rounded-lg border border-amber-600/30 text-center">
                <h3 className="text-xl text-amber-400 font-cinzel mb-4 border-b border-amber-600/30 pb-2 inline-block">A Prayer for Your Dream</h3>
                <p className="text-amber-100 italic text-lg leading-relaxed">{report.prayer}</p>
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
                  Gift 50% off to friends • Track your impact
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
