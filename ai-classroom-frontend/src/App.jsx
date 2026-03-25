import { useState } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import client from "./api/client";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import CoursePage from "./pages/CoursePage";

function ProtectedRoute({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;
  return children;
}

function Layout() {
  const { user } = useAuth();
  const [isCreating, setIsCreating] = useState(false);
  const [newCourseName, setNewCourseName] = useState("");

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

  const handleCreateCourse = (e) => {
    e.preventDefault();
    if (newCourseName.trim()) {
      createCourse.mutate(newCourseName.trim());
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">🎓</div>
          <div>
            <p className="eyebrow">Local AI</p>
            <h1>Tutor</h1>
          </div>
        </div>
        <nav>
          <NavLink to="/">
            <span className="nav-icon">🏠</span> Dashboard
          </NavLink>
          {user && (
            <div className="sidebar-section">
              <div className="sidebar-section-header">
                <span className="nav-icon">📚</span> My Classrooms
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
              ) : (
                <button 
                  className="btn-secondary add-course-btn"
                  onClick={() => setIsCreating(true)}
                >
                  + New Classroom
                </button>
              )}
            </div>
          )}
        </nav>
        {user && (
          <div className="sidebar-user">
            <div className="user-avatar">{user.name?.[0] || "U"}</div>
            <div>
              <strong>{user.name}</strong>
              <p>{user.email}</p>
            </div>
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
