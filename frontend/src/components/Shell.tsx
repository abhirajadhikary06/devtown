import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { LightingPreference } from "../lighting";

export function Wordmark() {
  return <Link to="/" className="font-display text-xl font-bold tracking-tight text-ink">DevTown</Link>;
}
export function TownSearch() {
  const [username, setUsername] = useState("");
  const navigate = useNavigate();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const login = username.trim().replace(/^@/, "");
    if (login) navigate(`/u/${encodeURIComponent(login)}`);
  };
  return <form onSubmit={submit} role="search" className="flex w-full max-w-md items-center gap-2 rounded-xl border border-ink/15 bg-white p-1.5 shadow-sm focus-within:border-marigold focus-within:ring-2 focus-within:ring-marigold">
    <input aria-label="GitHub username" placeholder="Find a town by username" value={username} onChange={(e) => setUsername(e.target.value)}
      className="min-w-0 flex-1 rounded-lg bg-transparent px-3 py-2 text-sm outline-none placeholder:text-ink/45 focus-visible:outline-none" />
    <button className="flex h-10 w-12 shrink-0 items-center justify-center rounded-lg bg-marigold font-display text-2xl font-bold leading-none text-ink hover:brightness-95 focus-visible:outline-none" type="submit" aria-label="Find town" title="Find town">→</button>
  </form>;
}
export function LightingPicker({ value, onChange }: { value: LightingPreference; onChange: (mode: LightingPreference) => void }) {
  const modes: [LightingPreference, string][] = [["auto", "Auto"], ["day", "Day"], ["dusk", "Dusk"], ["night", "Night"]];
  return <div className="flex items-center justify-between gap-2 rounded-lg bg-mist p-1" role="group" aria-label="Map lighting">
    <span className="px-2 text-xs font-semibold text-ink/65">Lighting</span>
    <div className="flex min-w-0 flex-1 gap-1">{modes.map(([mode, label]) => <button key={mode} type="button" aria-pressed={value === mode}
      onClick={() => onChange(mode)} className={`min-w-0 flex-1 whitespace-nowrap rounded-md px-1.5 py-1.5 text-xs font-semibold transition ${value === mode ? "bg-white text-ink shadow-sm" : "text-ink/60 hover:bg-white/60"}`}>
      {label}</button>)}</div>
  </div>;
}
export function Page({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
        <Wordmark />
        <nav className="flex items-center gap-2 text-sm">
          <Link className="btn btn-ghost" to="/u/torvalds">Featured town</Link>
          <Link className="btn btn-ghost" to="/world">Community world</Link>
          <Link className="btn btn-ghost" to="/banner">README banner</Link>
          <Link className="btn btn-primary" to="/studio">Open studio</Link>
        </nav>
      </header>
      <main className={wide ? "" : "mx-auto max-w-6xl px-5 pb-16"}>{children}</main>
    </div>
  );
}
