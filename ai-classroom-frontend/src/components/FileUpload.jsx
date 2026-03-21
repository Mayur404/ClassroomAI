import { useState } from "react";
import client from "../api/client";

export default function FileUpload({ courseId, onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress(10);

    const formData = new FormData();
    formData.append("syllabus_pdf", file);

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
        setProgress(0);
      }, 500);
    } catch (error) {
      console.error("Upload failed:", error);
      alert("Syllabus upload and parsing failed. Check console for details.");
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div className="file-upload stack compact">
      <div className="upload-zone">
        <input type="file" accept=".pdf" onChange={handleFileChange} id="syllabus-file" />
        <label htmlFor="syllabus-file">
          {file ? file.name : "Drop syllabus PDF or Click to Browse"}
        </label>
      </div>
      {file && !uploading && (
        <button onClick={handleUpload}>Parse Syllabus PDF</button>
      )}
      {uploading && (
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }}></div>
          <span>{progress < 100 ? "AI is reading your syllabus..." : "Done!"}</span>
        </div>
      )}
    </div>
  );
}
