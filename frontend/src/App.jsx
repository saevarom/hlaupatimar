import { useEffect, useMemo, useState } from "react";
import SearchPage from "./components/SearchPage";
import RunnerPage from "./components/RunnerPage";
import RacePage from "./components/RacePage";
import RaceListPage from "./components/RaceListPage";

function normalizeSearchFilters(filters = {}) {
  const q = typeof filters.q === "string" ? filters.q : "";
  const gender = filters.gender === "F" || filters.gender === "M" ? filters.gender : "";
  const birthYearRaw = filters.birthYear;
  const birthYear =
    birthYearRaw === null || birthYearRaw === undefined ? "" : String(birthYearRaw).trim();
  const raceQ = typeof filters.raceQ === "string" ? filters.raceQ : "";

  return { q, gender, birthYear, raceQ };
}

function normalizeRaceBrowseFilters(filters = {}) {
  const q = typeof filters.q === "string" ? filters.q : "";
  const yearRaw = filters.year;
  const year = yearRaw === null || yearRaw === undefined ? "" : String(yearRaw).trim();
  const orderOptions = new Set(["date_desc", "date_asc", "speed_fastest", "speed_slowest"]);
  const order =
    typeof filters.order === "string" && orderOptions.has(filters.order)
      ? filters.order
      : "date_desc";
  const pageRaw = Number(filters.page);
  const page = Number.isFinite(pageRaw) && pageRaw > 0 ? Math.floor(pageRaw) : 1;

  return { q, year, order, page };
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

function buildRaceBrowseUrl(filters = {}) {
  const normalized = normalizeRaceBrowseFilters(filters);
  const params = new URLSearchParams();

  if (normalized.q.trim()) {
    params.set("q", normalized.q.trim());
  }
  if (normalized.year) {
    params.set("year", normalized.year);
  }
  if (normalized.order !== "date_desc") {
    params.set("order", normalized.order);
  }
  if (normalized.page > 1) {
    params.set("page", String(normalized.page));
  }

  const query = params.toString();
  return query ? `/hlaup?${query}` : "/hlaup";
}

function parseRoute(pathname, search) {
  const params = new URLSearchParams(search);
  if (pathname === "/hlaup" || pathname === "/hlaup/") {
    return {
      page: "races",
      browse: normalizeRaceBrowseFilters({
        q: params.get("q") || "",
        year: params.get("year") || "",
        order: params.get("order") || "date_desc",
        page: params.get("page") || 1
      })
    };
  }
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
      toRaces: (browseFilters = {}, historyMode = "push") => {
        const currentRoute = parseRoute(window.location.pathname, window.location.search);
        const mergedFilters =
          currentRoute.page === "races"
            ? normalizeRaceBrowseFilters({ ...currentRoute.browse, ...browseFilters })
            : normalizeRaceBrowseFilters(browseFilters);
        const target = buildRaceBrowseUrl(mergedFilters);
        if (historyMode === "push") {
          window.history.pushState({}, "", target);
        } else {
          window.history.replaceState({}, "", target);
        }
        setRoute({ page: "races", browse: mergedFilters });
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
            onOpenRaceList={navigation.toRaces}
          />
        ) : route.page === "races" ? (
          <RaceListPage
            initialBrowse={route.browse}
            onPersistBrowse={navigation.toRaces}
            onOpenRace={(raceId) => navigation.toRace(raceId, null)}
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
