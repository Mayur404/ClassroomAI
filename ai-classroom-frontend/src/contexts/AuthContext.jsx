import { createContext, useContext, useEffect, useState } from "react";

import client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("ai-classroom-token");
    if (!token) {
      setIsBootstrapping(false);
      return;
    }
    client
      .get("/auth/me/")
      .then((response) => setUser(response.data))
      .catch(() => {
        localStorage.removeItem("ai-classroom-token");
        localStorage.removeItem("ai-classroom-access-token");
        localStorage.removeItem("ai-classroom-refresh-token");
      })
      .finally(() => {
        setIsBootstrapping(false);
      });
  }, []);

  const login = async (payload) => {
    const response = await client.post("/auth/login/", payload);
    localStorage.setItem("ai-classroom-token", response.data.token);
    if (response.data.access_token) {
      localStorage.setItem("ai-classroom-access-token", response.data.access_token);
    }
    if (response.data.refresh_token) {
      localStorage.setItem("ai-classroom-refresh-token", response.data.refresh_token);
    }
    setUser(response.data.user);
  };

  const register = async (payload) => {
    const response = await client.post("/auth/register/", payload);
    localStorage.setItem("ai-classroom-token", response.data.token);
    if (response.data.access_token) {
      localStorage.setItem("ai-classroom-access-token", response.data.access_token);
    }
    if (response.data.refresh_token) {
      localStorage.setItem("ai-classroom-refresh-token", response.data.refresh_token);
    }
    setUser(response.data.user);
  };

  const logout = () => {
    client.post("/auth/logout/").catch(() => undefined);
    localStorage.removeItem("ai-classroom-token");
    localStorage.removeItem("ai-classroom-access-token");
    localStorage.removeItem("ai-classroom-refresh-token");
    setUser(null);
  };

  const updateUser = (newUserData) => {
    setUser((prev) => ({ ...prev, ...newUserData }));
  };

  return (
    <AuthContext.Provider value={{ user, setUser: updateUser, login, register, logout, isBootstrapping }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
