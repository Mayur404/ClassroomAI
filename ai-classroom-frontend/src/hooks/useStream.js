/**
 * React streaming hook for SSE endpoints
 * Handles connection, event parsing, error recovery
 */

import { useState, useCallback, useEffect, useRef } from 'react';

/**
 * Hook for streaming responses from SSE endpoints
 * 
 * Usage:
 * const { events, status, progress, error, start, abort } = useStream();
 * 
 * const handleStreamAnswer = () => {
 *   start({
 *     url: '/api/chat/stream-answer/',
 *     data: { query: 'What is AI?', course_id: 1 }
 *   });
 * };
 */
export function useStream() {
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState('idle'); // idle, connecting, streaming, complete, error
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [currentAnswer, setCurrentAnswer] = useState('');
  
  const requestAbortControllerRef = useRef(null);
  const bufferRef = useRef('');

  const parseEvent = useCallback((eventString) => {
    if (!eventString.trim()) return null;

    const lines = eventString.trim().split('\n');
    const event = {};

    for (const line of lines) {
      if (line.startsWith('event:')) {
        event.type = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        if (!event.data) event.data = '';
        event.data += line.substring(5).trim();
      } else if (line.startsWith('id:')) {
        event.id = line.substring(3).trim();
      } else if (line.startsWith('retry:')) {
        event.retry = parseInt(line.substring(6).trim());
      }
    }

    if (event.data) {
      try {
        event.data = JSON.parse(event.data);
      } catch (e) {
        // Keep as string
      }
    }

    return event.type ? event : null;
  }, []);

  const start = useCallback(async ({ url, data = {} }) => {
    setStatus('connecting');
    setEvents([]);
    setError(null);
    setProgress(0);
    setCurrentAnswer('');
    bufferRef.current = '';

    try {
      requestAbortControllerRef.current = new AbortController();

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Token ${localStorage.getItem('ai-classroom-token') || ''}`,
        },
        body: JSON.stringify(data),
        signal: requestAbortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      setStatus('streaming');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          setStatus('complete');
          break;
        }

        bufferRef.current += decoder.decode(value, { stream: true });

        // Process complete events (separated by double newline)
        const parts = bufferRef.current.split('\n\n');
        bufferRef.current = parts[parts.length - 1];

        for (let i = 0; i < parts.length - 1; i++) {
          const event = parseEvent(parts[i]);
          if (event) {
            setEvents((prev) => [...prev, event]);

            // Update UI based on event type
            if (event.data?.progress) {
              setProgress(event.data.progress);
            }

            if (event.type === 'answer_chunk') {
              setCurrentAnswer((prev) => prev + (event.data?.chunk || ''));
            }

            if (event.type === 'complete') {
              if (event.data?.answer) {
                setCurrentAnswer(event.data.answer);
              }
              setStatus('complete');
            }

            if (event.type === 'error') {
              setError(event.data?.message || 'Unknown error');
              setStatus('error');
            }
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        setStatus('cancelled');
      } else {
        setError(err.message);
        setStatus('error');
      }
    }
  }, [parseEvent]);

  const abort = useCallback(() => {
    if (requestAbortControllerRef.current) {
      requestAbortControllerRef.current.abort();
      setStatus('cancelled');
    }
  }, []);

  return {
    events,
    status,
    progress,
    error,
    currentAnswer,
    start,
    abort,
  };
}

/**
 * Higher-level hook for chat streaming
 */
export function useStreamChat() {
  const { events, status, progress, error, currentAnswer, start, abort } = useStream();

  const streamAnswer = useCallback((query, courseId) => {
    start({
      url: `/api/courses/${courseId}/chat/stream/`,
      data: { message: query },
    });
  }, [start]);

  const metadata = {
    retrieval_time: null,
    rerank_time: null,
    generation_time: null,
    documents_count: 0,
    quality_score: 0,
    documents: [],
  };

  // Extract metadata from events
  events.forEach((event) => {
    if (event.data) {
      if (event.data.retrieval_time_ms)
        metadata.retrieval_time = event.data.retrieval_time_ms;
      if (event.data.rerank_metrics)
        metadata.rerank_time = event.data.rerank_metrics.rerank_time_ms;
      if (event.data.generation_time_ms)
        metadata.generation_time = event.data.generation_time_ms;
      if (event.data.documents_count)
        metadata.documents_count = event.data.documents_count;
      if (event.data.quality_score)
        metadata.quality_score = event.data.quality_score;
      if (event.data.documents)
        metadata.documents = event.data.documents;
    }
  });

  return {
    events,
    status,
    progress,
    error,
    answer: currentAnswer,
    metadata,
    streamAnswer,
    abort,
    isLoading: status === 'connecting' || status === 'streaming',
    isComplete: status === 'complete',
    isFailed: status === 'error',
  };
}
