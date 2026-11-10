import { useState } from "react";
import type { FormEvent } from "react";

type User = {
  id: string;
  email: string;
  full_name: string;
  role: string;
};

type CareerPreference = {
  id: string;
  track: string;
  target_titles: string[];
  enabled: boolean;
  locations: string[];
  remote_preferred: boolean;
};

type CVVersion = {
  id: string;
  version: number;
  original_filename: string;
  media_type: string;
  sha256: string;
  uploaded_at: string;
  extracted_sections: Record<string, string[]>;
  review_flags: string[];
};

type MasterCV = {
  slot: number;
  created_at: string;
  updated_at: string;
  versions: CVVersion[];
};

type ProfileEntry = {
  text: string;
  source_version_ids: string[];
  source_slots: number[];
  verified: boolean;
};

type ProfessionalProfile = {
  candidate_data: Record<string, ProfileEntry[]>;
  review_flags: string[];
  updated_at: string;
};

const trackNames: Record<string, string> = {
  software_engineering: "Software Engineering",
  cybersecurity: "Cybersecurity",
  electrical_engineering: "Electrical & Engineering"
};

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState("");
  const [preferences, setPreferences] = useState<CareerPreference[]>([]);
  const [masterCVs, setMasterCVs] = useState<MasterCV[]>([]);
  const [profile, setProfile] = useState<ProfessionalProfile | null>(null);
  const [uploadingSlot, setUploadingSlot] = useState<number | null>(null);
  const [cvError, setCvError] = useState("");
  const [cvNotice, setCvNotice] = useState("");
  const [mode, setMode] = useState<"login" | "register">("register");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    const payload: Record<string, string> = {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? "")
    };
    if (mode === "register") {
      payload.full_name = String(form.get("full_name") ?? "");
    }

    try {
      if (mode === "register") {
        const response = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error(await responseMessage(response));
      }

      const loginResponse = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: payload.email, password: payload.password })
      });
      if (!loginResponse.ok) throw new Error(await responseMessage(loginResponse));
      const loginData = (await loginResponse.json()) as { access_token: string };
      setAccessToken(loginData.access_token);

      const [userResponse, preferenceResponse] = await Promise.all([
        fetch("/api/auth/me", {
          headers: { Authorization: `Bearer ${loginData.access_token}` }
        }),
        fetch("/api/auth/preferences", {
          headers: { Authorization: `Bearer ${loginData.access_token}` }
        })
      ]);
      if (!userResponse.ok || !preferenceResponse.ok) {
        throw new Error("Could not load your account workspace.");
      }
      setUser((await userResponse.json()) as User);
      setPreferences((await preferenceResponse.json()) as CareerPreference[]);
      await refreshCVData(loginData.access_token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    setAccessToken("");
    setUser(null);
    setPreferences([]);
    setMasterCVs([]);
    setProfile(null);
  }

  async function refreshCVData(token: string) {
    const headers = { Authorization: `Bearer ${token}` };
    const [cvResponse, profileResponse] = await Promise.all([
      fetch("/api/profile/cvs", { headers }),
      fetch("/api/profile", { headers })
    ]);
    if (!cvResponse.ok) throw new Error(await responseMessage(cvResponse));
    setMasterCVs((await cvResponse.json()) as MasterCV[]);
    if (profileResponse.ok) {
      setProfile((await profileResponse.json()) as ProfessionalProfile);
    } else if (profileResponse.status === 404) {
      setProfile(null);
    } else {
      throw new Error(await responseMessage(profileResponse));
    }
  }

  async function uploadCV(slot: number, file?: File) {
    if (!file || !accessToken) return;
    setUploadingSlot(slot);
    setCvError("");
    setCvNotice("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`/api/profile/cvs/${slot}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body
      });
      if (!response.ok) throw new Error(await responseMessage(response));
      await refreshCVData(accessToken);
      setCvNotice(`CV ${slot} uploaded. Review the extracted details before using them.`);
    } catch (caught) {
      setCvError(caught instanceof Error ? caught.message : "The CV could not be uploaded.");
    } finally {
      setUploadingSlot(null);
      const input = document.getElementById(`cv-upload-${slot}`) as HTMLInputElement | null;
      if (input) input.value = "";
    }
  }

  async function downloadCV(slot: number, version: CVVersion) {
    setCvError("");
    try {
      const response = await fetch(
        `/api/profile/cvs/${slot}/versions/${version.version}/download`,
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = version.original_filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setCvError(caught instanceof Error ? caught.message : "The CV could not be downloaded.");
    }
  }

  async function deleteCV(slot: number) {
    if (!accessToken || !window.confirm(`Delete CV ${slot} and its version history?`)) return;
    setCvError("");
    setCvNotice("");
    try {
      const response = await fetch(`/api/profile/cvs/${slot}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!response.ok) throw new Error(await responseMessage(response));
      await refreshCVData(accessToken);
      setCvNotice(`CV ${slot} and its stored versions were deleted.`);
    } catch (caught) {
      setCvError(caught instanceof Error ? caught.message : "The CV could not be deleted.");
    }
  }

  if (!user) {
    return (
      <main className="auth-page">
        <section className="auth-card">
          <div className="brand-mark">R</div>
          <p className="eyebrow">YOUR CAREER WORKSPACE</p>
          <h1>Make your next move<br />with confidence.</h1>
          <p className="muted">A private, human-approved workspace for your job search.</p>
          <form onSubmit={submitAuth}>
            {mode === "register" && (
              <label>
                Full name
                <input name="full_name" autoComplete="name" required maxLength={200} />
              </label>
            )}
            <label>
              Email address
              <input name="email" type="email" autoComplete="email" required />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                minLength={mode === "register" ? 12 : 1}
                maxLength={128}
                required
              />
              {mode === "register" && <span className="field-note">Use at least 12 characters.</span>}
            </label>
            {error && <p className="error" role="alert">{error}</p>}
            <button className="primary-button" disabled={busy}>
              {busy ? "Please wait…" : mode === "register" ? "Create your workspace" : "Sign in"}
            </button>
          </form>
          <button
            className="text-button"
            onClick={() => {
              setMode(mode === "register" ? "login" : "register");
              setError("");
            }}
          >
            {mode === "register" ? "Already have an account? Sign in" : "New here? Create an account"}
          </button>
          <p className="privacy-note">Your documents and profile stay private to your account.</p>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark small">C</span><strong>CareerPilot</strong></div>
        <p className="nav-heading">WORKSPACE</p>
        <a className="nav-item active" href="#overview"><span>◫</span> Overview</a>
        <a className="nav-item disabled" aria-disabled="true"><span>⌕</span> Job discovery <small>Phase 3</small></a>
        <a className="nav-item disabled" aria-disabled="true"><span>▤</span> My applications <small>Later</small></a>
        <a className="nav-item" href="#documents"><span>▧</span> My documents</a>
        <a className="nav-item disabled" aria-disabled="true"><span>✉</span> Recruitment email <small>Phase 6</small></a>
        <div className="sidebar-bottom">
          <div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div>
          <div className="user-copy"><strong>{user.full_name}</strong><span>{user.email}</span></div>
          <button className="sign-out" onClick={signOut} aria-label="Sign out">↗</button>
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar">
          <div><p className="eyebrow">{new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric" }).format(new Date()).toUpperCase()}</p><h1>Your career workspace</h1></div>
          <span className="status-pill"><i /> {profile ? "Profile needs review" : "Workspace ready"}</span>
        </header>

        <section className="welcome-panel">
          <div>
            <p className="eyebrow light">CAREERPILOT · PHASE 2</p>
            <h2>Welcome, {user.full_name.split(" ")[0]}.</h2>
            <p>Your private workspace is ready. Career tracks are set up independently so each can have its own search criteria.</p>
          </div>
          <div className="welcome-icon">✳</div>
        </section>

        <div className="section-title"><div><p className="eyebrow">PERSONALIZE YOUR SEARCH</p><h2>Your career tracks</h2></div><span className="track-count">03 TRACKS</span></div>
        <section className="track-grid">
          {preferences.map((preference, index) => (
            <article className="track-card" key={preference.id}>
              <div className={`track-icon track-${index}`}>{["⌘", "⌑", "⌁"][index]}</div>
              <p className="track-label">{trackNames[preference.track] ?? preference.track}</p>
              <h3>{preference.target_titles.length} target roles</h3>
              <div className="tag-row">
                {preference.target_titles.slice(0, 3).map((title) => <span className="tag" key={title}>{title}</span>)}
                {preference.target_titles.length > 3 && <span className="tag extra">+{preference.target_titles.length - 3}</span>}
              </div>
              <div className="card-footer"><span><i className="enabled-dot" /> {preference.enabled ? "Active" : "Paused"}</span><span>{preference.remote_preferred ? "Remote preferred" : "Location flexible"}</span></div>
            </article>
          ))}
        </section>

        <section className="documents-section" id="documents">
          <div className="section-title"><div><p className="eyebrow">VERIFIED PROFILE SOURCES</p><h2>Your master CVs</h2></div><span className="track-count">{masterCVs.length} / 2 UPLOADED</span></div>
          <p className="documents-intro">Upload a PDF or DOCX in either slot. New uploads replace the current CV while retaining its private version history. Extracted details are unverified until you check them against the original.</p>
          {cvError && <p className="error" role="alert">{cvError}</p>}
          {cvNotice && <p className="success-message" role="status">{cvNotice}</p>}
          <div className="cv-grid">
            {[1, 2].map((slot) => {
              const masterCV = masterCVs.find((item) => item.slot === slot);
              const current = masterCV?.versions.at(-1);
              return (
                <article className="cv-card" key={slot}>
                  <div className="cv-card-heading"><div className="track-icon">▤</div><div><span className="track-label">MASTER CV {slot}</span><h3>{current ? current.original_filename : "No document uploaded"}</h3></div></div>
                  {current ? (
                    <>
                      <p className="cv-version">Version {current.version} · {new Date(current.uploaded_at).toLocaleDateString()}</p>
                      <div className="cv-actions">
                        <button className="secondary-button" onClick={() => void downloadCV(slot, current)}>Download original</button>
                        <button className="text-button delete-button" onClick={() => void deleteCV(slot)}>Delete</button>
                      </div>
                      {masterCV && masterCV.versions.length > 1 && <p className="cv-history">{masterCV.versions.length} versions retained</p>}
                      <div className="cv-sections">
                        {Object.entries(current.extracted_sections).filter(([, entries]) => entries.length > 0).map(([section, entries]) => (
                          <div key={section}><strong>{section.replaceAll("_", " ")}</strong><span>{entries.length} extracted lines</span></div>
                        ))}
                        {current.review_flags.map((flag) => <p className="review-flag" key={flag}>Review needed: {flag}</p>)}
                      </div>
                    </>
                  ) : <p className="cv-empty">Your source document stays private and is never changed.</p>}
                  <label className="upload-button">
                    {uploadingSlot === slot ? "Uploading and extracting…" : current ? "Replace with a new version" : "Choose PDF or DOCX"}
                    <input
                      id={`cv-upload-${slot}`}
                      type="file"
                      accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                      disabled={uploadingSlot !== null}
                      onChange={(event) => void uploadCV(slot, event.target.files?.[0])}
                    />
                  </label>
                </article>
              );
            })}
          </div>

          {profile && (
            <section className="profile-review">
              <p className="eyebrow">EXTRACTED CANDIDATE PROFILE · NOT YET VERIFIED</p>
              <h3>Review the source-backed details</h3>
              <p className="documents-intro">Entries retain links to their source CVs. Exact duplicates across the current documents are grouped; dates, titles, and qualifications are not reconciled automatically.</p>
              {profile.review_flags.map((flag) => <p className="review-flag" key={flag}>{flag}</p>)}
              {Object.entries(profile.candidate_data).map(([section, entries]) => entries.length > 0 && (
                <div className="profile-category" key={section}>
                  <h4>{section.replaceAll("_", " ")}</h4>
                  {entries.map((entry, index) => (
                    <div className="profile-entry" key={`${section}-${index}`}>
                      <span>{entry.text}</span>
                      <small>Source CV{entry.source_slots.length > 1 ? "s" : ""} {entry.source_slots.join(", ")} · Unverified</small>
                    </div>
                  ))}
                </div>
              ))}
            </section>
          )}
        </section>

        <section className="next-step">
          <div className="next-step-icon">✦</div>
          <div><p className="eyebrow">UP NEXT · PHASE 3</p><h3>Discover and evaluate opportunities</h3><p>Your next phase will add compliant job-source imports, vacancy normalization, and evidence-based matching across your selected tracks.</p></div>
          <span className="coming-soon">COMING NEXT</span>
        </section>
        <footer className="footnote">Applications will never be submitted without your explicit approval.</footer>
      </main>
    </div>
  );
}

async function responseMessage(response: Response): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as { detail?: string };
  return body.detail ?? `Request failed (${response.status}).`;
}

export default App;
