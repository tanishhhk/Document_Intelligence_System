import { useEffect, useState, useSyncExternalStore } from "react";
import { AlertCircle, Check, Eye, EyeOff } from "lucide-react";

import { api, session } from "../api";
import Guru from "../components/Guru";
import { Logo } from "../components/Logo";

const MIN_PASSWORD = 12;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// True on the stacked phone layout, where the guru is framed close.
const narrow = window.matchMedia("(max-width: 820px)");
const useNarrow = () =>
  useSyncExternalStore(
    (notify) => {
      narrow.addEventListener("change", notify);
      return () => narrow.removeEventListener("change", notify);
    },
    () => narrow.matches,
  );

// What the guru says. Decorative: every fact here is also in the form's own text.
function line({ creating, focus, email, password, show, busy, troubled, failure }) {
  if (busy) return creating ? "Writing your name in my book." : "Opening your library.";
  if (failure) return "Hmm. That did not open the door. Try again?";
  if (troubled) return "Hmm. Read the note under the field and try again.";
  if (focus === "password") {
    if (show) return "Fine. One small peek.";
    if (!creating) return "I am not looking. Promise.";
    const left = MIN_PASSWORD - password.length;
    if (left === 1) return "One more character to fill my halo.";
    return left > 0 ? `${left} more characters to fill my halo.` : "Halo full. A strong secret.";
  }
  if (focus === "email") {
    if (!email) return "Your email, please. I never forget one.";
    if (/\.(edu|ac\.[a-z]+)$/i.test(email.trim())) return "A student, I sense. Exams soon?";
    return "Go on. I am listening.";
  }
  return creating
    ? "A new seeker. Bring me any PDF and I will answer from its pages."
    : "Welcome back, seeker. Your library missed you.";
}

// Types the guru's line out a few letters at a time. Keyed by the text, so
// each new line starts from its first letter.
function Speech({ text }) {
  const [count, setCount] = useState(() => (reduceMotion() ? text.length : 0));
  useEffect(() => {
    if (count >= text.length) return undefined;
    const timer = setTimeout(() => setCount((value) => value + 2), 18);
    return () => clearTimeout(timer);
  }, [count, text.length]);
  return (
    <p className="gc-speech" aria-hidden="true">
      {text.slice(0, count)}
      <span className="gc-speech-rest">{text.slice(count)}</span>
    </p>
  );
}

