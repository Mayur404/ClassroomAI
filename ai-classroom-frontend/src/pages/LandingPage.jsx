import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function LandingPage() {
  const { user } = useAuth();

  return (
    <>
      <div className="geometric-bg">
        <div className="blob blob-1"></div>
        <div className="blob blob-2"></div>
        <div className="blob blob-3"></div>
      </div>

      <nav className="landing-nav" style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: '0 5%', height: '75px', position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100, background: 'rgba(2, 6, 23, 0.7)', backdropFilter: 'blur(20px)' }}>
        <Link to="/" className="landing-nav-brand" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-main)', textDecoration: 'none', fontSize: '1.4rem', fontWeight: 700 }}>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ width: '24px', height: '24px', color: 'var(--primary)' }}>
            <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          AIEdu
        </Link>
        <div className="landing-nav-links" style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '1rem' }}>
          <Link to="/login" className="btn-outline" style={{ borderRadius: '0.5rem', padding: '0.5rem 1.25rem', fontSize: '0.9rem', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', height: '36px', boxSizing: 'border-box', border: '1px solid rgba(255,255,255,0.2)', color: 'var(--text-main)', textDecoration: 'none', background: 'transparent' }}>Log in</Link>
          <Link to="/login" className="btn-primary" style={{ borderRadius: '0.5rem', padding: '0.5rem 1.25rem', fontSize: '0.9rem', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', height: '36px', boxSizing: 'border-box' }}>Sign up</Link>
        </div>
      </nav>

      <main className="landing-content" style={{ paddingTop: '100px' }}>
        {/* HERO SECTION */}
        <section className="hero-section">
          <div className="badge-new animate-slide-up">
            <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: 'currentColor', boxShadow: '0 0 8px currentColor' }}></span>
            AI-Powered Education Platform
          </div>
          
          <h1 className="hero-title animate-slide-up delay-100" style={{ marginBottom: '3rem' }}>
            Transform Your <br />
            <span className="gradient-text-animate">Teaching & Learning</span>
          </h1>

          <div className="hero-cta animate-slide-up delay-300" style={{ marginBottom: '3rem' }}>
            <Link to="/login" className="btn-primary btn-large">
              Get Started Free
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </Link>
          </div>
        </section>

        {/* FEATURES SECTION */}
        <section className="features-section">
          <h2 className="features-title animate-slide-up">Powerful Features Built for Education</h2>
          
          <div className="feature-cards-grid animate-slide-up delay-100">
            <article className="feature-card-glass">
              <div className="icon-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
              </div>
              <h3>Smart Content Upload</h3>
              <p>
                Upload PDFs, documents, and notes. AI automatically extracts, chunks, and vectorizes everything into a searchable knowledge base in seconds.
              </p>
            </article>

            <article className="feature-card-glass">
              <div className="icon-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              </div>
              <h3>Grounded AI Tutor</h3>
              <p>
                Chat with your course materials. Get instant answers backed by 100% source citations. No more AI hallucinations confusing students.
              </p>
            </article>

            <article className="feature-card-glass">
              <div className="icon-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
              </div>
              <h3>Auto Grading</h3>
              <p>
                Grade assignments in seconds. Define rubrics once, and AI consistently evaluates student work with detailed, actionable feedback.
              </p>
            </article>

            <article className="feature-card-glass">
              <div className="icon-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
              </div>
              <h3>Quiz Generation</h3>
              <p>
                Auto-generate MCQs, flashcards, and study guides from your course materials. Customize difficulty and topic focus instantly.
              </p>
            </article>

            <article className="feature-card-glass">
              <div className="icon-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20m10-10H2"/><circle cx="12" cy="12" r="9"/></svg>
              </div>
              <h3>Multilingual Support</h3>
              <p>
                Support global classrooms. AI tutoring works fluently in Hindi, Tamil, Telugu, and more—all with Sarvam's indigenous AI backbone.
              </p>
            </article>

            <article className="feature-card-glass">
              <div className="icon-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 12l-8.5 8.5a2 2 0 0 1-2.828-2.828l8.5-8.5"/><path d="m9 4l3-2 6 4 1 1 1 6 4 3-2 3"/><path d="M5 2l3 3"/></svg>
              </div>
              <h3>Knowledge Gap Detection</h3>
              <p>
                AI clusters student questions to reveal knowledge gaps by topic. Teachers get insights on what struggled most across the class.
              </p>
            </article>
          </div>
        </section>

        {/* FINAL CTA SECTION */}
        <section className="cta-final">
          <div className="cta-content animate-slide-up">
            <h2 className="cta-title">Ready to Transform Your Classroom?</h2>
            <p className="cta-subtitle">
              Start free today. No credit card required. Set up your first classroom in under 2 minutes.
            </p>
            <Link to="/login" className="btn-primary btn-large">
              Create Your Classroom
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </Link>
          </div>
        </section>
      </main>
    </>
  );
}