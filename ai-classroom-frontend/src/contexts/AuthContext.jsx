import { createContext, useContext, useEffect, useState } from "react";

import client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem("ai-classroom-token");
    if (!token) {
      return;
    }
    client
      .get("/auth/me/")
      .then((response) => setUser(response.data))
      .catch(() => {
        localStorage.removeItem("ai-classroom-token");
      });
  }, []);

  const login = async (payload) => {
    const response = await client.post("/auth/demo-login/", payload);
    localStorage.setItem("ai-classroom-token", response.data.token);
    setUser(response.data.user);
  };

  const logout = () => {
    localStorage.removeItem("ai-classroom-token");
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
