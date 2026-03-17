import { useEffect, useMemo, useRef, useState } from "react";
import { getLatestEvents, searchRaces, searchRunners } from "../api";
import { formatDuration, formatIsoDate } from "../lib/time";

const RACE_TYPE_OPTIONS = [
  { value: "", label: "Allir flokkar" },
  { value: "5k", label: "5 km" },
  { value: "10k", label: "10 km" },
  { value: "half_marathon", label: "Hálft maraþon" },
  { value: "marathon", label: "Maraþon" },
  { value: "trail", label: "Utanvegahlaup" },
  { value: "ultra", label: "Ultra" },
  { value: "other", label: "Annað" }
];

const SURFACE_OPTIONS = [
  { value: "", label: "Öll yfirborð" },
  { value: "road", label: "Vegur" },
  { value: "trail", label: "Slóði" },
  { value: "mixed", label: "Blandað" },
  { value: "unknown", label: "Óþekkt" }
];

const RACE_ORDER_OPTIONS = [
  { value: "date_desc", label: "Nýjust fyrst" },
  { value: "date_asc", label: "Elst fyrst" },
  { value: "winning_fastest", label: "Stysti sigurtími fyrst" },
  { value: "winning_slowest", label: "Lengsti sigurtími fyrst" },
  { value: "speed_fastest", label: "Lægsti hraðastuðull fyrst" },
  { value: "speed_slowest", label: "Hæsti hraðastuðull fyrst" }
];

function birtaKyn(gender) {
  if (gender === "F") {
    return "Kona";
  }
  if (gender === "M") {
    return "Karl";
  }
  return "-";
}

function renderSpeedIndex(race) {
  if (race.speed_index === null || race.speed_index === undefined) {
    return "-";
  }

  return (
    <span
      className={`speed-index-pill ${
        race.speed_index < 100
          ? "speed-index-pill-fast"
          : race.speed_index > 100
            ? "speed-index-pill-slow"
            : "speed-index-pill-neutral"
      }`}
      title={
        race.speed_delta_percentage !== null && race.speed_delta_percentage !== undefined
          ? `${Math.abs(Number(race.speed_delta_percentage)).toFixed(1)}% ${
              Number(race.speed_delta_percentage) < 0 ? "hraðara" : "hægara"
            } en dæmigert sambærilegt hlaup`
          : "Ekki tiltækt"
      }
    >
      {Number(race.speed_index).toFixed(1)}
    </span>
  );
}

