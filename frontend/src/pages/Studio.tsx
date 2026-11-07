import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, post } from "../api";
import CityCanvas, { Tool, type LightingMode } from "../components/CityCanvas";
import { LightingPicker, Wordmark } from "../components/Shell";
import { automaticLighting, timezone, type LightingPreference } from "../lighting";
import type { Analysis, Balances, Building, City, Item } from "../types";

const RES: [keyof Balances, string][] = [["energy", "Energy"], ["coins", "Coins"], ["materials", "Materials"], ["reputation", "Reputation"]];
const humanKey = (k: string) => k.replace(/\./g, " ").replace(/_/g, " ");

export default function Studio() {
  const [state, setState] = useState<"loading" | "signin" | "analyze" | "ready">("loading");
  const [login, setLogin] = useState("");
  const [city, setCity] = useState<City | null>(null);
  const [cat, setCat] = useState<Building[]>([]);
  const [bal, setBal] = useState<Balances | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [tool, setTool] = useState<Tool>("build");
  const [sel, setSel] = useState<string | null>("home");
  const [rot, setRot] = useState(0);
  const [autoRotateView, setAutoRotateView] = useState(false);
  const [viewAngle, setViewAngle] = useState(45);
  const [lightingPreference, setLightingPreference] = useState<LightingPreference>("auto");
  const lightingMode: LightingMode = lightingPreference === "auto" ? automaticLighting() : lightingPreference;
  const [, refreshLighting] = useState(0);
  useEffect(() => { const timer = window.setInterval(() => refreshLighting((n) => n + 1), 60_000); return () => window.clearInterval(timer); }, []);
  const [msg, setMsg] = useState("");
  const [panel, setPanel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [autoBuild, setAutoBuild] = useState(true);

  const load = useCallback(async (u: string) => {
    const [c, k, p] = await Promise.all([api<City>(`/cities/${u}`), api<Building[]>("/catalogue"), api<{ analysis: Analysis | null; balances: Balances }>("/me/profile")]);
    setCity(c); setCat(k); setBal(p.balances); setAnalysis(p.analysis); setState("ready");
  }, []);

  useEffect(() => {
    api<{ login: string; has_city: boolean; balances: Balances }>("/me").then((m) => {
      setLogin(m.login); setBal(m.balances);
      m.has_city ? load(m.login) : setState("analyze");
    }).catch((e: ApiError) => setState(e.status === 401 ? "signin" : "signin"));
  }, [load]);

  useEffect(() => {
    if (!city) return;
    api<{ mode: LightingPreference; timezone: string }>("/me/lighting").then((p) => setLightingPreference(p.mode)).catch(() => {});
  }, [city]);

  const changeLighting = (mode: LightingPreference) => {
    setLightingPreference(mode);
    api("/me/lighting", { method: "PATCH", body: JSON.stringify({ mode, timezone: timezone() }) })
      .catch((e) => setMsg(`Could not save lighting: ${(e as Error).message}`));
  };

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
      if (!typing && (e.key === "r" || e.key === "R")) setRot((r) => (r + 1) % 4);
      if (e.key === "Escape") setTool("view");
    };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, []);

  const map = useMemo(() => Object.fromEntries(cat.map((b) => [b.id, b])), [cat]);
  const groups = useMemo(() => {
    const g: Record<string, Building[]> = {};
    for (const b of cat) (g[b.category] ??= []).push(b);
    return Object.entries(g);
  }, [cat]);

  const analyze = async () => {
    setBusy(true); setMsg("");
    try {
      const result = await post<{ built_structures?: number; deferred_buildings?: number }>("/me/sync", { auto_build: autoBuild });
      await load(login);
      setMsg(autoBuild
        ? `Your town was auto-built with ${result.built_structures ?? 0} structures${result.deferred_buildings ? `; ${result.deferred_buildings} did not fit yet.` : "."}`
        : "Your town is ready for manual building.");
    } catch (e) { setMsg((e as Error).message); }
    setBusy(false);
  };
  const place = async (x: number, z: number) => {
    if (!sel || !city) return;
    try {
      const r = await post<{ item: Item; version: number; balances: Balances }>("/me/city/items", { type: sel, x, z, rot });
      setCity({ ...city, items: [...city.items, r.item], version: r.version }); setBal(r.balances); setMsg("");
    } catch (e) { setMsg((e as Error).message); }
  };
  const remove = async (id: number) => {
    if (!city) return;
    try {
      const r = await api<{ version: number; balances: Balances }>(`/me/city/items/${id}`, { method: "DELETE" });
      setCity({ ...city, items: city.items.filter((i) => i.id !== id), version: r.version }); setBal(r.balances); setMsg("");
    } catch (e) { setMsg((e as Error).message); }
  };
  const expand = async (cx: number, cz: number) => {
    try { const r = await post<{ balances: Balances }>("/me/city/expand", { cx, cz }); setBal(r.balances); await load(login); setMsg("Land expanded."); }
    catch (e) { setMsg((e as Error).message); }
  };
  const rename = async (name: string) => { if (city && name.trim() && name !== city.name) { try { await api("/me/city", { method: "PATCH", body: JSON.stringify({ name }) }); setCity({ ...city, name }); } catch (e) { setMsg((e as Error).message); } } };

  if (state === "loading") return <div className="p-8">Loading your studio…</div>;
  if (state === "signin") return (
    <div className="mx-auto max-w-md p-8"><Wordmark /><h1 className="mt-6 text-3xl font-bold">Sign in to build your city</h1>
      <p className="mt-2 text-ink/75">DevTown reads your public GitHub profile. It never writes to GitHub.</p>
      <a className="btn btn-accent mt-5" href="/api/auth/github/login">Connect GitHub</a> <Link className="btn btn-ghost mt-5" to="/u/demo">Explore the demo</Link></div>);
  if (state === "analyze") return (
    <div className="mx-auto max-w-md p-8"><Wordmark /><h1 className="mt-6 text-3xl font-bold">Hi {login}. Ready to see your city?</h1>
      <p className="mt-2 text-ink/75">We will read your languages, repositories, pull requests and open-source work, then prepare your city. This takes about a minute.</p>
      <div className="mt-5 grid gap-2" role="group" aria-label="City setup mode">
        <button type="button" aria-pressed={autoBuild} onClick={() => setAutoBuild(true)}
          className={`rounded-xl border p-3 text-left ${autoBuild ? "border-plum bg-mist" : "border-ink/10"}`}>
          <b>Auto-build my town</b><span className="mt-1 block text-sm text-ink/65">Place a starter layout based on your GitHub profile.</span>
        </button>
        <button type="button" aria-pressed={!autoBuild} onClick={() => setAutoBuild(false)}
          className={`rounded-xl border p-3 text-left ${!autoBuild ? "border-plum bg-mist" : "border-ink/10"}`}>
          <b>Build manually</b><span className="mt-1 block text-sm text-ink/65">Start with an empty plot and place everything yourself.</span>
        </button>
      </div>
      <button className="btn btn-accent mt-5" onClick={analyze} disabled={busy}>{busy ? "Analyzing your GitHub…" : "Analyze my GitHub"}</button>
      {msg && <p role="alert" className="mt-3 text-red-700">{msg}</p>}</div>);

  const selB = sel ? map[sel] : null;
  return (
    <div className="flex h-screen flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-ink/10 bg-paper px-4 py-2">
        <Wordmark />
        <input aria-label="City name" defaultValue={city!.name} maxLength={40} onBlur={(e) => rename(e.target.value)} className="w-52 rounded border border-transparent bg-transparent px-2 py-1 font-display font-semibold hover:border-ink/20" />
        <span className="rounded-full bg-marigold px-2.5 py-0.5 text-xs font-bold">Level {city!.level}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2 text-sm">
          {RES.map(([k, l]) => <span key={k} className="rounded-md bg-mist px-2.5 py-1"><span className="text-ink/65">{l}</span> <b>{bal?.[k] ?? 0}</b></span>)}
          <button className="btn btn-ghost" onClick={() => setPanel(!panel)}>Developer profile</button>
          <button className="btn btn-ghost" onClick={analyze} disabled={busy}>{busy ? "Refreshing…" : "Refresh from GitHub"}</button>
          <Link className="btn btn-accent" to="/banner">README banner</Link>
        </div>
      </header>
      <div className="relative flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-ink/10 bg-paper p-3">
          <div className="mb-3 grid grid-cols-4 gap-1" role="toolbar" aria-label="Tools">
            {([["build", "Build"], ["demolish", "Demolish"], ["expand", "Expand"], ["view", "Look"]] as [Tool, string][]).map(([t, l]) => (
              <button key={t} aria-pressed={tool === t} onClick={() => setTool(t)} className={`btn !px-0.5 !text-xs leading-tight whitespace-normal ${tool === t ? "btn-primary" : "btn-ghost"}`}>{l}</button>))}
          </div>
          <div className="mb-3 space-y-2">
            <button type="button" aria-pressed={autoRotateView} onClick={() => setAutoRotateView((enabled) => !enabled)}
              className={`btn w-full ${autoRotateView ? "btn-primary" : "btn-ghost"}`}>
              Auto rotate town: {autoRotateView ? "On" : "Off"}
            </button>
            <LightingPicker value={lightingPreference} onChange={changeLighting} />
            <div className="flex items-center justify-between rounded-md bg-mist px-3 py-2 text-sm" aria-live="polite">
              <span>View direction</span>
              <span className="flex items-center gap-2"><span className="inline-block text-lg transition-transform" style={{ transform: `rotate(${viewAngle}deg)` }}>↑</span><b>{autoRotateView ? `Orbiting · ${viewAngle}°` : `${viewAngle}°`}</b></span>
            </div>
            <p className="px-1 text-xs text-ink/60">Drag the town to orbit freely through 360°; scroll to zoom.</p>
          </div>
          {tool === "expand" && <p className="mb-3 rounded bg-mist p-2 text-sm">Click a purple plot to claim it. Cost grows with each plot and needs a higher city level.</p>}
          {groups.map(([g, list]) => (
            <section key={g} className="mb-3"><h2 className="mb-1 text-sm font-bold capitalize text-ink/70">{g}</h2>
              <ul className="space-y-1">{list.map((b) => {
                const coinGap = Math.max(0, b.coins - (bal?.coins ?? b.coins));
                const materialGap = Math.max(0, b.materials - (bal?.materials ?? b.materials));
                const canAfford = coinGap === 0 && materialGap === 0;
                const lockReason = b.lock_reason ?? "Unlocks from public GitHub profile evidence";
                const shortage = [coinGap ? `${coinGap} more coins` : "", materialGap ? `${materialGap} more materials` : ""].filter(Boolean).join(" and ");
                const hint = !b.unlocked ? lockReason : !canAfford ? `Need ${shortage}. Sync GitHub to earn coins from activity and materials from repository evidence.` : "";
                return <li key={b.id}><span className="block" title={hint}>
                  <button disabled={!b.unlocked || !canAfford} onClick={() => { setSel(b.id); setTool("build"); }}
                  aria-label={`${b.name}${!b.unlocked ? `. Locked: ${lockReason}` : !canAfford ? `. ${hint}` : ""}`}
                  className={`flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left text-sm ${sel === b.id && tool === "build" ? "border-plum bg-mist" : "border-transparent hover:bg-mist"} disabled:opacity-40`}>
                  <span className="h-4 w-4 shrink-0 rounded-sm" style={{ background: b.color }} />
                  <span className="flex-1">{b.name}<span className="block text-xs text-ink/60">{b.w}×{b.d} · {b.coins}c {b.materials}m</span>
                    {b.unlocked && !canAfford && <span className="block text-xs leading-4 text-amber-800">Need {shortage} · Sync GitHub to earn</span>}</span>
                  {(!b.unlocked || !canAfford) && <span aria-label={!b.unlocked ? "Locked" : "Insufficient resources"}>{!b.unlocked ? "🔒" : "ⓘ"}</span>}</button>
                </span></li>;
              })}</ul></section>))}
        </aside>
        <div className="relative min-w-0 flex-1">
          <CityCanvas city={city!} cat={map} tool={tool} selected={sel} rot={rot} autoRotateView={autoRotateView} onViewAngle={setViewAngle} lightingMode={lightingMode}
            onPlace={place} onRemove={remove} onExpand={expand} />
          <div aria-live="polite" className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-lg bg-ink px-4 py-2 text-sm text-paper" style={{ display: msg ? "block" : "none" }}>{msg}</div>
          {tool === "build" && selB && <div className="pointer-events-none absolute left-3 top-3 rounded bg-paper/90 px-3 py-1.5 text-sm">Placing <b>{selB.name}</b> · facing {rot * 90}° · {selB.coins} coins, {selB.materials} materials</div>}
        </div>
        {panel && analysis && (
          <aside className="w-80 shrink-0 overflow-y-auto border-l border-ink/10 bg-paper p-4 text-sm">
            <h2 className="text-lg font-bold">Developer profile</h2>
            <p className="mt-1 text-ink/70">Specialization: {analysis.identity.specialization ?? "not detected"}. Population about {analysis.community.population}.</p>
            <h3 className="mt-4 font-bold">Languages</h3>
            {Object.entries(analysis.identity.shares).slice(0, 8).map(([l, s]) => (
              <div key={l} className="mt-1"><div className="flex justify-between"><span>{l}</span><span>{Math.round(s * 100)}%</span></div><div className="h-1.5 rounded bg-mist"><div className="h-1.5 rounded bg-plum" style={{ width: `${s * 100}%` }} /></div></div>))}
            <h3 className="mt-4 font-bold">Technologies found</h3>
            <ul className="mt-1 list-disc pl-5">{analysis.identity.tech_facilities.map((t) => <li key={t.tech}>{t.tech} <span className="text-ink/60">(from {t.evidence.join(", ")})</span></li>)}</ul>
            {analysis.identity.tech_facilities.length === 0 && <p className="text-ink/60">None detected in your public repositories.</p>}
            <h3 className="mt-4 font-bold">What we could not read</h3>
            <p className="text-ink/70">These earn nothing and are never estimated.</p>
            <ul className="mt-1 list-disc pl-5">{analysis.data_quality.unavailable.map((k) => <li key={k}>{humanKey(k)}</li>)}</ul>
            <h3 className="mt-4 font-bold">Estimated from a sample</h3>
            <ul className="mt-1 list-disc pl-5">{analysis.data_quality.inferred.map((k) => <li key={k}>{humanKey(k)}</li>)}</ul>
            {analysis.data_quality.notes.map((n) => <p key={n} className="mt-3 rounded bg-mist p-2">{n}</p>)}
          </aside>)}
      </div>
    </div>
  );
}
