import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useSearchParams, useLocation, useNavigate } from 'react-router-dom';
import PageContainer from '../components/PageContainer';
import { api } from '../services/api';

const SearchProgress = () => {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();

  const searchIdFromUrl = searchParams.get('searchId') || location.state?.searchId;

  const [searchData, setSearchData] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState('');
  const [error, setError] = useState(null);

  const pollTimerRef = useRef(null);

  // Fetch search record and real-time pipeline progress
  const fetchProgress = useCallback(async (searchId, showInitialLoader = false) => {
    if (showInitialLoader) setLoading(true);
    try {
      const [searchRes, progressRes] = await Promise.all([
        api.getSearch(searchId),
        api.getSearchProgress(searchId).catch(() => null),
      ]);

      setSearchData(searchRes);
      if (progressRes) {
        setProgressData(progressRes);
      }
      setError(null);
      return { search: searchRes, progress: progressRes };
    } catch (err) {
      console.error('Failed to fetch search progress:', err);
      setError(err.message || 'Unable to retrieve search information from backend.');
      return null;
    } finally {
      if (showInitialLoader) setLoading(false);
    }
  }, []);

  // Initial load and polling loop
  useEffect(() => {
    let isMounted = true;

    const init = async () => {
      let activeSearchId = searchIdFromUrl;

      // Fallback: load latest search from backend if none specified
      if (!activeSearchId) {
        try {
          const listRes = await api.listSearches(0, 1);
          if (listRes.searches && listRes.searches.length > 0) {
            activeSearchId = listRes.searches[0].id;
          }
        } catch (e) {
          console.warn('Could not list searches:', e);
        }
      }

      if (!activeSearchId) {
        if (isMounted) setLoading(false);
        return;
      }

      await fetchProgress(activeSearchId, true);

      // Start polling
      const poll = async () => {
        if (!isMounted) return;
        const res = await fetchProgress(activeSearchId, false);
        if (!res) return;

        const isCompleted =
          res.search?.status === 'completed' ||
          res.progress?.is_completed ||
          (res.progress?.total_websites > 0 &&
            res.progress?.scored_count >= res.progress?.total_websites);

        // Continue polling if still active
        if (!isCompleted && isMounted) {
          pollTimerRef.current = setTimeout(poll, 2500);
        }
      };

      pollTimerRef.current = setTimeout(poll, 2500);
    };

    init();

    return () => {
      isMounted = false;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
    };
  }, [searchIdFromUrl, fetchProgress]);

  // Handle manual trigger of discovery or pipeline execution
  const handleStartPipeline = async () => {
    if (!searchData?.id || actionLoading) return;

    setActionLoading(true);
    setActionMessage('Initiating AI search discovery and analysis...');
    setError(null);

    try {
      if (searchData.status === 'pending' || (searchData.total_results || 0) === 0) {
        setActionMessage('Discovering candidate websites via search engine...');
        await api.triggerDiscovery(searchData.id);
      } else {
        setActionMessage('Launching batch crawling and AI verification...');
        await api.processSearchPipeline(searchData.id, 5);
      }

      // Refresh immediately
      const refreshed = await fetchProgress(searchData.id, false);
      if (refreshed?.search?.status !== 'completed') {
        // Ensure polling is active
        if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
        pollTimerRef.current = setTimeout(async () => {
          await fetchProgress(searchData.id, false);
        }, 1500);
      }
    } catch (err) {
      console.error('Failed to run pipeline:', err);
      setError(err.message || 'Failed to trigger pipeline.');
    } finally {
      setActionLoading(false);
      setActionMessage('');
    }
  };

  const totalCandidates = progressData?.total_websites || searchData?.total_results || 0;
  const crawledCount = progressData?.crawled_count || 0;
  const verifiedCount = progressData?.verified_count || 0;
  const analyzedCount = progressData?.analyzed_count || 0;
  const scoredCount = progressData?.scored_count || 0;

  const isCompleted =
    searchData?.status === 'completed' ||
    progressData?.is_completed ||
    (totalCandidates > 0 && scoredCount >= totalCandidates);

  const isProcessing =
    !isCompleted &&
    (searchData?.status === 'processing' ||
      searchData?.status === 'crawling' ||
      searchData?.status === 'analyzing' ||
      crawledCount > 0 ||
      actionLoading);

  const isDiscovered = searchData?.status === 'discovered';
  const isPending = searchData?.status === 'pending' && totalCandidates === 0;

  // Calculate realistic progress percentage
  let progressPercentage = 0;
  if (isCompleted) {
    progressPercentage = 100;
  } else if (progressData?.progress_percentage) {
    progressPercentage = progressData.progress_percentage;
  } else if (isProcessing && totalCandidates > 0) {
    progressPercentage = Math.min(
      95,
      Math.round(
        ((crawledCount * 0.25 + verifiedCount * 0.25 + analyzedCount * 0.25 + scoredCount * 0.25) /
          totalCandidates) *
          100
      )
    );
  } else if (isDiscovered) {
    progressPercentage = 20;
  } else if (actionLoading) {
    progressPercentage = 10;
  }

  // Pipeline Stages definition
  const stages = [
    {
      id: 'discovery',
      name: 'Search Discovery',
      desc: 'Tavily multi-query candidate URL generation',
      status: totalCandidates > 0 ? 'completed' : isPending ? 'pending' : 'active',
      count: `${totalCandidates} URLs`,
    },
    {
      id: 'crawl',
      name: 'HTML Page Crawl',
      desc: 'Extract clean DOM, metadata, and links',
      status:
        crawledCount >= totalCandidates && totalCandidates > 0
          ? 'completed'
          : crawledCount > 0
          ? 'active'
          : 'pending',
      count: `${crawledCount} / ${totalCandidates}`,
    },
    {
      id: 'verification',
      name: 'AI Guest Post Verification',
      desc: 'Gemini semantic validation & guidelines check',
      status:
        verifiedCount >= totalCandidates && totalCandidates > 0
          ? 'completed'
          : verifiedCount > 0
          ? 'active'
          : 'pending',
      count: `${verifiedCount} / ${totalCandidates}`,
    },
    {
      id: 'analysis',
      name: 'Audience & Topic Analysis',
      desc: 'Niche alignment, authoritativeness & metrics',
      status:
        analyzedCount >= totalCandidates && totalCandidates > 0
          ? 'completed'
          : analyzedCount > 0
          ? 'active'
          : 'pending',
      count: `${analyzedCount} / ${totalCandidates}`,
    },
    {
      id: 'scoring',
      name: 'Deterministic Quality Scoring',
      desc: 'Comprehensive 0–100 opportunity index',
      status:
        scoredCount >= totalCandidates && totalCandidates > 0
          ? 'completed'
          : scoredCount > 0
          ? 'active'
          : 'pending',
      count: `${scoredCount} / ${totalCandidates}`,
    },
  ];

  return (
    <PageContainer title="Pipeline Progress">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Page Title */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 py-2">
          <div>
            <h2 className="text-2xl font-bold text-white tracking-tight flex items-center gap-3">
              <span>Pipeline Monitor</span>
              {isProcessing && (
                <span className="flex h-3 w-3 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-500"></span>
                </span>
              )}
            </h2>
            <p className="text-gray-400 text-sm mt-1">
              End-to-end autonomous discovery, crawling, verification, and AI analysis.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/search"
              className="bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white px-4 py-2 rounded-lg text-sm border border-gray-700 transition-colors"
            >
              + New Search
            </Link>
            {searchData && (
              <Link
                to={`/results?searchId=${searchData.id}`}
                className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all shadow-sm ${
                  isCompleted
                    ? 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-emerald-900/30'
                    : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-900/30'
                }`}
              >
                {isCompleted ? 'View Discovered Targets →' : 'View Results'}
              </Link>
            )}
          </div>
        </div>

        {/* Loading Initial State */}
        {loading && (
          <div className="bg-gray-800/80 rounded-2xl p-12 border border-gray-700 text-center shadow-xl backdrop-blur-sm">
            <div className="inline-block w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-gray-300 font-medium">Connecting to pipeline engine...</p>
          </div>
        )}

        {/* Error Alert */}
        {!loading && error && (
          <div className="bg-red-950/40 border border-red-500/50 rounded-2xl p-6 text-red-200 shadow-lg">
            <div className="flex items-start gap-3">
              <span className="text-2xl">⚠️</span>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Search Notice</h3>
                <p className="text-sm text-red-300 mt-1">{error}</p>
                <div className="mt-4 flex gap-3">
                  <button
                    onClick={() => searchData && fetchProgress(searchData.id, true)}
                    className="bg-red-800/80 hover:bg-red-700 text-white text-xs px-4 py-2 rounded-lg transition-colors cursor-pointer"
                  >
                    Retry Loading
                  </button>
                  <Link
                    to="/search"
                    className="bg-gray-800 hover:bg-gray-700 text-white text-xs px-4 py-2 rounded-lg transition-colors"
                  >
                    Start New Search
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* No Search Found State */}
        {!loading && !error && !searchData && (
          <div className="bg-gray-800/80 rounded-2xl p-12 border border-gray-700 text-center shadow-xl">
            <div className="text-5xl mb-4">🔍</div>
            <h3 className="text-xl font-bold text-white mb-2">No Active Search Selected</h3>
            <p className="text-gray-400 mb-6 text-sm max-w-md mx-auto">
              Start a new search to discover guest posting opportunities or review previously registered searches.
            </p>
            <div className="flex justify-center gap-4">
              <Link
                to="/search"
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-xl font-medium text-sm transition-colors"
              >
                Create Search
              </Link>
              <Link
                to="/history"
                className="bg-gray-700 hover:bg-gray-600 text-white px-6 py-2.5 rounded-xl font-medium text-sm transition-colors"
              >
                Search History
              </Link>
            </div>
          </div>
        )}

        {/* Search Data Loaded */}
        {!loading && searchData && (
          <>
            {/* Main Progress Card */}
            <div className="bg-gray-800/90 rounded-2xl p-6 md:p-8 border border-gray-700 shadow-xl backdrop-blur-md">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400 bg-indigo-950/60 px-2.5 py-0.5 rounded-md border border-indigo-800/50">
                      Search #{searchData.id}
                    </span>
                    <span className="text-xs text-gray-400">
                      Created {new Date(searchData.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <h3 className="text-2xl font-bold text-white mt-2">
                    Keyword: &ldquo;<span className="text-indigo-300">{searchData.keyword}</span>&rdquo;
                  </h3>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <span className="text-xs text-gray-400 block">Current Status</span>
                    <span
                      className={`inline-block px-3 py-1 rounded-full text-xs font-semibold capitalize mt-0.5 border ${
                        isCompleted
                          ? 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40'
                          : isProcessing
                          ? 'bg-indigo-950/70 text-indigo-300 border-indigo-500/50 animate-pulse'
                          : isDiscovered
                          ? 'bg-blue-950/60 text-blue-300 border-blue-500/40'
                          : 'bg-amber-950/60 text-amber-300 border-amber-500/40'
                      }`}
                    >
                      {isCompleted ? 'Completed' : isProcessing ? 'Processing Pipeline' : searchData.status}
                    </span>
                  </div>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="space-y-2 mb-6">
                <div className="flex justify-between text-xs text-gray-400">
                  <span className="font-medium text-gray-300">
                    {isCompleted
                      ? 'Pipeline finished successfully'
                      : isProcessing
                      ? 'Processing websites through crawler & AI...'
                      : isDiscovered
                      ? 'URLs discovered — ready for deep analysis'
                      : 'Registered in database'}
                  </span>
                  <span className="font-bold text-indigo-300">{progressPercentage}%</span>
                </div>
                <div className="w-full bg-gray-900 rounded-full h-3.5 p-0.5 border border-gray-700/60 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                      isCompleted
                        ? 'bg-gradient-to-r from-emerald-500 to-teal-400'
                        : 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-cyan-400'
                    }`}
                    style={{ width: `${Math.max(5, progressPercentage)}%` }}
                  ></div>
                </div>
              </div>

              {/* Action Banner if not running */}
              {(isPending || isDiscovered) && !isProcessing && (
                <div className="bg-gradient-to-r from-indigo-950/80 to-purple-950/80 border border-indigo-500/40 rounded-xl p-5 mb-6 flex flex-col sm:flex-row items-center justify-between gap-4">
                  <div>
                    <h4 className="text-white font-semibold text-sm">
                      {isPending
                        ? 'Ready to execute discovery & analysis'
                        : `${totalCandidates} candidate websites found`}
                    </h4>
                    <p className="text-gray-300 text-xs mt-1">
                      {isPending
                        ? 'Click below to search the web using Tavily, crawl pages, verify guest post guidelines with Gemini AI, and calculate opportunity scores.'
                        : 'Run the automated batch crawler and Gemini AI semantic verifier across all discovered opportunities.'}
                    </p>
                  </div>
                  <button
                    onClick={handleStartPipeline}
                    disabled={actionLoading}
                    className="w-full sm:w-auto shrink-0 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold px-6 py-2.5 rounded-lg text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {actionLoading && (
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    )}
                    <span>{isPending ? '🚀 Start AI Discovery' : '⚡ Run Full Pipeline'}</span>
                  </button>
                </div>
              )}

              {/* Action Feedback message */}
              {actionMessage && (
                <div className="bg-indigo-900/30 border border-indigo-600/40 rounded-lg p-3 text-xs text-indigo-300 mb-6 flex items-center gap-2">
                  <div className="w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin"></div>
                  <span>{actionMessage}</span>
                </div>
              )}

              {/* Live Metric Badges */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-gray-900/70 rounded-xl p-4 border border-gray-700/50 text-center">
                  <p className="text-xs text-gray-400 uppercase tracking-wider font-medium">Discovered</p>
                  <p className="text-2xl font-bold text-white mt-1">{totalCandidates}</p>
                  <span className="text-[11px] text-gray-500">Candidate URLs</span>
                </div>
                <div className="bg-gray-900/70 rounded-xl p-4 border border-gray-700/50 text-center">
                  <p className="text-xs text-gray-400 uppercase tracking-wider font-medium">Crawled</p>
                  <p className="text-2xl font-bold text-cyan-300 mt-1">{crawledCount}</p>
                  <span className="text-[11px] text-gray-500">Pages fetched</span>
                </div>
                <div className="bg-gray-900/70 rounded-xl p-4 border border-gray-700/50 text-center">
                  <p className="text-xs text-gray-400 uppercase tracking-wider font-medium">AI Verified</p>
                  <p className="text-2xl font-bold text-indigo-300 mt-1">{verifiedCount}</p>
                  <span className="text-[11px] text-gray-500">Guidelines verified</span>
                </div>
                <div className="bg-gray-900/70 rounded-xl p-4 border border-gray-700/50 text-center">
                  <p className="text-xs text-gray-400 uppercase tracking-wider font-medium">Scored</p>
                  <p className="text-2xl font-bold text-emerald-300 mt-1">{scoredCount}</p>
                  <span className="text-[11px] text-gray-500">Quality indexed</span>
                </div>
              </div>
            </div>

            {/* Pipeline Stage Breakdown */}
            <div className="bg-gray-800/90 rounded-2xl p-6 border border-gray-700 shadow-xl">
              <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
                <span>Autonomous Pipeline Stages</span>
              </h3>

              <div className="space-y-3">
                {stages.map((stage, idx) => {
                  const isStageCompleted = stage.status === 'completed';
                  const isStageActive = stage.status === 'active';

                  return (
                    <div
                      key={stage.id}
                      className={`flex items-center justify-between p-3.5 rounded-xl border transition-all ${
                        isStageCompleted
                          ? 'bg-emerald-950/20 border-emerald-500/30'
                          : isStageActive
                          ? 'bg-indigo-950/40 border-indigo-500/50 shadow-sm'
                          : 'bg-gray-900/40 border-gray-800/80 opacity-70'
                      }`}
                    >
                      <div className="flex items-center gap-3.5">
                        <div
                          className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                            isStageCompleted
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : isStageActive
                              ? 'bg-indigo-500/30 text-indigo-300 border border-indigo-400 animate-pulse'
                              : 'bg-gray-800 text-gray-500 border border-gray-700'
                          }`}
                        >
                          {isStageCompleted ? '✓' : idx + 1}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-white">{stage.name}</p>
                          <p className="text-xs text-gray-400">{stage.desc}</p>
                        </div>
                      </div>

                      <div className="text-right">
                        <span
                          className={`text-xs font-mono font-medium px-2.5 py-1 rounded-md ${
                            isStageCompleted
                              ? 'bg-emerald-900/40 text-emerald-300'
                              : isStageActive
                              ? 'bg-indigo-900/50 text-indigo-200'
                              : 'bg-gray-800 text-gray-400'
                          }`}
                        >
                          {stage.count}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Completed Success Banner */}
            {isCompleted && (
              <div className="bg-gradient-to-r from-emerald-950/70 to-teal-950/70 border border-emerald-500/40 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-4 text-left">
                  <span className="text-4xl">🎉</span>
                  <div>
                    <h3 className="text-lg font-bold text-white">Discovery & Analysis Finished!</h3>
                    <p className="text-emerald-200/90 text-xs mt-0.5">
                      Successfully crawled, verified guest posting acceptance, and scored {scoredCount} websites.
                    </p>
                  </div>
                </div>

                <Link
                  to={`/results?searchId=${searchData.id}`}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-6 py-2.5 rounded-xl text-sm shadow-md transition-all shrink-0"
                >
                  Explore Opportunities →
                </Link>
              </div>
            )}
          </>
        )}
      </div>
    </PageContainer>
  );
};

export default SearchProgress;
