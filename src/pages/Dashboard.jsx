import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import PageContainer from '../components/PageContainer';
import { api } from '../services/api';

const Dashboard = () => {
  const navigate = useNavigate();
  const [searchInput, setSearchInput] = useState('');
  const [recentSearches, setRecentSearches] = useState([]);
  const [totalSearches, setTotalSearches] = useState(0);

  useEffect(() => {
    let isMounted = true;
    const loadDashboardData = async () => {
      try {
        const data = await api.listSearches(0, 5);
        if (isMounted) {
          setRecentSearches(data.searches || []);
          setTotalSearches(data.total || 0);
        }
      } catch (err) {
        console.warn('Dashboard could not reach backend API:', err.message);
      }
    };
    loadDashboardData();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (searchInput.trim()) {
      navigate(`/search?keyword=${encodeURIComponent(searchInput.trim())}`);
    } else {
      navigate('/search');
    }
  };

  return (
    <PageContainer title="Dashboard">
      <div className="space-y-8">
        {/* Dashboard Description */}
        <div className="text-center py-6">
          <h2 className="text-2xl font-bold text-white mb-2">Guest Posting AI Dashboard</h2>
          <p className="text-gray-400 max-w-2xl mx-auto">
            Discover and manage guest posting opportunities with AI-powered insights. 
            Track your searches, save promising websites, and optimize your outreach strategy.
          </p>
        </div>

        {/* Search Section */}
        <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
          <h3 className="text-lg font-semibold text-white mb-4">Find Guest Posting Opportunities</h3>
          <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Enter a niche or keyword..."
              className="flex-1 bg-gray-800 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              type="submit"
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-6 py-3 rounded-lg transition-colors cursor-pointer"
            >
              Start New Search
            </button>
          </form>
        </div>

        {/* Statistics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
            <div className="flex items-center gap-3 mb-3">
              <div className="text-2xl">🌐</div>
              <div>
                <p className="text-gray-400 text-sm">Websites Discovered</p>
                <p className="text-2xl font-bold text-white">0</p>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
            <div className="flex items-center gap-3 mb-3">
              <div className="text-2xl">📝</div>
              <div>
                <p className="text-gray-400 text-sm">Opportunities Found</p>
                <p className="text-2xl font-bold text-white">0</p>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
            <div className="flex items-center gap-3 mb-3">
              <div className="text-2xl">⭐</div>
              <div>
                <p className="text-gray-400 text-sm">Saved Websites</p>
                <p className="text-2xl font-bold text-white">0</p>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
            <div className="flex items-center gap-3 mb-3">
              <div className="text-2xl">🔍</div>
              <div>
                <p className="text-gray-400 text-sm">Total Searches</p>
                <p className="text-2xl font-bold text-white">{totalSearches}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Searches */}
        <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white">Recent Searches</h3>
            <Link to="/history" className="text-indigo-400 hover:text-indigo-300 text-xs font-medium">
              View All History →
            </Link>
          </div>
          {recentSearches.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {recentSearches.map((s) => (
                <Link
                  key={s.id}
                  to={`/results?searchId=${s.id}`}
                  className="bg-gray-800 hover:bg-gray-600 border border-gray-600 text-gray-200 px-3 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2"
                >
                  <span>{s.keyword}</span>
                  <span className="text-xs text-indigo-400 font-mono">#{s.id}</span>
                </Link>
              ))}
            </div>
          ) : (
            <div>
              <div className="flex flex-wrap gap-2 mb-3">
                <span className="bg-gray-800 text-gray-400 px-3 py-1 rounded-full text-xs">AI</span>
                <span className="bg-gray-800 text-gray-400 px-3 py-1 rounded-full text-xs">Technology</span>
                <span className="bg-gray-800 text-gray-400 px-3 py-1 rounded-full text-xs">Digital Marketing</span>
                <span className="bg-gray-800 text-gray-400 px-3 py-1 rounded-full text-xs">Machine Learning</span>
              </div>
              <p className="text-gray-500 text-sm">Start your first search to see your live search history here.</p>
            </div>
          )}
        </div>

        {/* Product Overview */}
        <div className="bg-gray-700 rounded-xl p-6 border border-gray-600">
          <h3 className="text-lg font-semibold text-white mb-4">About Guest Posting AI</h3>
          <div className="space-y-3 text-gray-300">
            <p>
              Guest Posting AI helps content marketers and SEO professionals discover high-quality guest posting opportunities across the web.
            </p>
            <p>
              Our platform analyzes websites to identify those that accept guest posts, evaluates their domain authority, and matches them with your content niche and target audience.
            </p>
            <div className="flex gap-4 pt-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>
                <span className="text-sm">Smart Discovery</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>
                <span className="text-sm">Quality Scoring</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>
                <span className="text-sm">Easy Management</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </PageContainer>
  );
};

export default Dashboard;
