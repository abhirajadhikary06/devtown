import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { Page } from "../components/Shell";

type Town = {
  username: string; name: string; level: number; land_count: number; structures: number;
  width: number; depth: number;
  buildings: { x: number; z: number; w: number; d: number; color: string }[];
};
type World = { town_count: number; land_count: number; structure_count: number; towns: Town[] };

export default function WorldPage() {
  const [world, setWorld] = useState<World | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<World>("/world").then(setWorld).catch((e: ApiError) => setError(e.status === 404
      ? "The running backend has not loaded the community-world route yet. Restart the backend, then reload this page."
      : e.message));
  }, []);

  return <Page wide>
    <section className="mx-auto max-w-7xl px-5 pb-12">
      <div className="flex flex-wrap items-end justify-between gap-5 py-7">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-plum">One growing community</p>
          <h1 className="mt-2 text-4xl font-bold tracking-tight">The DevTown world</h1>
          <p className="mt-3 max-w-2xl text-ink/70">Every registered builder gets a plot in the shared city grid. Each town keeps its own layout, and the streets connect the neighborhoods.</p>
        </div>
        {world && <div className="flex flex-wrap gap-2 text-sm">
          <span className="rounded-lg bg-mist px-3 py-2"><b>{world.town_count}</b> towns</span>
          <span className="rounded-lg bg-mist px-3 py-2"><b>{world.land_count}</b> plots</span>
          <span className="rounded-lg bg-mist px-3 py-2"><b>{world.structure_count}</b> structures</span>
        </div>}
      </div>

      {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-4 text-red-800">Could not load the community world: {error}</p>}
      {!world && !error && <p className="py-12 text-center text-ink/60">Loading the community world…</p>}
      {world && world.towns.length === 0 && <div className="rounded-2xl border border-ink/10 bg-white p-8 text-center shadow-sm">
        <h2 className="text-2xl font-bold">The first plot is waiting</h2>
        <p className="mt-2 text-ink/70">Connect GitHub and build a town to start filling the shared map.</p>
        <Link className="btn btn-accent mt-5" to="/studio">Create your town</Link>
      </div>}

      {world && world.towns.length > 0 && <div className="community-world rounded-3xl border border-[#718778]/30 p-4 sm:p-7">
        <div className="mb-5 flex items-center gap-2 text-sm font-semibold text-[#263d35]">
          <span className="h-3 w-3 rounded-full bg-[#f2b134]" /> Connected neighborhoods
          <span className="font-normal text-[#263d35]/70">· roads extend as more towns join</span>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {world.towns.map((town) => <Link key={town.username} to={`/u/${encodeURIComponent(town.username)}`}
            className="group overflow-hidden rounded-2xl border border-white/80 bg-[#eef1e7] shadow-md transition hover:-translate-y-1 hover:shadow-xl focus-visible:outline-offset-4">
            <div className="relative aspect-[4/3] overflow-hidden border-b border-[#52645a]/20 bg-[#9fc28b]">
              <div className="absolute inset-0 town-parcel-grid" />
              <div className="absolute inset-[8%] rounded-lg border-2 border-white/60 bg-[#c6d8ad]/80 shadow-inner">
                <div className="absolute left-1/2 top-0 h-full w-[7%] -translate-x-1/2 bg-[#65737a]">
                  <div className="absolute left-1/2 top-0 h-full border-l border-dashed border-[#eee8cd]/80" />
                </div>
                <div className="absolute left-0 top-1/2 h-[7%] w-full -translate-y-1/2 bg-[#65737a]">
                  <div className="absolute left-0 top-1/2 w-full border-t border-dashed border-[#eee8cd]/80" />
                </div>
                {town.buildings.map((b, i) => <span key={i} className="absolute z-10 rounded-[2px] border border-black/20 shadow-sm transition group-hover:brightness-110"
                  style={{ left: `${(b.x / town.width) * 100}%`, top: `${(b.z / town.depth) * 100}%`,
                    width: `${Math.max((b.w / town.width) * 100, 2.5)}%`, height: `${Math.max((b.d / town.depth) * 100, 2.5)}%`,
                    background: b.color, boxShadow: "inset 0 -3px 0 #0002, 1px 2px 2px #0003" }} />)}
                {town.buildings.length === 0 && <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/85 px-3 py-1 text-xs font-semibold text-[#34483b]">New neighborhood</span>}
              </div>
              <span className="absolute right-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-xs font-bold text-[#263d35]">Level {town.level}</span>
            </div>
            <div className="flex items-center justify-between gap-3 p-4">
              <div className="min-w-0"><h2 className="truncate font-bold">{town.name}</h2><p className="mt-0.5 text-sm text-ink/60">@{town.username}</p></div>
              <div className="shrink-0 text-right text-xs text-ink/65"><p>{town.land_count} plots</p><p>{town.structures} buildings</p></div>
            </div>
          </Link>)}
        </div>
      </div>}
      <p className="mt-4 text-xs text-ink/55">All saved DevTown maps appear here, including your town and seeded featured towns.</p>
    </section>
  </Page>;
}
