"use client";

import { ChangeEvent, useMemo, useState } from "react";

type ApiResult = Record<string, unknown>;
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function postJson(path: string, body: unknown): Promise<ApiResult> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "The local API rejected the request.");
  return result;
}

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [uploadedPaths, setUploadedPaths] = useState<string[]>([]);
  const [result, setResult] = useState<ApiResult | null>(null);
  const [state, setState] = useState<"idle" | "uploading" | "detecting" | "processing">("idle");
  const [error, setError] = useState<string | null>(null);
  const [selectedTagIndex, setSelectedTagIndex] = useState<number | null>(null);
  const canStart = files.length >= 3 && state === "idle";
  const status = useMemo(() => ({ idle: "Ready", uploading: "Uploading photos", detecting: "Finding the tag", processing: "Analyzing garment" })[state], [state]);

  function choosePhotos(event: ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(event.target.files ?? []));
    setUploadedPaths([]); setResult(null); setError(null); setSelectedTagIndex(null);
  }

  async function uploadAndDetect() {
    if (!canStart) return;
    try {
      setState("uploading"); setError(null);
      const paths: string[] = [];
      for (const file of files) {
        const form = new FormData(); form.append("photo", file);
        const response = await fetch(`${apiBase}/uploads`, { method: "POST", body: form });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? `Could not upload ${file.name}.`);
        paths.push(payload.photo_path);
      }
      setUploadedPaths(paths); setState("detecting");
      const detected = await postJson("/photo-roles", { photo_paths: paths });
      setResult(detected);
      setState("idle");
    } catch (caught) {
      setState("idle"); setError(caught instanceof Error ? caught.message : "The local API is unavailable.");
    }
  }

  async function confirmTag() {
    if (!result || selectedTagIndex === null) return;
    try {
      setState("processing"); setError(null);
      const stage = result.photo_role_detection as { analysis: unknown };
      const metadata = result.photo_role_metadata;
      const classified = await postJson("/classifications/folder/confirmed", {
        photo_paths: uploadedPaths,
        photo_role_analysis: stage.analysis,
        photo_role_metadata: metadata,
        tag_photo_index: selectedTagIndex,
      });
      setResult(classified);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not continue classification.");
    } finally { setState("idle"); }
  }

  const needsTagReview = result?.status === "photo_role_review_required";
  return <main>
    <section className="hero">
      <p className="eyebrow">LOCAL LISTING WORKBENCH</p>
      <h1>Turn clothing photos into a reviewable listing.</h1>
      <p className="lede">Select at least three photos in any order. The local Python service identifies the tag and validates the garment details.</p>
    </section>
    <section className="panel">
      <div className="panel-head"><div><p className="eyebrow">01 · PHOTOS</p><h2>Choose your garment photos</h2></div><span className="status">{status}</span></div>
      <label className="dropzone"><input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={choosePhotos} /><span>Drop photos here or browse</span><small>JPEG, PNG, or WebP · at least 2 garment photos and 1 tag photo</small></label>
      {files.length > 0 && <ol className="files">{files.map((file, index) => <li key={`${file.name}-${index}`}><span>{index + 1}</span>{file.name}<small>{Math.ceil(file.size / 1024)} KB</small></li>)}</ol>}
      <button className="primary" disabled={!canStart} onClick={uploadAndDetect}>{files.length < 3 ? "Select at least 3 photos" : "Analyze photos"}</button>
      {error && <p className="error">{error}</p>}
    </section>
    {needsTagReview && <section className="panel"><p className="eyebrow">02 · TAG CONFIRMATION</p><h2>Which photo is the clothing tag?</h2><p className="lede">The service was below its 60% confidence threshold, so it needs your confirmation before the hosted analysis runs.</p><div className="choices">{files.map((file, index) => <button className={selectedTagIndex === index ? "choice active" : "choice"} key={file.name} onClick={() => setSelectedTagIndex(index)}>{index + 1}. {file.name}</button>)}</div><button className="primary" disabled={selectedTagIndex === null || state !== "idle"} onClick={confirmTag}>Confirm tag and continue</button></section>}
    {result && !needsTagReview && <section className="panel"><p className="eyebrow">03 · RESULT</p><h2>{String(result.status).replaceAll("_", " ")}</h2><p className="lede">This is the unchanged, structured Python pipeline result. Fact and listing-text editing will be added to this local interface next.</p><pre>{JSON.stringify(result, null, 2)}</pre></section>}
  </main>;
}
