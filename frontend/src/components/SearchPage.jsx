import { useEffect, useMemo, useRef, useState } from "react";
import { getLatestEvents, searchRaces, searchRunners } from "../api";
import { formatIsoDate } from "../lib/time";

function birtaKyn(gender) {
  if (gender === "F") {
    return "Kona";
  }
  if (gender === "M") {
    return "Karl";
  }
  return "-";
}

export default function SearchPage({
  initialSearch,
  onPersistSearch,
  onOpenRace,
  onSelectRunner
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
  const [raceLoading, setRaceLoading] = useState(false);
  const [raceError, setRaceError] = useState("");
  const [raceResults, setRaceResults] = useState([]);
  const [hasRaceSearched, setHasRaceSearched] = useState(false);

  const canSearch = useMemo(
    () => q.trim().length > 0 || gender || birthYear,
    [q, gender, birthYear]
  );
  const canSearchRaces = useMemo(() => raceQuery.trim().length > 0, [raceQuery]);

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
          raceQ: raceQuery.trim()
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

    syncingFromRouteRef.current = true;
    setQ(nextQ);
    setGender(nextGender);
    setBirthYear(nextBirthYear);
    setRaceQuery(nextRaceQ);
    setError("");
    setResults([]);
    setHasSearched(false);
    setRaceError("");
    setRaceResults([]);
    setHasRaceSearched(false);

    const hasRunnerCriteria =
      nextQ.trim().length > 0 || nextGender.length > 0 || nextBirthYear.length > 0;
    const hasRaceCriteria = nextRaceQ.trim().length > 0;

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
          historyMode: "replace",
          persistHistory: false
        })
      );
    }

    void Promise.allSettled(tasks).finally(() => {
      syncingFromRouteRef.current = false;
    });
  }, [initialSearch?.q, initialSearch?.gender, initialSearch?.birthYear, initialSearch?.raceQ]);

  async function runRaceSearchWithQuery(
    queryValue,
    { historyMode = "replace", persistHistory = true } = {}
  ) {
    const query = (queryValue || "").trim();
    if (!query) {
      return;
    }

    if (persistHistory) {
      onPersistSearch?.(
        {
          q: q.trim(),
          gender,
          birthYear,
          raceQ: query
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
      const races = await searchRaces({ q: query, limit: 30 });
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

    if (raceQuery.trim().length < 3) {
      return undefined;
    }

    const timeoutId = setTimeout(() => {
      void runRaceSearch("replace");
    }, 350);

    return () => clearTimeout(timeoutId);
  }, [raceQuery]);

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
                <th>Viðburður</th>
                <th>Fjöldi hlaupa</th>
                <th>Staða</th>
              </tr>
            </thead>
            <tbody>
              {upcomingEvents.map((event) => (
                <tr key={event.id}>
                  <td>{formatIsoDate(event.date)}</td>
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

      <h3 className="section-title">Leita að hlaupi</h3>
      <form className="race-search-form" onSubmit={onRaceSubmit}>
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
      </form>
      {raceError ? <p className="error">{raceError}</p> : null}
      {hasRaceSearched ? (
        <div className="results-table-wrap enter-up latest-races-wrap">
          <table className="results-table">
            <thead>
              <tr>
                <th>Dagsetning</th>
                <th>Hlaup</th>
                <th>Vegalengd</th>
                <th>Staður</th>
              </tr>
            </thead>
            <tbody>
              {raceResults.map((race) => (
                <tr key={race.id}>
                  <td>{formatIsoDate(race.date)}</td>
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
                  <th>Viðburður</th>
                  <th>Fjöldi hlaupa</th>
                  <th>Uppruni</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.map((event) => (
                  <tr key={event.id}>
                    <td>{formatIsoDate(event.date)}</td>
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
