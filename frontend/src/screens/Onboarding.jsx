import { useState } from "react";
import { ArrowLeft } from "lucide-react";

import { api } from "../api";
import { Logo } from "../components/Logo";
import UploadBox from "../components/UploadBox";
import { FOCUS, PROFESSIONS, focusPhrase, professionOf } from "../lenses";

function Choice({ label, line, selected, onSelect }) {
  return (
    <button type="button" className={`choice${selected ? " is-selected" : ""}`} aria-pressed={selected} onClick={onSelect}>
      <span className="choice-label">
        <span className={selected ? "hl" : ""}>{label}</span>
      </span>
      <span className="choice-line">{line}</span>
    </button>
  );
}

// Three short steps: who you are, what you need, your first document.
export default function Onboarding({ user, onDone, onSkip }) {
  const [step, setStep] = useState(user.profession ? 2 : 0);
  const [profession, setProfession] = useState(user.profession);
  const [focus, setFocus] = useState(user.focus);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const chosen = professionOf(profession);

  const saveFocus = async (value) => {
    setFocus(value);
    setSaving(true);
    setError("");
    try {
      const saved = await api("/auth/me/profile", { method: "PUT", body: { profession, focus: value } });
      onDone(saved, null, false);
      setStep(2);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="onboarding">
      <header className="onboarding-top">
        <Logo size={30} />
        <button type="button" className="onboarding-skip" onClick={onSkip}>
          Skip for now
        </button>
      </header>

      <section className="onboarding-page" aria-live="polite">
        <p className="onboarding-step folio" aria-label={`Step ${step + 1} of 3`}>{step + 1} of 3</p>

        {step === 0 && (
          <>
            <h1>What brings you to guruCool?</h1>
            <p className="onboarding-lede">This shapes the questions we suggest and how answers and stories are told.</p>
            <div className="choices">
              {PROFESSIONS.map((item) => (
                <Choice
                  key={item.id}
                  label={item.label}
                  line={item.line}
                  selected={profession === item.id}
                  onSelect={() => {
                    setProfession(item.id);
                    setFocus(null);
                    setStep(1);
                  }}
                />
              ))}
            </div>
          </>
        )}

        {step === 1 && chosen && (
          <>
            <button type="button" className="onboarding-back" onClick={() => setStep(0)}>
              <ArrowLeft size={16} strokeWidth={1.75} aria-hidden="true" />
              {chosen.label}
            </button>
            <h1>What will you use it for most?</h1>
            <p className="onboarding-lede">You can change this any time in Settings.</p>
            <div className={`choices${chosen.focuses.length > 2 ? " choices-grid" : ""}`}>
              {chosen.focuses.map((id) => (
                <Choice
                  key={id}
                  label={FOCUS[id].label}
                  line={FOCUS[id].line}
                  selected={focus === id}
                  onSelect={() => !saving && saveFocus(id)}
                />
              ))}
            </div>
            {error && <p className="field-error" role="alert">{error}</p>}
          </>
        )}

        {step === 2 && (
          <>
            <h1>Bring your first document.</h1>
            <p className="onboarding-lede">
              {(() => {
                const phrase = focus ? focusPhrase(focus) : "work";
                return `Any text PDF: ${/^[aeiou]/i.test(phrase) ? "an" : "a"} ${phrase} document, a chapter, a contract, a manual. Or start with our sample to see how it works.`;
              })()}
            </p>
            <UploadBox offerSample onReady={(document) => onDone(null, document, true)} />
          </>
        )}
      </section>
    </main>
  );
}
