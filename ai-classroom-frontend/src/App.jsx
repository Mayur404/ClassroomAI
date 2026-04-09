import { useState } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import client from "./api/client";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import CoursePage from "./pages/CoursePage";

function ProtectedRoute({ children }) {
  const { user, isBootstrapping } = useAuth();
  if (isBootstrapping) return <div className="loading-screen">Loading account...</div>;
  if (!user) return <Navigate to="/login" />;
  return children;
}

function Layout() {
  const { user, logout } = useAuth();
  const [isCreating, setIsCreating] = useState(false);
  const [newCourseName, setNewCourseName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [joinError, setJoinError] = useState("");

  const coursesQuery = useQuery({
    queryKey: ["courses"],
    queryFn: async () => {
      const res = await client.get("/courses/");
      return res.data;
    },
    enabled: !!user,
  });

  const createCourse = useMutation({
    mutationFn: async (name) => {
      const res = await client.post("/courses/", { name });
      return res.data;
    },
    onSuccess: () => {
      coursesQuery.refetch();
      setIsCreating(false);
      setNewCourseName("");
    },
  });

  const joinCourse = useMutation({
    mutationFn: async (code) => {
      const res = await client.post("/enrollments/", { invite_code: code });
      return res.data;
    },
    onSuccess: () => {
      coursesQuery.refetch();
      setInviteCode("");
      setJoinError("");
    },
    onError: (err) => {
      setJoinError(err?.response?.data?.detail || "Could not join classroom. Check invite code.");
    },
  });

  const handleCreateCourse = (e) => {
    e.preventDefault();
    if (newCourseName.trim()) {
      createCourse.mutate(newCourseName.trim());
    }
  };

  const handleJoinCourse = (e) => {
    e.preventDefault();
    if (!inviteCode.trim()) return;
    joinCourse.mutate(inviteCode.trim().toUpperCase());
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div>
            <p className="eyebrow">Platform</p>
            <h1>AI-Classroom</h1>
          </div>
        </div>
        <nav>
          <NavLink to="/">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="nav-icon"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
            Dashboard
          </NavLink>
          {user && (
            <div className="sidebar-section">
              <div className="sidebar-section-header">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="nav-icon"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>
                My Classrooms
              </div>
              <div className="course-list">
                {coursesQuery.isLoading ? (
                  <div className="course-link text-muted">Loading...</div>
                ) : coursesQuery.data?.length === 0 ? (
                  <div className="course-link text-muted">No classrooms yet</div>
                ) : (
                  coursesQuery.data?.map((course) => (
                    <NavLink
                      key={course.id}
                      to={`/learn/${course.id}`}
                      className={({ isActive }) =>
                        `course-link ${isActive ? "active" : ""}`
                      }
                    >
                      {course.name}
                    </NavLink>
                  ))
                )}
              </div>
              {isCreating ? (
                <form onSubmit={handleCreateCourse} className="create-course-form stack compact">
                  <input
                    type="text"
                    className="input-field"
                    placeholder="Classroom Name"
                    value={newCourseName}
                    onChange={(e) => setNewCourseName(e.target.value)}
                    autoFocus
                    disabled={createCourse.isPending}
                  />
                  <div className="actions row">
                    <button 
                      type="submit" 
                      className="btn-primary flex-1"
                      disabled={!newCourseName.trim() || createCourse.isPending}
                    >
                      {createCourse.isPending ? "..." : "Add"}
                    </button>
                    <button 
                      type="button" 
                      className="btn-secondary"
                      onClick={() => setIsCreating(false)}
                      disabled={createCourse.isPending}
                    >
                      ✕
                    </button>
                  </div>
                </form>
              ) : user?.role === "TEACHER" ? (
                <button 
                  className="btn-secondary add-course-btn"
                  onClick={() => setIsCreating(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: 'center' }}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  New Classroom
                </button>
              ) : (
                <form onSubmit={handleJoinCourse} className="create-course-form stack compact">
                  <input
                    type="text"
                    className="input-field"
                    placeholder="Invite Code"
                    value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value)}
                  />
                  <button type="submit" className="btn-secondary" disabled={!inviteCode.trim() || joinCourse.isPending}>
                    {joinCourse.isPending ? "Joining..." : "Join Classroom"}
                  </button>
                  {joinError && <p className="text-muted">{joinError}</p>}
                </form>
              )}
            </div>
          )}
        </nav>
        {user && (
          <div className="sidebar-user">
            <div className="user-avatar">{user.name?.[0] || "U"}</div>
            <div>
              <strong>{user.name}</strong>
              <p>{user.email} • {user.role}</p>
            </div>
            <button className="btn-secondary" onClick={logout} style={{ marginLeft: "auto", padding: "0.25rem 0.5rem" }}>Logout</button>
          </div>
        )}
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/learn/:courseId"
            element={
              <ProtectedRoute>
                <CoursePage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Layout />
    </AuthProvider>
  );
}
