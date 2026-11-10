// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DocumentWorkspace from "./DocumentWorkspace";

const source = {
  id: "source-id",
  version: 1,
  sha256: "a".repeat(64),
  extracted_text: "Experience\nPython Developer\nPersonal Projects\nPersonal Django app",
  verified_at: null as string | null
};

function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("source verification and CV generation", () => {
  it("blocks generation until a current source is verified", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response([]));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentWorkspace accessToken="test" sources={[{ slot: 1, versions: [source] }]} onVerified={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Generate PDF and DOCX" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Not verified")).toBeTruthy();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("never verifies if the user declines confirmation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response([]));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<DocumentWorkspace accessToken="test" sources={[{ slot: 1, versions: [source] }]} onVerified={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Confirm source accuracy" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("binds explicit verification to the exact source ID and hash", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({ ...source, verified_at: "2026-11-10T09:00:00Z" }));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onVerified = vi.fn().mockResolvedValue(undefined);
    render(<DocumentWorkspace accessToken="test" sources={[{ slot: 1, versions: [source] }]} onVerified={onVerified} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Confirm source accuracy" }));
    await waitFor(() => expect(onVerified).toHaveBeenCalledOnce());
    expect(fetchMock.mock.calls[1][0]).toBe("/api/profile/versions/source-id/verify");
    const options = fetchMock.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(options.body))).toEqual({
      confirmed: true, source_sha256: source.sha256, review_revision: 0
    });
  });

  it("shows failed generation without displaying fabricated documents", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({ detail: "No keyword overlap with a verified current CV." }, 422));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentWorkspace accessToken="test" sources={[{ slot: 1, versions: [{ ...source, verified_at: "2026-11-10T09:00:00Z" }] }]} onVerified={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Position"), { target: { value: "Accountant" } });
    fireEvent.change(screen.getByLabelText("Job description"), { target: { value: "Bookkeeping and financial reporting" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate PDF and DOCX" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("No generated CVs yet.")).toBeTruthy();
    expect(screen.queryByText("Download PDF")).toBeNull();
  });

  it("blocks unsaved edits and submits source-linked corrections and exclusions", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({ ...source, review_revision: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    const onVerified = vi.fn().mockResolvedValue(undefined);
    render(<DocumentWorkspace accessToken="test" sources={[{ slot: 1, versions: [{
      ...source, verified_at: "2026-11-10T09:00:00Z"
    }] }]} onVerified={onVerified} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText("Edit, exclude and organize source content"));
    fireEvent.change(screen.getByLabelText("Reviewed text for source line 2"), {
      target: { value: "Python Developer (personal project)" }
    });
    expect(screen.getByRole("button", { name: "Generate PDF and DOCX" }).hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByLabelText("Section for source line 2"), { target: { value: "projects" } });
    fireEvent.click(screen.getAllByLabelText("Exclude from profile and CV")[0]);
    fireEvent.change(screen.getByLabelText("Reason and evidence for corrections/exclusions"), {
      target: { value: "Compared with original; clarified project category." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save review and require fresh verification" }));
    await waitFor(() => expect(onVerified).toHaveBeenCalledOnce());
    expect(fetchMock.mock.calls[1][0]).toBe("/api/profile/versions/source-id/review");
    const payload = JSON.parse(String(fetchMock.mock.calls[1][1].body));
    expect(payload.source_sha256).toBe(source.sha256);
    expect(payload.expected_revision).toBe(0);
    expect(payload.excluded_source_lines).toEqual([1]);
    expect(payload.entries[0]).toEqual({
      section: "projects", text: "Python Developer (personal project)", source_lines: [2]
    });
  });

  it("sends the saved review revision when confirming accuracy", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({}));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<DocumentWorkspace accessToken="test" sources={[{ slot: 1, versions: [{
      ...source, review_revision: 3
    }] }]} onVerified={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Confirm source accuracy" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body)).review_revision).toBe(3);
  });

  it("keeps edits dirty and shows an explicit save failure", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response({ detail: "Review changed. Refresh before editing." }, 409));
    vi.stubGlobal("fetch", fetchMock);
    const onVerified = vi.fn();
    render(<DocumentWorkspace accessToken="test" sources={[{ slot: 1, versions: [source] }]} onVerified={onVerified} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText("Edit, exclude and organize source content"));
    fireEvent.change(screen.getByLabelText("Reason and evidence for corrections/exclusions"), {
      target: { value: "Checked source wording." }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save review and require fresh verification" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("Review changed. Refresh before editing.")).toBeTruthy();
    expect(onVerified).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Confirm source accuracy" }).hasAttribute("disabled")).toBe(true);
  });
});
