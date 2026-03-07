import { useEffect, useMemo, useState } from "react";
import { getRunnerDetail } from "../api";
import TrendChart from "./TrendChart";
import {
  buildTrends,
  getPersonalBest,
  getSurfaceCategories,
  normalizeSurfaceType
} from "../lib/trends";
import { formatDuration, formatIsoDate, formatSecondsToDuration } from "../lib/time";

function birtaKyn(gender) {
  if (gender === "F") {
    return "Kona";
  }
  if (gender === "M") {
    return "Karl";
  }
  return "Óþekkt";
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

function RunnerMeta({ runner }) {
  return (
    <div className="runner-meta">
      <h2>{runner.name}</h2>
      <div className="meta-tags">
        <span>{birtaKyn(runner.gender)}</span>
        <span>{runner.birth_year ?? "Óþekkt fæðingarár"}</span>
        <span>{runner.nationality}</span>
      </div>
    </div>
  );
}

export default function RunnerPage({ runnerId, onBack, onOpenRace }) {
  const [runner, setRunner] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedSurface, setSelectedSurface] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const response = await getRunnerDetail(runnerId);
        if (!cancelled) {
          setRunner(response);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || "Ekki tókst að sækja upplýsingar um hlaupara.");
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
  }, [runnerId]);

  const trends = useMemo(() => {
    if (!runner?.race_history) {
      return [];
    }
    return buildTrends(runner.race_history);
  }, [runner]);

  const surfaceOptions = useMemo(() => {
    const countsBySurface = {};
    trends.forEach((trend) => {
      countsBySurface[trend.surface.key] =
        (countsBySurface[trend.surface.key] || 0) + trend.points.length;
    });

    return getSurfaceCategories()
      .filter((surface) => countsBySurface[surface.key] > 0)
      .map((surface) => ({
        ...surface,
        raceCount: countsBySurface[surface.key]
      }));
  }, [trends]);

  useEffect(() => {
    if (!surfaceOptions.length) {
      setSelectedSurface(null);
      return;
    }
    setSelectedSurface((current) => {
      const exists = surfaceOptions.some((surface) => surface.key === current);
      if (exists) {
        return current;
      }
      const road = surfaceOptions.find((surface) => surface.key === "road");
      return road ? road.key : surfaceOptions[0].key;
    });
  }, [surfaceOptions]);

  const filteredTrends = useMemo(() => {
    if (!selectedSurface) {
      return [];
    }
    return trends.filter((trend) => trend.surface.key === selectedSurface);
  }, [trends, selectedSurface]);

  useEffect(() => {
    if (!filteredTrends.length) {
      setSelectedCategory(null);
      return;
    }
    setSelectedCategory((current) => {
      const exists = filteredTrends.some((trend) => trend.category.key === current);
      return exists ? current : filteredTrends[0].category.key;
    });
  }, [filteredTrends]);

  const selectedTrend = useMemo(
    () => filteredTrends.find((trend) => trend.category.key === selectedCategory) ?? null,
    [filteredTrends, selectedCategory]
  );

  const personalBest = useMemo(
    () => getPersonalBest(selectedTrend?.points ?? []),
    [selectedTrend]
  );

  const allResults = useMemo(
    () =>
      [...(runner?.race_history ?? [])].sort(
        (a, b) => new Date(b.race_date).getTime() - new Date(a.race_date).getTime()
      ),
    [runner]
  );

  if (loading) {
    return (
      <section className="panel">
        <p className="quiet">Hleð hlaupara...</p>
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

  if (!runner) {
    return null;
  }

  return (
    <section className="panel">
      <button className="ghost back-btn" onClick={onBack}>
        Til baka í leit
      </button>

      <RunnerMeta runner={runner} />

      <div className="stat-row enter-up">
        <article>
          <h3>Fjöldi hlaupa</h3>
          <p>{runner.total_races}</p>
        </article>
        <article>
          <h3>Vegalengdir</h3>
          <p>{filteredTrends.length}</p>
        </article>
        <article>
          <h3>Besti tími</h3>
          <p>{personalBest ? formatSecondsToDuration(personalBest.finishSeconds) : "-"}</p>
          {personalBest ? (
            <small>
              {selectedTrend.category.label} þann {formatIsoDate(personalBest.date)}
            </small>
          ) : null}
        </article>
      </div>

      <div className="tabs enter-up">
        {surfaceOptions.map((surface) => (
          <button
            key={surface.key}
            className={surface.key === selectedSurface ? "tab active" : "tab"}
            onClick={() => setSelectedSurface(surface.key)}
            type="button"
          >
            <span>{surface.label}</span>
            <strong>{surface.raceCount}</strong>
          </button>
        ))}
      </div>

      <div className="tabs enter-up">
        {filteredTrends.map((trend) => (
          <button
            key={`${trend.surface.key}-${trend.category.key}`}
            className={trend.category.key === selectedCategory ? "tab active" : "tab"}
            onClick={() => setSelectedCategory(trend.category.key)}
            type="button"
          >
            <span>{trend.category.label}</span>
            <strong>{trend.points.length}</strong>
          </button>
        ))}
      </div>

      {selectedTrend ? (
        <TrendChart
          points={selectedTrend.points}
          title={`${selectedTrend.surface.label} · ${selectedTrend.category.label} (${selectedTrend.points.length} hlaup)`}
        />
      ) : (
        <p className="quiet enter-up">
          Ekki tókst að búa til þróunargraf úr tiltækum vegalengd- og tímagögnum.
        </p>
      )}

      {selectedTrend ? (
        <div className="results-table-wrap enter-up">
          <table className="results-table">
            <thead>
              <tr>
                <th>Dagsetning</th>
                <th>Hlaup</th>
                <th>Yfirborð</th>
                <th>Vegalengd</th>
                <th className="time-col">Tími</th>
                <th>Staða</th>
              </tr>
            </thead>
            <tbody>
              {[...selectedTrend.points]
                .sort((a, b) => b.dateValue - a.dateValue)
                .slice(0, 30)
                .map((point, index) => (
                  <tr key={`${point.dateValue}-${point.raceName}-${index}`}>
                    <td>{formatIsoDate(point.date)}</td>
                    <td>
                      {point.raceId ? (
                        <button
                          className="link-button"
                          type="button"
                          onClick={() => onOpenRace(point.raceId)}
                        >
                          {point.raceName}
                        </button>
                      ) : (
                        point.raceName
                      )}
                    </td>
                    <td>{selectedTrend.surface.label}</td>
                    <td>{point.distanceKm ? `${point.distanceKm} km` : "-"}</td>
                    <td className="time-col">{formatSecondsToDuration(point.finishSeconds)}</td>
                    <td>{birtaStodu(point.status)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <h3 className="section-title">Öll úrslit ({allResults.length})</h3>
      <div className="results-table-wrap enter-up">
        <table className="results-table">
          <thead>
            <tr>
              <th>Dagsetning</th>
              <th>Hlaup</th>
              <th>Yfirborð</th>
              <th>Vegalengd</th>
              <th className="time-col">Tími</th>
              <th>Staða</th>
            </tr>
          </thead>
          <tbody>
            {allResults.map((race, index) => (
              <tr key={`${race.race_date}-${race.race_name}-${index}`}>
                <td>{formatIsoDate(race.race_date)}</td>
                <td>
                  {race.race_id ? (
                    <button
                      className="link-button"
                      type="button"
                      onClick={() => onOpenRace(race.race_id)}
                    >
                      {race.race_name}
                    </button>
                  ) : (
                    race.race_name
                  )}
                </td>
                <td>{normalizeSurfaceType(race.surface_type).label}</td>
                <td>{race.distance_km ? `${race.distance_km} km` : "-"}</td>
                <td className="time-col">{formatDuration(race.finish_time)}</td>
                <td>{birtaStodu(race.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
