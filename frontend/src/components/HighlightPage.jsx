import { useCallback, useEffect, useRef, useState } from "react";

// A page from the sample handbook. Highlighting a sentence shows the question
// it answers, which is how guruCool cites pages.
const SENTENCES = [
  { text: "Full-time employees receive 25 days of annual leave per calendar year, plus public holidays.",
    question: "How many days of holiday do I get?" },
  { text: "Up to 5 days of unused annual leave can be carried over into the next year and must be used before the end of March.",
    question: "Can I keep unused holiday for next year?" },
  { text: "Employees receive 10 days of paid sick leave per year.",
    question: "How much paid sick leave is there?" },
  { text: "Employees may work remotely for up to 2 days per week after completing their probation period of 6 months.",
    question: "When can I start working from home?" },
  { text: "New remote workers receive a one-time home office allowance of 300 euros.",
    question: "Is there money for a home office?" },
];

const WORDS = SENTENCES.flatMap((sentence, s) => sentence.text.split(" ").map((word) => ({ word, s })));
const START = SENTENCES.map((_, s) => WORDS.findIndex((w) => w.s === s));

function sentencesIn(from, to) {
  const [a, b] = from <= to ? [from, to] : [to, from];
  const touched = new Set();
  for (let i = a; i <= b; i += 1) touched.add(WORDS[i].s);
  // A sentence counts once at least two of its words, or all of a short drag, are covered.
  return [...touched].filter((s) => {
    const words = WORDS.map((w, i) => [w, i]).filter(([w]) => w.s === s).map(([, i]) => i);
    const covered = words.filter((i) => i >= a && i <= b).length;
    return covered >= Math.min(2, words.length) || b - a < 2;
  });
}

export default function HighlightPage() {
  const [marked, setMarked] = useState(() => new Set([0]));
  const [latest, setLatest] = useState(0);
  const [drag, setDrag] = useState(null);
  const pageRef = useRef(null);

  const finish = useCallback((from, to) => {
    const found = sentencesIn(from, to);
    if (!found.length) return;
    setMarked((previous) => {
      const next = new Set(previous);
      const allMarked = found.every((s) => next.has(s));
      found.forEach((s) => (allMarked && found.length === 1 ? next.delete(s) : next.add(s)));
      return next;
    });
    setLatest(found[found.length - 1]);
  }, []);

  const wordAt = (x, y) => {
    const element = document.elementFromPoint(x, y)?.closest?.("[data-w]");
    return element && pageRef.current?.contains(element) ? Number(element.dataset.w) : null;
  };

  // The drag lives in a ref, so its end is handled exactly once; state only draws it.
  const dragRef = useRef(null);
  const dragging = drag !== null;

  const startDrag = (index) => {
    dragRef.current = { from: index, to: index };
    setDrag(dragRef.current);
  };

  useEffect(() => {
    if (!dragging) return undefined;
    const move = (event) => {
      const index = wordAt(event.clientX, event.clientY);
      if (index === null || !dragRef.current) return;
      dragRef.current = { ...dragRef.current, to: index };
      setDrag(dragRef.current);
    };
    const up = (event) => {
      const current = dragRef.current;
      const index = wordAt(event.clientX, event.clientY);
      dragRef.current = null;
      setDrag(null);
      if (current) finish(current.from, index ?? current.to);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [dragging, finish]);

  const live = drag ? [Math.min(drag.from, drag.to), Math.max(drag.from, drag.to)] : null;
  const everything = marked.size === SENTENCES.length;

  return (
    <figure className="hp" aria-label="Try it: highlight a sentence on this sample page">
      <div className="hp-sheet" ref={pageRef}>
        <header className="hp-head">
          <span>Northwind Traders Employee Handbook</span>
          <span className="folio">2</span>
        </header>
        <h2 className="hp-title">Section 2. Leave</h2>
        <p
          className="hp-text"
          onPointerDown={(event) => {
            const index = wordAt(event.clientX, event.clientY);
            if (index === null) return;
            event.preventDefault();
            startDrag(index);
          }}
        >
          {SENTENCES.map((sentence, s) => (
            <span
              key={s}
              className={`hp-sentence${marked.has(s) ? " hl" : ""}${s === 0 && marked.has(0) && latest === 0 ? " hl-draw" : ""}`}
              role="button"
              tabIndex={0}
              aria-pressed={marked.has(s)}
              aria-label={`Highlight: ${sentence.text}`}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  finish(START[s], START[s] + 2);
                }
              }}
            >
              {sentence.text.split(" ").map((word, w) => {
                const index = START[s] + w;
                const inLive = live && index >= live[0] && index <= live[1];
                return (
                  <span key={w} data-w={index} className={inLive ? "hp-live" : undefined}>
                    {word}{" "}
                  </span>
                );
              })}
            </span>
          ))}
        </p>
      </div>

      <figcaption className="hp-margin" aria-live="polite">
        {everything ? (
          <p className="hp-note">
            Highlighting the whole page is a classic. guruCool remembers the important bits so you
            do not have to.
          </p>
        ) : marked.has(latest) ? (
          <p className="hp-note" key={latest}>
            <span className="hp-q">{SENTENCES[latest].question}</span>
            <span className="hp-cite">
              Answered on <span className="folio">p. 2</span>
            </span>
          </p>
        ) : null}
        <p className="hp-try">
          <strong>Try it.</strong> Drag across another sentence, or tab to one and press Enter.
        </p>
      </figcaption>
    </figure>
  );
}
