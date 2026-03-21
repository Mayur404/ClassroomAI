import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api",
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("ai-classroom-token");
  if (token) {
    config.headers.Authorization = `Token ${token}`;
  }
  return config;
});

export default client;
