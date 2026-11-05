import { useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";

import { api } from "../api";
import { DEFAULT_QUESTIONS, FOCUS } from "../lenses";

function pagesOf(source) {
  if (!source.page_start) return "";
  return source.page_start === source.page_end ? `p. ${source.page_start}` : `pp. ${source.page_start} to ${source.page_end}`;
}

// Inline text: **bold** and [S1] markers, which become the page they point to.
function inline(text, pages, key) {
  return text.split(/(\*\*[^*]+\*\*|\[S\d+\])/g).map((part, index) => {
    const cite = part.match(/^\[(S\d+)\]$/);
    if (cite) return pages[cite[1]] ? <sup key={`${key}-${index}`} className="folio cite">{pages[cite[1]]}</sup> : " ";
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={`${key}-${index}`}>{part.slice(2, -2)}</strong>;
    return part.replace(/(^|\s)[*_]+|[*_]+(\s|$)/g, "$1$2");
  });
}

// Models answer in light markdown: paragraphs, bold and lists.
function AnswerText({ text, sources }) {
  const pages = Object.fromEntries(sources.map((source) => [source.source_id, pagesOf(source)]));
  const blocks = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim().replace(/^#+\s*/, "");
    const item = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (!line) blocks.push(null);
    else if (item) {
      const last = blocks[blocks.length - 1];
      if (Array.isArray(last)) last.push(item[1]);
      else blocks.push([item[1]]);
    } else blocks.push(line);
  }
  return (
    <div className="answer-text">
      {blocks.filter(Boolean).map((block, index) =>
        Array.isArray(block) ? (
          <ul key={index}>
            {block.map((entry, i) => <li key={i}>{inline(entry, pages, `${index}-${i}`)}</li>)}
          </ul>
        ) : (
          <p key={index}>{inline(block, pages, index)}</p>
        ),
      )}
    </div>
  );
}

const WORD = /[a-z0-9]{4,}/g;
const HEADING = /^(section|chapter|part|article|clause)\s+[\d.]+\.?$/i;

// Highlight the sentence of a passage that best matches the answer (or, for the
// no-AI fallback, the question). Headings and fragments are never highlighted.
function Excerpt({ source, against }) {
  const cut = source.preview.length >= 360;
  let text = source.preview.trim();
  if (cut) {
    text = text.slice(0, text.lastIndexOf(" ")).trimEnd();
    if (!/[.!?]$/.test(text)) text += "…"; // No ellipsis after a full stop.
  }
  // Lines are split too, so a heading line never joins the sentence under it.
  const sentences = text.split(/(?<=[.!?])\s+|\s*\n+\s*/).filter(Boolean);
  // Compare word stems (first five letters), so "expense" matches "expenses".
  const stems = (value) => (value.toLowerCase().match(WORD) || []).map((word) => word.slice(0, 5));
  const wanted = new Set(stems(against));
  const scores = sentences.map((sentence) =>
    sentence.split(/\s+/).length < 5 || HEADING.test(sentence.trim())
      ? 0
      : stems(sentence).filter((stem) => wanted.has(stem)).length,
  );
  const top = Math.max(...scores);
  const best = top > 0 ? scores.indexOf(top) : -1;
  return (
    <blockquote className="excerpt">
      <span className="excerpt-page folio">{pagesOf(source)}</span>
      <p>
        {sentences.map((sentence, index) => (
          <span key={index}>
            {index === best ? <span className="hl">{sentence}</span> : sentence}{" "}
          </span>
        ))}
      </p>
    </blockquote>
  );
}

function Answer({ reply, question }) {
  const extractive = reply.answer_status === "extractive";
  const shown = extractive ? reply.sources : reply.sources.filter((source) => source.cited);
  const text = extractive
    ? "No AI answer is available right now, so here are the passages that match your question best."
    : reply.answer;
  return (
    <article className="answer">
      <AnswerText text={text} sources={reply.sources} />
      {shown.length > 0 && (
        <div className="excerpts">
          {shown.map((source) => (
            <Excerpt key={source.source_id} source={source} against={extractive ? question : reply.answer} />
          ))}
        </div>
      )}
    </article>
  );
}

export default function AskPanel({ document, focus, onUsed }) {
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const end = useRef(null);
  const suggestions = focus ? FOCUS[focus].questions : DEFAULT_QUESTIONS;

  useEffect(() => {
    setTurns([]);
  }, [document.id]);
  // scrollIntoView returns a promise in newer browsers; an effect must not return it.
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, asking]);

  const ask = async (text) => {
    const asked = text.trim();
    if (!asked || asking) return;
    setQuestion("");
    setAsking(true);
    setTurns((previous) => [...previous, { question: asked }]);
    try {
      const reply = await api("/chat/ask", { method: "POST", body: { question: asked, document_id: document.id } });
      setTurns((previous) => previous.map((turn, index) => (index === previous.length - 1 ? { ...turn, reply } : turn)));
    } catch (error) {
      setTurns((previous) =>
        previous.map((turn, index) => (index === previous.length - 1 ? { ...turn, error: error.message } : turn)),
      );
    } finally {
      setAsking(false);
      onUsed();
    }
  };

  return (
    <div className="ask">
      {turns.length === 0 ? (
        <div className="ask-empty">
          <h2>Ask anything about this document.</h2>
          <p>Answers come only from its pages, and show you where.</p>
          <ul className="suggestions">
            {suggestions.map((suggestion) => (
              <li key={suggestion}>
                <button type="button" onClick={() => ask(suggestion)}>
                  {suggestion}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <ol className="turns">
          {turns.map((turn, index) => (
            <li key={index} className="turn">
              <p className="turn-question">{turn.question}</p>
              {turn.reply && <Answer reply={turn.reply} question={turn.question} />}
              {turn.error && <p className="field-error" role="alert">{turn.error}</p>}
              {!turn.reply && !turn.error && (
                <p className="turn-wait" role="status">
                  <span className="spinner" aria-hidden="true" /> Reading the pages
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
      <div ref={end} />

      <form
        className="ask-bar"
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
      >
        <label htmlFor="question" className="visually-hidden">
          Your question
        </label>
        <input
          id="question"
          className="input"
          placeholder="Ask about this document"
          maxLength={1000}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={asking}
        />
        <button type="submit" className="button button-primary ask-send" disabled={asking || !question.trim()} aria-label="Ask">
          <ArrowUp size={20} strokeWidth={2} aria-hidden="true" />
        </button>
      </form>
    </div>
  );
}
