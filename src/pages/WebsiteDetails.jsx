import { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom';
import PageContainer from '../components/PageContainer';
import { api } from '../services/api';
import { useAuth } from '../context/useAuth';

const WebsiteDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated } = useAuth();

  const [website, setWebsite] = useState(null);
  const [loading, setLoading] = useState(() => Boolean(id));
  const [error, setError] = useState(null);
  const [isSaved, setIsSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  useEffect(() => {
    if (!id) return;

    let isMounted = true;

    const fetchWebsite = async () => {
      try {
        const data = await api.getWebsite(id);
        if (isMounted) {
          setWebsite(data);
          setIsSaved(Boolean(data.is_saved));
          setError(null);
        }
      } catch (err) {
        console.error(`Failed to fetch website ID ${id}:`, err);
        if (isMounted) {
          setError(
            err.message || `Website with ID ${id} was not found or backend service is unavailable.`
          );
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchWebsite();

    return () => {
      isMounted = false;
    };
  }, [id]);

  const handleToggleSave = async () => {
    if (!website) return;
    if (!isAuthenticated) {
      navigate('/login', { state: { from: location } });
      return;
    }
    setSaving(true);
    try {
      if (isSaved) {
        await api.unsaveWebsite(website.id);
        setIsSaved(false);
        setActionMessage({ type: 'success', text: 'Website removed from saved list.' });
      } else {
        await api.saveWebsite(website.id);
        setIsSaved(true);
        setActionMessage({ type: 'success', text: 'Website saved to your bookmarks!' });
      }
      setTimeout(() => setActionMessage(null), 4000);
    } catch (err) {
      console.error('Failed to update bookmark:', err);
      setActionMessage({ type: 'error', text: err.message || 'Failed to update saved status.' });
    } finally {
      setSaving(false);
    }
  };

  const handleRunAnalysis = async () => {
    if (!website?.id) return;
    setAnalyzing(true);
    setActionMessage({
      type: 'info',
      text: 'Running crawling, submission extraction, and AI verification pipeline...',
    });
    try {
      const updated = await api.processWebsitePipeline(website.id);
      setWebsite(updated);
      setIsSaved(Boolean(updated.is_saved));
      setActionMessage({
        type: 'success',
        text: `AI analysis complete! Quality Score: ${updated.analysis?.quality_score ?? 'N/A'}/100`,
      });
      setTimeout(() => setActionMessage(null), 6000);
    } catch (err) {
      console.error('Failed to run AI pipeline:', err);
      setActionMessage({
        type: 'error',
        text: err.message || 'Failed to complete AI verification pipeline. Please try again.',
      });
    } finally {
      setAnalyzing(false);
    }
  };

  const handleVisitWebsite = () => {
    if (website?.url) {
      window.open(website.url, '_blank', 'noopener,noreferrer');
    }
  };

  const getQualityScoreColor = (score) => {
    if (!score && score !== 0) return 'bg-gray-500';
    if (score >= 85) return 'bg-emerald-500';
    if (score >= 70) return 'bg-green-500';
    if (score >= 50) return 'bg-amber-500';
    return 'bg-red-500';
  };

  const getSignalBadge = (level) => {
    switch (level) {
      case 'High':
      case 'Yes':
        return <span className="bg-green-600 text-white text-xs px-2.5 py-1 rounded-full font-medium">High</span>;
      case 'Good':
      case 'Strong':
        return <span className="bg-blue-600 text-white text-xs px-2.5 py-1 rounded-full font-medium">{level}</span>;
      case 'Medium':
        return <span className="bg-yellow-600 text-white text-xs px-2.5 py-1 rounded-full font-medium">Medium</span>;
      case 'Low':
      case 'No':
      case 'Weak':
        return <span className="bg-red-600 text-white text-xs px-2.5 py-1 rounded-full font-medium">{level}</span>;
      default:
        return <span className="bg-gray-600 text-gray-300 text-xs px-2.5 py-1 rounded-full font-medium">{level || 'Pending'}</span>;
    }
  };

  const getVerificationBadge = (status) => {
    const s = (status || '').toLowerCase();
    if (s === 'verified') {
      return (
        <span className="inline-flex items-center gap-1.5 bg-green-500/20 text-green-300 border border-green-500/40 px-3 py-1 rounded-full text-xs font-semibold">
          <span className="w-2 h-2 rounded-full bg-green-400"></span>
          AI Verified: Accepts Guest Posts
        </span>
      );
    }
    if (s === 'rejected') {
      return (
        <span className="inline-flex items-center gap-1.5 bg-red-500/20 text-red-300 border border-red-500/40 px-3 py-1 rounded-full text-xs font-semibold">
          <span className="w-2 h-2 rounded-full bg-red-400"></span>
          AI Rejected: Not Accepting
        </span>
      );
    }
    if (s === 'uncertain') {
      return (
        <span className="inline-flex items-center gap-1.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 px-3 py-1 rounded-full text-xs font-semibold">
          <span className="w-2 h-2 rounded-full bg-amber-400"></span>
          AI Verification: Informational / Uncertain
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 bg-gray-600/30 text-gray-300 border border-gray-600 px-3 py-1 rounded-full text-xs font-medium">
        <span className="w-2 h-2 rounded-full bg-gray-400"></span>
        Unverified
      </span>
    );
  };

  const safeArray = (val) => {
    if (!val) return [];
    if (Array.isArray(val)) return val;
    if (typeof val === 'string') {
      try {
        const parsed = JSON.parse(val);
        if (Array.isArray(parsed)) return parsed;
      } catch {
        return [val];
      }
      return [val];
    }
    return [];
  };

  const analysis = website?.analysis;
  const gpInfo = website?.guest_post_info;
  const scoreBreakdown = analysis?.score_breakdown;

  const topics = safeArray(analysis?.topics);
  const trustSignals = safeArray(analysis?.trust_signals);
  const editorialStandards = safeArray(analysis?.editorial_standards);
  const strengths = safeArray(analysis?.strengths);
  const weaknesses = safeArray(analysis?.weaknesses);
  const warnings = safeArray(analysis?.warnings);

  return (
    <PageContainer title="Website Details">
      <div className="space-y-6">
        {/* Back to Results Navigation */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-gray-300 hover:text-white transition-colors py-2 px-3 rounded-lg hover:bg-gray-700/50 w-fit cursor-pointer"
          >
            <span className="text-xl">←</span>
            <span className="font-medium">Back</span>
          </button>

          {website && (
            <div className="flex items-center gap-3">
              <button
                onClick={handleRunAnalysis}
                disabled={analyzing}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs md:text-sm px-4 py-2 rounded-lg transition-colors cursor-pointer flex items-center gap-2 font-medium shadow-sm"
                title="Execute crawling, guideline extraction & Gemini AI verification"
              >
                {analyzing ? (
                  <>
                    <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
                    <span>Analyzing Pipeline...</span>
                  </>
                ) : (
                  <>
                    <span>⚡</span>
                    <span>{analysis?.quality_score != null ? 'Re-analyze Website' : 'Run AI Analysis'}</span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* Action Message Alert */}
        {actionMessage && (
          <div
            className={`p-4 rounded-xl text-sm flex items-center justify-between gap-3 border transition-all ${
              actionMessage.type === 'success'
                ? 'bg-green-950/60 border-green-500/50 text-green-200'
                : actionMessage.type === 'error'
                ? 'bg-red-950/60 border-red-500/50 text-red-200'
                : 'bg-indigo-950/60 border-indigo-500/50 text-indigo-200 animate-pulse'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <span>{actionMessage.type === 'success' ? '✓' : actionMessage.type === 'error' ? '⚠️' : '⏳'}</span>
              <span>{actionMessage.text}</span>
            </div>
            {actionMessage.type !== 'info' && (
              <button
                onClick={() => setActionMessage(null)}
                className="text-xs opacity-70 hover:opacity-100 cursor-pointer font-bold px-1"
              >
                ✕
              </button>
            )}
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="bg-gray-700 rounded-xl p-12 border border-gray-600 text-center">
            <div className="inline-block w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-gray-300">Loading website details from backend...</p>
          </div>
        )}

        {/* Error / Not Found State */}
        {!loading && (error || !website) && (
          <div className="bg-red-900/40 border border-red-500/50 rounded-xl p-8 text-red-200">
            <div className="flex items-start gap-4">
              <span className="text-3xl">⚠️</span>
              <div>
                <h3 className="text-xl font-bold text-white mb-2">Website Not Found</h3>
                <p className="text-red-300 mb-6">{error || `No website found matching ID ${id}.`}</p>
                <div className="flex gap-4">
                  <button
                    onClick={() => navigate('/results')}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-5 py-2.5 rounded-lg transition-colors cursor-pointer"
                  >
                    Go to Results
                  </button>
                  <Link
                    to="/history"
                    className="bg-gray-700 hover:bg-gray-600 text-white text-sm px-5 py-2.5 rounded-lg transition-colors"
                  >
                    View Search History
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Website Content */}
        {!loading && !error && website && (
          <>
            {/* 1. Website Header */}
            <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <h1 className="text-2xl md:text-3xl font-bold text-white">
                      {website.name || website.domain}
                    </h1>
                    <span className="text-xs text-gray-400 bg-gray-800/80 px-2 py-0.5 rounded border border-gray-600">
                      ID #{website.id}
                    </span>
                  </div>

                  <p className="text-lg text-gray-300 font-mono break-all">{website.domain}</p>

                  <div className="flex flex-wrap items-center gap-2.5">
                    {/* Guest Post Acceptance */}
                    <span
                      className={`text-white text-xs px-3 py-1 rounded-full font-medium ${
                        gpInfo?.accepts_guest_posts === true
                          ? 'bg-green-600'
                          : gpInfo?.accepts_guest_posts === false
                          ? 'bg-red-600'
                          : 'bg-gray-600'
                      }`}
                    >
                      {gpInfo?.accepts_guest_posts === true
                        ? '✓ Accepts Guest Posts'
                        : gpInfo?.accepts_guest_posts === false
                        ? '✗ Not Accepting'
                        : 'Pending Check'}
                    </span>

                    {/* AI Verification Badge */}
                    {getVerificationBadge(gpInfo?.verification_status)}

                    {/* Crawl Status Badge */}
                    {website.crawl_status === 'success' ? (
                      <span className="bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 text-xs px-3 py-1 rounded-full font-medium">
                        ✓ Crawled (HTTP {website.http_status || 200})
                      </span>
                    ) : website.crawl_status === 'failed' ? (
                      <span className="bg-red-950/70 text-red-300 border border-red-500/40 text-xs px-3 py-1 rounded-full font-medium">
                        ✗ Crawl Blocked (HTTP {website.http_status || 'Error'})
                      </span>
                    ) : (
                      <span className="bg-gray-800 text-gray-400 border border-gray-600 text-xs px-3 py-1 rounded-full font-medium">
                        Crawl Pending
                      </span>
                    )}

                    {gpInfo?.pricing && (
                      <span
                        className={`text-white text-xs px-3 py-1 rounded-full font-medium capitalize ${
                          gpInfo.pricing.toLowerCase() === 'free' ? 'bg-blue-600' : 'bg-purple-600'
                        }`}
                      >
                        {gpInfo.pricing}
                      </span>
                    )}
                  </div>
                </div>

                {/* Score & Bookmark Box */}
                <div className="flex flex-col items-start md:items-end gap-3 shrink-0">
                  <div className="text-left md:text-right bg-gray-800/80 p-4 rounded-xl border border-gray-600 min-w-[150px]">
                    <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">Quality Score</p>
                    <p className="text-4xl font-bold text-white">
                      {analysis?.quality_score != null ? analysis.quality_score : '—'}
                      {analysis?.quality_score != null && <span className="text-base text-gray-400 font-normal">/100</span>}
                    </p>
                    {analysis?.scoring_status && (
                      <p className="text-xs text-gray-400 mt-1 capitalize">{analysis.scoring_status}</p>
                    )}
                  </div>

                  <div className="flex gap-2 w-full md:w-auto">
                    <button
                      onClick={handleToggleSave}
                      disabled={saving}
                      className={`text-sm px-4 py-2 rounded-lg transition-colors cursor-pointer flex items-center justify-center gap-1.5 font-medium shadow-sm flex-1 md:flex-initial ${
                        isSaved
                          ? 'bg-amber-900/60 text-amber-300 border border-amber-500/50 hover:bg-amber-800/80'
                          : 'bg-gray-800 text-gray-300 hover:text-white border border-gray-600 hover:bg-gray-700'
                      }`}
                      title={isSaved ? 'Remove from saved websites' : 'Save this website'}
                    >
                      {saving ? (
                        <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
                      ) : (
                        <span>{isSaved ? '★' : '☆'}</span>
                      )}
                      <span>{isSaved ? 'Saved' : 'Save'}</span>
                    </button>

                    <button
                      onClick={handleVisitWebsite}
                      className="bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-600 text-sm px-4 py-2 rounded-lg transition-colors cursor-pointer"
                      title="Open website in new tab"
                    >
                      Visit ↗
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* 2. Website Overview & Semantic Niche */}
            <div className="bg-gray-700 rounded-xl p-6 border border-gray-600 space-y-4">
              <h2 className="text-xl font-bold text-white">Website Overview</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="bg-gray-800/60 p-3.5 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Domain</p>
                  <p className="text-white font-medium break-all">{website.domain}</p>
                </div>
                <div className="bg-gray-800/60 p-3.5 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Target URL</p>
                  <a
                    href={website.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-400 hover:text-indigo-300 text-sm break-all underline"
                  >
                    {website.url}
                  </a>
                </div>
                <div className="bg-gray-800/60 p-3.5 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Primary Niche</p>
                  <p className="text-white font-medium">
                    {analysis?.primary_niche || 'General / Unclassified'}
                  </p>
                </div>
                <div className="bg-gray-800/60 p-3.5 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Niche Relevance</p>
                  <p className="text-white font-medium">
                    {analysis?.niche_relevance != null ? `${analysis.niche_relevance}%` : 'Pending'}
                  </p>
                </div>
                <div className="bg-gray-800/60 p-3.5 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Pricing</p>
                  <p className="text-white font-medium capitalize">{gpInfo?.pricing || 'Not stated / Free'}</p>
                </div>
                <div className="bg-gray-800/60 p-3.5 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Submission Method</p>
                  <p className="text-white font-medium">{gpInfo?.submission_method || 'Pending extraction'}</p>
                </div>
              </div>

              {/* Semantic Topics */}
              {topics.length > 0 && (
                <div className="pt-2">
                  <p className="text-gray-400 text-xs mb-2 uppercase tracking-wider">Semantic Topics & Tags</p>
                  <div className="flex flex-wrap gap-2">
                    {topics.map((t, idx) => (
                      <span
                        key={idx}
                        className="bg-indigo-950/60 text-indigo-300 border border-indigo-500/40 text-xs px-3 py-1 rounded-full font-medium"
                      >
                        #{t}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* 3. Guest Posting Guidelines & Contact Info */}
            <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
              <h2 className="text-xl font-bold text-white mb-4">Guest Posting Submission Info</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Accepts Guest Posts</p>
                  <p className="text-white font-medium text-base">
                    {gpInfo?.accepts_guest_posts === true
                      ? '✓ Yes (Verified Opportunity)'
                      : gpInfo?.accepts_guest_posts === false
                      ? '✗ No (Not Accepting)'
                      : 'Pending AI Analysis'}
                  </p>
                </div>
                <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Rule Detection Confidence</p>
                  <p className="text-white font-medium text-base">
                    {gpInfo?.confidence != null ? `${gpInfo.confidence}%` : 'Pending'}
                  </p>
                </div>
                <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Submission Link / Form</p>
                  <p className="text-white font-medium text-base break-all">
                    {gpInfo?.submission_url ? (
                      <a
                        href={gpInfo.submission_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-400 hover:text-indigo-300 underline"
                      >
                        {gpInfo.submission_url}
                      </a>
                    ) : (
                      <span className="text-gray-400 text-sm">None detected</span>
                    )}
                  </p>
                </div>
                <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Contact Email</p>
                  <p className="text-white font-medium text-base">
                    {gpInfo?.contact_email ? (
                      <a href={`mailto:${gpInfo.contact_email}`} className="text-indigo-400 hover:text-indigo-300 underline">
                        {gpInfo.contact_email}
                      </a>
                    ) : (
                      <span className="text-gray-400 text-sm">No email extracted</span>
                    )}
                  </p>
                </div>
                <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Contributor Guidelines URL</p>
                  <p className="text-white font-medium text-base break-all">
                    {gpInfo?.guidelines_url ? (
                      <a
                        href={gpInfo.guidelines_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-400 hover:text-indigo-300 underline"
                      >
                        {gpInfo.guidelines_url}
                      </a>
                    ) : (
                      <span className="text-gray-400 text-sm">No dedicated guidelines link</span>
                    )}
                  </p>
                </div>
                <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40">
                  <p className="text-gray-400 text-xs mb-1 uppercase tracking-wider">Backlink Type (Dofollow)</p>
                  <p className="text-white font-medium text-base">
                    {gpInfo?.dofollow === true
                      ? '✓ Dofollow Backlink'
                      : gpInfo?.dofollow === false
                      ? '✗ Nofollow / Sponsored'
                      : 'Unspecified'}
                  </p>
                </div>
              </div>
            </div>

            {/* 4. Quality Analysis & Deterministic Score Breakdown */}
            <div className="bg-gray-700 rounded-xl p-6 border border-gray-600 space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-gray-600/60 pb-4">
                <div>
                  <h2 className="text-xl font-bold text-white">Quality & Deterministic Scoring</h2>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Multi-dimensional scoring across 6 deterministic evaluation criteria (0–100).
                  </p>
                </div>
                {analysis?.quality_score != null && (
                  <span className="text-2xl font-bold text-white">
                    {analysis.quality_score} <span className="text-sm text-gray-400 font-normal">/ 100</span>
                  </span>
                )}
              </div>

              {analysis?.quality_score != null ? (
                <>
                  {/* Overall Bar */}
                  <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40 space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-300 font-medium">Overall Composite Score</span>
                      <span className="text-white font-bold">{analysis.quality_score}%</span>
                    </div>
                    <div className="w-full bg-gray-600 rounded-full h-3">
                      <div
                        className={`h-3 rounded-full transition-all duration-500 ${getQualityScoreColor(
                          analysis.quality_score
                        )}`}
                        style={{ width: `${analysis.quality_score}%` }}
                      ></div>
                    </div>
                  </div>

                  {/* 6 Deterministic Breakdown Cards */}
                  {scoreBreakdown && typeof scoreBreakdown === 'object' && (
                    <div>
                      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                        Deterministic Factor Breakdown
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {Object.entries(scoreBreakdown).map(([key, item]) => {
                          const titleMap = {
                            guest_post_acceptance: 'Guest Post Acceptance',
                            niche_relevance: 'Niche Relevance',
                            content_quality: 'Content Quality',
                            trust_signals: 'Trust Signals',
                            editorial_standards: 'Editorial Standards',
                            ai_verification: 'AI Verification',
                          };
                          const pct =
                            item.max_points > 0 ? Math.round((item.points / item.max_points) * 100) : 0;

                          return (
                            <div
                              key={key}
                              className="bg-gray-800/60 p-3.5 rounded-lg border border-gray-600/40 flex flex-col justify-between"
                            >
                              <div>
                                <div className="flex justify-between items-start gap-2 mb-1.5">
                                  <span className="text-xs font-medium text-gray-300">
                                    {titleMap[key] || key}
                                  </span>
                                  <span className="text-xs font-bold text-white whitespace-nowrap">
                                    {item.points} / {item.max_points} pts
                                  </span>
                                </div>
                                <div className="w-full bg-gray-700 rounded-full h-1.5 mb-2">
                                  <div
                                    className={`h-1.5 rounded-full ${getQualityScoreColor(pct)}`}
                                    style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                                  ></div>
                                </div>
                                <p className="text-xs text-gray-400 leading-relaxed">{item.reason}</p>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Dimension Metrics Sliders */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-2">
                    <div className="bg-gray-800/50 p-3 rounded-lg border border-gray-600/30">
                      <div className="flex justify-between text-xs text-gray-300 mb-1.5">
                        <span>Content Quality</span>
                        <span className="font-semibold text-white">{analysis.content_quality ?? '—'}/100</span>
                      </div>
                      <div className="w-full bg-gray-700 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${getQualityScoreColor(analysis.content_quality)}`}
                          style={{ width: `${analysis.content_quality || 0}%` }}
                        ></div>
                      </div>
                    </div>

                    <div className="bg-gray-800/50 p-3 rounded-lg border border-gray-600/30">
                      <div className="flex justify-between text-xs text-gray-300 mb-1.5">
                        <span>Website Trust</span>
                        <span className="font-semibold text-white">{analysis.website_trust ?? '—'}/100</span>
                      </div>
                      <div className="w-full bg-gray-700 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${getQualityScoreColor(analysis.website_trust)}`}
                          style={{ width: `${analysis.website_trust || 0}%` }}
                        ></div>
                      </div>
                    </div>

                    <div className="bg-gray-800/50 p-3 rounded-lg border border-gray-600/30">
                      <div className="flex justify-between text-xs text-gray-300 mb-1.5">
                        <span>Niche Relevance</span>
                        <span className="font-semibold text-white">{analysis.niche_relevance ?? '—'}/100</span>
                      </div>
                      <div className="w-full bg-gray-700 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${getQualityScoreColor(analysis.niche_relevance)}`}
                          style={{ width: `${analysis.niche_relevance || 0}%` }}
                        ></div>
                      </div>
                    </div>

                    <div className="bg-gray-800/50 p-3 rounded-lg border border-gray-600/30">
                      <div className="flex justify-between text-xs text-gray-300 mb-1.5">
                        <span>Post Quality</span>
                        <span className="font-semibold text-white">{analysis.guest_post_quality ?? '—'}/100</span>
                      </div>
                      <div className="w-full bg-gray-700 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${getQualityScoreColor(analysis.guest_post_quality)}`}
                          style={{ width: `${analysis.guest_post_quality || 0}%` }}
                        ></div>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="bg-gray-800/60 p-6 rounded-lg text-center space-y-3">
                  <p className="text-gray-300 text-sm">
                    Detailed deterministic quality scoring has not been computed for this website yet.
                  </p>
                  <button
                    onClick={handleRunAnalysis}
                    disabled={analyzing}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs px-5 py-2.5 rounded-lg font-medium transition-colors cursor-pointer inline-flex items-center gap-2"
                  >
                    <span>⚡</span>
                    <span>Run AI Quality Analysis</span>
                  </button>
                </div>
              )}
            </div>

            {/* 5. Website Signals & Editorial Strengths */}
            <div className="bg-gray-700 rounded-xl p-6 border border-gray-600 space-y-4">
              <h2 className="text-xl font-bold text-white">Editorial Signals & Evaluation</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex items-center justify-between bg-gray-800/50 p-3.5 rounded-lg border border-gray-600/30">
                  <span className="text-gray-300 text-sm font-medium">Guest Post Availability</span>
                  {getSignalBadge(
                    gpInfo?.accepts_guest_posts === true
                      ? 'High'
                      : gpInfo?.accepts_guest_posts === false
                      ? 'Low'
                      : 'Pending'
                  )}
                </div>
                <div className="flex items-center justify-between bg-gray-800/50 p-3.5 rounded-lg border border-gray-600/30">
                  <span className="text-gray-300 text-sm font-medium">Niche Relevance</span>
                  {getSignalBadge(
                    analysis?.niche_relevance != null
                      ? analysis.niche_relevance >= 75
                        ? 'High'
                        : 'Medium'
                      : 'Pending'
                  )}
                </div>
                <div className="flex items-center justify-between bg-gray-800/50 p-3.5 rounded-lg border border-gray-600/30">
                  <span className="text-gray-300 text-sm font-medium">Dofollow Status</span>
                  {getSignalBadge(
                    gpInfo?.dofollow === true ? 'High' : gpInfo?.dofollow === false ? 'Low' : 'Pending'
                  )}
                </div>
              </div>

              {/* Editorial Standards Detected */}
              {editorialStandards.length > 0 && (
                <div className="bg-gray-800/50 p-4 rounded-lg border border-gray-600/30 space-y-2">
                  <p className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                    <span>📋</span>
                    <span>Editorial Standards & Contributor Guidelines</span>
                  </p>
                  <ul className="space-y-1.5 text-xs text-gray-200 list-disc list-inside">
                    {editorialStandards.map((std, idx) => (
                      <li key={idx} className="leading-relaxed">{std}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Trust Signals */}
              {trustSignals.length > 0 && (
                <div className="bg-gray-800/50 p-4 rounded-lg border border-gray-600/30 space-y-2">
                  <p className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                    <span>🛡️</span>
                    <span>Verified Trust & Authority Signals</span>
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {trustSignals.map((ts, idx) => (
                      <span
                        key={idx}
                        className="bg-blue-950/60 text-blue-200 border border-blue-500/40 text-xs px-3 py-1 rounded-full"
                      >
                        ✓ {ts}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Strengths & Weaknesses Grid */}
              {(strengths.length > 0 || weaknesses.length > 0) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                  {strengths.length > 0 && (
                    <div className="bg-emerald-950/20 border border-emerald-500/30 rounded-lg p-4 space-y-2">
                      <p className="text-xs font-semibold text-emerald-300 uppercase tracking-wider flex items-center gap-1.5">
                        <span>✓</span>
                        <span>Key Strengths</span>
                      </p>
                      <ul className="space-y-1 text-xs text-emerald-100 list-disc list-inside">
                        {strengths.map((st, idx) => (
                          <li key={idx} className="leading-relaxed">{st}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {weaknesses.length > 0 && (
                    <div className="bg-amber-950/20 border border-amber-500/30 rounded-lg p-4 space-y-2">
                      <p className="text-xs font-semibold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
                        <span>⚠️</span>
                        <span>Areas to Note</span>
                      </p>
                      <ul className="space-y-1 text-xs text-amber-100 list-disc list-inside">
                        {weaknesses.map((wk, idx) => (
                          <li key={idx} className="leading-relaxed">{wk}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Warnings if any */}
              {warnings.length > 0 && (
                <div className="bg-red-950/20 border border-red-500/30 rounded-lg p-4 space-y-1.5">
                  <p className="text-xs font-semibold text-red-300 uppercase tracking-wider flex items-center gap-1.5">
                    <span>🚨</span>
                    <span>AI Warnings</span>
                  </p>
                  <ul className="space-y-1 text-xs text-red-200 list-disc list-inside">
                    {warnings.map((w, idx) => (
                      <li key={idx} className="leading-relaxed">{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* 6. Evidence & AI Verification Reasoning */}
            <div className="bg-gray-700 rounded-xl p-6 border border-gray-600 space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-gray-600/60 pb-4">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span>🤖</span>
                    <span>Evidence & Verification Reasoning</span>
                  </h2>
                  <p className="text-xs text-gray-400 mt-1">
                    AI verification verdict, crawler quote extractions, and semantic rationale.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {getVerificationBadge(gpInfo?.verification_status)}
                  {gpInfo?.ai_confidence != null && (
                    <span className="text-xs bg-gray-800 text-gray-300 border border-gray-600 px-2.5 py-1 rounded-full font-medium">
                      AI Confidence: {gpInfo.ai_confidence}%
                    </span>
                  )}
                </div>
              </div>

              {/* AI Verification Verdict & Reasoning Callout */}
              {gpInfo?.ai_reason ? (
                <div className="bg-indigo-950/40 border border-indigo-500/40 rounded-xl p-5 space-y-2.5">
                  <div className="flex items-center gap-2 text-indigo-300 font-semibold text-sm">
                    <span>✨</span>
                    <span>AI Verification Verdict & Reasoning</span>
                  </div>
                  <p className="text-gray-100 text-sm leading-relaxed font-sans">
                    {gpInfo.ai_reason}
                  </p>
                  {gpInfo.verified_at && (
                    <p className="text-xs text-indigo-300/70 pt-1">
                      Verified at: {new Date(gpInfo.verified_at).toLocaleString()}
                    </p>
                  )}
                </div>
              ) : (
                <div className="bg-gray-800/50 p-5 rounded-xl border border-gray-600/30 text-gray-300 text-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <p className="font-semibold text-white mb-1">AI Verification Not Yet Executed</p>
                    <p className="text-gray-400 text-xs leading-relaxed">
                      Run automated pipeline processing to fetch webpage content, extract guest post guidelines, and verify publisher eligibility using Gemini AI.
                    </p>
                  </div>
                  <button
                    onClick={handleRunAnalysis}
                    disabled={analyzing}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs px-4 py-2 rounded-lg font-medium transition-colors cursor-pointer shrink-0"
                  >
                    {analyzing ? 'Analyzing...' : '⚡ Run AI Analysis'}
                  </button>
                </div>
              )}

              {/* Page-Extracted Crawl Evidence Quotes */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                  <span>📄</span>
                  <span>Crawled Webpage Evidence Quotes</span>
                </h3>
                {gpInfo?.evidence ? (
                  <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40 space-y-2 max-h-72 overflow-y-auto">
                    {gpInfo.evidence
                      .split(/\s*\|\s*/)
                      .filter(Boolean)
                      .map((snippet, idx) => (
                        <div
                          key={idx}
                          className="text-xs text-gray-200 bg-gray-900/70 p-2.5 rounded border border-gray-700/60 font-mono leading-relaxed"
                        >
                          &ldquo;{snippet.trim()}&rdquo;
                        </div>
                      ))}
                  </div>
                ) : gpInfo?.ai_evidence ? (
                  <div className="bg-gray-800/60 p-4 rounded-lg border border-gray-600/40 text-xs text-gray-200 font-mono leading-relaxed">
                    &ldquo;{gpInfo.ai_evidence}&rdquo;
                  </div>
                ) : (
                  <div className="bg-gray-800/40 p-4 rounded-lg border border-gray-600/30 text-gray-400 text-xs">
                    {website.crawl_status === 'failed' ? (
                      <div className="flex items-start gap-2 text-amber-300">
                        <span>⚠️</span>
                        <span>
                          Crawl could not access this website (HTTP {website.http_status || 'Blocked'}). The publisher may employ Cloudflare anti-bot checks or geo-restrictions. Click &ldquo;Re-analyze Website&rdquo; to attempt re-crawling.
                        </span>
                      </div>
                    ) : (
                      <span>No guest-posting text quotes have been extracted from this page yet.</span>
                    )}
                  </div>
                )}
              </div>

              {/* Semantic Relevance & Quality Rationale */}
              {(analysis?.relevance_reason || analysis?.content_quality_reason) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                  {analysis?.relevance_reason && (
                    <div className="bg-gray-800/50 p-4 rounded-lg border border-gray-600/30 space-y-1.5">
                      <p className="text-xs text-indigo-400 font-semibold uppercase tracking-wider">
                        Niche Relevance Reasoning
                      </p>
                      <p className="text-xs md:text-sm text-gray-200 leading-relaxed">
                        {analysis.relevance_reason}
                      </p>
                    </div>
                  )}

                  {analysis?.content_quality_reason && (
                    <div className="bg-gray-800/50 p-4 rounded-lg border border-gray-600/30 space-y-1.5">
                      <p className="text-xs text-indigo-400 font-semibold uppercase tracking-wider">
                        Editorial & Content Quality Reasoning
                      </p>
                      <p className="text-xs md:text-sm text-gray-200 leading-relaxed">
                        {analysis.content_quality_reason}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 7. Action Buttons Bar */}
            <div className="flex flex-wrap gap-4 pt-2">
              <button
                onClick={handleRunAnalysis}
                disabled={analyzing}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-6 py-3 rounded-lg font-medium transition-colors cursor-pointer flex items-center gap-2 shadow"
              >
                {analyzing ? (
                  <>
                    <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
                    <span>Analyzing Pipeline...</span>
                  </>
                ) : (
                  <>
                    <span>⚡</span>
                    <span>{analysis?.quality_score != null ? 'Re-analyze Website' : 'Run AI Analysis'}</span>
                  </>
                )}
              </button>

              <button
                onClick={handleToggleSave}
                disabled={saving}
                className={`px-6 py-3 rounded-lg font-medium transition-colors cursor-pointer flex items-center gap-2 ${
                  isSaved
                    ? 'bg-green-600 hover:bg-green-700 text-white'
                    : 'bg-gray-700 hover:bg-gray-600 text-white border border-gray-600'
                }`}
              >
                {saving ? (
                  <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
                ) : (
                  <span>{isSaved ? '✓ Saved in Bookmarks' : '★ Save Website'}</span>
                )}
              </button>

              <button
                onClick={handleVisitWebsite}
                className="bg-gray-800 hover:bg-gray-700 text-white border border-gray-600 px-6 py-3 rounded-lg font-medium transition-colors cursor-pointer"
              >
                Visit Website ↗
              </button>
            </div>
          </>
        )}
      </div>
    </PageContainer>
  );
};

export default WebsiteDetails;
