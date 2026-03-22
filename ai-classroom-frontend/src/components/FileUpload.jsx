import { useState } from "react";
import client from "../api/client";

export default function FileUpload({ courseId, onUploadSuccess }) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setText(""); // Clear text if file selected
    if (!title && e.target.files[0]) {
      setTitle(e.target.files[0].name.replace(".pdf", ""));
    }
  };

  const handleTextChange = (e) => {
    setText(e.target.value);
    setFile(null); // Clear file if text entered
  };

  const handleUpload = async () => {
    if (!file && !text.trim()) {
      alert("Please provide either a PDF or paste some text.");
      return;
    }
    setUploading(true);
    setProgress(10);

    const formData = new FormData();
    formData.append("title", title.trim() || "Untitled Material");
    if (file) {
      formData.append("syllabus_pdf", file);
    } else {
      formData.append("syllabus_text", text);
    }

    try {
      setProgress(40);
      const response = await client.post(`/courses/${courseId}/syllabus/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setProgress(100);
      setTimeout(() => {
        onUploadSuccess(response.data);
        setUploading(false);
        setFile(null);
        setText("");
        setTitle("");
        setProgress(0);
      }, 500);
    } catch (error) {
      console.error("Upload failed:", error);
      alert("Material upload failed. Check console for details.");
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div className="file-upload stack compact">
      <input
        type="text"
        className="input-field"
        placeholder="Material Title (e.g. Week 1 Slides)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        disabled={uploading}
      />
      
      <div className="upload-options grid">
        <div className="upload-zone">
          <input type="file" accept=".pdf" onChange={handleFileChange} id="syllabus-file" disabled={uploading} />
          <label htmlFor="syllabus-file">
            {file ? file.name : "📄 Upload PDF"}
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

      {(file || text.trim()) && !uploading && (
        <button className="btn-primary" onClick={handleUpload}>Add Material & Analyze</button>
      )}
      
      {uploading && (
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }}></div>
          <span>{progress < 100 ? "AI is analyzing material..." : "Done!"}</span>
        </div>
      )}
    </div>
  );
}
