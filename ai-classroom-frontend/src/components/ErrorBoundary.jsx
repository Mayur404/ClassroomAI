/**
 * Frontend Error Boundary Component
 * Catches React component errors and displays user-friendly fallback UI
 */

import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { 
      hasError: false, 
      error: null, 
      errorInfo: null,
      correlationId: null 
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    const correlationId = crypto.randomUUID();
    
    this.setState({
      error: error,
      errorInfo: errorInfo,
      correlationId: correlationId,
    });

    // Log to backend
    console.error('Error caught by boundary:', error, errorInfo);
    
    // Send to error tracking service
    this.reportError(error, correlationId);
  }

  reportError = (error, correlationId) => {
    // Send to backend for logging
    const baseURL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";
    const token = localStorage.getItem("ai-classroom-token");

    fetch(`${baseURL}/errors/log`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': token ? `Token ${token}` : ""
      },
      body: JSON.stringify({
        message: error.toString(),
        stack: error.stack,
        timestamp: new Date().toISOString(),
        url: window.location.href,
        correlationId: correlationId,
      }),
    }).catch(console.error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <div className="error-container">
            <h2>Something went wrong</h2>
            <details className="error-details">
              <summary>Error details (Correlation ID: {this.state.correlationId})</summary>
              <p>{this.state.error && this.state.error.toString()}</p>
              <pre>{this.state.errorInfo && this.state.errorInfo.componentStack}</pre>
            </details>
            <button onClick={() => window.location.reload()}>
              Reload Page
            </button>
            <button onClick={() => this.setState({ hasError: false })}>
              Dismiss
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