export default function SignIn({ onSignedIn }) {
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [focus, setFocus] = useState(null);
  const [errors, setErrors] = useState({});
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const close = useNarrow();
  const creating = mode === "create";
  const troubled = Boolean(failure || errors.email || errors.password);

  const validate = () => {
    const next = {};
    if (!EMAIL.test(email.trim())) next.email = "Enter an email address like name@example.com";
    if (!password) next.password = "Enter your password";
    else if (creating && password.length < MIN_PASSWORD) next.password = `Use at least ${MIN_PASSWORD} characters`;
    else if (new TextEncoder().encode(password).length > 72)
      next.password = "That password is too long. Try a shorter sentence.";
    setErrors(next);
    return !Object.keys(next).length;
  };

  const submit = async (event) => {
    event.preventDefault();
    if (busy || !validate()) return;
    setBusy(true);
    setFailure("");
    const credentials = { email: email.trim(), password };
    try {
      if (creating) await api("/auth/register", { method: "POST", body: credentials });
      const { access_token: token } = await api("/auth/login", { method: "POST", body: credentials });
      session.save(token);
      onSignedIn();
    } catch (error) {
      setFailure(error.message);
      setBusy(false);
    }
  };

  const switchTo = (next) => {
    setMode(next);
    setErrors({});
    setFailure("");
  };

  const edit = (setter, field) => (event) => {
    setter(event.target.value);
    if (errors[field] || failure) {
      setErrors((current) => ({ ...current, [field]: undefined }));
      setFailure("");
    }
  };

  let mood = "watch";
  if (busy) mood = "bliss";
  else if (troubled) mood = "oops";
  else if (focus === "password") mood = show ? "peek" : "shy";

  // While the email is typed, his eyes follow the text along the field.
  const look = focus === "email" ? { x: 0.35 + Math.min(1, email.length / 28) * 0.65, y: 0.45 } : null;
  const speech = line({ creating, focus, email, password, show, busy, troubled, failure });
  const lit = creating ? Math.min(4, Math.floor(password.length / (MIN_PASSWORD / 4))) : 4;
  const passwordNote = errors.password
    ? null
    : creating
      ? password.length >= MIN_PASSWORD
        ? "Long enough."
        : `At least ${MIN_PASSWORD} characters. A short sentence works well.`
      : null;

  return (
    <main className="gc-signin">
      <section className="gc-stage">
        <Speech key={speech} text={speech} />
        <Guru mood={mood} look={look} lit={lit} close={close} />
      </section>

      <section className="gc-panel">
        <Logo size={30} className="gc-logo" />
        <div className="gc-panel-inner">
          <h1 className="gc-title">{creating ? "Create your account" : "Welcome back"}</h1>
          <p className="gc-lede">Ask any PDF a question and see the page each answer comes from.</p>

          <div className="gc-switch" role="group" aria-label="Account">
            {[
              ["signin", "Sign in"],
              ["create", "Create account"],
            ].map(([id, label]) => (
              <button key={id} type="button" aria-pressed={mode === id} onClick={() => switchTo(id)}>
                {label}
              </button>
            ))}
          </div>

          <form className="gc-form" onSubmit={submit} noValidate>
            <div className="gc-field">
              <label htmlFor="email">Email</label>
              <div className="gc-input-wrap">
                <input
                  id="email"
                  className="gc-input"
                  type="email"
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck="false"
                  value={email}
                  onChange={edit(setEmail, "email")}
                  onFocus={() => setFocus("email")}
                  onBlur={() => setFocus(null)}
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? "email-error" : undefined}
                />
                {/* The guru's seal: the address looks right. */}
                <span className={`gc-seal${EMAIL.test(email.trim()) ? " is-on" : ""}`} aria-hidden="true">
                  <Check size={16} strokeWidth={3} />
                </span>
              </div>
              {errors.email && (
                <p className="gc-error" id="email-error">
                  <AlertCircle size={16} strokeWidth={2} aria-hidden="true" />
                  {errors.email}
                </p>
              )}
            </div>

            <div className="gc-field">
              <label htmlFor="password">Password</label>
              <div className="gc-input-wrap">
                <input
                  id="password"
                  className="gc-input"
                  type={show ? "text" : "password"}
                  autoComplete={creating ? "new-password" : "current-password"}
                  value={password}
                  onChange={edit(setPassword, "password")}
                  onFocus={() => setFocus("password")}
                  onBlur={() => setFocus(null)}
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby="password-note"
                />
                {creating && (
                  // Prayer beads that fill with the halo, one per three characters.
                  <span className="gc-beads" aria-hidden="true">
                    {[0, 1, 2, 3].map((bead) => (
                      <span key={bead} className={bead < lit ? "is-lit" : ""} />
                    ))}
                  </span>
                )}
                <button
                  type="button"
                  className="gc-reveal"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => setShow((value) => !value)}
                  aria-label={show ? "Hide password" : "Show password"}
                  aria-pressed={show}
                >
                  {show ? <EyeOff size={20} strokeWidth={2} /> : <Eye size={20} strokeWidth={2} />}
                </button>
              </div>
              <p id="password-note" className={errors.password ? "gc-error" : "gc-note"}>
                {errors.password && <AlertCircle size={16} strokeWidth={2} aria-hidden="true" />}
                {errors.password || passwordNote}
              </p>
            </div>

            <button type="submit" className="gc-submit" disabled={busy}>
              {busy && <span className="spinner" aria-hidden="true" />}
              {busy ? (creating ? "Creating your account" : "Signing in") : creating ? "Create account" : "Sign in"}
            </button>

            {failure && (
              <p className="gc-error gc-failure" role="alert">
                <AlertCircle size={16} strokeWidth={2} aria-hidden="true" />
                {failure}
              </p>
            )}
          </form>
        </div>
      </section>
    </main>
  );
}
