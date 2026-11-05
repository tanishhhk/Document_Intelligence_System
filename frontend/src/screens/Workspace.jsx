import { useCallback, useEffect, useState } from "react";
import { BookOpen, Library as LibraryIcon, MessageSquareText, Settings as SettingsIcon } from "lucide-react";

import { api } from "../api";
import { Logo } from "../components/Logo";
import UploadBox from "../components/UploadBox";
import { focusPhrase } from "../lenses";
import AskPanel from "./AskPanel";
import Library from "./Library";
import Settings from "./Settings";
import StoryPanel from "./StoryPanel";

function UsageLine({ usage }) {
  if (!usage) return null;
  const left = (kind) => Math.max(0, usage.limits[kind] - usage.used[kind]);
  return (
    <p className="usage" title="Daily limits reset at midnight UTC">
      <span>{left("question")} questions</span>
      <span>{left("story")} stories</span>
      <span>{left("upload")} uploads left today</span>
    </p>
  );
}

export default function Workspace({ user, initialDocument, onUser, onSignOut }) {
  const [document, setDocument] = useState(initialDocument);
  const [view, setView] = useState(initialDocument ? "ask" : "library");
  const [usage, setUsage] = useState(null);

  const refreshUsage = useCallback(() => {
    api("/auth/me/usage").then(setUsage).catch(() => {});
  }, []);
  useEffect(() => {
    refreshUsage();
  }, [refreshUsage]);

  // Open the most recent ready document when none was passed in.
  useEffect(() => {
    if (document) return;
    api("/documents?limit=1&sort=newest&status=completed")
      .then((page) => {
        if (page.items[0]) {
          setDocument(page.items[0]);
          setView("ask");
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const open = (next) => {
    setDocument(next);
    setView("ask");
  };

  const tabs = [
    ["ask", "Ask", MessageSquareText],
    ["story", "Story", BookOpen],
  ];

  return (
    <div className="workspace">
      <header className="topbar">
        <Logo size={28} className="topbar-logo" />
        <nav className="topbar-nav" aria-label="Main">
          <button type="button" className={view === "library" ? "is-current" : ""} onClick={() => setView("library")}>
            <LibraryIcon size={18} strokeWidth={1.75} aria-hidden="true" />
            <span>Library</span>
          </button>
          <button type="button" className={view === "settings" ? "is-current" : ""} onClick={() => setView("settings")}>
            <SettingsIcon size={18} strokeWidth={1.75} aria-hidden="true" />
            <span>Settings</span>
          </button>
        </nav>
        <UsageLine usage={usage} />
      </header>

      <main className="desk">
        {view === "library" && (
          <Library
            current={document}
            usage={usage}
            onUsed={refreshUsage}
            onOpen={open}
            onDeletedCurrent={() => setDocument(null)}
          />
        )}

        {view === "settings" && <Settings user={user} onSaved={onUser} onSignOut={onSignOut} />}

        {(view === "ask" || view === "story") &&
          (document ? (
            <div className="page">
              <header className="page-head">
                <div>
                  <h1 className="page-title">{document.filename.replace(/\.pdf$/i, "")}</h1>
                  <p className="page-meta">
                    <span>{document.page_count} pages</span>
                    {user.focus && <span>Read for {focusPhrase(user.focus)}</span>}
                  </p>
                </div>
                <div className="tabs" role="tablist" aria-label="What to do with this document">
                  {tabs.map((tab) => {
                    const [id, label, TabIcon] = tab;
                    return (
                      <button key={id} type="button" role="tab" aria-selected={view === id} className={view === id ? "is-active" : ""} onClick={() => setView(id)}>
                        <TabIcon size={18} strokeWidth={1.75} aria-hidden="true" />
                        {label}
                      </button>
                    );
                  })}
                </div>
              </header>
              {view === "ask" ? (
                <AskPanel document={document} focus={user.focus} onUsed={refreshUsage} />
              ) : (
                <StoryPanel document={document} focus={user.focus} onUsed={refreshUsage} />
              )}
            </div>
          ) : (
            <div className="page page-empty">
              <h1>Bring a document to start.</h1>
              <UploadBox offerSample onReady={(next) => { refreshUsage(); open(next); }} />
            </div>
          ))}
      </main>
    </div>
  );
}
