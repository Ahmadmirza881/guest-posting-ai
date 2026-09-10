import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import PageContainer from '../components/PageContainer';
import { api, downloadBlob } from '../services/api';

const Saved = () => {
  const navigate = useNavigate();
  const [savedWebsites, setSavedWebsites] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [unsavingId, setUnsavingId] = useState(null);
  const [exportingCsv, setExportingCsv] = useState(false);

  const pageSize = 15;

  useEffect(() => {
    let isMounted = true;

    const loadSavedWebsites = async () => {
      try {
        const data = await api.getSavedWebsites(currentPage, pageSize);
        if (isMounted) {
          setSavedWebsites(data.items || []);
          setTotalCount(data.total || 0);
          setTotalPages(data.total_pages || 1);
          setError(null);
        }
      } catch (err) {
        console.error('Failed to load saved websites:', err);
        if (isMounted) {
          setError(err.message || 'Failed to retrieve saved websites from server.');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadSavedWebsites();

    return () => {
      isMounted = false;
    };
  }, [currentPage, pageSize]);

  const reloadSavedWebsites = () => {
    setLoading(true);
    api.getSavedWebsites(currentPage, pageSize)
      .then((data) => {
        setSavedWebsites(data.items || []);
        setTotalCount(data.total || 0);
        setTotalPages(data.total_pages || 1);
        setError(null);
      })
      .catch((err) => {
        setError(err.message || 'Failed to retrieve saved websites.');
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const handleUnsave = async (websiteId, e) => {
    if (e) e.stopPropagation();
    setUnsavingId(websiteId);
    try {
      await api.unsaveWebsite(websiteId);
      // Remove from local list or refetch
      setSavedWebsites((prev) => prev.filter((item) => item.website_id !== websiteId));
      setTotalCount((prev) => Math.max(0, prev - 1));
    } catch (err) {
      console.error('Failed to unsave website:', err);
      alert(err.message || 'Failed to remove website from saved list.');
    } finally {
      setUnsavingId(null);
    }
  };

  const handleExportCsv = async () => {
    setExportingCsv(true);
    try {
      const blob = await api.exportSavedWebsitesCsv();
      downloadBlob(blob, 'saved_guest_posting_websites.csv');
    } catch (err) {
      console.error('Failed to export CSV:', err);
      alert(err.message || 'Failed to export saved websites CSV.');
    } finally {
      setExportingCsv(false);
    }
  };

  // Badge helpers
  const getStatusBadge = (accepts) => {
    if (accepts === true) {
      return (
        <span className="bg-green-900/60 text-green-300 border border-green-500/40 text-xs px-2.5 py-0.5 rounded-full font-medium">
          ✓ Accepting
        </span>
      );
    }
    if (accepts === false) {
      return (
        <span className="bg-red-900/60 text-red-300 border border-red-500/40 text-xs px-2.5 py-0.5 rounded-full font-medium">
          ✗ Not Accepting
        </span>
      );
    }
    return (
      <span className="bg-gray-800 text-gray-400 border border-gray-600 text-xs px-2.5 py-0.5 rounded-full font-medium">
        Pending Check
      </span>
    );
  };

  const getPricingBadge = (pricing) => {
    if (!pricing || pricing === 'unknown') {
      return <span className="text-gray-400 text-xs">—</span>;
    }
    const isFree = pricing.toLowerCase() === 'free';
    return (
      <span
        className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
          isFree
            ? 'bg-blue-900/60 text-blue-300 border border-blue-500/40'
            : 'bg-purple-900/60 text-purple-300 border border-purple-500/40'
        }`}
      >
        {pricing}
      </span>
    );
  };

  const getQualityScoreColor = (score) => {
    if (score == null) return 'text-gray-400';
    if (score >= 80) return 'text-green-400';
    if (score >= 60) return 'text-blue-400';
    if (score >= 40) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <PageContainer title="Saved Websites">
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-gray-700">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <span>⭐</span>
              <span>Saved Websites</span>
            </h2>
            <p className="text-gray-400 text-sm mt-1">
              Curated list of bookmarked guest posting opportunities ({totalCount} total)
            </p>
          </div>
          <div className="flex items-center gap-3">
            {totalCount > 0 && (
              <button
                onClick={handleExportCsv}
                disabled={exportingCsv}
                className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors font-medium flex items-center gap-2 cursor-pointer shadow-sm"
                title="Export all saved websites to CSV file"
              >
                {exportingCsv ? (
                  <>
                    <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    <span>Exporting...</span>
                  </>
                ) : (
                  <>
                    <span>📥</span>
                    <span>Export CSV</span>
                  </>
                )}
              </button>
            )}
            <Link
              to="/search"
              className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-4 py-2 rounded-lg transition-colors font-medium inline-flex items-center gap-1.5"
            >
              <span>🔍</span>
              <span>Find More</span>
            </Link>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="bg-gray-800 rounded-xl p-12 border border-gray-700 text-center">
            <div className="inline-block w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-gray-300">Loading your saved opportunities...</p>
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div className="bg-red-900/40 border border-red-500/50 rounded-xl p-6 text-red-200">
            <div className="flex items-start gap-3">
              <span className="text-2xl">⚠️</span>
              <div>
                <h3 className="font-semibold text-lg">Unable to Load Saved Websites</h3>
                <p className="text-sm text-red-300 mt-1">{error}</p>
                <div className="mt-4 flex gap-3">
                  <button
                    onClick={reloadSavedWebsites}
                    className="bg-red-700 hover:bg-red-600 text-white text-sm px-4 py-2 rounded-lg transition-colors cursor-pointer"
                  >
                    Retry
                  </button>
                  <Link
                    to="/search"
                    className="bg-gray-700 hover:bg-gray-600 text-white text-sm px-4 py-2 rounded-lg transition-colors"
                  >
                    Go to Search
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && savedWebsites.length === 0 && (
          <div className="bg-gray-800 rounded-xl p-12 border border-gray-700 text-center space-y-4 max-w-lg mx-auto">
            <div className="text-6xl mb-2">⭐</div>
            <h3 className="text-xl font-bold text-white">No Saved Websites Yet</h3>
            <p className="text-gray-400 text-sm leading-relaxed">
              When you discover promising guest posting opportunities in search results or website details,
              click the star icon to bookmark them here for easy outreach.
            </p>
            <div className="pt-2">
              <Link
                to="/search"
                className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-6 py-2.5 rounded-lg transition-colors font-medium inline-block shadow-md"
              >
                Discover Opportunities
              </Link>
            </div>
          </div>
        )}

        {/* Saved Websites List Table */}
        {!loading && !error && savedWebsites.length > 0 && (
          <>
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-900/80 border-b border-gray-700">
                    <tr>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Domain &amp; Name
                      </th>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Niche
                      </th>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Guest Post Status
                      </th>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Pricing
                      </th>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Quality Score
                      </th>
                      <th className="px-4 py-3.5 text-left text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Submission
                      </th>
                      <th className="px-4 py-3.5 text-right text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-700">
                    {savedWebsites.map((item) => (
                      <tr
                        key={item.id}
                        className="hover:bg-gray-700/50 transition-colors cursor-pointer"
                        onClick={() => navigate(`/website/${item.website_id}`)}
                      >
                        <td className="px-4 py-3.5">
                          <div className="font-semibold text-white text-sm hover:text-indigo-400 transition-colors">
                            {item.domain}
                          </div>
                          {item.name && (
                            <div className="text-xs text-gray-400 mt-0.5 line-clamp-1">
                              {item.name}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3.5">
                          {item.niche ? (
                            <span className="bg-gray-700 text-gray-200 text-xs px-2.5 py-1 rounded-md font-medium border border-gray-600 inline-block max-w-[150px] truncate">
                              {item.niche}
                            </span>
                          ) : (
                            <span className="text-gray-500 text-xs">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5">{getStatusBadge(item.accepts_guest_posts)}</td>
                        <td className="px-4 py-3.5">{getPricingBadge(item.pricing)}</td>
                        <td className="px-4 py-3.5">
                          {item.quality_score != null ? (
                            <div className="flex items-center gap-1.5">
                              <span className={`font-bold text-sm ${getQualityScoreColor(item.quality_score)}`}>
                                {item.quality_score}
                              </span>
                              <span className="text-gray-500 text-xs">/100</span>
                            </div>
                          ) : (
                            <span className="text-gray-500 text-xs">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5">
                          <span className="text-gray-300 text-xs font-medium capitalize">
                            {item.submission_method || '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-right">
                          <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => navigate(`/website/${item.website_id}`)}
                              className="bg-indigo-600/80 hover:bg-indigo-600 text-white text-xs px-3 py-1.5 rounded-lg transition-colors cursor-pointer font-medium"
                            >
                              View Details
                            </button>
                            <button
                              onClick={(e) => handleUnsave(item.website_id, e)}
                              disabled={unsavingId === item.website_id}
                              className="bg-gray-700 hover:bg-red-900/60 text-amber-300 hover:text-red-300 border border-gray-600 hover:border-red-500/50 text-xs px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer flex items-center gap-1 font-medium"
                              title="Remove from saved websites"
                            >
                              {unsavingId === item.website_id ? (
                                <span className="inline-block w-3 h-3 border border-amber-300 border-t-transparent rounded-full animate-spin"></span>
                              ) : (
                                <span>★</span>
                              )}
                              <span>Saved</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-2">
                <p className="text-gray-400 text-xs">
                  Showing page {currentPage} of {totalPages} ({totalCount} total opportunities)
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage <= 1}
                    className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-300 text-xs px-3 py-1.5 rounded-lg border border-gray-700 transition-colors cursor-pointer"
                  >
                    Previous
                  </button>
                  <span className="text-xs text-gray-400 px-2">
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-300 text-xs px-3 py-1.5 rounded-lg border border-gray-700 transition-colors cursor-pointer"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </PageContainer>
  );
};

export default Saved;
