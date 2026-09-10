import { useState } from 'react';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import PageContainer from '../components/PageContainer';
import { api } from '../services/api';

const Search = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const [niche, setNiche] = useState(() => {
    return searchParams.get('keyword') || location.state?.keyword || '';
  });
  const [numWebsites, setNumWebsites] = useState('100');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [filters, setFilters] = useState({
    freeGuestPosts: false,
    paidGuestPosts: false,
    dofollow: false,
    nicheRelevant: false,
    highQuality: false,
  });

  const handleFilterChange = (filterName) => {
    setFilters(prev => ({
      ...prev,
      [filterName]: !prev[filterName]
    }));
  };

  const handleStartSearch = async (e) => {
    if (e) e.preventDefault();
    if (!niche.trim() || loading) return;

    setLoading(true);
    setError(null);

    try {
      const response = await api.createSearch({
        keyword: niche.trim(),
        requestedWebsiteCount: parseInt(numWebsites, 10),
      });

      // Navigate to search progress with search ID from backend
      navigate(`/search/progress?searchId=${response.id}`, {
        state: {
          searchId: response.id,
          keyword: response.keyword,
          requestedCount: response.requested_website_count,
        }
      });
    } catch (err) {
      console.error('Failed to create search:', err);
      const isConnectionError =
        !err.message ||
        err.message === 'Failed to fetch' ||
        err.message.includes('backend') ||
        err.message.includes('connect');
      setError(
        isConnectionError
          ? 'Unable to connect to the backend server. Please check your network and try again.'
          : err.message
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageContainer title="New Search">
      <div className="max-w-2xl mx-auto space-y-8">
        {/* Page Header */}
        <div className="text-center py-6">
          <h2 className="text-2xl font-bold text-white mb-2">New Search</h2>
          <p className="text-gray-400">
            Enter a niche or keyword to discover guest posting opportunities tailored to your content strategy.
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="bg-red-900/40 border border-red-500/50 rounded-xl p-4 text-red-200">
            <div className="flex items-start gap-3">
              <span className="text-xl">⚠️</span>
              <div className="flex-1">
                <p className="font-semibold">Search Creation Error</p>
                <p className="text-sm text-red-300 mt-1">{error}</p>
              </div>
              <button
                type="button"
                onClick={() => setError(null)}
                className="text-red-400 hover:text-red-200 text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        <form onSubmit={handleStartSearch} className="space-y-8">
          {/* Niche / Keyword Input */}
          <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
            <label htmlFor="search-keyword" className="block text-lg font-semibold text-white mb-3">
              Niche or Keyword
            </label>
            <input
              id="search-keyword"
              type="text"
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              placeholder="Enter a niche or keyword..."
              disabled={loading}
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            />
            <p className="text-gray-500 text-sm mt-2">
              Examples: AI, Machine Learning, Technology, Digital Marketing
            </p>
          </div>

          {/* Number of Websites */}
          <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
            <label htmlFor="num-websites-select" className="block text-lg font-semibold text-white mb-3">
              Number of Websites
            </label>
            <select
              id="num-websites-select"
              value={numWebsites}
              onChange={(e) => setNumWebsites(e.target.value)}
              disabled={loading}
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="250">250</option>
              <option value="500">500</option>
            </select>
            <p className="text-gray-500 text-sm mt-2">
              Select how many websites you want to search for
            </p>
          </div>

          {/* Filters */}
          <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
            <label className="block text-lg font-semibold text-white mb-4">
              Filters
            </label>
            <div className="space-y-3">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={filters.freeGuestPosts}
                  onChange={() => handleFilterChange('freeGuestPosts')}
                  disabled={loading}
                  className="w-5 h-5 bg-gray-800 border-gray-600 rounded focus:ring-indigo-500 focus:ring-offset-gray-700"
                />
                <span className="text-gray-300">Free Guest Posts</span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={filters.paidGuestPosts}
                  onChange={() => handleFilterChange('paidGuestPosts')}
                  disabled={loading}
                  className="w-5 h-5 bg-gray-800 border-gray-600 rounded focus:ring-indigo-500 focus:ring-offset-gray-700"
                />
                <span className="text-gray-300">Paid Guest Posts</span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={filters.dofollow}
                  onChange={() => handleFilterChange('dofollow')}
                  disabled={loading}
                  className="w-5 h-5 bg-gray-800 border-gray-600 rounded focus:ring-indigo-500 focus:ring-offset-gray-700"
                />
                <span className="text-gray-300">Dofollow Links</span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={filters.nicheRelevant}
                  onChange={() => handleFilterChange('nicheRelevant')}
                  disabled={loading}
                  className="w-5 h-5 bg-gray-800 border-gray-600 rounded focus:ring-indigo-500 focus:ring-offset-gray-700"
                />
                <span className="text-gray-300">Niche Relevant</span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={filters.highQuality}
                  onChange={() => handleFilterChange('highQuality')}
                  disabled={loading}
                  className="w-5 h-5 bg-gray-800 border-gray-600 rounded focus:ring-indigo-500 focus:ring-offset-gray-700"
                />
                <span className="text-gray-300">High Quality</span>
              </label>
            </div>
          </div>

          {/* Start Search Button */}
          <div className="flex justify-center">
            <button
              type="submit"
              disabled={!niche.trim() || loading}
              className={`bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-8 py-4 rounded-lg transition-colors text-lg text-center flex items-center gap-2 ${
                !niche.trim() || loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
              }`}
            >
              {loading ? (
                <>
                  <span className="inline-block w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  <span>Creating Search...</span>
                </>
              ) : (
                'Start Search'
              )}
            </button>
          </div>
        </form>

        {/* Helpful Information */}
        <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
          <h3 className="text-lg font-semibold text-white mb-4">What happens next?</h3>
          <div className="space-y-3 text-gray-300">
            <p>
              Guest Posting AI registers your search in the backend database.
            </p>
            <p>
              Automated discovery searches candidate URLs, crawls page guidelines, and performs Gemini AI verification with deterministic quality scoring.
            </p>
            <div className="flex gap-4 pt-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>
                <span className="text-sm">Search Registration</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>
                <span className="text-sm">Database Tracking</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>
                <span className="text-sm">Results Pipeline</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </PageContainer>
  );
};

export default Search;
