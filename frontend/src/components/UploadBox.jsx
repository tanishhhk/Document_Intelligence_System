import { useRef, useState } from "react";
import { FileText, Upload } from "lucide-react";

import { uploadPdf, waitForDocument } from "../api";

const MAX_BYTES = 10 * 1024 * 1024;

async function sampleFile() {
  const response = await fetch(`${import.meta.env.BASE_URL}sample-handbook.pdf`);
  return new File([await response.blob()], "Northwind employee handbook.pdf", { type: "application/pdf" });
}

// Pick or drop a PDF, upload it, and wait until it has been read.
export default function UploadBox({ onReady, offerSample = false, compact = false }) {
  const input = useRef(null);
  const [state, setState] = useState({ phase: "idle" });
  const [over, setOver] = useState(false);
  const busy = state.phase === "uploading" || state.phase === "reading";

  const send = async (file) => {
    if (!file || busy) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setState({ phase: "error", message: "That is not a PDF. Choose a .pdf file." });
      return;
    }
    if (file.size > MAX_BYTES) {
      setState({ phase: "error", message: "That PDF is over 10 MB. Try a smaller file or split it." });
      return;
    }
    try {
      setState({ phase: "uploading", name: file.name });
      const created = await uploadPdf(file);
      setState({ phase: "reading", name: file.name });
      const document = await waitForDocument(created.id);
      if (document.status === "failed") {
        setState({ phase: "error", message: document.error_message || "This PDF could not be read." });
        return;
      }
      setState({ phase: "idle" });
      onReady(document);
    } catch (error) {
      setState({ phase: "error", message: error.message });
    }
  };

  return (
    <div className={`upload${compact ? " upload-compact" : ""}`}>
      <div
        className={`upload-drop${over ? " is-over" : ""}${busy ? " is-busy" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          send(event.dataTransfer.files[0]);
        }}
      >
        {busy ? (
          <div className="upload-status" role="status">
            <span className="spinner" aria-hidden="true" />
            <span>
              <strong>{state.name}</strong>
              <br />
              {state.phase === "uploading" ? "Uploading" : "Reading every page. Usually under a minute."}
            </span>
          </div>
        ) : (
          <>
            <Upload size={compact ? 20 : 28} strokeWidth={1.6} aria-hidden="true" />
            <p className="upload-line">
              Drop a PDF here, or{" "}
              <button type="button" className="upload-pick" onClick={() => input.current?.click()}>
                choose a file
              </button>
            </p>
            <p className="upload-limits">Up to 10 MB and 100 pages. Text PDFs only; scans have no text to read.</p>
          </>
        )}
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          className="visually-hidden"
          tabIndex={-1}
          onChange={(event) => {
            send(event.target.files[0]);
            event.target.value = "";
          }}
        />
      </div>

      {offerSample && !busy && (
        <button type="button" className="button button-quiet upload-sample" onClick={async () => send(await sampleFile())}>
          <FileText size={18} strokeWidth={1.75} aria-hidden="true" />
          Try the sample handbook instead
        </button>
      )}

      {state.phase === "error" && (
        <p className="field-error" role="alert">
          {state.message}
        </p>
      )}
    </div>
  );
}
