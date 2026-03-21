import { NavLink, Route, Routes, Navigate } from "react-router-dom";
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">🎓</div>
          <div>
            <p className="eyebrow">Gemini AI</p>
            <h1>Tutor</h1>
          </div>
        </div>
        <nav>
          <NavLink to="/">
            <span className="nav-icon">🏠</span> Dashboard
          </NavLink>
          {user && (
            <NavLink to="/learn">
              <span className="nav-icon">📚</span> My Classroom
            </NavLink>
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
            path="/learn"
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
