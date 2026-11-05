import { useEffect, useState } from "react";
import { Download, Play } from "lucide-react";

import { api, wait } from "../api";
import { FOCUS } from "../lenses";

const ACTIVE = ["queued", "running"];

function Options({ value, onChange, options, label }) {
  return (
    <fieldset className="segmented">
      <legend>{label}</legend>
      {options.map(([id, title, line]) => (
        <label key={id} className={value === id ? "is-selected" : ""}>
          <input type="radio" name={label} value={id} checked={value === id} onChange={() => onChange(id)} />
          <span className="segmented-title">{title}</span>
          <span className="segmented-line">{line}</span>
        </label>
      ))}
    </fieldset>
  );
}

export default function StoryPanel({ document, focus, onUsed }) {
  const [style, setStyle] = useState(focus ? FOCUS[focus].strictness : "strict");
  const [depth, setDepth] = useState("overview");
  const [job, setJob] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [error, setError] = useState("");

  // Show this document's latest story, if there is one.
  useEffect(() => {
    let cancelled = false;
    setJob(null);
    setVideoUrl(null);
    api("/videos")
      .then(async (stories) => {
        const latest = stories.find((story) => story.document_id === document.id);
        if (!latest || cancelled) return;
        const detail = await api(`/videos/${latest.id}`);
        // A slow answer must not replace a story started since this page opened.
        if (!cancelled) setJob((current) => current ?? detail);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [document.id]);

  // Follow a story while it is written and rendered.
  useEffect(() => {
    if (!job || !ACTIVE.includes(job.status)) return undefined;
    let stopped = false;
    (async () => {
      while (!stopped) {
        await wait(2500);
        try {
          const next = await api(`/videos/${job.id}`);
          if (!stopped) setJob(next);
          if (!ACTIVE.includes(next.status)) break;
        } catch {
          // Keep polling through brief network trouble.
        }
      }
    })();
    return () => {
      stopped = true;
    };
  }, [job?.id, job?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // The video needs the sign-in header, so fetch it as a blob.
  useEffect(() => {
    if (job?.video_status !== "ready") return undefined;
    let url;
    api(`/videos/${job.id}/download`, { raw: true })
      .then((response) => response.blob())
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setVideoUrl(url);
      })
      .catch(() => {});
    return () => url && URL.revokeObjectURL(url);
  }, [job?.id, job?.video_status]);

  const start = async () => {
    setError("");
    try {
      setVideoUrl(null);
      setJob(await api(`/videos/generate/${document.id}`, { method: "POST", body: { strictness: style, depth } }));
    } catch (failure) {
      setError(failure.message);
    } finally {
      onUsed();
    }
  };

  const writing = job && ACTIVE.includes(job.status);
  const hasStory = job?.scenes?.length > 0;

  return (
    <div className="story">
      {!writing && (
        <section className="story-setup" aria-label="Story options">
          <Options
            label="Telling"
            value={style}
            onChange={setStyle}
            options={[
              ["strict", "Stick to the facts", "Only what the document says"],
              ["exam", "Explain it simply", "In plainer words, like a tutor"],
            ]}
          />
          <Options
            label="Length"
            value={depth}
            onChange={setDepth}
            options={[
              ["overview", "Short", "About 2 minutes"],
              ["detailed", "Detailed", "About 4 minutes"],
            ]}
          />
          <button type="button" className="button button-primary" onClick={start}>
            <Play size={18} strokeWidth={2} aria-hidden="true" />
            {hasStory ? "Tell a new story" : "Tell its story"}
          </button>
          {error && <p className="field-error" role="alert">{error}</p>}
        </section>
      )}

      {writing && (
        <div className="story-progress" role="status">
          <p className="story-stage">{job.stage.replace(/;/g, ",")}</p>
          <div className="story-track">
            <span className="story-bar" style={{ transform: `scaleX(${Math.max(0.04, job.progress / 100)})` }} />
          </div>
        </div>
      )}

      {job?.status === "failed" && <p className="field-error" role="alert">{job.error}</p>}

      {hasStory && (
        <article className="chapter">
          <h2 className="chapter-title">{job.title}</h2>
          <p className="chapter-source">
            {job.story_source === "ai" ? "Told by your narrator" : "Told in the document's own words"}
          </p>
          {job.scenes.map((scene, index) => (
            <section key={index} className="scene">
              <h3>{scene.heading}</h3>
              <p>{scene.text}</p>
            </section>
          ))}
          <footer className="chapter-video">
            {videoUrl ? (
              <>
                <video src={videoUrl} controls className="video" />
                <a className="button button-quiet" href={videoUrl} download={`${document.filename.replace(/\.pdf$/i, "")} story.mp4`}>
                  <Download size={18} strokeWidth={1.75} aria-hidden="true" />
                  Download the video
                </a>
              </>
            ) : job.video_status === "rendering" ? (
              <p className="story-note">The narrated video is being made. Read on while it finishes.</p>
            ) : job.video_error ? (
              <p className="story-note">{job.video_error}</p>
            ) : null}
          </footer>
        </article>
      )}
    </div>
  );
}
