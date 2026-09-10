import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import PageContainer from '../components/PageContainer';
import { api } from '../services/api';

const History = () => {
  const navigate = useNavigate();
  const [searches, setSearches] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let isMounted = true;

    const fetchHistory = async () => {
      try {
        const data = await api.listSearches(0, 50);
        if (isMounted) {
          setSearches(data.searches || []);
          setTotal(data.total || 0);
          setError(null);
        }
      } catch (err) {
        console.error('Failed to load search history:', err);
        if (isMounted) {
          setError(
            err.message || 'Unable to retrieve search history from backend service.'
          );
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchHistory();

    return () => {
      isMounted = false;
    };
  }, [reloadKey]);

  const handleRetry = () => {
    setLoading(true);
    setReloadKey(k => k + 1);
  };

  const handleDeleteSearch = async (searchId, keyword) => {
    if (!window.confirm(`Are you sure you want to delete search #${searchId} ("${keyword}")? This cannot be undone.`)) {
      return;
    }

    setDeletingId(searchId);
    setActionMessage(null);

    try {
      await api.deleteSearch(searchId);
      setSearches(prev => prev.filter(s => s.id !== searchId));
      setTotal(prev => Math.max(0, prev - 1));
      setActionMessage({
        type: 'success',
        text: `Search #${searchId} deleted successfully.`,
      });
    } catch (err) {
      console.error('Failed to delete search:', err);
      setActionMessage({
        type: 'error',
        text: err.message || `Failed to delete search #${searchId}.`,
      });
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <PageContainer title="Search History">
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-white mb-1">Search History</h2>
            <p className="text-gray-400 text-sm">
              Review and access all previously executed guest-posting searches.
            </p>
          </div>
          <Link
            to="/search"
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-5 py-2.5 rounded-lg transition-colors font-medium self-start md:self-auto"
          >
            + Start New Search
          </Link>
        </div>

        {/* Action Message Alert */}
        {actionMessage && (
          <div
            className={`p-4 rounded-xl border text-sm flex items-center justify-between ${
              actionMessage.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-300'
                : 'bg-red-900/40 border-red-500/50 text-red-200'
            }`}
          >
            <span>{actionMessage.text}</span>
            <button
              onClick={() => setActionMessage(null)}
              className="text-gray-400 hover:text-white text-xs ml-4 cursor-pointer"
            >
              ✕
            </button>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="bg-gray-700 rounded-xl p-12 border border-gray-600 text-center">
            <div className="inline-block w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-gray-300">Loading search history from backend...</p>
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div className="bg-red-900/40 border border-red-500/50 rounded-xl p-6 text-red-200">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <span className="text-2xl">⚠️</span>
                <div>
                  <h3 className="font-semibold text-lg">Error Loading Search History</h3>
                  <p className="text-sm text-red-300 mt-1">{error}</p>
                </div>
              </div>
              <button
                onClick={handleRetry}
                className="bg-red-700 hover:bg-red-600 text-white text-xs px-4 py-2 rounded-lg transition-colors cursor-pointer"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && searches.length === 0 && (
          <div className="bg-gray-700 rounded-xl p-12 border border-gray-600 text-center space-y-4">
            <div className="text-6xl">📜</div>
            <h3 className="text-xl font-bold text-white">No Searches Yet</h3>
            <p className="text-gray-400 max-w-md mx-auto text-sm">
              You have not performed any searches yet. Start a new search to discover guest posting opportunities.
            </p>
            <Link
              to="/search"
              className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-6 py-2.5 rounded-lg transition-colors font-medium inline-block"
            >
              Start First Search
            </Link>
          </div>
        )}

        {/* Searches Table / List */}
        {!loading && !error && searches.length > 0 && (
          <>
            <div className="bg-gray-700 rounded-xl border border-gray-600 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-800">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-white">Search ID</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-white">Keyword / Niche</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-white">Target Websites</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-white">Discovered</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-white">Status</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-white">Created Date</th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-white">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-600">
                    {searches.map((s) => (
                      <tr key={s.id} className="hover:bg-gray-600/70 transition-colors">
                        <td className="px-4 py-3 text-white font-mono text-sm">#{s.id}</td>
                        <td className="px-4 py-3 text-white font-medium">{s.keyword}</td>
                        <td className="px-4 py-3 text-gray-300 text-sm">{s.requested_website_count}</td>
                        <td className="px-4 py-3 text-gray-300 text-sm">{s.results_count || 0}</td>
                        <td className="px-4 py-3">
                          <span className="bg-indigo-900/60 text-indigo-300 border border-indigo-500/40 text-xs px-2.5 py-1 rounded-full font-medium capitalize">
                            {s.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-400 text-xs">
                          {new Date(s.created_at).toLocaleString()}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => navigate(`/results?searchId=${s.id}`)}
                              className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs px-3 py-1.5 rounded transition-colors cursor-pointer"
                            >
                              Results
                            </button>
                            <button
                              onClick={() => navigate(`/search/progress?searchId=${s.id}`)}
                              className="bg-gray-600 hover:bg-gray-500 text-white text-xs px-3 py-1.5 rounded transition-colors cursor-pointer"
                            >
                              Status
                            </button>
                            <button
                              onClick={() => handleDeleteSearch(s.id, s.keyword)}
                              disabled={deletingId === s.id}
                              className="bg-red-600/80 hover:bg-red-600 text-white text-xs px-2.5 py-1.5 rounded transition-colors cursor-pointer disabled:opacity-50"
                              title="Delete search"
                            >
                              {deletingId === s.id ? '...' : '🗑️'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="text-gray-400 text-sm text-right">
              Total searches recorded: <span className="font-semibold text-white">{total}</span>
            </div>
          </>
        )}
      </div>
    </PageContainer>
  );
};

export default History;

