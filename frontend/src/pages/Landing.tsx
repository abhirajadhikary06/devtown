import { useEffect } from "react";
import { api, post } from "../api";
import { Page, TownSearch } from "../components/Shell";

const FEATURED_PROFILE = "torvalds";
const FEATURED_PROFILES = ["charliermarsh", "karpathy", "peppy", "sindresorhus", "antfu", "gaearon"];

function useSeedFeaturedTowns() {
  useEffect(() => {
    const key = "devtown-featured-seed-requested";
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "checking");
    api<{ cities: { login: string; seeded: boolean }[] }>("/showcase").then((status) => {
      const missing = FEATURED_PROFILES.some((login) => !status.cities.find((city) => city.login === login)?.seeded);
      if (!missing) { sessionStorage.removeItem(key); return; }
      sessionStorage.setItem(key, "requested");
      return post("/showcase/seed", {}).catch(() => sessionStorage.removeItem(key));
    }).catch(() => sessionStorage.removeItem(key));
  }, []);
}

export default function Landing() {
  useSeedFeaturedTowns();
  return (
    <Page>
      <section className="grid items-center gap-10 pt-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
        <div>
          <h1 className="text-5xl font-bold leading-[1.05] tracking-tight">Your GitHub history, built as a city.</h1>
          <p className="mt-5 max-w-md text-lg text-ink/80">
            Connect GitHub and DevTown lays out a starter city from the languages you write, the tools you use and the projects you help with. Then it is yours to rebuild.
          </p>
          <div className="mt-6 max-w-md">
            <p className="mb-2 text-sm font-semibold text-ink/75">Explore a town</p>
            <TownSearch />
          </div>
          <div className="mt-7 flex flex-wrap gap-3">
            <a className="btn btn-accent" href="/api/auth/github/login">Connect GitHub</a>
            <a className="btn btn-ghost" href={`/u/${FEATURED_PROFILE}`}>Explore the featured town</a>
          </div>
          <p className="mt-4 text-sm text-ink/65">Read-only access to your public profile. No scripts, tokens or Actions needed for the README banner.</p>
        </div>
        <figure>
          <img src={`/api/banners/${FEATURED_PROFILE}.png`} width={1734} height={574} alt="A voxel town generated from Linus Torvalds's public GitHub profile"
               className="w-full rounded-xl shadow-lg ring-1 ring-ink/10" />
          <figcaption className="mt-2 text-sm text-ink/65">Featured town built from <a className="font-semibold underline" href={`/u/${FEATURED_PROFILE}`}>@{FEATURED_PROFILE}</a>'s public GitHub profile.</figcaption>
        </figure>
      </section>
      <section className="mt-12">
        <div className="mb-4">
          <h2 className="text-2xl font-bold">Featured developers</h2>
          <p className="mt-1 text-sm text-ink/65">Explore towns generated from these public GitHub profiles.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURED_PROFILES.map((login) => <a key={login} href={`/u/${login}`}
            className="flex items-center justify-between rounded-xl border border-ink/10 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-plum/40 hover:shadow-md">
            <span className="font-display font-bold">@{login}</span>
            <span className="text-sm font-semibold text-plum">Explore town →</span>
          </a>)}
        </div>
      </section>
      <section className="mt-12 flex flex-wrap items-center justify-between gap-5 rounded-2xl border border-ink/10 bg-white p-6 shadow-sm sm:p-8">
        <div><p className="text-xs font-bold uppercase tracking-[0.16em] text-plum">A city made by everyone</p>
          <h2 className="mt-2 text-2xl font-bold">See the community world grow</h2>
          <p className="mt-2 max-w-xl text-sm text-ink/65">Explore registered builders’ towns on one connected map. Each new neighborhood fills in another part of DevTown.</p></div>
        <a className="btn btn-accent" href="/world">Explore the community world</a>
      </section>
    </Page>
  );
}
