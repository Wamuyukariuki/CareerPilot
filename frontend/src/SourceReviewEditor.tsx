import { useState } from "react";

type ReviewEntry = { section: string; text: string; source_lines: number[] };
type Review = {
  revision: number;
  entries: ReviewEntry[];
  excluded_source_lines: number[];
  reason: string;
};
export type ReviewableSource = {
  id: string;
  sha256: string;
  extracted_text: string;
  review_revision?: number;
  review_history?: Review[];
  quality_warnings?: string[];
};
type Row = ReviewEntry & { excluded: boolean };
type Props = {
  source: ReviewableSource;
  accessToken: string;
  disabled: boolean;
  onSaved: () => Promise<void>;
  onDirty: () => void;
};

const sections: Record<string, string> = {
  contact: "Name / Contact", summary: "Professional Summary",
  skills: "Skills", employment_history: "Work Experience", education: "Education",
  certifications: "Certifications", projects: "Projects", languages: "Languages",
  other: "Additional Information"
};

function initialRows(source: ReviewableSource): Row[] {
  const lines = source.extracted_text.split(/\r?\n/);
  const review = source.review_history?.at(-1);
  if (review) {
    return [
      ...review.entries.map((entry) => ({ ...entry, excluded: false })),
      ...review.excluded_source_lines.map((line) => ({
        section: "other", text: lines[line - 1], source_lines: [line], excluded: true
      }))
    ];
  }
  return lines.map((text, index) => ({
    text, section: "other", source_lines: [index + 1], excluded: false
  }));
}

export default function SourceReviewEditor({ source, accessToken, disabled, onSaved, onDirty }: Props) {
  const [rows, setRows] = useState<Row[]>(() => initialRows(source));
  const [reason, setReason] = useState(source.review_history?.at(-1)?.reason ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);

  function change(index: number, patch: Partial<Row>) {
    setRows((previous) => previous.map((row, i) => i === index ? { ...row, ...patch } : row));
    setDirty(true);
    onDirty();
  }
  function move(index: number, direction: number) {
    setRows((previous) => {
      const next = [...previous];
      [next[index], next[index + direction]] = [next[index + direction], next[index]];
      return next;
    });
    setDirty(true);
    onDirty();
  }
  async function save() {
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`/api/profile/versions/${source.id}/review`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          source_sha256: source.sha256,
          expected_revision: source.review_revision ?? 0,
          entries: rows.filter((row) => !row.excluded).map(({ section, text, source_lines }) => ({ section, text, source_lines })),
          excluded_source_lines: rows.filter((row) => row.excluded).flatMap((row) => row.source_lines),
          reason
        })
      });
      if (!response.ok) {
        const body: unknown = await response.json();
        const detail = typeof body === "object" && body !== null && "detail" in body ? body.detail : null;
        throw new Error(typeof detail === "string" ? detail : "Check entries, source references and review reason.");
      }
      await onSaved();
      setDirty(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Source review could not be saved.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <details className="source-editor">
      <summary>Edit, exclude and organize source content</summary>
      <p className="documents-intro">
        Review every line against your original. Exclude template names, sample contacts,
        duplicate passages and unsupported claims. Assign a section to each retained entry.
        Correct broken links/reading order without guessing dates or metrics. Use a multiline
        entry to keep each employer, role, dates and its bullets together, then exclude the
        original continuation lines. Arrow controls change order within sections.
      </p>
      <p className="review-flag">
        Saving revokes verification. Reconfirm this exact saved review before generating.
        Corrections are owner-provided, not independently verified. The original is never edited.
      </p>
      {(source.quality_warnings ?? []).map((warning) => <p className="review-flag" key={warning}>{warning}</p>)}
      <fieldset disabled={disabled || saving} className="review-fieldset">
        <div className="review-rows">
          {rows.map((row, index) => (
            <div className={`review-row ${row.excluded ? "excluded" : ""}`} key={row.source_lines.join("-")}>
              <p>Original line{row.source_lines.length > 1 ? "s" : ""} {row.source_lines.join(", ")}</p>
              <details><summary>Original wording</summary><pre className="document-text">{row.source_lines.map((line) => source.extracted_text.split(/\r?\n/)[line - 1]).join("\n")}</pre></details>
              <label><input type="checkbox" checked={row.excluded} onChange={(event) => change(index, { excluded: event.target.checked })} /> Exclude from profile and CV</label>
              {!row.excluded && <>
                <label>Section for source line {row.source_lines.join(", ")}
                  <select value={row.section} onChange={(event) => change(index, { section: event.target.value })}>
                    {Object.entries(sections).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
                  </select>
                </label>
                <label>Reviewed text for source line {row.source_lines.join(", ")}
                  <textarea rows={3} value={row.text} onChange={(event) => change(index, { text: event.target.value })} />
                </label>
              </>}
              <div className="cv-actions">
                <button type="button" className="secondary-button" disabled={index === 0} onClick={() => move(index, -1)}>Move up</button>
                <button type="button" className="secondary-button" disabled={index === rows.length - 1} onClick={() => move(index, 1)}>Move down</button>
              </div>
            </div>
          ))}
        </div>
        <label>Reason and evidence for corrections/exclusions
          <textarea value={reason} minLength={5} maxLength={2000} onChange={(event) => { setReason(event.target.value); setDirty(true); onDirty(); }} />
        </label>
        <button type="button" className="secondary-button" disabled={reason.trim().length < 5 || rows.every((row) => row.excluded)} onClick={() => void save()}>
          {saving ? "Saving review…" : "Save review and require fresh verification"}
        </button>
      </fieldset>
      {dirty && <p className="review-flag">Unsaved edits: verification and generation are disabled until you save or reload.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {source.review_history && source.review_history.length > 0 && <details>
        <summary>Preview saved reviewed content</summary>
        <pre className="document-text">{Object.entries(sections).flatMap(([section, title]) => {
          const entries = source.review_history?.at(-1)?.entries.filter((entry) => entry.section === section) ?? [];
          if (entries.length === 0) return [];
          return [(section === "contact" ? "" : `${title}\n`) + entries.map((entry) => entry.text).join("\n")];
        }).join("\n\n")}</pre>
      </details>}
      {source.review_history && source.review_history.length > 0 && <details>
        <summary>Review history ({source.review_history.length} revisions)</summary>
        {source.review_history.map((review) => <p key={review.revision}>
          Revision {review.revision}: {review.entries.length} retained entries,
          {" "}{review.excluded_source_lines.length} excluded source lines. {review.reason}
        </p>)}
      </details>}
    </details>
  );
}
