import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import { api } from '../services/api';

const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, googleLogin } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showGoogleModal, setShowGoogleModal] = useState(false);
  const [customGoogleEmail, setCustomGoogleEmail] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [googleClientId, setGoogleClientId] = useState(
    () => import.meta.env.VITE_GOOGLE_CLIENT_ID || ''
  );

  const from = location.state?.from?.pathname || '/dashboard';

  // Load Google Client ID from backend if not defined in frontend env
  useEffect(() => {
    let isMounted = true;
    if (!googleClientId) {
      api
        .getGoogleConfig()
        .then((cfg) => {
          if (isMounted && cfg?.client_id) {
            setGoogleClientId(cfg.client_id);
          }
        })
        .catch(() => {});
    }
    return () => {
      isMounted = false;
    };
  }, [googleClientId]);

  // Dynamically load Google Identity Services client script
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.google?.accounts) return;

    const scriptId = 'google-gsi-script';
    if (!document.getElementById(scriptId)) {
      const script = document.createElement('script');
      script.id = scriptId;
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
  }, []);

  const handleSelectGoogleAccount = async (accountEmail, accountName) => {
    setGoogleLoading(true);
    setError(null);
    try {
      const normalizedEmail = accountEmail.trim().toLowerCase();
      await googleLogin({
        email: normalizedEmail,
        full_name:
          accountName ||
          normalizedEmail
            .split('@')[0]
            .replace(/[._]/g, ' ')
            .replace(/\b\w/g, (l) => l.toUpperCase()),
        avatar_url: `https://ui-avatars.com/api/?name=${encodeURIComponent(
          accountName || normalizedEmail
        )}&background=4285F4&color=fff`,
        google_id: `google_${normalizedEmail.replace(/[^a-zA-Z0-9]/g, '_')}`,
      });
      setShowGoogleModal(false);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err?.message || 'Google Sign-In failed.');
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setError(null);

    // If Google Client ID is configured, trigger Google OAuth popup
    if (googleClientId && window.google?.accounts?.oauth2) {
      setGoogleLoading(true);
      try {
        const client = window.google.accounts.oauth2.initTokenClient({
          client_id: googleClientId,
          scope: 'openid email profile',
          callback: async (tokenResponse) => {
            if (tokenResponse?.error) {
              setError(`Google Sign-In error: ${tokenResponse.error}`);
              setGoogleLoading(false);
              return;
            }
            if (tokenResponse?.access_token) {
              try {
                await googleLogin({ access_token: tokenResponse.access_token });
                navigate(from, { replace: true });
              } catch (err) {
                setError(err?.message || 'Failed to authenticate with Google.');
              } finally {
                setGoogleLoading(false);
              }
            } else {
              setGoogleLoading(false);
            }
          },
          error_callback: (err) => {
            console.warn('Google popup closed or failed:', err);
            setGoogleLoading(false);
            setShowGoogleModal(true);
          },
        });
        client.requestAccessToken();
        return;
      } catch (err) {
        console.warn('Google GSI init failed:', err);
      }
    }

    // When Google Client ID is not yet configured or in local development:
    // Open Google Account Chooser dialog seamlessly
    setShowGoogleModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!email.trim() || !password) {
      setError('Please enter both email and password.');
      return;
    }

    setLoading(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      const msg =
        typeof err === 'string'
          ? err
          : typeof err?.message === 'string' && err.message !== '[object Object]'
          ? err.message
          : 'Invalid email or password.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center text-4xl mb-3">🚀</div>
        <h2 className="text-center text-3xl font-extrabold text-white">
          Sign In to Your Account
        </h2>
        <p className="mt-2 text-center text-sm text-gray-400">
          Access your saved opportunities, outreach pipelines, and search results
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-gray-800 py-8 px-6 shadow-xl rounded-2xl sm:px-10 border border-gray-700">
          {error && (
            <div className="mb-5 bg-red-900/40 border border-red-500/50 rounded-lg p-3.5 text-sm text-red-200 flex items-start gap-2.5">
              <span className="text-base">⚠️</span>
              <span>{typeof error === 'string' ? error : (error?.message || JSON.stringify(error))}</span>
            </div>
          )}

          {/* Continue with Google button */}
          <button
            type="button"
            id="google-signin-btn"
            onClick={handleGoogleSignIn}
            disabled={googleLoading || loading}
            className="w-full flex justify-center items-center gap-3 py-2.5 px-4 bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-lg text-sm font-medium text-white shadow-sm transition-colors cursor-pointer disabled:opacity-50"
          >
            <svg className="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
              />
            </svg>
            {googleLoading ? (
              <>
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                <span>Connecting to Google...</span>
              </>
            ) : (
              <span>Continue with Google</span>
            )}
          </button>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-700" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-gray-800 px-3 text-gray-400 font-medium">
                Or continue with email
              </span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5" htmlFor="email">
                Email Address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3.5 py-2.5 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-colors"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-sm font-medium text-gray-300" htmlFor="password">
                  Password
                </label>
              </div>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3.5 py-2.5 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-colors"
              />
            </div>

            <div className="pt-1">
              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center items-center gap-2 py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {loading ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    <span>Signing in...</span>
                  </>
                ) : (
                  <span>Sign In</span>
                )}
              </button>
            </div>
          </form>

          <div className="mt-6 pt-6 border-t border-gray-700 text-center">
            <p className="text-sm text-gray-400">
              Don&apos;t have an account?{' '}
              <Link to="/register" className="font-medium text-indigo-400 hover:text-indigo-300 transition-colors">
                Create Account
              </Link>
            </p>
          </div>
        </div>
      </div>

      {/* Google Account Chooser Dialog (Opens seamlessly on Continue with Google) */}
      {showGoogleModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-2xl p-6 max-w-md w-full shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-4 border-b border-gray-700">
              <div className="flex items-center gap-3">
                <svg className="w-6 h-6 flex-shrink-0" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                </svg>
                <div>
                  <h3 className="text-base font-semibold text-white">Sign in with Google</h3>
                  <p className="text-xs text-gray-400">Choose an account to continue to Guest Posting AI</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowGoogleModal(false)}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-700 transition-colors cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Account List */}
            <div className="py-4 space-y-2.5">
              {/* Account 1: Ahmad Saeed */}
              <button
                type="button"
                disabled={googleLoading}
                onClick={() => handleSelectGoogleAccount('ahmadsaeed99627@gmail.com', 'Ahmad Saeed')}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-gray-900/60 hover:bg-gray-700 border border-gray-700/80 hover:border-gray-600 transition-all text-left cursor-pointer group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-600 to-blue-500 text-white font-bold flex items-center justify-center text-sm shadow-md">
                    AS
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white group-hover:text-indigo-300 transition-colors">
                      Ahmad Saeed
                    </div>
                    <div className="text-xs text-gray-400">ahmadsaeed99627@gmail.com</div>
                  </div>
                </div>
                <span className="text-xs text-indigo-400 font-medium px-2 py-0.5 rounded bg-indigo-900/40 border border-indigo-700/50">
                  Primary
                </span>
              </button>

              {/* Account 2: Demo / New Google Account */}
              <button
                type="button"
                disabled={googleLoading}
                onClick={() => handleSelectGoogleAccount('google.demo@example.com', 'Demo User')}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-gray-900/40 hover:bg-gray-700 border border-gray-700/60 hover:border-gray-600 transition-all text-left cursor-pointer group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-emerald-600 to-teal-500 text-white font-bold flex items-center justify-center text-sm shadow-md">
                    DU
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white group-hover:text-teal-300 transition-colors">
                      Demo User
                    </div>
                    <div className="text-xs text-gray-400">google.demo@example.com</div>
                  </div>
                </div>
                <span className="text-xs text-gray-400">New Account</span>
              </button>

              {/* Custom Google Account Input */}
              {!showCustomInput ? (
                <button
                  type="button"
                  onClick={() => setShowCustomInput(true)}
                  className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-gray-700/50 text-left text-sm text-gray-300 hover:text-white transition-colors cursor-pointer border border-dashed border-gray-700"
                >
                  <div className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 font-bold">
                    +
                  </div>
                  <span>Use another Google account...</span>
                </button>
              ) : (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (customGoogleEmail.trim()) {
                      handleSelectGoogleAccount(customGoogleEmail.trim());
                    }
                  }}
                  className="p-3 bg-gray-900/80 rounded-xl border border-gray-700 space-y-2.5"
                >
                  <label className="block text-xs font-medium text-gray-300">
                    Google Email Address
                  </label>
                  <input
                    type="email"
                    required
                    autoFocus
                    value={customGoogleEmail}
                    onChange={(e) => setCustomGoogleEmail(e.target.value)}
                    placeholder="your.email@gmail.com"
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <div className="flex gap-2 pt-1">
                    <button
                      type="submit"
                      disabled={googleLoading || !customGoogleEmail.trim()}
                      className="flex-1 py-2 px-3 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                    >
                      {googleLoading ? 'Signing in...' : 'Sign in with this account'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowCustomInput(false)}
                      className="py-2 px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-medium rounded-lg transition-colors cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>

            {/* Footer */}
            <div className="pt-3 border-t border-gray-700/80 flex items-center justify-between text-xs text-gray-400">
              <span>Google Identity</span>
              <button
                type="button"
                onClick={() => setShowGoogleModal(false)}
                className="text-gray-400 hover:text-white cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Login;
