import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, post } from "../api";
import { Page } from "../components/Shell";
import type { BannerInfo } from "../types";

const STEPS = [
  "Open your GitHub profile repository (the one named after your username).",
  "Edit README.md.",
  "Paste the copied Markdown.",
  "Commit the change.",
];

export default function BannerPage() {
  const [info, setInfo] = useState<BannerInfo | null>(null);
  const [err, setErr] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<BannerInfo>("/me/banner").then(setInfo).catch((e: ApiError) => setErr(e.status === 401 ? "signin" : e.message)); }, []);
  const regen = async () => { setBusy(true); try { setInfo(await post<BannerInfo>("/me/banner/regenerate")); } catch (e) { setErr((e as Error).message); } setBusy(false); };
  const copy = async () => {
    if (!info) return;
    try { await navigator.clipboard.writeText(info.markdown); } catch {
      const t = document.createElement("textarea"); t.value = info.markdown; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove();
    }
    setCopied(true); setTimeout(() => setCopied(false), 2000);
  };
  if (err === "signin") return <Page><h1 className="text-3xl font-bold">README banner</h1><p className="mt-3">Connect GitHub and generate your city first.</p><a className="btn btn-accent mt-4" href="/api/auth/github/login">Connect GitHub</a></Page>;
  if (err) return <Page><h1 className="text-3xl font-bold">README banner</h1><p role="alert" className="mt-3">{err}</p><Link to="/studio" className="btn btn-primary mt-4">Go to studio</Link></Page>;
  return (
    <Page>
      <h1 className="text-3xl font-bold">README banner</h1>
      <p className="mt-2 max-w-xl text-ink/75">Drawn from your saved city. It updates after you change your city, so the embedded image never goes stale.</p>
      {info && <>
        <img src={info.versioned_url} width={info.width} height={info.height} alt="Your DevTown banner" className="mt-6 w-full max-w-4xl rounded-xl shadow-lg ring-1 ring-ink/10" />
        <p className="mt-2 text-sm text-ink/65">{info.width} × {info.height} PNG. Current lighting: <b className="capitalize">{info.resolved_mode ?? "day"}</b>. GitHub shows it at about {info.display_width} × {info.display_height}.</p>
        <div className="mt-5 flex flex-wrap gap-3">
          <button className="btn btn-accent" onClick={copy}>{copied ? "Copied" : "Copy Markdown"}</button>
          <a className="btn btn-primary" href={info.versioned_url} download={`devtown-banner.png`}>Download PNG</a>
          <button className="btn btn-ghost" onClick={regen} disabled={busy}>{busy ? "Regenerating…" : "Regenerate banner"}</button>
        </div>
        <pre className="mt-4 max-w-4xl overflow-x-auto rounded-lg bg-ink p-4 text-sm text-paper"><code>{info.markdown}</code></pre>
        <span className="sr-only" aria-live="polite">{copied ? "Markdown copied to clipboard" : ""}</span>
        <h2 className="mt-10 text-xl font-bold">Add it to your profile</h2>
        <ol className="mt-3 max-w-xl list-decimal space-y-1.5 pl-5">{STEPS.map((s) => <li key={s}>{s}</li>)}</ol>
        <p className="mt-3 text-sm text-ink/65">That is all. No GitHub Actions, scripts or tokens.</p>
        <h2 className="mt-10 text-xl font-bold">How it will look on GitHub</h2>
        <img src={info.versioned_url} width={info.display_width} height={info.display_height} alt="" className="mt-3 rounded ring-1 ring-ink/10" style={{ width: info.display_width, height: info.display_height }} />
      </>}
    </Page>
  );
}
