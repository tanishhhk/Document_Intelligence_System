import { useCallback, useEffect, useState } from "react";

import { api, session, waitForServer } from "./api";
import { Mark } from "./components/Logo";
import Onboarding from "./screens/Onboarding";
import SignIn from "./screens/SignIn";
import Workspace from "./screens/Workspace";

const SKIPPED = "gurucool_onboarding_skipped";

function Waiting({ waking }) {
  return (
    <main className="boot" role="status">
      <Mark size={48} className="boot-mark" />
      <p>{waking ? "Waking the server. On the free plan this takes about a minute after a quiet spell." : "Loading"}</p>
    </main>
  );
}

export default function App() {
  const [stage, setStage] = useState("boot");
  const [waking, setWaking] = useState(false);
  const [user, setUser] = useState(null);
  const [firstDocument, setFirstDocument] = useState(null);

  const enter = useCallback(async () => {
    try {
      const me = await api("/auth/me");
      setUser(me);
      setStage(me.focus || localStorage.getItem(`${SKIPPED}:${me.id}`) ? "workspace" : "onboarding");
    } catch {
      session.clear();
      setStage("signin");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    waitForServer(() => setWaking(true), controller.signal).then((up) => {
      if (controller.signal.aborted) return;
      if (!up) setStage("down");
      else if (session.token) enter();
      else setStage("signin");
    });
    return () => controller.abort();
  }, [enter]);

  useEffect(() => {
    const signedOut = () => {
      setUser(null);
      setStage("signin");
    };
    window.addEventListener("gurucool:signed-out", signedOut);
    return () => window.removeEventListener("gurucool:signed-out", signedOut);
  }, []);

  const signOut = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    session.clear();
    setUser(null);
    setFirstDocument(null);
    setStage("signin");
  };

  if (stage === "boot") return <Waiting waking={waking} />;
  if (stage === "down") {
    return (
      <main className="boot" role="alert">
        <Mark size={48} />
        <p>The server is not responding. Try again in a few minutes.</p>
        <button type="button" className="button button-primary" onClick={() => window.location.reload()}>
          Try again
        </button>
      </main>
    );
  }
  if (stage === "signin") return <SignIn onSignedIn={enter} />;
  if (stage === "onboarding") {
    return (
      <Onboarding
        user={user}
        onSkip={() => {
          localStorage.setItem(`${SKIPPED}:${user.id}`, "1");
          setStage("workspace");
        }}
        onDone={(saved, document, finished) => {
          if (saved) setUser(saved);
          if (document) setFirstDocument(document);
          if (finished) setStage("workspace");
        }}
      />
    );
  }
  return <Workspace user={user} initialDocument={firstDocument} onUser={setUser} onSignOut={signOut} />;
}
