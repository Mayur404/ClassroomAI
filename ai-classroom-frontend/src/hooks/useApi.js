/**
 * Frontend API and State Management Utilities
 * Enhanced error handling, caching, and state management with Zustand
 */

import { useCallback, useState, useRef, useEffect } from 'react';
import axios from 'axios';

// ============================================================================
// GLOBAL STATE MANAGEMENT (Zustand-like simple store)
// ============================================================================

class StateManager {
  constructor() {
    this.state = {
      user: null,
      course: null,
      notifications: [],
      loading: false,
      errors: {},
    };
    this.subscribers = new Set();
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  setState(updates) {
    this.state = { ...this.state, ...updates };
    this.subscribers.forEach(cb => cb(this.state));
  }

  getState() {
    return this.state;
  }
}

export const stateManager = new StateManager();

// ============================================================================
// NOTIFICATION SYSTEM (Toast-like)
// ============================================================================

export const Notification = {
  SUCCESS: 'success',
  ERROR: 'error',
  WARNING: 'warning',
  INFO: 'info',
};

export const showNotification = (message, type = Notification.INFO, duration = 3000) => {
  const id = Date.now();
  const notification = { id, message, type, timestamp: new Date() };
  
  const currentState = stateManager.getState();
  stateManager.setState({
    notifications: [...currentState.notifications, notification],
  });

  if (duration > 0) {
    setTimeout(() => {
      const state = stateManager.getState();
      stateManager.setState({
        notifications: state.notifications.filter(n => n.id !== id),
      });
    }, duration);
  }

  return id;
};

// ============================================================================
// API ERROR HANDLING
// ============================================================================

class APIError extends Error {
  constructor(message, code, correlationId, status) {
    super(message);
    this.code = code;
    this.correlationId = correlationId;
    this.status = status;
    this.name = 'APIError';
  }
}

// ============================================================================
// ENHANCED API HOOKS
// ============================================================================

/**
 * useApi - Enhanced fetch/query hook with error handling and caching
 */
export const useApi = (url, options = {}) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const cacheRef = useRef(new Map());

  const fetchData = useCallback(async (queryParams = {}) => {
    // Check cache
    const cacheKey = JSON.stringify({ url, queryParams });
    if (cacheRef.current.has(cacheKey)) {
      setData(cacheRef.current.get(cacheKey));
      return cacheRef.current.get(cacheKey);
    }

    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(url, {
        params: queryParams,
        timeout: options.timeout || 30000,
        ...options,
      });

      if (response.data.success === false) {
        throw new APIError(
          response.data.error || 'API Error',
          response.data.code,
          response.data.correlation_id,
          response.status
        );
      }

      setData(response.data.data || response.data);
      
      // Cache result
      if (options.cache !== false) {
        cacheRef.current.set(cacheKey, response.data.data || response.data);
      }

      return response.data.data || response.data;
    } catch (err) {
      const apiError = new APIError(
        err.response?.data?.error || err.message,
        err.response?.data?.code || 'UNKNOWN_ERROR',
        err.response?.data?.correlation_id,
        err.response?.status
      );

      setError(apiError);
      
      // Show error notification
      showNotification(apiError.message, Notification.ERROR);
      
      // Log error with correlation ID
      console.error('API Error:', {
        url,
        error: apiError.message,
        correlationId: apiError.correlationId,
      });

      throw apiError;
    } finally {
      setLoading(false);
    }
  }, [url, options]);

  useEffect(() => {
    if (options.skip === false && options.autoFetch !== false) {
      fetchData();
    }
  }, [url, fetchData, options]);

  return { data, loading, error, fetchData };
};

/**
 * useMutation - Enhanced mutation hook for POST/PUT/DELETE
 */
export const useMutation = (method = 'POST') => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const mutation = useCallback(async (url, data = null, options = {}) => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios({
        method,
        url,
        data,
        timeout: options.timeout || 30000,
        ...options,
      });

      if (response.data.success === false) {
        throw new APIError(
          response.data.error || 'API Error',
          response.data.code,
          response.data.correlation_id,
          response.status
        );
      }

      showNotification(options.successMessage || 'Operation successful', Notification.SUCCESS);

      return response.data.data || response.data;
    } catch (err) {
      const apiError = new APIError(
        err.response?.data?.error || err.message,
        err.response?.data?.code || 'UNKNOWN_ERROR',
        err.response?.data?.correlation_id,
        err.response?.status
      );

      setError(apiError);
      showNotification(apiError.message, Notification.ERROR);

      throw apiError;
    } finally {
      setLoading(false);
    }
  }, [method]);

  return { mutation, loading, error };
};

