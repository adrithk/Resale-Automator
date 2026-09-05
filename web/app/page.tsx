"use client";

import { ChangeEvent, useState } from "react";

type Json = Record<string, any>;
type Stage = "photos" | "facts" | "draft" | "done";
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const factNames = [
  "category", "item_type", "brand", "condition", "size", "inseam",
  "primary_color", "secondary_color", "source_1", "source_2",
  "age", "style_1", "style_2", "style_3",
];
const stageHeadings: Record<Stage, string> = {
  photos: "Add photos",
  facts: "Review facts",
  draft: "Review listing text",
  done: "Listing saved",
};

async function post(path: string, body: unknown): Promise<Json> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? "The local API rejected the request.");
  return payload;
}

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<Json | null>(null);
  const [facts, setFacts] = useState<Record<string, string>>(Object.fromEntries(factNames.map((name) => [name, ""])));
  const [draft, setDraft] = useState({ draft_title: "", description: "" });
  const [price, setPrice] = useState("");
  const [stage, setStage] = useState<Stage>("photos");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errors, setErrors] = useState<string[]>([]);
  const canAnalyze = files.length >= 3 && files.length <= 8 && !busy;
  const heading = stageHeadings[stage];

  function choosePhotos(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? []);
    setFiles(selected);
    setErrors(selected.length > 8 ? ["Depop supports at most 8 photos. Select 3–8 photos; all will be included."] : []);
    setProgress(0);
  }

  async function analyze() {
    if (!canAnalyze) return;
    setBusy(true);
    setErrors([]);
    setProgress(0);
    try {
      const paths: string[] = [];
      for (const [index, file] of files.entries()) {
        const form = new FormData();
        form.append("photo", file);
        const response = await fetch(`${apiBase}/uploads`, { method: "POST", body: form });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? `Could not upload ${file.name}.`);
        paths.push(payload.photo_path);
        setProgress(Math.round(((index + 1) / files.length) * 45));
      }
      setProgress(55);
      const classified = await post("/photo-roles", { photo_paths: paths });
      if (!classified.validated_facts) throw new Error(classified.error?.message ?? classified.tag_retake_instructions?.join(" ") ?? "The photos could not produce reviewable facts.");
      setResult({ ...classified, uploaded_photo_paths: paths });
      setFacts(Object.fromEntries(factNames.map((name) => [name, classified.validated_facts[name]?.value ?? ""])));
      setProgress(100);
      setStage("facts");
    } catch (caught) {
      setErrors([caught instanceof Error ? caught.message : "The local API is unavailable."]);
    } finally {
      setBusy(false);
    }
  }

  async function approveFacts() {
    setBusy(true);
    setErrors([]);
    try {
      const validation = await post("/facts/validate", { facts });
      if (!validation.valid) {
        setErrors(validation.errors.map((error: Json) => `${error.field}: ${error.message}`));
        return;
      }
      setFacts(validation.approved_facts);
      const generated = await post("/listing-drafts", { facts: validation.approved_facts });
      setDraft(generated.listing_draft);
      setPrice(generated.price);
      setResult((previous) => previous ? { ...previous, pricing_metadata: generated.pricing_metadata } : previous);
      setStage("draft");
    } catch (caught) {
      setErrors([caught instanceof Error ? caught.message : "Facts could not be validated."]);
    } finally {
      setBusy(false);
    }
  }

  async function approveListing() {
    if (!result) return;
    setBusy(true);
    setErrors([]);
    try {
      const approved = await post("/listings/approve", {
        pipeline_result: result,
        facts,
        listing_draft: draft,
        price,
        photo_paths: result.uploaded_photo_paths,
      });
      if (approved.status !== "listing_approved") {
        setErrors([...(approved.fact_errors ?? []), ...(approved.draft_errors ?? [])].map((error: Json) => `${error.field}: ${error.message}`));
        return;
      }
      setResult(approved);
      setStage("done");
    } catch (caught) {
      setErrors([caught instanceof Error ? caught.message : "The listing could not be saved."]);
    } finally {
      setBusy(false);
    }
  }

  async function downloadCsv() {
    if (!result) return;
    setBusy(true);
    setErrors([]);
    try {
      const response = await fetch(`${apiBase}/listings/export.csv`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved_facts: result.approved_facts,
          listing_draft: result.listing_draft,
          price: result.price,
          picture_urls: result.picture_urls,
          user_approved: true,
        }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail ?? "The CSV could not be created.");
      }
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? "depop-listing.csv";
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setErrors([caught instanceof Error ? caught.message : "The CSV could not be downloaded."]);
    } finally {
      setBusy(false);
    }
  }

  const stageIndex = ["photos", "facts", "draft", "done"].indexOf(stage);
  const reset = () => {
    setStage("photos");
    setFiles([]);
    setResult(null);
    setProgress(0);
    setErrors([]);
    setFacts(Object.fromEntries(factNames.map((name) => [name, ""])));
    setDraft({ draft_title: "", description: "" });
    setPrice("");
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">relist</div>
        <div className="topbar-copy">
          <strong>Local listing workspace</strong>
          <span>Photo hosting for Depop CSV</span>
        </div>
        <span className="local-badge"><i /> Local</span>
      </header>

      <aside className="sidebar">
        <h2>Selling Hub</h2>
        <button className="new-listing" disabled={busy} onClick={reset}>
          <span>＋</span> New listing
        </button>
        <nav aria-label="Listing progress">
          {["Add photos", "Review facts", "Listing draft", "Approved"].map((label, index) => (
            <div
              className={index === stageIndex ? "active" : index < stageIndex ? "complete" : ""}
              key={label}
            >
              <span>{index < stageIndex ? "✓" : index + 1}</span>{label}
            </div>
          ))}
        </nav>
      </aside>

      <main className="workspace">
        <header className="hero">
          <p className="eyebrow">CREATE A LISTING</p>
          <h1>{heading}</h1>
          <p className="lede">Turn clothing photos into a resale listing.</p>
        </header>
        <nav className="steps" aria-label="Current step">
          {["Photos", "Facts", "Listing", "Saved"].map((label, index) => (
            <span className={index <= stageIndex ? "current" : ""} key={label}>
              {index + 1} · {label}
            </span>
          ))}
        </nav>

        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">STEP {stageIndex + 1} OF 4</p>
              <h2>{heading}</h2>
            </div>
            {busy && <span className="status">Working…</span>}
          </div>

          {stage === "photos" && (
            <>
              <label className="dropzone">
                <input
                  type="file"
                  accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/jpg,image/pjpeg,image/png,image/webp"
                  multiple
                  disabled={busy}
                  onChange={choosePhotos}
                />
                <strong>Drop photos here or browse</strong>
                <small>Choose 3–8 photos: at least two garment views and one readable tag.</small>
                <small>
                  All photos, including the tag, are hosted automatically when you save the listing.
                  The order below becomes the CSV order; the first photo is the cover.
                  Anyone with the image links can view them.
                </small>
              </label>
              {files.length > 0 && (
                <ol className="files">
                  {files.map((file, index) => (
                    <li key={`${file.name}-${index}`}>
                      <span>{index + 1}</span>{file.name}<small>{Math.ceil(file.size / 1024)} KB</small>
                    </li>
                  ))}
                </ol>
              )}
              {busy && <div className="progress"><i style={{ width: `${progress}%` }} /></div>}
              <button className="primary" disabled={!canAnalyze} onClick={analyze}>
                {files.length < 3
                  ? "Select at least 3 photos"
                  : files.length > 8
                    ? "Select no more than 8 photos"
                    : "Analyze photos"}
              </button>
            </>
          )}

          {stage === "facts" && (
            <>
              <div className="form-grid">
                {factNames.map((name) => (
                  <label key={name}>
                    <span>{name.replaceAll("_", " ")}</span>
                    <input
                      value={facts[name] ?? ""}
                      onChange={(event) => setFacts({ ...facts, [name]: event.target.value })}
                      placeholder="Leave optional fields blank"
                    />
                  </label>
                ))}
              </div>
              <button className="primary" disabled={busy} onClick={approveFacts}>
                Validate facts and generate listing
              </button>
            </>
          )}

          {stage === "draft" && (
            <>
              <label className="wide">
                <span>Title</span>
                <input
                  value={draft.draft_title}
                  onChange={(event) => setDraft({ ...draft, draft_title: event.target.value })}
                />
              </label>
              <label className="wide">
                <span>Description</span>
                <textarea
                  rows={7}
                  value={draft.description}
                  onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                />
              </label>
              <label className="wide">
                <span>Price (USD)</span>
                <input
                  type="number"
                  inputMode="decimal"
                  min="0.01"
                  step="0.01"
                  value={price}
                  onChange={(event) => setPrice(event.target.value)}
                />
              </label>
              <button className="primary" disabled={busy} onClick={approveListing}>
                {busy ? "Hosting photos and saving…" : "Approve and save locally"}
              </button>
            </>
          )}

          {stage === "done" && (
            <div className="success">
              <span className="success-mark">✓</span>
              <strong>Approved listing saved.</strong>
              <p>{result?.saved_to?.split(/[\\/]/).pop()}</p>
              <div className="export-note">
                <strong>Depop draft CSV</strong>
                <span>
                  Includes all {result?.picture_urls?.length ?? 0} hosted photos, your approved price
                  (${result?.price}), and {result?.shipping_location}. Upload the CSV manually in
                  Depop's Selling Hub. Keep photos hosted until import completes and finish shipping
                  details in Depop.
                </span>
              </div>
              <div className="button-row">
                <button className="primary export" disabled={busy} onClick={downloadCsv}>
                  Download Depop CSV
                </button>
                <button className="secondary" disabled={busy} onClick={reset}>
                  Create another listing
                </button>
              </div>
            </div>
          )}

          {errors.length > 0 && (
            <ul className="errors">
              {errors.map((error) => <li key={error}>{error}</li>)}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
