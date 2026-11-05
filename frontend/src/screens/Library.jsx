import { useCallback, useEffect, useState } from "react";
import { Search, Trash2 } from "lucide-react";

import { api } from "../api";
import UploadBox from "../components/UploadBox";

const STATUS = { queued: "Waiting to be read", processing: "Reading", failed: "Could not be read" };

function Row({ document, current, onOpen, onDeleted }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const ready = document.status === "completed";

  const remove = async () => {
    setBusy(true);
    try {
      await api(`/documents/${document.id}`, { method: "DELETE" });
      onDeleted(document.id);
    } catch {
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <li className={`library-row${current ? " is-current" : ""}`}>
      <button type="button" className="library-open" disabled={!ready} onClick={() => onOpen(document)}>
        <span className="library-name">{document.filename}</span>
        <span className="library-meta">
          <span>{ready ? `${document.page_count} ${document.page_count === 1 ? "page" : "pages"}` : STATUS[document.status]}</span>
          <span>{new Date(document.upload_date + "Z").toLocaleDateString(undefined, { day: "numeric", month: "short" })}</span>
        </span>
      </button>
      <div className="library-delete">
        {confirming ? (
          <>
            <button type="button" className="button button-danger" onClick={remove} disabled={busy}>
              Delete for good
            </button>
            <button type="button" className="button button-quiet" onClick={() => setConfirming(false)}>
              Keep
            </button>
          </>
        ) : (
          <button type="button" className="icon-button" aria-label={`Delete ${document.filename}`} onClick={() => setConfirming(true)}>
            <Trash2 size={18} strokeWidth={1.75} aria-hidden="true" />
          </button>
        )}
      </div>
    </li>
  );
}

export default function Library({ current, onOpen, onDeletedCurrent, usage, onUsed }) {
  const [items, setItems] = useState(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "50", sort: "newest" });
      if (query.trim()) params.set("q", query.trim());
      const page = await api(`/documents?${params}`);
      setItems(page.items);
      setError("");
    } catch (failure) {
      setError(failure.message);
    }
  }, [query]);

  useEffect(() => {
    const timer = setTimeout(load, 200);
    return () => clearTimeout(timer);
  }, [load]);

  const full = usage && usage.documents >= usage.max_documents;

  return (
    <div className="library">
      <header className="library-head">
        <h1>Your documents</h1>
        {usage && (
          <p className="library-count">
            {usage.documents} of {usage.max_documents} kept
          </p>
        )}
      </header>

      {full ? (
        <p className="notice">Your library is full. Delete a document to upload another.</p>
      ) : (
        <UploadBox
          compact
          onReady={(document) => {
            onUsed();
            onOpen(document);
          }}
        />
      )}

      <label className="library-search">
        <Search size={18} strokeWidth={1.75} aria-hidden="true" />
        <span className="visually-hidden">Search your documents</span>
        <input className="input" placeholder="Search by name" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>

      {error && <p className="field-error" role="alert">{error}</p>}
      {items && items.length === 0 && (
        <p className="library-empty">{query ? "No document has that in its name." : "Nothing here yet. Upload a PDF above."}</p>
      )}
      {items && items.length > 0 && (
        <ul className="library-list">
          {items.map((document) => (
            <Row
              key={document.id}
              document={document}
              current={document.id === current?.id}
              onOpen={onOpen}
              onDeleted={(id) => {
                setItems((previous) => previous.filter((item) => item.id !== id));
                onUsed();
                if (id === current?.id) onDeletedCurrent();
              }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
