import { useEffect, useMemo, useRef, useState } from "react";
import { getEventRaces, getRaceDetail, getRaceResultsTable } from "../api";
import { normalizeSurfaceType } from "../lib/trends";
import { formatDuration, formatIsoDate } from "../lib/time";

function birtaKyn(gender) {
  if (gender === "F") {
    return "Kona";
  }
  if (gender === "M") {
    return "Karl";
  }
  return "-";
}

function birtaStodu(status) {
  const normalized = String(status ?? "").trim().toLowerCase();
  if (normalized === "finished" || normalized === "lokid") {
    return "Lokið";
  }
  if (normalized === "dnf") {
    return "Hætti";
  }
  if (normalized === "dns") {
    return "Mætti ekki";
  }
  if (normalized === "dq" || normalized === "dsq") {
    return "Ógilt";
  }
  return status || "-";
}

export default function RacePage({
  raceId,
  focusedRunnerId,
  onBack,
  onOpenRace,
  onOpenRunner
}) {
  const [race, setRace] = useState(null);
  const [results, setResults] = useState([]);
  const [eventRaces, setEventRaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const resultsTableRef = useRef(null);
  const lastScrollKeyRef = useRef("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const [raceData, resultsData, eventRacesData] = await Promise.all([
          getRaceDetail(raceId),
          getRaceResultsTable(raceId),
          getEventRaces(raceId)
        ]);

        if (!cancelled) {
          setRace(raceData);
          setResults(resultsData);
          setEventRaces(eventRacesData);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || "Ekki tókst að sækja hlaup og úrslit.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [raceId]);

  const focusedMatches = useMemo(() => {
    const focused = String(focusedRunnerId || "").trim();
    if (!focused) {
      return () => false;
    }
    return (row) =>
      focused === String(row.runner_id || "") ||
      focused === String(row.runner_stable_id || "");
  }, [focusedRunnerId]);

  useEffect(() => {
    const focused = String(focusedRunnerId || "").trim();
    if (!focused || loading || !results.length) {
      return;
    }

    const scrollKey = `${raceId}:${focused}`;
    if (lastScrollKeyRef.current === scrollKey) {
      return;
    }

    const table = resultsTableRef.current;
    if (!table) {
      return;
    }

    const highlightedRow = table.querySelector("tbody tr.highlight-row");
    if (!highlightedRow) {
      return;
    }

    highlightedRow.scrollIntoView({ behavior: "smooth", block: "center" });
    lastScrollKeyRef.current = scrollKey;
  }, [focusedRunnerId, loading, raceId, results]);

  if (loading) {
    return (
      <section className="panel">
        <p className="quiet">Hleð hlaupi...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel">
        <button className="ghost back-btn" onClick={onBack}>
          Til baka
        </button>
        <p className="error">{error}</p>
      </section>
    );
  }

  if (!race) {
    return null;
  }

  const surface = normalizeSurfaceType(race.surface_type);

  return (
    <section className="panel">
      <button className="ghost back-btn" onClick={onBack}>
        Til baka
      </button>

      <div className="runner-meta">
        <h2>{race.name}</h2>
        <div className="meta-tags">
          <span>{formatIsoDate(race.date)}</span>
          <span>{race.location || "-"}</span>
          <span>{race.distance_km ? `${race.distance_km} km` : "-"}</span>
          <span>{surface.label}</span>
        </div>
      </div>

      <div className="stat-row enter-up">
        <article>
          <h3>Fjöldi úrslita</h3>
          <p>{results.length}</p>
        </article>
        <article>
          <h3>Vegalengd</h3>
          <p>{race.distance_km ? `${race.distance_km} km` : "-"}</p>
        </article>
        <article>
          <h3>Yfirborð</h3>
          <p>{surface.label}</p>
        </article>
      </div>

      {eventRaces.length ? (
        <>
          <h3 className="section-title">Önnur hlaup í sama viðburði</h3>
          <div className="results-table-wrap enter-up">
            <table className="results-table">
              <thead>
                <tr>
                  <th>Dagsetning</th>
                  <th>Hlaup</th>
                  <th>Vegalengd</th>
                </tr>
              </thead>
              <tbody>
                {eventRaces.map((eventRace) => (
                  <tr key={eventRace.id}>
                    <td>{formatIsoDate(eventRace.date)}</td>
                    <td>
                      <button
                        className="link-button"
                        type="button"
                        onClick={() => onOpenRace(eventRace.id)}
                      >
                        {eventRace.name}
                      </button>
                    </td>
                    <td>{eventRace.distance_km ? `${eventRace.distance_km} km` : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      <div className="results-table-wrap enter-up race-results-wrap" ref={resultsTableRef}>
        <table className="results-table">
          <thead>
            <tr>
              <th>Sæti</th>
              <th>Hlaupari</th>
              <th>Kyn</th>
              <th>Fæðingarár</th>
              <th>Félag</th>
              <th className="time-col">Tími</th>
              <th className="time-col">Á eftir</th>
              <th>Staða</th>
            </tr>
          </thead>
          <tbody>
            {results.map((row) => {
              const rowIsFocused = focusedMatches(row);
              const runnerKey = row.runner_stable_id || row.runner_id;
              return (
                <tr key={row.id} className={rowIsFocused ? "highlight-row" : ""}>
                  <td>{row.position}</td>
                  <td>
                    {runnerKey ? (
                      <button
                        className="link-button"
                        type="button"
                        onClick={() => onOpenRunner(runnerKey)}
                      >
                        {row.runner_name}
                      </button>
                    ) : (
                      row.runner_name
                    )}
                  </td>
                  <td>{birtaKyn(row.gender)}</td>
                  <td>{row.birth_year ?? "-"}</td>
                  <td>{row.club || "-"}</td>
                  <td className="time-col">{formatDuration(row.finish_time)}</td>
                  <td className="time-col">{formatDuration(row.time_behind)}</td>
                  <td>{birtaStodu(row.status)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
