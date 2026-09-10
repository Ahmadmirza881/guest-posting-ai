import { createContext, useState, useEffect, useCallback } from 'react';
import {
  api,
  getAuthToken,
  setAuthToken,
  clearAuthToken,
  getStoredUser,
  setStoredUser,
} from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(() => getAuthToken());
  const [user, setUser] = useState(() => getStoredUser());
  const [loading, setLoading] = useState(true);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // Ignore network errors on logout
    } finally {
      clearAuthToken();
      setToken(null);
      setUser(null);
    }
  }, []);

  // Validate session on mount if token is found
  useEffect(() => {
    let isMounted = true;

    const verifyAuth = async () => {
      const existingToken = getAuthToken();
      if (!existingToken) {
        if (isMounted) {
          setLoading(false);
        }
        return;
      }

      try {
        const userData = await api.getMe();
        if (isMounted) {
          setUser(userData);
          setStoredUser(userData);
        }
      } catch (err) {
        console.warn('Session expired or invalid:', err.message);
        if (isMounted) {
          clearAuthToken();
          setToken(null);
          setUser(null);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    verifyAuth();

    // Listen for unauthorized 401 events dispatched from api.js
    const handleUnauthorized = () => {
      setToken(null);
      setUser(null);
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);

    return () => {
      isMounted = false;
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, []);

  const login = async (email, password) => {
    const data = await api.login({ email, password });
    setAuthToken(data.access_token);
    setStoredUser(data.user);
    setToken(data.access_token);
    setUser(data.user);
    return data;
  };

  const register = async (email, password) => {
    await api.register({ email, password });
    // Automatically log in upon successful registration
    return await login(email, password);
  };

  const googleLogin = async (payload) => {
    const data = await api.googleLogin(payload);
    setAuthToken(data.access_token);
    setStoredUser(data.user);
    setToken(data.access_token);
    setUser(data.user);
    return data;
  };

  const value = {
    user,
    token,
    isAuthenticated: Boolean(token && user),
    loading,
    login,
    register,
    googleLogin,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export { AuthContext };
export default AuthContext;
