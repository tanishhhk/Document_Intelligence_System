import { useState } from "react";

import { api } from "../api";
import { FOCUS, PROFESSIONS, professionOf } from "../lenses";

export default function Settings({ user, onSaved, onSignOut }) {
  const [profession, setProfession] = useState(user.profession || "student");
  const [focus, setFocus] = useState(user.focus || professionOf(user.profession || "student").focuses[0]);
  const [state, setState] = useState("");
  const options = professionOf(profession).focuses;

  const save = async (event) => {
    event.preventDefault();
    setState("saving");
    try {
      onSaved(await api("/auth/me/profile", { method: "PUT", body: { profession, focus } }));
      setState("saved");
    } catch (error) {
      setState(error.message);
    }
  };

  return (
    <div className="settings">
      <h1>Settings</h1>
      <form className="settings-form" onSubmit={save}>
        <div className="field">
          <label htmlFor="profession">I am a</label>
          <select
            id="profession"
            className="input"
            value={profession}
            onChange={(event) => {
              setProfession(event.target.value);
              setFocus(professionOf(event.target.value).focuses[0]);
              setState("");
            }}
          >
            {PROFESSIONS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="focus">Mostly for</label>
          <select
            id="focus"
            className="input"
            value={focus}
            onChange={(event) => {
              setFocus(event.target.value);
              setState("");
            }}
          >
            {options.map((id) => (
              <option key={id} value={id}>
                {FOCUS[id].label}
              </option>
            ))}
          </select>
          <p className="field-hint">{FOCUS[focus].line}</p>
        </div>
        <div className="settings-actions">
          <button type="submit" className="button button-primary" disabled={state === "saving"}>
            Save changes
          </button>
          {state === "saved" && <p className="settings-saved" role="status">Saved.</p>}
          {state && state !== "saving" && state !== "saved" && <p className="field-error" role="alert">{state}</p>}
        </div>
      </form>

      <section className="settings-account">
        <h2>Account</h2>
        <p>Signed in as {user.email}</p>
        <button type="button" className="button button-quiet" onClick={onSignOut}>
          Sign out
        </button>
      </section>
    </div>
  );
}
