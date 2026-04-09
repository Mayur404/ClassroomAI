import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api",
  timeout: 120000,
});

const bareClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api",
  timeout: 120000,
});

client.interceptors.request.use((config) => {
  const accessToken = localStorage.getItem("ai-classroom-access-token");
  const token = localStorage.getItem("ai-classroom-token");
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  } else if (token) {
    config.headers.Authorization = `Token ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config || {};
    const status = error?.response?.status;

    if (status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    const refreshToken = localStorage.getItem("ai-classroom-refresh-token");
    if (!refreshToken) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;
    try {
      const refreshResponse = await bareClient.post("/auth/token/refresh/", {
        refresh_token: refreshToken,
      });
      const newAccessToken = refreshResponse?.data?.access_token;
      const newRefreshToken = refreshResponse?.data?.refresh_token;

      if (!newAccessToken) {
        return Promise.reject(error);
      }

      localStorage.setItem("ai-classroom-access-token", newAccessToken);
      if (newRefreshToken) {
        localStorage.setItem("ai-classroom-refresh-token", newRefreshToken);
      }

      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
      return client(originalRequest);
    } catch (refreshError) {
      localStorage.removeItem("ai-classroom-access-token");
      localStorage.removeItem("ai-classroom-refresh-token");
      return Promise.reject(refreshError);
    }
  }
);

export default client;