// ============================================================================
// VALIDATION UTILITIES
// ============================================================================

export const validators = {
  email: (email) => {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email) ? null : 'Invalid email address';
  },

  required: (value) => {
    return value && value.trim() ? null : 'This field is required';
  },

  minLength: (min) => (value) => {
    return value && value.length >= min ? null : `Minimum ${min} characters required`;
  },

  maxLength: (max) => (value) => {
    return value && value.length <= max ? null : `Maximum ${max} characters allowed`;
  },

  match: (pattern, message) => (value) => {
    return pattern.test(value) ? null : message;
  },
};

/**
 * useForm - Form state management with validation
 */
export const useForm = (initialValues = {}, onSubmit) => {
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState({});
  const [touched, setTouched] = useState({});
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setValues(v => ({ ...v, [name]: value }));
  };

  const handleBlur = (e) => {
    const { name } = e.target;
    setTouched(t => ({ ...t, [name]: true }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      await onSubmit(values);
    } catch (err) {
      console.error('Form submission error:', err);
    } finally {
      setLoading(false);
    }
  };

  const setFieldValue = (name, value) => {
    setValues(v => ({ ...v, [name]: value }));
  };

  const setFieldError = (name, error) => {
    setErrors(e => ({ ...e, [name]: error }));
  };

  return {
    values,
    errors,
    touched,
    loading,
    handleChange,
    handleBlur,
    handleSubmit,
    setFieldValue,
    setFieldError,
    setValues,
    setErrors,
  };
};

// ============================================================================
// DEBOUNCE & THROTTLE UTILITIES
// ============================================================================

export const useDebounce = (value, delay = 500) => {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(timeout);
  }, [value, delay]);

  return debouncedValue;
};

export const useThrottle = (callback, delay = 1000) => {
  const lastRunRef = useRef(null);

  return useCallback((...args) => {
    const now = Date.now();
    if (!lastRunRef.current || now - lastRunRef.current >= delay) {
      callback(...args);
      lastRunRef.current = now;
    }
  }, [callback, delay]);
};

// ============================================================================
// LOCAL STORAGE UTILITIES
// ============================================================================

export const useLocalStorage = (key, initialValue) => {
  const [storedValue, setStoredValue] = useState(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.error(`Failed to read localStorage[${key}]:`, error);
      return initialValue;
    }
  });

  const setValue = (value) => {
    try {
      const valueToStore = value instanceof Function ? value(storedValue) : value;
      setStoredValue(valueToStore);
      window.localStorage.setItem(key, JSON.stringify(valueToStore));
    } catch (error) {
      console.error(`Failed to write localStorage[${key}]:`, error);
    }
  };

  return [storedValue, setValue];
};

// ============================================================================
// REACT QUERY REPLACEMENT (Simple Caching)
// ============================================================================

export const QueryCache = new Map();

export const useQuery = (key, queryFn, options = {}) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Check cache
    if (QueryCache.has(key)) {
      setData(QueryCache.get(key));
      setLoading(false);
      return;
    }

    let isMounted = true;

    (async () => {
      try {
        const result = await queryFn();
        if (isMounted) {
          setData(result);
          QueryCache.set(key, result);
          
          // Cache expiration
          if (options.staleTime) {
            setTimeout(() => QueryCache.delete(key), options.staleTime);
          }
        }
      } catch (err) {
        if (isMounted) {
          setError(err);
          showNotification(err.message, Notification.ERROR);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    })();

    return () => {
      isMounted = false;
    };
  }, [key, queryFn, options]);

  return { data, loading, error };
};

// Clear all cache
export const invalidateQueries = () => {
  QueryCache.clear();
};

// ============================================================================
// API CLIENT CONFIGURATION
// ============================================================================

export const setupAxiosInterceptors = () => {
  // Request interceptor
  axios.interceptors.request.use((config) => {
    // Add auth token if available
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Add correlation ID
    config.headers['X-Correlation-ID'] = crypto.randomUUID();
    
    return config;
  });

  // Response interceptor
  axios.interceptors.response.use(
    (response) => response,
    (error) => {
      // Handle 401 - redirect to login
      if (error.response?.status === 401) {
        localStorage.removeItem('auth_token');
        window.location.href = '/login';
      }

      // Handle 429 - rate limit
      if (error.response?.status === 429) {
        showNotification('Too many requests. Please try again later.', Notification.ERROR, 5000);
      }

      return Promise.reject(error);
    }
  );
};
