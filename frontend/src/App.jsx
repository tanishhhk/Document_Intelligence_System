import { useState, useEffect, useRef } from "react";
import "./App.css";

// Set VITE_API_URL when building for a deployed backend.
const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const ACTIVE = ["queued", "running"];

// FastAPI returns `detail` as a string for HTTPException but as an array of
// error objects for validation failures. Rendering the array directly prints
// "[object Object]", so unwrap it to the first readable message.
function readError(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    const msg = typeof first === "string" ? first : first?.msg;
    if (msg) return msg.replace(/^Value error,\s*/, "");
  }
  return fallback;
}

// The signature element: a marigold highlighter stroke that draws itself
// behind "guru" on load. Studying a document is highlighting it.
function Wordmark({ compact = false }) {
  return (
    <div className={`wordmark ${compact ? "is-compact" : ""}`}>
      <span className="wordmark-text">
        <span className="wordmark-guru">
          <svg
            className="wordmark-swipe"
            viewBox="0 0 200 44"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <path
              d="M4 30C56 20 140 18 196 26C142 34 58 36 4 30Z"
              fill="var(--marigold)"
            />
          </svg>
          <span className="wordmark-guru-label">guru</span>
        </span>
        <span className="wordmark-cool">Cool</span>
      </span>
    </div>
  );
}

function StoryCard({ job, videoUrl, fileName }) {
  return (
    <section className="story-card" aria-label="The story of your document">
      <p className="story-eyebrow">
        {job.story_source === "ai"
          ? "A story by your narrator"
          : "Told in the document's own words"}
      </p>
      <h3 className="story-title">{job.title}</h3>
      <ol className="story-scenes">
        {job.scenes.map((scene, index) => (
          <li key={index} className="story-scene">
            <h4>{scene.heading}</h4>
            <p>{scene.text}</p>
          </li>
        ))}
      </ol>
      {videoUrl ? (
        <div className="story-video">
          <video src={videoUrl} controls className="video-player" />
          <a
            className="video-download"
            href={videoUrl}
            download={`${fileName.replace(/\.pdf$/i, "")}-story.mp4`}
          >
            Download the video
          </a>
        </div>
      ) : job.video_status === "rendering" ? (
        <p className="story-note">
          The narrated video is being made. Read on while it finishes.
        </p>
      ) : job.video_error ? (
        <p className="story-note">{job.video_error}</p>
      ) : null}
    </section>
  );
}

