import { useEffect, useMemo, useState } from "react";
import SearchPage from "./components/SearchPage";
import RunnerPage from "./components/RunnerPage";
import RacePage from "./components/RacePage";

function normalizeSearchFilters(filters = {}) {
  const q = typeof filters.q === "string" ? filters.q : "";
  const gender = filters.gender === "F" || filters.gender === "M" ? filters.gender : "";
  const birthYearRaw = filters.birthYear;
  const birthYear =
    birthYearRaw === null || birthYearRaw === undefined ? "" : String(birthYearRaw).trim();
  const raceQ = typeof filters.raceQ === "string" ? filters.raceQ : "";

  return { q, gender, birthYear, raceQ };
}

function buildSearchUrl(filters = {}) {
  const normalized = normalizeSearchFilters(filters);
  const params = new URLSearchParams();

  if (normalized.q.trim()) {
    params.set("q", normalized.q.trim());
  }
  if (normalized.gender) {
    params.set("gender", normalized.gender);
  }
  if (normalized.birthYear) {
    params.set("birthYear", normalized.birthYear);
  }
  if (normalized.raceQ.trim()) {
    params.set("raceQ", normalized.raceQ.trim());
  }

  const query = params.toString();
  return query ? `/?${query}` : "/";
}

function parseRoute(pathname, search) {
  const params = new URLSearchParams(search);
  if (pathname.startsWith("/runner/")) {
    const rawId = pathname.replace("/runner/", "").trim();
    return { page: "runner", runnerId: decodeURIComponent(rawId) };
  }
  if (pathname.startsWith("/hlaup/")) {
    const rawId = pathname.replace("/hlaup/", "").trim();
    return {
      page: "race",
      raceId: decodeURIComponent(rawId),
      focusedRunnerId: params.get("runner") || null
    };
  }
  return {
    page: "search",
    search: normalizeSearchFilters({
      q: params.get("q") || "",
      gender: params.get("gender") || "",
      birthYear: params.get("birthYear") || "",
      raceQ: params.get("raceQ") || ""
    })
  };
}

export default function App() {
  const [route, setRoute] = useState(() =>
    parseRoute(window.location.pathname, window.location.search)
  );

  useEffect(() => {
    const onPopState = () =>
      setRoute(parseRoute(window.location.pathname, window.location.search));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigation = useMemo(
    () => ({
      toSearch: () => {
        window.history.pushState({}, "", "/");
        setRoute({ page: "search", search: normalizeSearchFilters() });
      },
      persistSearch: (searchFilters, historyMode = "replace") => {
        const currentRoute = parseRoute(window.location.pathname, window.location.search);
        const mergedFilters =
          currentRoute.page === "search"
            ? normalizeSearchFilters({ ...currentRoute.search, ...searchFilters })
            : normalizeSearchFilters(searchFilters);
        const target = buildSearchUrl(mergedFilters);
        if (historyMode === "push") {
          window.history.pushState({}, "", target);
        } else {
          window.history.replaceState({}, "", target);
        }
        setRoute({
          page: "search",
          search: mergedFilters
        });
      },
      toRunner: (runnerId) => {
        const target = `/runner/${encodeURIComponent(runnerId)}`;
        window.history.pushState({}, "", target);
        setRoute({ page: "runner", runnerId });
      },
      toRace: (raceId, focusedRunnerId) => {
        const query = focusedRunnerId
          ? `?runner=${encodeURIComponent(focusedRunnerId)}`
          : "";
        const target = `/hlaup/${encodeURIComponent(raceId)}${query}`;
        window.history.pushState({}, "", target);
        setRoute({ page: "race", raceId: String(raceId), focusedRunnerId: focusedRunnerId || null });
      }
    }),
    []
  );

  return (
    <div className="app-shell">
      <div className="aurora aurora-1" aria-hidden />
      <div className="aurora aurora-2" aria-hidden />
      <header className="topbar">
        <button className="brand-button" onClick={navigation.toSearch}>
          <h1>Hlaupatímar</h1>
        </button>
      </header>

      <main className="content">
        {route.page === "search" ? (
          <SearchPage
            initialSearch={route.search}
            onPersistSearch={navigation.persistSearch}
            onOpenRace={(raceId) => navigation.toRace(raceId, null)}
            onSelectRunner={navigation.toRunner}
          />
        ) : route.page === "runner" ? (
          <RunnerPage
            runnerId={route.runnerId}
            onBack={navigation.toSearch}
            onOpenRace={(raceId) => navigation.toRace(raceId, route.runnerId)}
          />
        ) : (
          <RacePage
            raceId={route.raceId}
            focusedRunnerId={route.focusedRunnerId}
            onOpenRace={(raceId) => navigation.toRace(raceId, route.focusedRunnerId)}
            onBack={() => {
              if (route.focusedRunnerId) {
                navigation.toRunner(route.focusedRunnerId);
                return;
              }
              navigation.toSearch();
            }}
            onOpenRunner={navigation.toRunner}
          />
        )}
      </main>
    </div>
  );
}
