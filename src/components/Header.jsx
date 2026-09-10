import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';

const Header = () => {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const userInitial = user?.email ? user.email[0].toUpperCase() : 'U';

  return (
    <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h2 className="text-lg font-semibold text-white">Guest Posting AI</h2>
        </div>

        <div className="flex items-center gap-4">
          {isAuthenticated ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-indigo-600 rounded-full flex items-center justify-center text-white font-medium text-sm">
                  {userInitial}
                </div>
                <span className="text-sm text-gray-300 font-medium max-w-[200px] truncate" title={user?.email}>
                  {user?.email}
                </span>
              </div>
              <button
                onClick={handleLogout}
                className="bg-gray-700 hover:bg-gray-600 text-gray-300 hover:text-white text-xs px-3 py-1.5 rounded-lg border border-gray-600 transition-colors cursor-pointer"
                title="Log out of account"
              >
                Log Out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                to="/login"
                className="text-gray-300 hover:text-white text-sm px-3 py-1.5 rounded-lg hover:bg-gray-700 transition-colors font-medium"
              >
                Sign In
              </Link>
              <Link
                to="/register"
                className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-3.5 py-1.5 rounded-lg transition-colors font-medium shadow-sm"
              >
                Register
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