function App() {
  // Auth state
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [token, setToken] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);

  // Workflow state
  const [step, setStep] = useState(1); // 1: Upload, 2: Chat

  // Document state
  const [file, setFile] = useState(null);
  const [documentId, setDocumentId] = useState(null);
  const [uploadedFileName, setUploadedFileName] = useState("");

  // Chat state
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [chatMode, setChatMode] = useState("strict"); // "strict" or "exam"
  const messagesEndRef = useRef(null);

  // Video state. Strictness reuses chatMode; depth is the second axis.
  const [videoDepth, setVideoDepth] = useState("overview"); // "overview" or "detailed"
  const [videoJob, setVideoJob] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);

  // UI status
  const [status, setStatus] = useState("");

  // A stored token may already have expired. Check it against /auth/me before
  // trusting it, otherwise the app renders signed-in and every call 401s.
  useEffect(() => {
    const savedToken = localStorage.getItem("gurucool_token");
    if (!savedToken) {
      setCheckingSession(false);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const response = await fetch(`${API_URL}/auth/me`, {
          headers: { Authorization: `Bearer ${savedToken}` },
        });
        if (cancelled) return;

        if (response.ok) {
          const user = await response.json();
          setToken(savedToken);
          setEmail(user.email);
        } else {
          localStorage.removeItem("gurucool_token");
          localStorage.removeItem("gurucool_email");
        }
      } catch {
        // Backend unreachable — stay signed out rather than half-broken.
        if (!cancelled) {
          localStorage.removeItem("gurucool_token");
        }
      } finally {
        if (!cancelled) setCheckingSession(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // Save token to localStorage when it changes
  useEffect(() => {
    if (token) {
      localStorage.setItem("gurucool_token", token);
      localStorage.setItem("gurucool_email", email);
    } else {
      localStorage.removeItem("gurucool_token");
      localStorage.removeItem("gurucool_email");
    }
  }, [token, email]);

  // Auto-scroll chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, asking, videoJob?.scenes?.length]);

  // Poll an in-flight video job. Depends on id/status rather than the whole
  // job object so the interval isn't torn down on every progress tick.
  useEffect(() => {
    if (!token || !videoJob) return;
    if (!ACTIVE.includes(videoJob.status)) return;

    const timer = setInterval(async () => {
      try {
        const response = await fetch(
          `${API_URL}/videos/${videoJob.id}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (!response.ok) return;

        const job = await response.json();
        setVideoJob(job);

        if (job.status === "completed" && job.video_status === "ready") {
          loadVideo(job.id);
        } else if (job.status === "failed") {
          setMessages((prev) => [
            ...prev,
            {
              type: "error",
              text: `The story could not be written: ${job.error || "unknown error"}`,
            },
          ]);
        }
      } catch (err) {
        console.error("Poll error:", err);
      }
    }, 2000);

    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoJob?.id, videoJob?.status, token]);

  // Release the blob URL when it's replaced or the app unmounts.
  useEffect(() => {
    return () => {
      if (videoUrl) URL.revokeObjectURL(videoUrl);
    };
  }, [videoUrl]);

  // ---------------- AUTH ----------------

  // Field-level validation. Errors sit next to the input they belong to,
  // not stacked at the top of the form.
  const validateAuth = () => {
    const next = {};

    if (!email.trim()) {
      next.email = "Enter your email address";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      next.email = "That doesn't look like an email address";
    }

    if (!password) {
      next.password = "Enter your password";
    } else if (!isLogin) {
      const bytes = new TextEncoder().encode(password).length;
      if (password.length < 12) {
        next.password = "Use at least 12 characters";
      } else if (bytes > 72) {
        next.password = "Too long — shorten it (accents and emoji count extra)";
      }
    }

    if (!isLogin && confirmPassword !== password) {
      next.confirmPassword = "Both passwords need to match";
    }

    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleAuthSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    if (!validateAuth()) return;

    setSubmitting(true);
    setStatus("");

    const path = isLogin ? "login" : "register";
    const credentials = JSON.stringify({ email: email.trim(), password });
    const post = (route) =>
      fetch(`${API_URL}/auth/${route}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: credentials,
      });

    try {
      if (!isLogin) {
        const created = await post("register");
        if (!created.ok) {
          const failure = await created.json().catch(() => ({}));
          throw new Error(readError(failure, "Something went wrong. Try again."));
        }
      }
      const response = await post("login");
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(readError(data, "Something went wrong. Try again."));
      }

      setToken(data.access_token);
      setEmail(email.trim());
      setPassword("");
      setConfirmPassword("");
      setFieldErrors({});
      setStep(1);
    } catch (err) {
      setStatus(err.message);
      console.error(`${path} error:`, err);
    } finally {
      setSubmitting(false);
    }
  };

  const switchAuthMode = (login) => {
    setIsLogin(login);
    setStatus("");
    setFieldErrors({});
    setPassword("");
    setConfirmPassword("");
  };

  const handleLogout = () => {
    if (messages.length > 0 && !window.confirm("Are you sure you want to logout? Your chat history will be lost.")) {
      return;
    }
    
    setToken(null);
    setDocumentId(null);
    setFile(null);
    setUploadedFileName("");
    setQuestion("");
    setMessages([]);
    setStatus("");
    setStep(1);
    setChatMode("strict");
    setVideoJob(null);
    setVideoUrl(null);
  };

  // ---------------- DOCUMENT UPLOAD ----------------

  const handleUpload = async () => {
    if (!token) {
      setStatus("✗ Session expired. Please login again.");
      return;
    }
    if (!file) {
      setStatus("✗ Please select a PDF first");
      return;
    }

    // Check file size (10MB limit)
    if (file.size > 10 * 1024 * 1024) {
      setStatus("✗ File too large. Maximum size is 10MB");
      return;
    }

    // Check file type
    if (!file.type.includes("pdf")) {
      setStatus("✗ Please upload a PDF file");
      return;
    }

    setStatus("Uploading document...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_URL}/documents/upload`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          // Lets a retried upload return the same document instead of a copy.
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(readError(err, "Upload failed"));
      }

      let data = await response.json();
      const docId = data.id;

      // Processing happens in the background; wait until it is done.
      const deadline = Date.now() + 5 * 60 * 1000;
      while (!["completed", "failed"].includes(data.status)) {
        if (Date.now() > deadline) throw new Error("Processing is taking too long. Try again later.");
        setStatus("Studying your document… this takes a few seconds per page.");
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const check = await fetch(`${API_URL}/documents/${docId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!check.ok) throw new Error("Lost track of the upload. Try again.");
        data = await check.json();
      }
      if (data.status === "failed") {
        throw new Error(data.error_message || "The document could not be processed.");
      }

      setDocumentId(docId);
      setUploadedFileName(file.name);
      setStatus("");
      setStep(2);
      
      setMessages([
        {
          type: "system",
          text: `✓ "${file.name}" is ready: ${data.page_count} pages studied.\n\nAsk anything about it, or press "Tell its story" for a narrated walkthrough.`,
        },
      ]);
      
    } catch (err) {
      setStatus(`✗ ${err.message}`);
      console.error("Upload error:", err);
    }
  };

  // ---------------- CHAT ----------------

  const handleAskQuestion = async () => {
    // Prevent duplicate requests
    if (asking) return;

    // Check if document is uploaded
    if (!documentId) {
      setMessages((prev) => [
        ...prev,
        {
          type: "error",
          text: "⚠️ No document uploaded. Please upload a document first.",
        },
      ]);
      console.error("No document ID found. Current documentId:", documentId);
      return;
    }

    if (!question.trim()) return;

    const userMessage = { type: "user", text: question };
    setMessages((prev) => [...prev, userMessage]);
    setQuestion("");
    setAsking(true);

    try {
      const response = await fetch(`${API_URL}/chat/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          document_id: documentId,
          question: userMessage.text,
        }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(readError(err, "Question failed"));
      }

      const data = await response.json();
      const pages = [
        ...new Set(
          (data.sources || [])
            .filter((source) => source.cited || data.answer_status === "extractive")
            .map((source) => source.page_start)
            .filter(Boolean)
        ),
      ];
      const where = pages.length
        ? `\n\n${pages.length > 1 ? "Pages" : "Page"} ${pages.join(", ")}`
        : "";

      setMessages((prev) => [
        ...prev,
        { type: "assistant", text: (data.answer || "No answer received") + where },
      ]);
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) => [
        ...prev,
        { type: "error", text: `❌ Error: ${err.message}` },
      ]);
    } finally {
      setAsking(false);
    }
  };

  const handleGenerateVideo = async () => {
    if (!documentId) return;
    if (videoJob && ACTIVE.includes(videoJob.status)) return;

    setVideoUrl(null);

    try {
      const response = await fetch(
        `${API_URL}/videos/generate/${documentId}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ strictness: chatMode, depth: videoDepth }),
        }
      );

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(readError(err, "Could not start the story"));
      }

      const job = await response.json();
      setVideoJob(job);
      setMessages((prev) => [
        ...prev,
        {
          type: "system",
          text: `Writing ${videoDepth === "overview" ? "a short" : "a detailed"} story${
            chatMode === "exam" ? " that explains as it goes" : " that sticks to the facts"
          }. It appears here in under a minute; the narrated video follows. Keep chatting meanwhile.`,
        },
      ]);
    } catch (err) {
      console.error("Video error:", err);
      setMessages((prev) => [
        ...prev,
        { type: "error", text: err.message },
      ]);
    }
  };

  // The mp4 needs the auth header, so fetch it as a blob rather than
  // pointing <video src> straight at the endpoint.
  const loadVideo = async (jobId) => {
    try {
      const response = await fetch(
        `${API_URL}/videos/${jobId}/download`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!response.ok) throw new Error("Could not download video");
      const blob = await response.blob();
      setVideoUrl(URL.createObjectURL(blob));
    } catch (err) {
      console.error("Video download error:", err);
      setMessages((prev) => [
        ...prev,
        { type: "error", text: `❌ ${err.message}` },
      ]);
    }
  };

  const handleModeChange = (mode) => {
    setChatMode(mode);
    setMessages((prev) => [
      ...prev,
      {
        type: "system",
        text: mode === "strict"
          ? "Stories will stick to the document's facts."
          : "Stories will explain and simplify, like a tutor before an exam. Chat answers always quote the document.",
      },
    ]);
  };

  // ---------------- UI ----------------

  // Don't flash the sign-in page while we're checking a stored token.
  if (checkingSession) {
    return (
      <div className="app-wrapper">
        <div className="session-check" role="status">
          Loading…
        </div>
      </div>
    );
  }

  return (
    <div className={`app-wrapper ${token ? "is-logged-in" : ""}`}>
      <div className={`container ${!token ? "is-auth" : "is-loggedin"}`}>
        {!token ? (
          <div className="auth">
            <section className="auth-pitch">
              <p className="auth-eyebrow">The guru–shishya way</p>
              <Wordmark />
              <p className="auth-tagline">
                One teacher, one student, and no moving on until the concept
                actually landed. That's the idea here — it studies your
                document, then teaches it back to you, in as much detail as you
                want.
              </p>

              <ol className="auth-flow">
                <li>
                  <span className="auth-flow-label">Bring the text</span>
                  <span className="auth-flow-text">
                    A 200-page PDF is fine.
                  </span>
                </li>
                <li>
                  <span className="auth-flow-label">It studies</span>
                  <span className="auth-flow-text">
                    Every section, not just the first few pages.
                  </span>
                </li>
                <li>
                  <span className="auth-flow-label">It teaches</span>
                  <span className="auth-flow-text">
                    Ask until it clicks, or watch it explain the whole thing.
                  </span>
                </li>
              </ol>
            </section>

            <section className="auth-card">
              <div className="auth-switch" role="tablist" aria-label="Account">
                <button
                  type="button"
                  role="tab"
                  aria-selected={isLogin}
                  className={`auth-switch-btn ${isLogin ? "is-active" : ""}`}
                  onClick={() => switchAuthMode(true)}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={!isLogin}
                  className={`auth-switch-btn ${!isLogin ? "is-active" : ""}`}
                  onClick={() => switchAuthMode(false)}
                >
                  Create account
                </button>
              </div>

              <form className="auth-form" onSubmit={handleAuthSubmit} noValidate>
                <div className="field">
                  <label htmlFor="email">Email</label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    autoCapitalize="none"
                    spellCheck="false"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    aria-invalid={Boolean(fieldErrors.email)}
                    aria-describedby={fieldErrors.email ? "email-error" : undefined}
                  />
                  {fieldErrors.email && (
                    <p className="field-error" id="email-error">
                      {fieldErrors.email}
                    </p>
                  )}
                </div>

                <div className="field">
                  <label htmlFor="password">Password</label>
                  <div className="field-with-action">
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete={isLogin ? "current-password" : "new-password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      aria-invalid={Boolean(fieldErrors.password)}
                      aria-describedby={
                        fieldErrors.password
                          ? "password-error"
                          : !isLogin
                          ? "password-hint"
                          : undefined
                      }
                    />
                    <button
                      type="button"
                      className="field-action"
                      onClick={() => setShowPassword((v) => !v)}
                      aria-pressed={showPassword}
                    >
                      {showPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                  {fieldErrors.password ? (
                    <p className="field-error" id="password-error">
                      {fieldErrors.password}
                    </p>
                  ) : (
                    !isLogin && (
                      <p className="field-hint" id="password-hint">
                        At least 12 characters. A short sentence works well.
                      </p>
                    )
                  )}
                </div>

                {!isLogin && (
                  <div className="field">
                    <label htmlFor="confirmPassword">Confirm password</label>
                    <input
                      id="confirmPassword"
                      name="confirmPassword"
                      type={showPassword ? "text" : "password"}
                      autoComplete="new-password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      aria-invalid={Boolean(fieldErrors.confirmPassword)}
                      aria-describedby={
                        fieldErrors.confirmPassword ? "confirm-error" : undefined
                      }
                    />
                    {fieldErrors.confirmPassword && (
                      <p className="field-error" id="confirm-error">
                        {fieldErrors.confirmPassword}
                      </p>
                    )}
                  </div>
                )}

                <button
                  type="submit"
                  className="btn-primary"
                  disabled={submitting}
                >
                  {submitting
                    ? isLogin
                      ? "Signing in…"
                      : "Creating account…"
                    : isLogin
                    ? "Sign in"
                    : "Create account"}
                </button>

                {status && (
                  <p className="form-error" role="alert">
                    {status}
                  </p>
                )}
              </form>
            </section>
          </div>
        ) : (
          <>
            {/* ---- Sticky top navigation ---- */}
            <nav className="topbar">
              <div className="topbar-left">
                <Wordmark compact />
                <span className="topbar-email">{email}</span>
              </div>
              <button className="logout-btn" onClick={handleLogout}>
                Sign out
              </button>
            </nav>

            {/* ==================== STEP 1: Upload ==================== */}
            {step === 1 && (
              <div className="upload-page">
                <div className="upload-content">
                  <div className="step-badge">
                    <span className="step-dot" />
                    Step 1 of 2
                  </div>

                  <h1 className="upload-hero-title">
                    Upload your document,
                    <br />
                    <span className="accent">unlock its knowledge.</span>
                  </h1>

                  <p className="upload-hero-subtitle">
                    Drop a PDF and let guruCool study every page — then ask questions,
                    get explanations, or hear the whole thing told as a story.
                  </p>

                  <div className="features-row">
                    <div className="feature-tile">
                      <span className="feature-tile-icon">💬</span>
                      <h3>Ask Questions</h3>
                      <p>Get instant, cited answers drawn directly from your document</p>
                    </div>
                    <div className="feature-tile">
                      <span className="feature-tile-icon">🎬</span>
                      <h3>Story Mode</h3>
                      <p>A witty narrated story of the whole document, with a video</p>
                    </div>
                    <div className="feature-tile">
                      <span className="feature-tile-icon">🎓</span>
                      <h3>Exam Mode</h3>
                      <p>Concepts simplified and explained like a personal tutor</p>
                    </div>
                  </div>

                  <div className={`drop-zone ${file ? "has-file" : ""}`}>
                    <input
                      type="file"
                      accept="application/pdf"
                      onChange={(e) => setFile(e.target.files[0])}
                      id="file-input"
                    />
                    <label htmlFor="file-input" className="drop-zone-label">
                      {file ? (
                        <div className="drop-zone-file">
                          <div className="drop-zone-icon">📄</div>
                          <span className="drop-zone-file-name">{file.name}</span>
                          <span className="drop-zone-file-size">
                            {(file.size / 1024 / 1024).toFixed(2)} MB
                          </span>
                        </div>
                      ) : (
                        <>
                          <div className="drop-zone-icon">📤</div>
                          <span className="drop-zone-text">
                            Click to select your PDF
                          </span>
                          <span className="drop-zone-hint">
                            PDF files up to 10 MB
                          </span>
                        </>
                      )}
                    </label>
                  </div>

                  <button
                    className="upload-cta"
                    onClick={handleUpload}
                    disabled={!file}
                  >
                    <span>Upload & Continue →</span>
                  </button>

                  {status && <p className="status-toast">{status}</p>}
                </div>
              </div>
            )}

            {/* ==================== STEP 2: Chat ==================== */}
            {step === 2 && (
              <div className="chat-page">
                <div className="chat-page-header">
                  <div className="chat-page-header-left">
                    <h2>Chat with Your Document</h2>
                    <p className="chat-doc-name">📄 {uploadedFileName}</p>
                  </div>
                  <button
                    className="video-btn"
                    onClick={handleGenerateVideo}
                    disabled={videoJob && ACTIVE.includes(videoJob.status)}
                  >
                    {videoJob && ACTIVE.includes(videoJob.status)
                      ? `🎬 ${videoJob.progress}%`
                      : "🎬 Tell its story"}
                  </button>
                </div>

                {/* Chat Mode Selector */}
                <div className="mode-selector">
                  <div className="mode-label">Story style</div>
                  <div className="mode-buttons">
                    <button
                      className={`mode-btn ${chatMode === "strict" ? "active" : ""}`}
                      onClick={() => handleModeChange("strict")}
                      title="Only the document's facts"
                    >
                      <span className="mode-icon">📋</span>
                      <div className="mode-info">
                        <div className="mode-title">Strict</div>
                        <div className="mode-desc">Facts only</div>
                      </div>
                    </button>
                    <button
                      className={`mode-btn ${chatMode === "exam" ? "active" : ""}`}
                      onClick={() => handleModeChange("exam")}
                      title="Explains and simplifies while staying accurate"
                    >
                      <span className="mode-icon">🎓</span>
                      <div className="mode-info">
                        <div className="mode-title">Exam / Research</div>
                        <div className="mode-desc">Explain & teach</div>
                      </div>
                    </button>
                  </div>
                </div>

                {/* Video Depth Selector — the second mode axis */}
                <div className="mode-selector">
                  <div className="mode-label">Story length</div>
                  <div className="mode-buttons">
                    <button
                      className={`mode-btn ${videoDepth === "overview" ? "active" : ""}`}
                      onClick={() => setVideoDepth("overview")}
                      title="A short story of the key points"
                    >
                      <span className="mode-icon">⚡</span>
                      <div className="mode-info">
                        <div className="mode-title">Overview</div>
                        <div className="mode-desc">~2 min, key points</div>
                      </div>
                    </button>
                    <button
                      className={`mode-btn ${videoDepth === "detailed" ? "active" : ""}`}
                      onClick={() => setVideoDepth("detailed")}
                      title="A longer walkthrough of the whole document"
                    >
                      <span className="mode-icon">📚</span>
                      <div className="mode-info">
                        <div className="mode-title">Detailed</div>
                        <div className="mode-desc">~4 min, more depth</div>
                      </div>
                    </button>
                  </div>
                </div>

                {/* Video progress / player */}
                {videoJob && ACTIVE.includes(videoJob.status) && (
                  <div className="video-panel">
                    <div className="video-stage">{videoJob.stage}</div>
                    <div className="video-progress-track">
                      <div
                        className="video-progress-bar"
                        style={{ width: `${videoJob.progress}%` }}
                      />
                    </div>
                  </div>
                )}

                <div className="chat-body">
                  <div className="messages">
                    {messages.map((msg, idx) => (
                      <div key={idx} className={`message ${msg.type}`}>
                        {msg.type === "user" && (
                          <div className="message-avatar">You</div>
                        )}
                        {msg.type === "assistant" && (
                          <div className="message-avatar">AI</div>
                        )}
                        {msg.type === "system" && (
                          <div className="message-avatar">ℹ️</div>
                        )}
                        <div className="message-content">{msg.text}</div>
                      </div>
                    ))}
                    {videoJob?.scenes?.length > 0 && (
                      <StoryCard
                        job={videoJob}
                        videoUrl={videoUrl}
                        fileName={uploadedFileName}
                      />
                    )}
                    {asking && (
                      <div className="message assistant">
                        <div className="message-avatar">AI</div>
                        <div className="message-content typing">
                          <span></span>
                          <span></span>
                          <span></span>
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>

                  <div className="chat-input-area">
                    <input
                      type="text"
                      placeholder="Ask a question about your document..."
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyPress={(e) =>
                        e.key === "Enter" && !asking && handleAskQuestion()
                      }
                      disabled={asking}
                    />
                    <button
                      className="send-btn"
                      onClick={handleAskQuestion}
                      disabled={asking || !question.trim()}
                    >
                      {asking ? "..." : "Send"}
                    </button>
                  </div>
                </div>

                <button
                  className="back-btn"
                  onClick={() => {
                    setStep(1);
                    setDocumentId(null);
                    setFile(null);
                    setUploadedFileName("");
                    setMessages([]);
                    setChatMode("strict");
                    setVideoJob(null);
                    setVideoUrl(null);
                  }}
                >
                  ← Upload New Document
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default App;