export default function SearchPage({
  initialSearch,
  onPersistSearch,
  onOpenRace,
  onSelectRunner,
  onOpenRaceList
}) {
  const [q, setQ] = useState(initialSearch?.q || "");
  const [gender, setGender] = useState(initialSearch?.gender || "");
  const [birthYear, setBirthYear] = useState(initialSearch?.birthYear || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [latestEvents, setLatestEvents] = useState([]);
  const [latestEventsLoading, setLatestEventsLoading] = useState(true);
  const [latestEventsError, setLatestEventsError] = useState("");
  const requestRef = useRef(0);
  const raceRequestRef = useRef(0);
  const syncingFromRouteRef = useRef(false);
  const [raceQuery, setRaceQuery] = useState(initialSearch?.raceQ || "");
  const [raceType, setRaceType] = useState(initialSearch?.raceType || "");
  const [raceSurface, setRaceSurface] = useState(initialSearch?.raceSurface || "");
  const [raceRequireSpeed, setRaceRequireSpeed] = useState(Boolean(initialSearch?.raceRequireSpeed));
  const [raceOrder, setRaceOrder] = useState(initialSearch?.raceOrder || "date_desc");
  const [raceLoading, setRaceLoading] = useState(false);
  const [raceError, setRaceError] = useState("");
  const [raceResults, setRaceResults] = useState([]);
  const [hasRaceSearched, setHasRaceSearched] = useState(false);

  const canSearch = useMemo(
    () => q.trim().length > 0 || gender || birthYear,
    [q, gender, birthYear]
  );
  const canSearchRaces = useMemo(
    () =>
      raceQuery.trim().length > 0 ||
      raceType.length > 0 ||
      raceSurface.length > 0 ||
      raceRequireSpeed,
    [raceQuery, raceType, raceSurface, raceRequireSpeed]
  );

  async function runSearchWithFilters(
    filters,
    { historyMode = "replace", persistHistory = true } = {}
  ) {
    const searchFilters = {
      q: (filters?.q || "").trim(),
      gender: filters?.gender || "",
      birthYear: filters?.birthYear || ""
    };
    const hasCriteria =
      searchFilters.q.length > 0 || searchFilters.gender || searchFilters.birthYear;

    if (!hasCriteria) {
      return;
    }

    if (persistHistory) {
      onPersistSearch?.(
        {
          ...searchFilters,
          raceQ: raceQuery.trim(),
          raceType,
          raceSurface,
          raceRequireSpeed,
          raceOrder
        },
        historyMode
      );
    }

    const requestId = requestRef.current + 1;
    requestRef.current = requestId;

    setLoading(true);
    setError("");
    setHasSearched(true);

    try {
      const runners = await searchRunners({
        q: searchFilters.q,
        gender: searchFilters.gender,
        birth_year: searchFilters.birthYear ? Number(searchFilters.birthYear) : undefined,
        limit: 50
      });
      if (requestRef.current === requestId) {
        setResults(runners);
      }
    } catch (fetchError) {
      if (requestRef.current === requestId) {
        setError(fetchError.message || "Ekki tókst að leita að hlaupurum.");
        setResults([]);
      }
    } finally {
      if (requestRef.current === requestId) {
        setLoading(false);
      }
    }
  }

  async function runSearch(historyMode = "replace") {
    await runSearchWithFilters(
      { q, gender, birthYear },
      { historyMode, persistHistory: true }
    );
  }

  async function onSubmit(event) {
    event.preventDefault();
    await runSearch("push");
  }

  useEffect(() => {
    if (syncingFromRouteRef.current) {
      return undefined;
    }

    if (q.trim().length < 3) {
      return undefined;
    }

    const timeoutId = setTimeout(() => {
      void runSearch("replace");
    }, 350);

    return () => clearTimeout(timeoutId);
  }, [q, gender, birthYear]);

  useEffect(() => {
    const nextQ = initialSearch?.q || "";
    const nextGender = initialSearch?.gender || "";
    const nextBirthYear = initialSearch?.birthYear || "";
    const nextRaceQ = initialSearch?.raceQ || "";
    const nextRaceType = initialSearch?.raceType || "";
    const nextRaceSurface = initialSearch?.raceSurface || "";
    const nextRaceRequireSpeed = Boolean(initialSearch?.raceRequireSpeed);
    const nextRaceOrder = initialSearch?.raceOrder || "date_desc";

    syncingFromRouteRef.current = true;
    setQ(nextQ);
    setGender(nextGender);
    setBirthYear(nextBirthYear);
    setRaceQuery(nextRaceQ);
    setRaceType(nextRaceType);
    setRaceSurface(nextRaceSurface);
    setRaceRequireSpeed(nextRaceRequireSpeed);
    setRaceOrder(nextRaceOrder);
    setError("");
    setResults([]);
    setHasSearched(false);
    setRaceError("");
    setRaceResults([]);
    setHasRaceSearched(false);

    const hasRunnerCriteria =
      nextQ.trim().length > 0 || nextGender.length > 0 || nextBirthYear.length > 0;
    const hasRaceCriteria =
      nextRaceQ.trim().length > 0 || nextRaceType || nextRaceSurface || nextRaceRequireSpeed;

    if (!hasRunnerCriteria && !hasRaceCriteria) {
      syncingFromRouteRef.current = false;
      return;
    }

    const tasks = [];
    if (hasRunnerCriteria) {
      tasks.push(
        runSearchWithFilters(
          { q: nextQ, gender: nextGender, birthYear: nextBirthYear },
          { historyMode: "replace", persistHistory: false }
        )
      );
    }
    if (hasRaceCriteria) {
      tasks.push(
        runRaceSearchWithQuery(nextRaceQ, {
          raceType: nextRaceType,
          raceSurface: nextRaceSurface,
          raceRequireSpeed: nextRaceRequireSpeed,
          raceOrder: nextRaceOrder,
          historyMode: "replace",
          persistHistory: false
        })
      );
    }

    void Promise.allSettled(tasks).finally(() => {
      syncingFromRouteRef.current = false;
    });
  }, [
    initialSearch?.q,
    initialSearch?.gender,
    initialSearch?.birthYear,
    initialSearch?.raceQ,
    initialSearch?.raceType,
    initialSearch?.raceSurface,
    initialSearch?.raceRequireSpeed,
    initialSearch?.raceOrder
  ]);

  async function runRaceSearchWithQuery(
    queryValue,
    {
      raceType: nextRaceType = raceType,
      raceSurface: nextRaceSurface = raceSurface,
      raceRequireSpeed: nextRaceRequireSpeed = raceRequireSpeed,
      raceOrder: nextRaceOrder = raceOrder,
      historyMode = "replace",
      persistHistory = true
    } = {}
  ) {
    const query = (queryValue || "").trim();
    if (!query && !nextRaceType && !nextRaceSurface && !nextRaceRequireSpeed) {
      return;
    }

    if (persistHistory) {
      onPersistSearch?.(
        {
          q: q.trim(),
          gender,
          birthYear,
          raceQ: query,
          raceType: nextRaceType,
          raceSurface: nextRaceSurface,
          raceRequireSpeed: nextRaceRequireSpeed,
          raceOrder: nextRaceOrder
        },
        historyMode
      );
    }

    const requestId = raceRequestRef.current + 1;
    raceRequestRef.current = requestId;

    setRaceLoading(true);
    setRaceError("");
    setHasRaceSearched(true);

    try {
      const races = await searchRaces({
        q: query || undefined,
        race_type: nextRaceType || undefined,
        surface_type: nextRaceSurface || undefined,
        require_speed_index: nextRaceRequireSpeed || undefined,
        order_by: nextRaceOrder,
        limit: 30
      });
      if (raceRequestRef.current === requestId) {
        setRaceResults(races);
      }
    } catch (loadError) {
      if (raceRequestRef.current === requestId) {
        setRaceError(loadError.message || "Ekki tókst að leita að hlaupi.");
        setRaceResults([]);
      }
    } finally {
      if (raceRequestRef.current === requestId) {
        setRaceLoading(false);
      }
    }
  }

  async function runRaceSearch(historyMode = "replace") {
    await runRaceSearchWithQuery(raceQuery, { historyMode, persistHistory: true });
  }

  async function onRaceSubmit(event) {
    event.preventDefault();
    await runRaceSearch("push");
  }

  useEffect(() => {
    if (syncingFromRouteRef.current) {
      return undefined;
    }

    const hasCriteria = raceQuery.trim().length > 0 || raceType || raceSurface || raceRequireSpeed;
    if (!hasCriteria || (raceQuery.trim().length > 0 && raceQuery.trim().length < 3)) {
      return undefined;
    }

    const timeoutId = setTimeout(() => {
      void runRaceSearch("replace");
    }, 350);

    return () => clearTimeout(timeoutId);
  }, [raceQuery, raceType, raceSurface, raceRequireSpeed, raceOrder]);

  useEffect(() => {
    let cancelled = false;

    async function loadLatestEvents() {
      setLatestEventsLoading(true);
      setLatestEventsError("");
      try {
        const events = await getLatestEvents({ limit: 24 });
        if (!cancelled) {
          setLatestEvents(events);
        }
      } catch (loadError) {
        if (!cancelled) {
          setLatestEventsError(loadError.message || "Ekki tókst að sækja nýjustu viðburði.");
          setLatestEvents([]);
        }
      } finally {
        if (!cancelled) {
          setLatestEventsLoading(false);
        }
      }
    }

    loadLatestEvents();
    return () => {
      cancelled = true;
    };
  }, []);

  const upcomingEvents = useMemo(
    () =>
      [...latestEvents]
        .filter((event) => event.is_upcoming)
        .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()),
    [latestEvents]
  );

  const recentEvents = useMemo(
    () =>
      [...latestEvents]
        .filter((event) => !event.is_upcoming)
        .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()),
    [latestEvents]
  );

  return (
    <section className="panel enter-up">
      <div className="panel-header">
        <p className="kicker">Leit að hlaupurum</p>
        <h2>Finndu hlaupara og skoðaðu úrslit yfir tíma</h2>
      </div>

      <form className="search-form" onSubmit={onSubmit}>
        <label>
          Nafn
          <input
            type="search"
            placeholder="Prófaðu: Anna, Jón, Guðrún..."
            value={q}
            onChange={(event) => setQ(event.target.value)}
          />
        </label>

        <label>
          Kyn
          <select value={gender} onChange={(event) => setGender(event.target.value)}>
            <option value="">Öll</option>
            <option value="F">Kona</option>
            <option value="M">Karl</option>
          </select>
        </label>

        <label>
          Fæðingarár
          <input
            type="number"
            min="1900"
            max="2026"
            placeholder="1988"
            value={birthYear}
            onChange={(event) => setBirthYear(event.target.value)}
          />
        </label>

        <button type="submit" disabled={!canSearch || loading}>
          {loading ? "Leita..." : "Leita"}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}

      {!hasSearched ? (
        <p className="quiet">Leitaðu eftir nafni, kyni eða fæðingarári.</p>
      ) : (
        <div className="results-table-wrap">
          <table className="results-table">
            <thead>
              <tr>
                <th>Nafn</th>
                <th title="Fæðingarár">F.ár</th>
                <th>Kyn</th>
                <th>Hlaup</th>
              </tr>
            </thead>
            <tbody>
              {results.map((runner) => {
                const runnerKey = runner.stable_id || runner.id;
                return (
                  <tr key={runnerKey}>
                    <td>
                      <button
                        className="link-button"
                        onClick={() => onSelectRunner(runnerKey)}
                        type="button"
                      >
                        {runner.name}
                      </button>
                    </td>
                    <td>{runner.birth_year ?? "-"}</td>
                    <td>{birtaKyn(runner.gender)}</td>
                    <td>{runner.total_races}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {hasSearched && !loading && results.length === 0 ? (
            <p className="quiet">Enginn hlaupari fannst fyrir þessa leit.</p>
          ) : null}
        </div>
      )}

      <h3 className="section-title">Næstu viðburðir</h3>
      {latestEventsLoading ? <p className="quiet">Sæki nýjustu viðburði...</p> : null}
      {latestEventsError ? <p className="error">{latestEventsError}</p> : null}
      {!latestEventsLoading && !latestEventsError ? (
        <div className="results-table-wrap enter-up latest-races-wrap">
          <table className="results-table">
            <thead>
              <tr>
                <th>Dagsetning</th>
                <th className="time-col">Sigurtími</th>
                <th>Viðburður</th>
                <th>Fjöldi hlaupa</th>
                <th>Staða</th>
              </tr>
            </thead>
            <tbody>
              {upcomingEvents.map((event) => (
                <tr key={event.id}>
                  <td>{formatIsoDate(event.date)}</td>
                  <td className="time-col">{formatDuration(event.winning_time)}</td>
                  <td>{event.name}</td>
                  <td>{event.race_count ?? 0}</td>
                  <td>{event.has_results ? "Úrslit til" : "Úrslit ekki komin"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!upcomingEvents.length ? (
            <p className="quiet">Engir væntanlegir viðburðir fundust.</p>
          ) : null}
        </div>
      ) : null}

      <div className="section-title-row">
        <h3 className="section-title">Leita að hlaupi</h3>
        <button
          className="link-button section-link-button"
          onClick={() =>
            onOpenRaceList?.(
              {
                q: raceQuery.trim(),
                raceType,
                surfaceType: raceSurface,
                requireSpeedIndex: raceRequireSpeed,
                order: raceOrder,
                page: 1
              },
              "push"
            )
          }
          type="button"
        >
          Sjá öll hlaup
        </button>
      </div>
      <form className="race-search-form" onSubmit={onRaceSubmit}>
        <div className="race-search-form-primary">
          <label>
            Hlaup
            <input
              type="search"
              placeholder="Prófaðu: Reykjavíkurmaraþon, vetrarhlaup..."
              value={raceQuery}
              onChange={(event) => setRaceQuery(event.target.value)}
            />
          </label>
          <button type="submit" disabled={!canSearchRaces || raceLoading}>
            {raceLoading ? "Leita..." : "Leita"}
          </button>
        </div>
        <div className="race-search-form-secondary">
          <label>
            Flokkur
            <select value={raceType} onChange={(event) => setRaceType(event.target.value)}>
              {RACE_TYPE_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Yfirborð
            <select value={raceSurface} onChange={(event) => setRaceSurface(event.target.value)}>
              {SURFACE_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Röðun
            <select value={raceOrder} onChange={(event) => setRaceOrder(event.target.value)}>
              {RACE_ORDER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={raceRequireSpeed}
              onChange={(event) => setRaceRequireSpeed(event.target.checked)}
            />
            <span>Sleppa hlaupum án hraðastuðuls</span>
          </label>
        </div>
      </form>
      {raceError ? <p className="error">{raceError}</p> : null}
      {hasRaceSearched ? (
        <div className="results-table-wrap enter-up latest-races-wrap">
          <table className="results-table">
            <thead>
              <tr>
                <th>Dagsetning</th>
                <th className="time-col">Sigurtími</th>
                <th className="time-col">Hraðastuðull</th>
                <th>Hlaup</th>
                <th>Vegalengd</th>
                <th>Staður</th>
              </tr>
            </thead>
            <tbody>
              {raceResults.map((race) => (
                <tr key={race.id}>
                  <td>{formatIsoDate(race.date)}</td>
                  <td className="time-col">{formatDuration(race.winning_time)}</td>
                  <td className="time-col">{renderSpeedIndex(race)}</td>
                  <td>
                    <button className="link-button" onClick={() => onOpenRace(race.id)} type="button">
                      {race.name}
                    </button>
                  </td>
                  <td>{race.distance_km ? `${race.distance_km} km` : "-"}</td>
                  <td>{race.location || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!raceLoading && raceResults.length === 0 ? (
            <p className="quiet">Engin hlaup fundust fyrir þessa leit.</p>
          ) : null}
        </div>
      ) : null}

      {!latestEventsLoading && !latestEventsError ? (
        <>
          <h3 className="section-title">Nýjustu úrslit</h3>
          <div className="results-table-wrap enter-up latest-races-wrap">
            <table className="results-table">
              <thead>
                <tr>
                  <th>Dagsetning</th>
                  <th className="time-col">Sigurtími</th>
                  <th>Viðburður</th>
                  <th>Fjöldi hlaupa</th>
                  <th>Uppruni</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.map((event) => (
                  <tr key={event.id}>
                    <td>{formatIsoDate(event.date)}</td>
                    <td className="time-col">{formatDuration(event.winning_time)}</td>
                    <td>
                      {event.has_results && event.preview_race_id ? (
                        <button
                          className="link-button"
                          onClick={() => onOpenRace(event.preview_race_id)}
                          type="button"
                        >
                          {event.name}
                        </button>
                      ) : (
                        event.name
                      )}
                    </td>
                    <td>{event.race_count ?? 0}</td>
                    <td>{event.source || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!recentEvents.length ? (
              <p className="quiet">Engin nýleg úrslit fundust.</p>
            ) : null}
          </div>
        </>
      ) : null}

      {!latestEventsLoading &&
      !latestEventsError &&
      !upcomingEvents.length &&
      !recentEvents.length ? (
        <p className="quiet">Engir viðburðir fundust.</p>
      ) : null}
    </section>
  );
}
