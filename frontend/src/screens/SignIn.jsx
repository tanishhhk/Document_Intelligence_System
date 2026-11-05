import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { api, session } from "../api";
import HighlightPage from "../components/HighlightPage";
import { Logo } from "../components/Logo";

const MIN_PASSWORD = 12;

export default function SignIn({ onSignedIn }) {
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState({});
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const creating = mode === "create";
  const filled = Math.min(1, password.length / MIN_PASSWORD);

  const validate = () => {
    const next = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) next.email = "Enter an email address like name@example.com";
    if (!password) next.password = "Enter your password";
    else if (creating && password.length < MIN_PASSWORD) next.password = `Use at least ${MIN_PASSWORD} characters`;
    else if (new TextEncoder().encode(password).length > 72) next.password = "That is too long; use at most 72 bytes";
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
    } finally {
      setBusy(false);
    }
  };

  const switchTo = (next) => {
    setMode(next);
    setErrors({});
    setFailure("");
  };

  return (
    <main className="signin">
      <section className="signin-desk" aria-label="What guruCool does">
        <HighlightPage />
      </section>

      <section className="signin-panel">
        <Logo size={34} className="signin-logo" />
        <h1 className="signin-title">Every answer comes with its page.</h1>
        <p className="signin-lede">
          Upload a PDF and ask anything. guruCool answers only from your document and shows the
          exact passage, highlighted. It can also tell the whole thing as a short narrated story.
        </p>

        <div className="signin-switch" role="tablist" aria-label="Account">
          {[
            ["signin", "Sign in"],
            ["create", "Create account"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={mode === id}
              className={mode === id ? "is-active" : ""}
              onClick={() => switchTo(id)}
            >
              {label}
            </button>
          ))}
        </div>

        <form className="signin-form" onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck="false"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? "email-error" : undefined}
            />
            {errors.email && <p className="field-error" id="email-error">{errors.email}</p>}
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="input-with-action">
              <input
                id="password"
                className="input"
                type={show ? "text" : "password"}
                autoComplete={creating ? "new-password" : "current-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(errors.password)}
                aria-describedby="password-help"
              />
              <button
                type="button"
                className="input-action"
                onClick={() => setShow((value) => !value)}
                aria-label={show ? "Hide password" : "Show password"}
                aria-pressed={show}
              >
                {show ? <EyeOff size={18} strokeWidth={1.75} /> : <Eye size={18} strokeWidth={1.75} />}
              </button>
            </div>
            {creating && (
              <div className="pw-meter" aria-hidden="true">
                <span className="pw-stroke" style={{ transform: `scaleX(${filled})` }} />
              </div>
            )}
            <p id="password-help" className={errors.password ? "field-error" : "field-hint"}>
              {errors.password ||
                (creating
                  ? filled < 1
                    ? `At least ${MIN_PASSWORD} characters. A short sentence works well.`
                    : "Long enough. Nicely highlighted."
                  : " ")}
            </p>
          </div>

          <button type="submit" className="button button-primary signin-submit" disabled={busy}>
            {busy && <span className="spinner" aria-hidden="true" />}
            {busy ? (creating ? "Creating your account" : "Signing in") : creating ? "Create account" : "Sign in"}
          </button>

          {failure && (
            <p className="signin-failure" role="alert">
              {failure}
            </p>
          )}
        </form>
      </section>
    </main>
  );
}
