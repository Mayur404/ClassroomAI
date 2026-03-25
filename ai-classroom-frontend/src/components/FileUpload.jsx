import { useEffect, useRef, useState } from "react";

import client from "../api/client";

export default function FileUpload({ courseId, onUploadSuccess }) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [uploadState, setUploadState] = useState({
    active: false,
    phase: "idle",
    percent: 0,
    detail: "",
    summary: null,
    error: "",
  });
  const processingTimerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (processingTimerRef.current) {
        clearInterval(processingTimerRef.current);
      }
    };
  }, []);

  const uploading = uploadState.active;

  const stopProcessingAnimation = () => {
    if (processingTimerRef.current) {
      clearInterval(processingTimerRef.current);
      processingTimerRef.current = null;
    }
  };

  const startProcessingAnimation = (detail) => {
    setUploadState((prev) => {
      if (prev.phase === "processing") {
        return prev;
      }
      return {
        ...prev,
        phase: "processing",
        percent: Math.max(prev.percent, 72),
        detail,
      };
    });

    if (processingTimerRef.current) return;

    processingTimerRef.current = setInterval(() => {
      setUploadState((prev) => {
        if (!prev.active || prev.phase !== "processing") {
          return prev;
        }
        const increment = prev.percent < 85 ? 4 : 2;
        return {
          ...prev,
          percent: Math.min(prev.percent + increment, 95),
        };
      });
    }, 450);
  };

  const buildSummary = (responseData) => {
    const extraction = responseData?.parse_metadata?.last_extraction;
    if (!extraction) return null;

    const parts = [];
    if (extraction.page_count) parts.push(`${extraction.page_count} pages`);
    if (extraction.image_page_count) parts.push(`${extraction.image_page_count} image page(s)`);
    if (extraction.ocr_page_count) parts.push(`OCR used on ${extraction.ocr_page_count} page(s)`);
    if (extraction.word_count) parts.push(`${extraction.word_count} words extracted`);
    if (extraction.warnings?.length) parts.push(extraction.warnings[0]);

    return parts.join(" · ");
  };

  const handleFileChange = (event) => {
    const nextFile = event.target.files?.[0] || null;
    setFile(nextFile);
    setText("");
    if (!title && nextFile) {
      setTitle(nextFile.name.replace(/\.pdf$/i, ""));
    }
    setUploadState((prev) => ({ ...prev, error: "", summary: null }));
  };

  const handleTextChange = (event) => {
    setText(event.target.value);
    setFile(null);
    setUploadState((prev) => ({ ...prev, error: "", summary: null }));
  };

  const handleUpload = async () => {
    if (!file && !text.trim()) {
      alert("Please provide either a PDF or paste some text.");
      return;
    }

    stopProcessingAnimation();
    setUploadState({
      active: true,
      phase: file ? "uploading" : "processing",
      percent: file ? 5 : 20,
      detail: file
        ? `Uploading ${file.name}...`
        : "Sending text and preparing extraction...",
      summary: null,
      error: "",
    });

    const formData = new FormData();
    formData.append("title", title.trim() || "Untitled Material");
    if (file) {
      formData.append("syllabus_pdf", file);
    } else {
      formData.append("syllabus_text", text);
      startProcessingAnimation("Text received. Extracting topics, indexing content, and rebuilding the learning path...");
    }

    try {
      const response = await client.post(`/courses/${courseId}/syllabus/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (event) => {
          if (!file) return;

          const total = event.total || file.size || 0;
          if (!total) return;

          const rawPercent = Math.round((event.loaded / total) * 100);
          const uploadPercent = Math.max(5, Math.min(70, Math.round((event.loaded / total) * 70)));

          setUploadState((prev) => ({
            ...prev,
            active: true,
            phase: "uploading",
            percent: Math.max(prev.percent, uploadPercent),
            detail: `Uploading ${file.name}... ${rawPercent}%`,
          }));

          if (event.loaded >= total) {
            startProcessingAnimation(
              "Upload complete. Extracting text, OCR-ing scanned pages, indexing content, and rebuilding the learning path..."
            );
          }
        },
      });

      stopProcessingAnimation();
      setUploadState({
        active: true,
        phase: "done",
        percent: 100,
        detail: "Material analyzed successfully.",
        summary: buildSummary(response.data),
        error: "",
      });

      setTimeout(() => {
        onUploadSuccess(response.data);
        setUploadState({
          active: false,
          phase: "idle",
          percent: 0,
          detail: "",
          summary: buildSummary(response.data),
          error: "",
        });
        setFile(null);
        setText("");
        setTitle("");
      }, 250);
    } catch (error) {
      stopProcessingAnimation();
      const detail =
        error?.response?.data?.detail ||
        "Material upload failed. Check backend logs for extraction details.";
      console.error("Upload failed:", error);
      setUploadState({
        active: false,
        phase: "idle",
        percent: 0,
        detail: "",
        summary: null,
        error: detail,
      });
      alert(detail);
    }
  };

  return (
    <div className="file-upload stack compact">
      <input
        type="text"
        className="input-field"
        placeholder="Material Title (e.g. Week 1 Slides)"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        disabled={uploading}
      />

      <div className="upload-options grid">
        <div className="upload-zone">
          <input
            type="file"
            accept=".pdf,application/pdf"
            onChange={handleFileChange}
            id="syllabus-file"
            disabled={uploading}
          />
          <label htmlFor="syllabus-file">
            {file ? file.name : "Upload PDF"}
          </label>
        </div>
        <div className="text-divider text-muted">OR</div>
        <textarea
          className="input-field"
          placeholder="Paste text here..."
          value={text}
          onChange={handleTextChange}
          disabled={uploading}
          rows="3"
        />
      </div>

      <p className="text-muted text-small">
        Searchable PDFs, scanned PDFs, and PDFs containing embedded images are supported. OCR runs automatically when needed.
      </p>

      {(file || text.trim()) && !uploading && (
        <button className="btn-primary" onClick={handleUpload}>
          Add Material & Analyze
        </button>
      )}

      {uploadState.active && (
        <div className={`progress-shell phase-${uploadState.phase}`}>
          <div className="progress-meta">
            <strong>
              {uploadState.phase === "uploading"
                ? "Uploading"
                : uploadState.phase === "processing"
                ? "Processing"
                : "Completed"}
            </strong>
            <span>{uploadState.percent}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${uploadState.percent}%` }}></div>
          </div>
          <span>{uploadState.detail}</span>
          {uploadState.summary && (
            <p className="upload-summary">{uploadState.summary}</p>
          )}
        </div>
      )}

      {!uploadState.active && uploadState.summary && (
        <p className="upload-summary">{uploadState.summary}</p>
      )}

      {uploadState.error && (
        <p className="upload-error">{uploadState.error}</p>
      )}
    </div>
  );
}
