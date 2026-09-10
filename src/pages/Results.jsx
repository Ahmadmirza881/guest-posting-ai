import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, useLocation, Link } from 'react-router-dom';
import PageContainer from '../components/PageContainer';
import { api, downloadBlob } from '../services/api';
import { useAuth } from '../context/useAuth';

const Results = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const searchIdFromUrl = searchParams.get('searchId');
  const { isAuthenticated } = useAuth();

  const [searchData, setSearchData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filter state
  // Filter state
  const [filters, setFilters] = useState({
    guestPostStatus: 'all',
    pricing: 'all',
    minQualityScore: 0,
    nicheRelevant: false,
    dofollow: false,
  });

  // Sorting state
  const [sortBy, setSortBy] = useState('quality-desc');

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const resultsPerPage = 10;

  // Step 20: Saved websites tracking and CSV export
  const [savedWebsiteIds, setSavedWebsiteIds] = useState(new Set());
  const [savingId, setSavingId] = useState(null);
  const [exportingCsv, setExportingCsv] = useState(false);

  useEffect(() => {
    let isMounted = true;
    if (!isAuthenticated) return;

    const loadSaved = async () => {
      try {
        const res = await api.getSavedWebsites(1, 100);
        if (isMounted && res.items) {
          setSavedWebsiteIds(new Set(res.items.map((it) => it.website_id)));
        }
      } catch (e) {
        console.warn('Could not load saved website IDs:', e);
      }
    };
    loadSaved();
    return () => {
      isMounted = false;
    };
  }, [isAuthenticated]);

  const effectiveSavedWebsiteIds = isAuthenticated ? savedWebsiteIds : new Set();

  const handleToggleSave = async (websiteId, e) => {
    if (e) e.stopPropagation();
    if (!isAuthenticated) {
      navigate('/login', { state: { from: location } });
      return;
    }
    setSavingId(websiteId);
    const isCurrentlySaved = savedWebsiteIds.has(websiteId);
    try {
      if (isCurrentlySaved) {
        await api.unsaveWebsite(websiteId);
        setSavedWebsiteIds((prev) => {
          const next = new Set(prev);
          next.delete(websiteId);
          return next;
        });
      } else {
        await api.saveWebsite(websiteId);
        setSavedWebsiteIds((prev) => {
          const next = new Set(prev);
          next.add(websiteId);
          return next;
        });
      }
    } catch (err) {
      console.error('Failed to update bookmark:', err);
      alert(err.message || 'Failed to update saved status.');
    } finally {
      setSavingId(null);
    }
  };

  const handleExportFilteredCsv = async () => {
    setExportingCsv(true);
    try {
      const exportParams = {
        search_id: searchData?.id,
        guest_post_status: filters.guestPostStatus !== 'all' ? filters.guestPostStatus : undefined,
        pricing: filters.pricing !== 'all' ? filters.pricing : undefined,
        min_quality_score: filters.minQualityScore > 0 ? filters.minQualityScore : undefined,
        min_relevance_score: filters.nicheRelevant ? 80 : undefined,
      };
      const blob = await api.exportWebsitesCsv(exportParams);
      const filename = `guest_posting_results_search_${searchData?.id || 'all'}.csv`;
      downloadBlob(blob, filename);
    } catch (err) {
      console.error('Failed to export CSV:', err);
      alert(err.message || 'Failed to export CSV.');
    } finally {
      setExportingCsv(false);
    }
  };

  useEffect(() => {
    let isMounted = true;

    const fetchResults = async () => {
      setLoading(true);
      setError(null);

      try {
        let targetSearchId = searchIdFromUrl;

        // If no searchId provided in URL, look for the most recent search
        if (!targetSearchId) {
          const historyRes = await api.listSearches(0, 1);
          if (historyRes.searches && historyRes.searches.length > 0) {
            targetSearchId = historyRes.searches[0].id;
          }
        }

        if (targetSearchId) {
          const data = await api.getSearch(targetSearchId);
          if (isMounted) {
            setSearchData(data);
          }
        } else {
          if (isMounted) {
            setSearchData(null);
          }
        }
      } catch (err) {
        console.error('Failed to load search results:', err);
        if (isMounted) {
          setError(err.message || 'Failed to retrieve results from backend.');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchResults();

    return () => {
      isMounted = false;
    };
  }, [searchIdFromUrl]);

  const rawResults = searchData?.results || [];

  // Apply filters and sorting
  const getFilteredAndSortedResults = () => {
    let filtered = [...rawResults];

    // Apply filters
    if (filters.guestPostStatus !== 'all') {
      const isAccepting = filters.guestPostStatus === 'accepting';
      filtered = filtered.filter(result => result.accepts_guest_posts === isAccepting);
    }
    if (filters.pricing !== 'all') {
      filtered = filtered.filter(result =>
        (result.pricing || '').toLowerCase() === filters.pricing.toLowerCase()
      );
    }
    if (filters.minQualityScore > 0) {
      filtered = filtered.filter(result => (result.quality_score || 0) >= filters.minQualityScore);
    }
    if (filters.nicheRelevant) {
      filtered = filtered.filter(result => (result.relevance || 0) >= 80);
    }
    if (filters.dofollow) {
      filtered = filtered.filter(result => (result.quality_score || 0) >= 85);
    }

    // Apply sorting
    switch (sortBy) {
      case 'quality-desc':
        filtered.sort((a, b) => (b.quality_score || 0) - (a.quality_score || 0));
        break;
      case 'quality-asc':
        filtered.sort((a, b) => (a.quality_score || 0) - (b.quality_score || 0));
        break;
      case 'relevance-desc':
        filtered.sort((a, b) => (b.relevance || 0) - (a.relevance || 0));
        break;
      case 'name-asc':
        filtered.sort((a, b) => (a.domain || '').localeCompare(b.domain || ''));
        break;
      default:
        break;
    }

    return filtered;
  };

  const filteredResults = getFilteredAndSortedResults();

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filteredResults.length / resultsPerPage));
  const startIndex = (currentPage - 1) * resultsPerPage;
  const endIndex = startIndex + resultsPerPage;
  const currentResults = filteredResults.slice(startIndex, endIndex);

  const handleFilterChange = (filterName, value) => {
    setFilters(prev => ({ ...prev, [filterName]: value }));
    setCurrentPage(1);
  };

  const handleResetFilters = () => {
    setFilters({
      guestPostStatus: 'all',
      pricing: 'all',
      minQualityScore: 0,
      nicheRelevant: false,
      dofollow: false,
    });
    setCurrentPage(1);
  };

  const getStatusBadge = (accepts) => {
    if (accepts === true) {
      return (
        <span className="bg-green-600/90 text-white text-xs px-2.5 py-1 rounded-full font-medium">
          Accepting
        </span>
      );
    }
    if (accepts === false) {
      return (
        <span className="bg-red-600/90 text-white text-xs px-2.5 py-1 rounded-full font-medium">
          Not Accepting
        </span>
      );
    }
    return (
      <span className="bg-gray-600 text-gray-300 text-xs px-2.5 py-1 rounded-full font-medium">
        Pending Check
      </span>
    );
  };

  const getPricingBadge = (pricing) => {
    if (!pricing) {
      return <span className="text-gray-400 text-xs">—</span>;
    }
    const isFree = pricing.toLowerCase() === 'free';
    return (
      <span className={`${isFree ? 'bg-blue-600/90' : 'bg-purple-600/90'} text-white text-xs px-2.5 py-1 rounded-full font-medium capitalize`}>
        {pricing}
      </span>
    );
  };

  const getQualityScoreColor = (score) => {
    if (!score && score !== 0) return 'text-gray-400';
    if (score >= 90) return 'text-green-400';
    if (score >= 80) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <PageContainer title="Search Results">
      <div className="space-y-6">
        {/* Loading State */}
        {loading && (
          <div className="bg-gray-700 rounded-xl p-12 border border-gray-600 text-center">
            <div className="inline-block w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-gray-300">Loading search results from backend...</p>
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div className="bg-red-900/40 border border-red-500/50 rounded-xl p-6 text-red-200">
            <div className="flex items-start gap-3">
              <span className="text-2xl">⚠️</span>
              <div>
                <h3 className="font-semibold text-lg">Error Loading Results</h3>
                <p className="text-sm text-red-300 mt-1">{error}</p>
                <div className="mt-4 flex gap-3">
                  <Link
                    to="/search"
                    className="bg-red-700 hover:bg-red-600 text-white text-sm px-4 py-2 rounded-lg transition-colors"
                  >
                    Start New Search
                  </Link>
                  <Link
                    to="/history"
                    className="bg-gray-700 hover:bg-gray-600 text-white text-sm px-4 py-2 rounded-lg transition-colors"
                  >
                    View History
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* No Searches in Database */}
        {!loading && !error && !searchData && (
          <div className="bg-gray-700 rounded-xl p-8 border border-gray-600 text-center">
            <div className="text-6xl mb-4">🔍</div>
            <h3 className="text-xl font-bold text-white mb-2">No Searches Found</h3>
            <p className="text-gray-400 mb-6">
              You have not performed any searches yet. Start a search to discover guest posting opportunities.
            </p>
            <Link
              to="/search"
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg font-medium transition-colors inline-block"
            >
              Start First Search
            </Link>
          </div>
        )}

        {/* Search Data Available */}
        {!loading && !error && searchData && (
          <>
            {/* Page Header */}
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold text-white mb-1">
                  Results for &ldquo;{searchData.keyword}&rdquo;
                </h2>
                <p className="text-gray-400 text-sm">
                  Search ID #{searchData.id} • Target: {searchData.requested_website_count} websites • Status: <span className="capitalize font-semibold text-indigo-400">{searchData.status}</span>
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={handleExportFilteredCsv}
                  disabled={exportingCsv || rawResults.length === 0}
                  className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors font-medium flex items-center gap-1.5 cursor-pointer shadow-sm"
                  title="Export filtered opportunities to CSV"
                >
                  {exportingCsv ? (
                    <>
                      <span className="inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                      <span>Exporting...</span>
                    </>
                  ) : (
                    <>
                      <span>📥</span>
                      <span>Export CSV</span>
                    </>
                  )}
                </button>
                <Link
                  to={`/search/progress?searchId=${searchData.id}`}
                  className="bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm px-4 py-2 rounded-lg border border-gray-600 transition-colors"
                >
                  Check Status
                </Link>
                <Link
                  to="/search"
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-4 py-2 rounded-lg transition-colors"
                >
                  New Search
                </Link>
              </div>
            </div>

            {/* Results Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-700 rounded-xl p-4 border border-gray-600">
                <p className="text-gray-400 text-sm mb-1">Requested Count</p>
                <p className="text-2xl font-bold text-white">{searchData.requested_website_count}</p>
              </div>
              <div className="bg-gray-700 rounded-xl p-4 border border-gray-600">
                <p className="text-gray-400 text-sm mb-1">Discovered Results</p>
                <p className="text-2xl font-bold text-white">{searchData.total_results || 0}</p>
              </div>
              <div className="bg-gray-700 rounded-xl p-4 border border-gray-600">
                <p className="text-gray-400 text-sm mb-1">Accepting Guest Posts</p>
                <p className="text-2xl font-bold text-white">
                  {rawResults.filter(r => r.accepts_guest_posts === true).length}
                </p>
              </div>
              <div className="bg-gray-700 rounded-xl p-4 border border-gray-600">
                <p className="text-gray-400 text-sm mb-1">Backend Pipeline</p>
                <p className="text-lg font-bold text-indigo-300 capitalize">{searchData.status}</p>
              </div>
            </div>

            {/* Results Table & Filter Section if results exist */}
            {rawResults.length > 0 ? (
              <>
                {/* Filters and Sorting */}
                <div className="bg-gray-700 rounded-xl p-4 border border-gray-600">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {/* Guest Post Status Filter */}
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Guest Post Status
                      </label>
                      <select
                        value={filters.guestPostStatus}
                        onChange={(e) => handleFilterChange('guestPostStatus', e.target.value)}
                        className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="all">All</option>
                        <option value="accepting">Accepting</option>
                        <option value="not-accepting">Not Accepting</option>
                      </select>
                    </div>

                    {/* Pricing Filter */}
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Pricing
                      </label>
                      <select
                        value={filters.pricing}
                        onChange={(e) => handleFilterChange('pricing', e.target.value)}
                        className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="all">All</option>
                        <option value="free">Free</option>
                        <option value="paid">Paid</option>
                      </select>
                    </div>

                    {/* Minimum Quality Score */}
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Minimum Quality Score: {filters.minQualityScore}
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={filters.minQualityScore}
                        onChange={(e) => handleFilterChange('minQualityScore', parseInt(e.target.value))}
                        className="w-full"
                      />
                    </div>

                    {/* Sorting */}
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Sort By
                      </label>
                      <select
                        value={sortBy}
                        onChange={(e) => setSortBy(e.target.value)}
                        className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="quality-desc">Quality Score — High to Low</option>
                        <option value="quality-asc">Quality Score — Low to High</option>
                        <option value="relevance-desc">Relevance — High to Low</option>
                        <option value="name-asc">Domain — A to Z</option>
                      </select>
                    </div>

                    {/* Additional Filters */}
                    <div className="flex items-center gap-4 pt-6">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={filters.nicheRelevant}
                          onChange={(e) => handleFilterChange('nicheRelevant', e.target.checked)}
                          className="w-4 h-4 bg-gray-800 border-gray-600 rounded focus:ring-indigo-500"
                        />
                        <span className="text-sm text-gray-300">Niche Relevant</span>
                      </label>
                    </div>

                    {/* Reset Filters */}
                    <div className="flex items-end">
                      <button
                        onClick={handleResetFilters}
                        className="bg-gray-600 hover:bg-gray-500 text-white text-sm px-4 py-2 rounded-lg transition-colors cursor-pointer"
                      >
                        Reset Filters
                      </button>
                    </div>
                  </div>
                </div>

                {/* Table View */}
                {currentResults.length > 0 ? (
                  <>
                    <div className="bg-gray-700 rounded-xl border border-gray-600 overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead className="bg-gray-800">
                            <tr>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-white">Domain</th>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-white">Guest Post Status</th>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-white">Pricing</th>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-white">Submission</th>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-white">Relevance</th>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-white">Quality Score</th>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-white">Actions</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-600">
                            {currentResults.map((result) => (
                              <tr key={result.id} className="hover:bg-gray-600/70 transition-colors">
                                <td className="px-4 py-3 text-white font-medium">
                                  <div>{result.domain}</div>
                                  {result.name && <div className="text-xs text-gray-400">{result.name}</div>}
                                </td>
                                <td className="px-4 py-3">{getStatusBadge(result.accepts_guest_posts)}</td>
                                <td className="px-4 py-3">{getPricingBadge(result.pricing)}</td>
                                <td className="px-4 py-3 text-gray-300 text-sm">
                                  {result.submission_method || '—'}
                                </td>
                                <td className="px-4 py-3 text-gray-300 text-sm">
                                  {result.relevance != null ? `${result.relevance}%` : '—'}
                                </td>
                                <td className="px-4 py-3">
                                  {result.quality_score != null ? (
                                    <span className={`font-bold ${getQualityScoreColor(result.quality_score)}`}>
                                      {result.quality_score}/100
                                    </span>
                                  ) : (
                                    <span className="text-gray-400 text-sm">—</span>
                                  )}
                                </td>
                                <td className="px-4 py-3">
                                  <div className="flex items-center gap-2">
                                    <button
                                      onClick={() => navigate(`/website/${result.website_id}`)}
                                      className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-3 py-1.5 rounded transition-colors cursor-pointer"
                                    >
                                      View Details
                                    </button>
                                    <button
                                      onClick={(e) => handleToggleSave(result.website_id, e)}
                                      disabled={savingId === result.website_id}
                                      className={`text-sm px-2.5 py-1.5 rounded transition-colors cursor-pointer flex items-center gap-1 font-medium ${
                                        effectiveSavedWebsiteIds.has(result.website_id)
                                          ? 'bg-amber-900/60 text-amber-300 border border-amber-500/50 hover:bg-amber-800/80'
                                          : 'bg-gray-800 text-gray-400 hover:text-white border border-gray-600 hover:bg-gray-700'
                                      }`}
                                      title={effectiveSavedWebsiteIds.has(result.website_id) ? 'Remove bookmark' : 'Bookmark website'}
                                    >
                                      {savingId === result.website_id ? (
                                        <span className="inline-block w-3.5 h-3.5 border border-current border-t-transparent rounded-full animate-spin"></span>
                                      ) : (
                                        <span>{effectiveSavedWebsiteIds.has(result.website_id) ? '★' : '☆'}</span>
                                      )}
                                      <span className="text-xs">
                                        {effectiveSavedWebsiteIds.has(result.website_id) ? 'Saved' : 'Save'}
                                      </span>
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Pagination */}
                    <div className="flex items-center justify-between">
                      <div className="text-gray-400 text-sm">
                        Showing {startIndex + 1}-{Math.min(endIndex, filteredResults.length)} of {filteredResults.length} results
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                          disabled={currentPage === 1}
                          className="bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed text-white px-3 py-1.5 rounded-lg transition-colors text-sm cursor-pointer"
                        >
                          Previous
                        </button>
                        <span className="text-gray-300 text-sm px-2">
                          Page {currentPage} of {totalPages}
                        </span>
                        <button
                          onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                          disabled={currentPage === totalPages}
                          className="bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed text-white px-3 py-1.5 rounded-lg transition-colors text-sm cursor-pointer"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  /* Filter Empty State */
                  <div className="bg-gray-700 rounded-xl p-8 border border-gray-600 text-center">
                    <div className="text-5xl mb-3">🔍</div>
                    <h3 className="text-lg font-bold text-white mb-2">No Matching Results</h3>
                    <p className="text-gray-400 mb-4 text-sm">
                      No results matched the currently selected filter options.
                    </p>
                    <button
                      onClick={handleResetFilters}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-5 py-2 rounded-lg transition-colors cursor-pointer"
                    >
                      Reset Filters
                    </button>
                  </div>
                )}
              </>
            ) : (
              /* No Discovered Websites Yet for this Search */
              <div className="bg-gray-700 rounded-xl p-8 border border-gray-600 text-center space-y-4">
                <div className="text-5xl">🌐</div>
                <h3 className="text-xl font-bold text-white">No Discovered Websites Yet</h3>
                <p className="text-gray-300 max-w-lg mx-auto text-sm leading-relaxed">
                  Search <span className="font-semibold text-white">#{searchData.id}</span> for &ldquo;<span className="text-indigo-400 font-semibold">{searchData.keyword}</span>&rdquo; has been created in the database.
                </p>
                <div className="bg-gray-800/80 max-w-md mx-auto p-4 rounded-lg border border-gray-600 text-left text-xs text-gray-400 space-y-1">
                  <p className="text-gray-300 font-semibold mb-1">Automated Pipeline Capabilities:</p>
                  <p>• Automated multi-provider discovery & URL candidate processing</p>
                  <p>• Page crawling & guest post guideline extraction</p>
                  <p>• Gemini AI semantic verification & deterministic quality scoring</p>
                </div>
                <div className="flex justify-center gap-4 pt-2">
                  <Link
                    to="/search"
                    className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-6 py-2.5 rounded-lg transition-colors font-medium"
                  >
                    Start New Search
                  </Link>
                  <Link
                    to="/history"
                    className="bg-gray-600 hover:bg-gray-500 text-white text-sm px-6 py-2.5 rounded-lg transition-colors font-medium"
                  >
                    View Search History
                  </Link>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </PageContainer>
  );
};

export default Results;
