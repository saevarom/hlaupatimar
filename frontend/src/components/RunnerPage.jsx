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

const DISTANCE_FILTER_ORDER = {
  "5k": 0,
  "10k": 1,
  half: 2,
  marathon: 3,
  ultra: 4,
  other: 5
};

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
  if (normalized === "dnf" || normalized === "did not finish" || normalized === "didnotfinish") {
    return "Hætti";
  }
  if (normalized === "dns" || normalized === "did not start" || normalized === "didnotstart") {
    return "Mætti ekki";
  }
  if (
    normalized === "dq" ||
    normalized === "dsq" ||
    normalized === "disqualified"
  ) {
    return "Ógilt";
  }
  if (normalized === "needsconfirmation" || normalized === "needs confirmation") {
    return "Óstaðfest";
  }
  return status || "-";
}

function birtaTimaEfLokid(value, status) {
  const normalized = String(status ?? "").trim().toLowerCase();
  if (normalized && normalized !== "finished" && normalized !== "lokid") {
    return "-";
  }
  return formatDuration(value);
}

function birtaMillitimaLabel(split) {
  const name = String(split?.name || "").trim() || "Millitími";
  const distance = Number(split?.distance_km);
  if (Number.isFinite(distance) && distance > 0) {
    return `${name} (${distance} km)`;
  }
  return name;
}

function SplitsCell({ splits }) {
  const items = Array.isArray(splits) ? splits : [];
  if (!items.length) {
    return "-";
  }

  return (
    <details className="splits-details">
      <summary>{items.length} millitímar</summary>
      <ul>
        {items.map((split, index) => (
          <li key={`${split.name || "split"}-${split.distance_km || "na"}-${index}`}>
            <span>{birtaMillitimaLabel(split)}</span>
            <strong>{formatDuration(split.time)}</strong>
          </li>
        ))}
      </ul>
    </details>
  );
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
  const [ultraOnly, setUltraOnly] = useState(false);

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
    const visibleTrends = ultraOnly
      ? trends.filter((trend) => trend.category.key === "ultra")
      : trends;
    const countsBySurface = {};
    visibleTrends.forEach((trend) => {
      countsBySurface[trend.surface.key] =
        (countsBySurface[trend.surface.key] || 0) + trend.points.length;
    });

    return getSurfaceCategories()
      .filter((surface) => countsBySurface[surface.key] > 0)
      .map((surface) => ({
        ...surface,
        raceCount: countsBySurface[surface.key]
      }));
  }, [trends, ultraOnly]);

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
    return trends
      .filter((trend) => trend.surface.key === selectedSurface)
      .filter((trend) => (ultraOnly ? trend.category.key === "ultra" : true))
      .sort((a, b) => {
        const aOrder = DISTANCE_FILTER_ORDER[a.category.key] ?? Number.MAX_SAFE_INTEGER;
        const bOrder = DISTANCE_FILTER_ORDER[b.category.key] ?? Number.MAX_SAFE_INTEGER;
        if (aOrder !== bOrder) {
          return aOrder - bOrder;
        }
        return a.category.label.localeCompare(b.category.label, "is");
      });
  }, [trends, selectedSurface, ultraOnly]);

  useEffect(() => {
    if (!filteredTrends.length) {
      setSelectedCategory(null);
      return;
    }
    setSelectedCategory((current) => {
      const exists = filteredTrends.some((trend) => trend.category.key === current);
      if (exists) {
        return current;
      }

      const trendWithMostResults = filteredTrends.reduce((best, trend) =>
        trend.points.length > best.points.length ? trend : best
      );
      return trendWithMostResults.category.key;
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
    () => {
      const history = [...(runner?.race_history ?? [])];
      const filteredHistory = ultraOnly
        ? history.filter((race) => Number(race.distance_km) > 43.5)
        : history;
      return filteredHistory.sort(
        (a, b) => new Date(b.race_date).getTime() - new Date(a.race_date).getTime()
      );
    },
    [runner, ultraOnly]
  );

  const splitsByRaceKey = useMemo(() => {
    const map = new Map();
    (runner?.race_history ?? []).forEach((race) => {
      const fallbackKey = `${race.race_date || ""}|${race.race_name || ""}`;
      if (race.race_id !== null && race.race_id !== undefined) {
        map.set(`id:${race.race_id}`, race.splits ?? []);
      }
      if (!map.has(`fallback:${fallbackKey}`)) {
        map.set(`fallback:${fallbackKey}`, race.splits ?? []);
      }
    });
    return map;
  }, [runner]);

  const getSplitsForPoint = (point) => {
    if (point?.raceId !== null && point?.raceId !== undefined) {
      return splitsByRaceKey.get(`id:${point.raceId}`) ?? [];
    }
    return splitsByRaceKey.get(`fallback:${point?.date || ""}|${point?.raceName || ""}`) ?? [];
  };

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

      <div className="tabs enter-up">
        <button
          className={ultraOnly ? "tab" : "tab active"}
          onClick={() => setUltraOnly(false)}
          type="button"
        >
          <span>Öll hlaup</span>
        </button>
        <button
          className={ultraOnly ? "tab active" : "tab"}
          onClick={() => setUltraOnly(true)}
          type="button"
        >
          <span>Aðeins ofurhlaup</span>
        </button>
      </div>

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
                <th>Millitímar</th>
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
                    <td><SplitsCell splits={getSplitsForPoint(point)} /></td>
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
              <th>Millitímar</th>
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
                <td className="time-col">{birtaTimaEfLokid(race.finish_time, race.status)}</td>
                <td><SplitsCell splits={race.splits} /></td>
                <td>{birtaStodu(race.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
