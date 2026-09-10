/**
 * API Client Service for communicating with FastAPI backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const TOKEN_STORAGE_KEY = 'auth_token';
const USER_STORAGE_KEY = 'auth_user';

/**
 * Token and User persistence utilities.
 */
export function getAuthToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export function clearAuthToken() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USER_STORAGE_KEY);
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user) {
  if (user) {
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(USER_STORAGE_KEY);
  }
}

/**
 * Cleanly format backend error messages (handles strings, Pydantic validation arrays, and objects).
 */
function formatApiErrorMessage(detail, status) {
  if (!detail) {
    return `API request failed with status ${status}`;
  }
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item?.msg) {
          const cleanMsg = item.msg.replace(/^Value error,\s*/i, '');
          const field = Array.isArray(item.loc)
            ? item.loc.filter((l) => l !== 'body').join(' ')
            : '';
          return field ? `${field}: ${cleanMsg}` : cleanMsg;
        }
        return typeof item === 'object' ? JSON.stringify(item) : String(item);
      })
      .filter(Boolean);
    return messages.length > 0 ? messages.join('. ') : `Validation failed (${status})`;
  }
  if (typeof detail === 'object') {
    if (detail.msg) return detail.msg.replace(/^Value error,\s*/i, '');
    if (detail.message) return detail.message;
    try {
      return JSON.stringify(detail);
    } catch {
      return `API error (${status})`;
    }
  }
  return String(detail);
}

/**
 * Generic fetch wrapper with JSON parsing and error handling.
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const token = getAuthToken();

  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      if (response.status === 401) {
        clearAuthToken();
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        }
      }
      const errorMsg = formatApiErrorMessage(data?.detail, response.status);
      throw new Error(errorMsg);
    }

    return data;
  } catch (error) {
    console.error(`[API Error] ${options.method || 'GET'} ${url}:`, error.message);
    if (
      error instanceof TypeError ||
      error.message === 'Failed to fetch' ||
      error.message?.includes('NetworkError') ||
      error.message?.includes('Failed to fetch')
    ) {
      throw new Error(
        'Unable to connect to backend server (http://localhost:8000). Please make sure the FastAPI backend is running.'
      );
    }
    throw error;
  }
}

export const api = {
  // Authentication (Step 21)
  register: ({ email, password }) =>
    request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  login: ({ email, password }) =>
    request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  googleLogin: (payload) =>
    request('/auth/google', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getGoogleConfig: () => request('/auth/google/config'),

  getMe: () => request('/auth/me'),

  logout: () =>
    request('/auth/logout', {
      method: 'POST',
    }),

  // Health Checks
  getHealth: () => request('/health'),
  getDbHealth: () => request('/health/db'),

  // Searches
  createSearch: ({ keyword, requestedWebsiteCount = 100, userId = null }) =>
    request('/searches', {
      method: 'POST',
      body: JSON.stringify({
        keyword,
        requested_website_count: requestedWebsiteCount,
        user_id: userId,
      }),
    }),

  triggerDiscovery: (searchId) =>
    request(`/searches/${searchId}/discover`, {
      method: 'POST',
    }),

  listSearches: (skip = 0, limit = 50) =>
    request(`/searches?skip=${skip}&limit=${limit}`),

  getSearch: (searchId) =>
    request(`/searches/${searchId}`),

  deleteSearch: (searchId) =>
    request(`/searches/${searchId}`, {
      method: 'DELETE',
    }),


  // Websites
  listWebsites: (skip = 0, limit = 50) =>
    request(`/websites?skip=${skip}&limit=${limit}`),

  getWebsite: (websiteId) =>
    request(`/websites/${websiteId}`),

  crawlWebsite: (websiteId) =>
    request(`/websites/${websiteId}/crawl`, {
      method: 'POST',
    }),

  detectGuestPost: (websiteId) =>
    request(`/websites/${websiteId}/detect-guest-post`, {
      method: 'POST',
    }),

  extractSubmissionInformation: (websiteId) =>
    request(`/websites/${websiteId}/extract-submission`, {
      method: 'POST',
    }),

  verifyWebsite: (websiteId) =>
    request(`/websites/${websiteId}/verify`, {
      method: 'POST',
    }),

  analyzeWebsite: (websiteId, keyword = null) => {
    const query = keyword ? `?keyword=${encodeURIComponent(keyword)}` : '';
    return request(`/websites/${websiteId}/analyze${query}`, {
      method: 'POST',
    });
  },

  scoreWebsite: (websiteId) =>
    request(`/websites/${websiteId}/score`, {
      method: 'POST',
    }),

  processSearchPipeline: (searchId, concurrency = 3) =>
    request(`/searches/${searchId}/process?concurrency=${concurrency}`, {
      method: 'POST',
    }),

  getSearchProgress: (searchId) =>
    request(`/searches/${searchId}/progress`),

  processWebsitePipeline: (websiteId, keyword = null) => {
    const query = keyword ? `?keyword=${encodeURIComponent(keyword)}` : '';
    return request(`/websites/${websiteId}/process${query}`, {
      method: 'POST',
    });
  },

  filterWebsites: (filters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        params.append(key, value);
      }
    });
    const queryString = params.toString();
    return request(`/websites/filter${queryString ? `?${queryString}` : ''}`);
  },

  // Saved Websites & Bookmarks (Step 20 & 21)
  saveWebsite: (websiteId) =>
    request(`/websites/${websiteId}/save`, {
      method: 'POST',
    }),

  unsaveWebsite: (websiteId) =>
    request(`/websites/${websiteId}/save`, {
      method: 'DELETE',
    }),

  getSavedWebsites: (page = 1, pageSize = 25) =>
    request(`/websites/saved?page=${page}&page_size=${pageSize}`),

  exportWebsitesCsv: async (filters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        params.append(key, value);
      }
    });
    const queryString = params.toString();
    const url = `${API_BASE_URL}/websites/export/csv${queryString ? `?${queryString}` : ''}`;
    const token = getAuthToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await fetch(url, { headers });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(data?.detail || `Export failed with status ${response.status}`);
    }
    return response.blob();
  },

  exportSavedWebsitesCsv: async () => {
    const url = `${API_BASE_URL}/websites/saved/export/csv`;
    const token = getAuthToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await fetch(url, { headers });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(data?.detail || `Export failed with status ${response.status}`);
    }
    return response.blob();
  },
};

/**
 * Trigger download of a Blob file in the browser.
 */
export function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

export default api;
