import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import CityCanvas, { type LightingMode } from "../components/CityCanvas";
import { LightingPicker, Page } from "../components/Shell";
import { automaticLighting, type LightingPreference } from "../lighting";
import type { Building, City } from "../types";

export default function CityPage() {
  const p = useParams();
  const username = p.username ?? (p.handle?.startsWith("@") ? p.handle.slice(1) : null);
  const [city, setCity] = useState<City | null>(null);
  const [cat, setCat] = useState<Building[]>([]);
  const [err, setErr] = useState("");
  const [autoRotateView, setAutoRotateView] = useState(false);
  const [viewAngle, setViewAngle] = useState(45);
  const [lightingPreference, setLightingPreference] = useState<LightingPreference>("auto");
  const lightingMode: LightingMode = lightingPreference === "auto" ? automaticLighting() : lightingPreference;
  const [, refreshLighting] = useState(0);
  useEffect(() => { const timer = window.setInterval(() => refreshLighting((n) => n + 1), 60_000); return () => window.clearInterval(timer); }, []);
  useEffect(() => {
    if (!username) return;
    api<City>(`/cities/${username}`).then(setCity).catch((e) => setErr(e.message));
    api<Building[]>("/catalogue").then(setCat).catch(() => {});
  }, [username]);
  const map = useMemo(() => Object.fromEntries(cat.map((b) => [b.id, b])), [cat]);
  if (!username) return <Page><h1 className="text-3xl font-bold">Page not found</h1><Link className="btn btn-primary mt-4" to="/">Back to DevTown</Link></Page>;
  return (
    <Page wide>
      <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-3 px-5 pb-3">
        <div>
          <h1 className="text-3xl font-bold">{city?.name ?? `@${username}`}</h1>
          {city && <p className="text-ink/70">@{city.username} · level {city.level} · {city.unlocked.length} land plots · {city.items.length} structures</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-mist px-3 py-2 text-sm text-ink/75" aria-live="polite">View {viewAngle}°</span>
          <LightingPicker value={lightingPreference} onChange={setLightingPreference} />
          <button type="button" aria-pressed={autoRotateView} onClick={() => setAutoRotateView((enabled) => !enabled)}
            className={`btn ${autoRotateView ? "btn-primary" : "btn-ghost"}`}>
            Auto rotate: {autoRotateView ? "On" : "Off"}
          </button>
          <Link className="btn btn-accent" to="/studio">Build your own city</Link>
        </div>
      </div>
      {err && <p role="alert" className="mx-auto max-w-6xl px-5 text-red-700">{err}</p>}
      <div className="h-[70vh] w-full">{city && cat.length > 0 && <CityCanvas city={city} cat={map} tool="view" selected={null} rot={0}
        autoRotateView={autoRotateView} onViewAngle={setViewAngle} lightingMode={lightingMode} />}</div>
      <p className="mx-auto max-w-6xl px-5 py-2 text-sm text-ink/60">Drag to pan, scroll to zoom.</p>
    </Page>
  );
}
