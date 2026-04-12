import { useState } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import client from "./api/client";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import DashboardPage from "./pages/DashboardPage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import CoursePage from "./pages/CoursePage";
import ModifyAccountPage from "./pages/ModifyAccountPage";

function ProtectedRoute({ children }) {
  const { user, isBootstrapping } = useAuth();
  if (isBootstrapping) return <div className="loading-screen">Loading account...</div>;
  if (!user) return <Navigate to="/login" />;
  return children;
}

function Layout() {
  const { user, logout, isBootstrapping } = useAuth();
  const [isCreating, setIsCreating] = useState(false);
  const [newCourseName, setNewCourseName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [joinError, setJoinError] = useState("");
  const [showUserMenu, setShowUserMenu] = useState(false);

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

  if (isBootstrapping) {
    return <div className="loading-screen">Loading account...</div>;
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div>
            <p className="eyebrow">Platform</p>
            <h1>AIEdu</h1>
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
          <div className="sidebar-user" style={{ padding: '0.75rem', borderTop: '1px solid var(--border)', marginTop: 'auto', position: 'relative' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', overflow: 'hidden' }}>
                <div className="user-avatar" style={{ width: '32px', height: '32px', minWidth: '32px', borderRadius: '50%', backgroundColor: 'var(--primary)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>
                  {user.name?.[0] || "U"}
                </div>
                <div style={{ overflow: 'hidden' }}>
                  <strong style={{ display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '0.9rem' }}>{user.name}</strong>
                  <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)' }}>{user.role}</p>
                </div>
              </div>
              <button 
                className="btn-icon" 
                onClick={() => setShowUserMenu(!showUserMenu)}
                style={{ padding: '0.5rem', background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', borderRadius: '50%' }}
                aria-label="User settings"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
              </button>
            </div>
            
            {showUserMenu && (
              <div className="user-popover" style={{ position: 'absolute', bottom: '100%', right: '10px', marginBottom: '10px', background: 'var(--panel-bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)', minWidth: '150px', zIndex: 10, display: 'flex', flexDirection: 'column' }}>
                <NavLink 
                  to="/account" 
                  className={({ isActive }) => `menu-item ${isActive ? "active" : ""}`}
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0.75rem 1rem', color: 'var(--text)', textDecoration: 'none', fontSize: '0.85rem', borderBottom: '1px solid var(--border)' }}
                  onClick={() => setShowUserMenu(false)}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                  Modify Account
                </NavLink>
                <button 
                  onClick={() => {
                    setShowUserMenu(false);
                    logout();
                  }}
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0.75rem 1rem', background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '0.85rem', textAlign: 'left', width: '100%' }}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                  Logout
                </button>
              </div>
            )}
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
          <Route
            path="/account"
            element={
              <ProtectedRoute>
                <ModifyAccountPage />
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
