import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import SourceReviewEditor from "./SourceReviewEditor";
import type { ReviewableSource } from "./SourceReviewEditor";

type SourceVersion = ReviewableSource & {
  id: string;
  version: number;
  sha256: string;
  extracted_text: string;
  verified_at: string | null;
};

type SourceCV = {
  slot: number;
  versions: SourceVersion[];
};

type GeneratedCV = {
  id: string;
  source_version_id: string;
  review_revision?: number;
  job_title: string;
  selection_explanation: string;
  matched_keywords: string[];
  comparison: string[];
  content_blocks: string[][];
  created_at: string;
};

type Props = {
  accessToken: string;
  sources: SourceCV[];
  onVerified: () => Promise<void>;
};

async function errorMessage(response: Response): Promise<string> {
  const body: unknown = await response.json();
  if (typeof body === "object" && body !== null && "detail" in body) {
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "Check the form fields and try again.";
  }
  return `Request failed (${response.status}).`;
}

export default function DocumentWorkspace({ accessToken, sources, onVerified }: Props) {
  const [documents, setDocuments] = useState<GeneratedCV[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [dirtySources, setDirtySources] = useState<string[]>([]);
  const headers = { Authorization: `Bearer ${accessToken}` };

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch("/api/documents/cvs", {
          headers: { Authorization: `Bearer ${accessToken}` },
          signal: controller.signal
        });
        if (!response.ok) throw new Error(await errorMessage(response));
        setDocuments((await response.json()) as GeneratedCV[]);
      } catch (caught) {
        if (!controller.signal.aborted) {
          setError(caught instanceof Error ? caught.message : "Could not load generated CVs.");
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [accessToken, sources]);

  async function verify(source: SourceVersion, revoke = false) {
    if (!revoke && !window.confirm(
      "I have compared the saved review (or complete extraction if unedited) with " +
      "my original CV. I confirm its identities, dates, qualifications, metrics, " +
      "proficiency, corrections and project types are accurate and supported. " +
      "I have checked the quality warnings and excluded template examples. " +
      "This verifies only this exact source and saved review revision."
    )) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(
        `/api/profile/versions/${source.id}/${revoke ? "verification" : "verify"}`,
        {
          method: revoke ? "DELETE" : "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          ...(!revoke && { body: JSON.stringify({
            confirmed: true, source_sha256: source.sha256,
            review_revision: source.review_revision ?? 0
          }) })
        }
      );
      if (!response.ok) throw new Error(await errorMessage(response));
      await onVerified();
      setNotice(revoke ? "Verification revoked. Exports from this source are blocked." : "This source version is now verified by you.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Verification could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/documents/cvs", {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          job_title: data.get("job_title"),
          job_description: data.get("job_description")
        })
      });
      if (!response.ok) throw new Error(await errorMessage(response));
      const generated = (await response.json()) as GeneratedCV;
      setDocuments((previous) => [generated, ...previous].slice(0, 100));
      setNotice("PDF and DOCX saved. Preview both before using them.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "CV generation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function download(document: GeneratedCV, format: "pdf" | "docx") {
    setError("");
    try {
      const response = await fetch(`/api/documents/cvs/${document.id}/download/${format}`, { headers });
      if (!response.ok) throw new Error(await errorMessage(response));
      const url = URL.createObjectURL(await response.blob());
      const link = window.document.createElement("a");
      link.href = url;
      link.download = `careerpilot-${document.id}.${format}`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Document download failed.");
    }
  }

  const verifiedSources = sources.filter((source) => source.versions.at(-1)?.verified_at);
  const hasUnsavedChanges = sources.some((source) =>
    dirtySources.includes(source.versions.at(-1)?.id ?? "")
  );

  return (
    <section className="profile-review" id="generated-documents">
      <p className="eyebrow">VERIFY BEFORE GENERATING</p>
      <h3>Source verification and tailored CVs</h3>
      <p className="documents-intro">
        Review the original and the complete extraction. Use the source editor to exclude
        template examples, correct extraction and organize sections. Verify the saved review,
        not an unreviewed text dump. Verification never carries over to replacements or edits.
      </p>
      {sources.map((source) => {
        const current = source.versions.at(-1);
        if (!current) return null;
        return (
          <div className="source-review" key={current.id}>
            <h4>CV {source.slot} · Version {current.version}</h4>
            <details><summary>Review complete extracted text</summary><pre className="document-text">{current.extracted_text}</pre></details>
            {(current.quality_warnings ?? []).map((warning) => <p className="review-flag" key={warning}>{warning}</p>)}
            <SourceReviewEditor
              key={`${current.id}-${current.review_revision ?? 0}`}
              source={current}
              accessToken={accessToken}
              disabled={busy}
              onDirty={() => setDirtySources((previous) => [...new Set([...previous, current.id])])}
              onSaved={async () => {
                await onVerified();
                setDirtySources((previous) => previous.filter((id) => id !== current.id));
                setNotice("Review saved. Check it and confirm accuracy before generating.");
              }}
            />
            <p className="cv-version">{current.verified_at ? `Verified by you on ${new Date(current.verified_at).toLocaleString()}` : "Not verified"}</p>
            <button type="button" className="secondary-button" disabled={busy || (!current.verified_at && dirtySources.includes(current.id))} onClick={() => void verify(current, current.verified_at !== null)}>
              {current.verified_at ? "Revoke verification" : "Confirm source accuracy"}
            </button>
          </div>
        );
      })}
      <form className="generation-form" onSubmit={(event) => void generate(event)}>
        <h3>Prepare a CV for a vacancy</h3>
        <p className="documents-intro">Selects a verified current source using keyword overlap, then ranks whole sections. Saved owner corrections/exclusions are applied; original evidence and cleanup notes remain traceable. No AI rewriting or application submission.</p>
        <label>Position<input name="job_title" required maxLength={200} /></label>
        <label>Job description<textarea name="job_description" required minLength={20} maxLength={30000} rows={6} /></label>
        <button className="primary-button" disabled={busy || verifiedSources.length === 0 || hasUnsavedChanges}>
          {busy ? "Saving…" : "Generate PDF and DOCX"}
        </button>
        {verifiedSources.length === 0 && <p className="review-flag">Verify at least one current source CV to enable generation.</p>}
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {notice && <p role="status" className="success-message">{notice}</p>}
      <h3>Generated CV history</h3>
      {documents.length === 0 && <p className="documents-intro">No generated CVs yet.</p>}
      {documents.map((document) => (
        <article className="generated-cv" key={document.id}>
          <h4>{document.job_title}</h4>
          <p className="cv-version">{new Date(document.created_at).toLocaleString()} · Source version: {document.source_version_id} · Review revision: {document.review_revision ?? 0}</p>
          {sources.flatMap((source) => source.versions).some((source) =>
            source.id === document.source_version_id &&
            (source.review_revision ?? 0) !== (document.review_revision ?? 0)
          ) && <p className="review-flag">Outdated review: downloads are blocked. Generate a new CV after confirming the current review.</p>}
          <p>{document.selection_explanation}</p>
          <p>Keyword overlap: {document.matched_keywords.join(", ")}</p>
          <details><summary>What changed and why</summary>{document.comparison.map((line) => <p key={line}>{line}</p>)}</details>
          <details><summary>Preview generated wording</summary><pre className="document-text">{document.content_blocks.map((block) => block.join("\n")).join("\n\n")}</pre></details>
          <div className="cv-actions">
            <button className="secondary-button" disabled={hasUnsavedChanges} onClick={() => void download(document, "pdf")}>Download PDF</button>
            <button className="secondary-button" disabled={hasUnsavedChanges} onClick={() => void download(document, "docx")}>Download DOCX</button>
          </div>
        </article>
      ))}
    </section>
  );
}
