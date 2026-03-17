import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  createRaceCorrectionSuggestion,
  getEventRaces,
  getRaceDetail,
  getRaceResultsTable,
  getRaceStats
} from "../api";
import { normalizeSurfaceType } from "../lib/trends";
import { formatDuration, formatIsoDate, formatSecondsToDuration, parseDurationToSeconds } from "../lib/time";

const DISCIPLINE_OPTIONS = [
  { value: "running", label: "Hlaup" },
  { value: "biking", label: "Hjólreiðar" },
  { value: "skiing", label: "Skíði" },
  { value: "unknown", label: "Óþekkt" }
];

const RACE_TYPE_OPTIONS = [
  { value: "5k", label: "5 km" },
  { value: "10k", label: "10 km" },
  { value: "half_marathon", label: "Hálft maraþon" },
  { value: "marathon", label: "Maraþon" },
  { value: "trail", label: "Utanvegahlaup" },
  { value: "ultra", label: "Ultra" },
  { value: "other", label: "Annað" }
];

const SURFACE_OPTIONS = [
  { value: "road", label: "Götuhlaup" },
  { value: "trail", label: "Utanvegahlaup" },
  { value: "unknown", label: "Óþekkt" }
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

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(1)}%`;
}

function formatComparisonDelta(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Ekki tiltækt";
  }
  const absolute = Math.abs(Number(value));
  if (absolute < 0.1) {
    return "Mjög nálægt meðaltali";
  }
  if (value < 0) {
    return `${absolute.toFixed(1)}% hraðara`;
  }
  return `${absolute.toFixed(1)}% hægara`;
}

function getComparisonTone(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "neutral";
  }
  if (Math.abs(Number(value)) < 0.1) {
    return "neutral";
  }
  return value < 0 ? "faster" : "slower";
}

function formatComparisonRank(metric, cohortRaceCount) {
  if (!metric?.rank || !cohortRaceCount) {
    return "-";
  }
  return `${metric.rank}. af ${cohortRaceCount}`;
}

function formatDeltaDuration(value, baseline) {
  const valueSeconds = parseDurationToSeconds(value);
  const baselineSeconds = parseDurationToSeconds(baseline);
  if (valueSeconds === null || baselineSeconds === null) {
    return "-";
  }
  const deltaSeconds = Math.round(valueSeconds - baselineSeconds);
  if (deltaSeconds === 0) {
    return "0:00";
  }
  const sign = deltaSeconds > 0 ? "+" : "-";
  return `${sign}${formatSecondsToDuration(Math.abs(deltaSeconds))}`;
}

function barWidth(value, maxValue) {
  if (!maxValue || maxValue <= 0) {
    return "0%";
  }
  const ratio = Math.max(0, Math.min(1, Number(value) / Number(maxValue)));
  return `${(ratio * 100).toFixed(1)}%`;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function getPercentileExplanation(label) {
  const match = String(label || "").match(/^P(\d{1,2})$/i);
  if (!match) {
    return "Percentíll sem sýnir hlutfallslega stöðu innan hlaupsins.";
  }
  const percentile = Number(match[1]);
  const fasterOrEqual = Math.max(0, Math.min(100, percentile));
  const slower = 100 - fasterOrEqual;
  return `${label}: ${fasterOrEqual}% hlaupara voru jafnhraðir eða hraðari, ${slower}% voru hægari.`;
}

function formatDisciplineLabel(value) {
  return DISCIPLINE_OPTIONS.find((option) => option.value === value)?.label ?? "Óþekkt";
}

function formatRaceTypeLabel(value) {
  return RACE_TYPE_OPTIONS.find((option) => option.value === value)?.label ?? "Annað";
}

function InfoTip({ text }) {
  const tooltipId = useId();

  return (
    <span className="info-tip" aria-label={text} aria-describedby={tooltipId} tabIndex={0}>
      <svg
        className="info-tip-icon"
        viewBox="0 0 20 20"
        width="14"
        height="14"
        aria-hidden="true"
        focusable="false"
      >
        <circle cx="10" cy="10" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <line x1="10" y1="8.4" x2="10" y2="13.3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="10" cy="6.2" r="1" fill="currentColor" />
      </svg>
      <span className="info-tip-popup" id={tooltipId} role="tooltip">
        {text}
      </span>
    </span>
  );
}

export default function RacePage({
  raceId,
  focusedRunnerId,
  onBack,
  onOpenRace,
  onOpenRunner
}) {
  const [race, setRace] = useState(null);
  const [stats, setStats] = useState(null);
  const [results, setResults] = useState([]);
  const [eventRaces, setEventRaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [resultsLoading, setResultsLoading] = useState(true);
  const [error, setError] = useState("");
  const [statsError, setStatsError] = useState("");
  const [resultsError, setResultsError] = useState("");
  const [selectedGender, setSelectedGender] = useState("");
  const [suggestionForm, setSuggestionForm] = useState({
    suggested_surface_type: "",
    suggested_distance_km: "",
    suggested_discipline: "",
    suggested_race_type: "",
    comment: "",
    submitter_name: "",
    submitter_email: ""
  });
  const [suggestionSubmitting, setSuggestionSubmitting] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [suggestionSuccess, setSuggestionSuccess] = useState("");
  const [suggestionModalOpen, setSuggestionModalOpen] = useState(false);
  const resultsTableRef = useRef(null);
  const lastScrollKeyRef = useRef("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const [raceData, eventRacesData] = await Promise.all([
          getRaceDetail(raceId),
          getEventRaces(raceId)
        ]);

        if (!cancelled) {
          setRace(raceData);
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

  useEffect(() => {
    let cancelled = false;

    async function loadStats() {
      setStatsLoading(true);
      setStatsError("");
      setStats(null);
      try {
        const statsData = await getRaceStats(raceId, {
          gender: selectedGender || undefined
        });
        if (!cancelled) {
          setStats(statsData);
        }
      } catch (statsLoadError) {
        if (!cancelled) {
          setStatsError(statsLoadError.message || "Ekki tókst að sækja tölfræði.");
        }
      } finally {
        if (!cancelled) {
          setStatsLoading(false);
        }
      }
    }

    loadStats();
    return () => {
      cancelled = true;
    };
  }, [raceId, selectedGender]);

  useEffect(() => {
    setSuggestionForm({
      suggested_surface_type: "",
      suggested_distance_km: "",
      suggested_discipline: "",
      suggested_race_type: "",
      comment: "",
      submitter_name: "",
      submitter_email: ""
    });
    setSuggestionError("");
    setSuggestionSuccess("");
    setSuggestionModalOpen(false);
  }, [raceId]);

  useEffect(() => {
    if (!suggestionModalOpen) {
      return undefined;
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setSuggestionModalOpen(false);
      }
    }

    document.body.classList.add("modal-open");
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.classList.remove("modal-open");
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [suggestionModalOpen]);

  useEffect(() => {
    let cancelled = false;

    async function loadResults() {
      setResultsLoading(true);
      setResultsError("");
      try {
        const pageSize = 500;
        const maxRows = 20000;
        let offset = 0;
        let allRows = [];

        while (offset < maxRows) {
          const page = await getRaceResultsTable(raceId, {
            gender: selectedGender || undefined,
            limit: pageSize,
            offset
          });

          allRows = [...allRows, ...page];

          if (cancelled || page.length < pageSize) {
            break;
          }

          offset += pageSize;
        }

        if (!cancelled) {
          setResults(allRows);
        }
      } catch (loadError) {
        if (!cancelled) {
          setResults([]);
          setResultsError(loadError.message || "Ekki tókst að sækja úrslit.");
        }
      } finally {
        if (!cancelled) {
          setResultsLoading(false);
        }
      }
    }

    loadResults();
    return () => {
      cancelled = true;
    };
  }, [raceId, selectedGender]);

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
  const subXBuckets = stats?.sub_x_buckets ?? [];
  const maxSubXCount = subXBuckets.reduce(
    (maxValue, bucket) => Math.max(maxValue, bucket.count ?? 0),
    0
  );
  const genderRows = (stats?.gender_breakdown ?? []).filter((row) => (row.total ?? 0) > 0);
  const maxGenderCount = genderRows.reduce(
    (maxValue, row) => Math.max(maxValue, row.total ?? 0),
    0
  );
  const statusRows = [
    { label: "Lokið", count: stats?.finished ?? 0 },
    { label: "DNF", count: stats?.dnf ?? 0 },
    { label: "DNS", count: stats?.dns ?? 0 },
    { label: "DQ", count: stats?.dq ?? 0 }
  ];
  const maxStatusCount = statusRows.reduce(
    (maxValue, row) => Math.max(maxValue, row.count ?? 0),
    0
  );
  const timeMetricCards = [
    { key: "winner", label: "Besti tími", value: stats?.time_stats?.winner },
    { key: "average", label: "Meðaltími", value: stats?.time_stats?.average },
    { key: "p50", label: "Miðgildi", value: stats?.time_stats?.p50 }
  ];
  const rawPercentileMarkers = [
    { key: "p10", label: "P10", value: stats?.time_stats?.p10 },
    { key: "p25", label: "P25", value: stats?.time_stats?.p25 },
    { key: "p50", label: "P50", value: stats?.time_stats?.p50 },
    { key: "p75", label: "P75", value: stats?.time_stats?.p75 },
    { key: "p90", label: "P90", value: stats?.time_stats?.p90 }
  ];
  const percentileMarkers = rawPercentileMarkers
    .map((marker) => ({
      ...marker,
      seconds: parseDurationToSeconds(marker.value)
    }))
    .filter((marker) => marker.seconds !== null);
  const percentileMinSeconds = percentileMarkers.length
    ? Math.min(...percentileMarkers.map((marker) => marker.seconds))
    : 0;
  const percentileMaxSeconds = percentileMarkers.length
    ? Math.max(...percentileMarkers.map((marker) => marker.seconds))
    : 0;
  const percentileSpread = percentileMaxSeconds - percentileMinSeconds;
  const percentileDistribution = [...percentileMarkers]
    .sort((a, b) => a.seconds - b.seconds)
    .map((marker, index, array) => ({
      ...marker,
      position:
        percentileSpread > 0
          ? clamp(((marker.seconds - percentileMinSeconds) / percentileSpread) * 100, 8, 92)
          : (index / Math.max(1, array.length - 1)) * 100
    }));
  const percentileSegments = percentileDistribution.slice(0, -1).map((marker, index) => {
    const next = percentileDistribution[index + 1];
    return {
      key: `${marker.key}-${next.key}`,
      start: marker.position,
      width: Math.max(0, next.position - marker.position),
      index
    };
  });
  const overallMedian = stats?.time_stats?.p50;
  const overallAverage = stats?.time_stats?.average;
  const comparisonRows = [
    { key: "median", label: "Miðgildi", metric: stats?.comparison?.median },
    { key: "winner", label: "Sigurtími", metric: stats?.comparison?.winner }
  ];

  function updateSuggestionField(field, value) {
    setSuggestionForm((current) => ({
      ...current,
      [field]: value
    }));
  }

  async function handleSuggestionSubmit(event) {
    event.preventDefault();
    setSuggestionSubmitting(true);
    setSuggestionError("");
    setSuggestionSuccess("");

    try {
      const payload = {
        suggested_surface_type: suggestionForm.suggested_surface_type || undefined,
        suggested_distance_km:
          suggestionForm.suggested_distance_km === ""
            ? undefined
            : Number(suggestionForm.suggested_distance_km),
        suggested_discipline: suggestionForm.suggested_discipline || undefined,
        suggested_race_type: suggestionForm.suggested_race_type || undefined,
        comment: suggestionForm.comment.trim() || undefined,
        submitter_name: suggestionForm.submitter_name.trim() || undefined,
        submitter_email: suggestionForm.submitter_email.trim() || undefined
      };

      await createRaceCorrectionSuggestion(raceId, payload);
      setSuggestionSuccess("Takk. Tillagan hefur verið vistuð og bíður yfirferðar.");
      setSuggestionForm({
        suggested_surface_type: "",
        suggested_distance_km: "",
        suggested_discipline: "",
        suggested_race_type: "",
        comment: "",
        submitter_name: "",
        submitter_email: ""
      });
      setSuggestionModalOpen(false);
    } catch (submitError) {
      setSuggestionError(submitError.message || "Ekki tókst að senda tillögu.");
    } finally {
      setSuggestionSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <div className="race-header">
        <div className="runner-meta">
          <h2>{race.name}</h2>
          <div className="meta-tags">
            <span>{formatIsoDate(race.date)}</span>
            <span>{race.location || "-"}</span>
            <span>{race.distance_km ? `${race.distance_km} km` : "-"}</span>
            <span>{surface.label}</span>
          </div>
        </div>
        <button className="ghost back-btn" onClick={onBack}>
          Til baka
        </button>
      </div>

      <div className="tabs enter-up">
        <button
          className={selectedGender === "" ? "tab active" : "tab"}
          onClick={() => setSelectedGender("")}
          type="button"
        >
          <span>Allir</span>
        </button>
        <button
          className={selectedGender === "F" ? "tab active" : "tab"}
          onClick={() => setSelectedGender("F")}
          type="button"
        >
          <span>Konur</span>
        </button>
        <button
          className={selectedGender === "M" ? "tab active" : "tab"}
          onClick={() => setSelectedGender("M")}
          type="button"
        >
          <span>Karlar</span>
        </button>
      </div>

      <div className="stat-row enter-up">
        <article>
          <h3>Fjöldi úrslita</h3>
          <p>{stats?.total_results ?? results.length}</p>
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

      <div className="correction-suggestion-launch enter-up">
        <div>
          <h3 className="section-title with-info">
            Leiðréttingartillaga
            <InfoTip text="Ef flokkun hlaupsins er röng geturðu sent inn tillögu um rétt yfirborð, vegalengd, grein eða flokk." />
          </h3>
          <p className="quiet">
            Sendu inn breytingatillögu ef hlaup er rangt flokkað.
          </p>
        </div>
        <button type="button" onClick={() => setSuggestionModalOpen(true)}>
          Senda tillögu
        </button>
      </div>

      {suggestionSuccess ? <p className="success-text">{suggestionSuccess}</p> : null}

      {suggestionModalOpen && typeof document !== "undefined"
        ? createPortal(
            <div
              className="modal-backdrop"
              role="presentation"
              onClick={(event) => {
                if (event.target === event.currentTarget && !suggestionSubmitting) {
                  setSuggestionModalOpen(false);
                }
              }}
            >
              <div
                className="modal-card correction-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="correction-modal-title"
              >
                <div className="modal-header">
                  <div>
                    <h3 id="correction-modal-title">Senda leiðréttingartillögu</h3>
                    <p className="quiet">
                      Veldu aðeins þau gildi sem ættu að breytast.
                    </p>
                  </div>
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => setSuggestionModalOpen(false)}
                    disabled={suggestionSubmitting}
                  >
                    Loka
                  </button>
                </div>

                <form className="correction-suggestion-form" onSubmit={handleSuggestionSubmit}>
                  <div className="correction-current-grid">
                    <div className="correction-current-item">
                      <span>Núverandi yfirborð</span>
                      <strong>{surface.label}</strong>
                    </div>
                    <div className="correction-current-item">
                      <span>Núverandi vegalengd</span>
                      <strong>{race.distance_km ? `${race.distance_km} km` : "-"}</strong>
                    </div>
                    <div className="correction-current-item">
                      <span>Núverandi grein</span>
                      <strong>{formatDisciplineLabel(race.discipline)}</strong>
                    </div>
                    <div className="correction-current-item">
                      <span>Núverandi flokkur</span>
                      <strong>{formatRaceTypeLabel(race.race_type)}</strong>
                    </div>
                  </div>

                  <div className="correction-fields-grid">
                    <label>
                      Yfirborð
                      <select
                        value={suggestionForm.suggested_surface_type}
                        onChange={(event) => updateSuggestionField("suggested_surface_type", event.target.value)}
                      >
                        <option value="">Halda óbreyttu</option>
                        {SURFACE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Vegalengd (km)
                      <input
                        type="number"
                        min="0.1"
                        step="0.1"
                        inputMode="decimal"
                        value={suggestionForm.suggested_distance_km}
                        onChange={(event) => updateSuggestionField("suggested_distance_km", event.target.value)}
                        placeholder={race.distance_km ? String(race.distance_km) : "t.d. 21.1"}
                      />
                    </label>

                    <label>
                      Grein
                      <select
                        value={suggestionForm.suggested_discipline}
                        onChange={(event) => updateSuggestionField("suggested_discipline", event.target.value)}
                      >
                        <option value="">Halda óbreyttu</option>
                        {DISCIPLINE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Flokkur
                      <select
                        value={suggestionForm.suggested_race_type}
                        onChange={(event) => updateSuggestionField("suggested_race_type", event.target.value)}
                      >
                        <option value="">Halda óbreyttu</option>
                        {RACE_TYPE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <label>
                    Athugasemd
                    <textarea
                      rows="4"
                      value={suggestionForm.comment}
                      onChange={(event) => updateSuggestionField("comment", event.target.value)}
                      placeholder="Hvað er rangt og hvað ætti að vera rétt?"
                    />
                  </label>

                  <div className="correction-fields-grid correction-fields-grid-contact">
                    <label>
                      Nafn
                      <input
                        type="text"
                        value={suggestionForm.submitter_name}
                        onChange={(event) => updateSuggestionField("submitter_name", event.target.value)}
                        placeholder="Valfrjálst"
                      />
                    </label>

                    <label>
                      Netfang
                      <input
                        type="email"
                        value={suggestionForm.submitter_email}
                        onChange={(event) => updateSuggestionField("submitter_email", event.target.value)}
                        placeholder="Valfrjálst"
                      />
                    </label>
                  </div>

                  {suggestionError ? <p className="error">{suggestionError}</p> : null}

                  <div className="correction-actions">
                    <button
                      className="ghost"
                      type="button"
                      onClick={() => setSuggestionModalOpen(false)}
                      disabled={suggestionSubmitting}
                    >
                      Hætta við
                    </button>
                    <button type="submit" disabled={suggestionSubmitting}>
                      {suggestionSubmitting ? "Sendi..." : "Senda tillögu"}
                    </button>
                  </div>
                </form>
              </div>
            </div>,
            document.body
          )
        : null}

      <h3 className="section-title with-info">
        Tölfræði
        <InfoTip text="Yfirlit yfir úrslit, dreifingu, stöðu og lykiltíma fyrir þetta hlaup." />
      </h3>
      <div className="results-table-wrap enter-up stats-wrap">
        {statsLoading ? <p className="quiet">Hleð tölfræði...</p> : null}
        {statsError ? <p className="error">{statsError}</p> : null}
        {stats ? (
          <>
            <div className="stat-row enter-up">
              <article>
                <h3 className="with-info">
                  Lokið
                  <InfoTip text="Fjöldi hlaupara sem skráðir eru með stöðuna Lokið." />
                </h3>
                <p>{stats.finished}</p>
              </article>
              <article>
                <h3 className="with-info">
                  Hætti / DNS / DQ
                  <InfoTip text="Samanlagður fjöldi DNF, DNS og DQ í hlaupinu." />
                </h3>
                <p>{stats.dnf + stats.dns + stats.dq}</p>
              </article>
              <article>
                <h3 className="with-info">
                  Markhlutfall
                  <InfoTip text="Hlutfall þátttakenda sem luku hlaupinu af öllum skráðum úrslitum." />
                </h3>
                <p>{formatPercent(stats.finish_rate)}</p>
              </article>
            </div>

            <div className="stats-chart-grid">
              <article className="stats-chart-card">
                <h4 className="with-info">
                  Samanburður við sambærileg hlaup
                  <InfoTip text="Ber saman þetta hlaup við önnur hlaup með sambærilega vegalengd og sama yfirborði. Lægri tími þýðir hraðara hlaup." />
                </h4>
                {stats.comparison ? (
                  <div className="comparison-panel">
                    <p className="comparison-cohort">
                      {stats.comparison.cohort_label}
                      {stats.comparison.gender_label ? ` · ${stats.comparison.gender_label}` : ""}
                    </p>
                    <p className="comparison-summary">
                      Byggt á {stats.comparison.cohort_race_count} sambærilegum hlaupum.
                    </p>
                    <div className="comparison-metric-list">
                      {comparisonRows.map((row) => (
                        <div className="comparison-metric" key={row.key}>
                          <div className="comparison-metric-top">
                            <span>{row.label}</span>
                            <strong className={`comparison-pill comparison-pill-${getComparisonTone(row.metric?.delta_from_peer_median_percentage)}`}>
                              {formatComparisonDelta(row.metric?.delta_from_peer_median_percentage)}
                            </strong>
                          </div>
                          <p className="comparison-meta">
                            Hraðara en {formatPercent(row.metric?.faster_than_percentage)} sambærilegra hlaupa · sæti {formatComparisonRank(row.metric, stats.comparison.cohort_race_count)}
                          </p>
                          <div className="comparison-times">
                            <div>
                              <small>Þetta hlaup</small>
                              <strong>{formatDuration(row.metric?.current)}</strong>
                            </div>
                            <div>
                              <small>Dæmigert hlaup</small>
                              <strong>{formatDuration(row.metric?.peer_median)}</strong>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="quiet">Ekki næg sambærileg gögn til að bera hlaupið saman enn.</p>
                )}
              </article>

              <article className="stats-chart-card">
                <h4 className="with-info">
                  Tímadreifing hlaupara
                  <InfoTip text="Dreifing lokatíma fyrir hlaupara í tímabilum sem miðast við vegalengd og flokkun hlaups." />
                </h4>
                <div className="stats-bars">
                  {subXBuckets.map((bucket) => (
                    <div className="stats-bar-row" key={bucket.label}>
                      <div className="stats-bar-meta">
                        <span>{bucket.label}</span>
                        <strong>
                          {bucket.count} · {formatPercent(bucket.percentage)}
                        </strong>
                      </div>
                      <div className="stats-bar-track">
                        <div
                          className="stats-bar-fill"
                          style={{ width: barWidth(bucket.count, maxSubXCount) }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </article>

              <article className="stats-chart-card">
                <h4 className="with-info">
                  Kynjaskipting
                  <InfoTip text="Fjöldi úrslita eftir kyni ásamt hlutfalli af heildarfjölda úrslita." />
                </h4>
                <div className="stats-bars">
                  {genderRows.map((row) => (
                    <div className="stats-bar-row" key={row.code}>
                      <div className="stats-bar-meta">
                        <span>{row.label}</span>
                        <strong>
                          {row.total} · {formatPercent(stats.total_results ? (row.total / stats.total_results) * 100 : 0)}
                        </strong>
                      </div>
                      <div className="stats-bar-track">
                        <div
                          className="stats-bar-fill stats-bar-fill-alt"
                          style={{ width: barWidth(row.total, maxGenderCount) }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </article>

              <article className="stats-chart-card">
                <h4 className="with-info">
                  Stöðuyfirlit
                  <InfoTip text="Skipting úrslita eftir stöðu: Lokið, DNF, DNS og DQ." />
                </h4>
                <div className="stats-bars">
                  {statusRows.map((row) => (
                    <div className="stats-bar-row" key={row.label}>
                      <div className="stats-bar-meta">
                        <span>{row.label}</span>
                        <strong>
                          {row.count} · {formatPercent(stats.total_results ? (row.count / stats.total_results) * 100 : 0)}
                        </strong>
                      </div>
                      <div className="stats-bar-track">
                        <div
                          className="stats-bar-fill stats-bar-fill-muted"
                          style={{ width: barWidth(row.count, maxStatusCount) }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </article>

              <article className="stats-chart-card stats-chart-card-wide">
                <h4 className="with-info">
                  Tímatölur
                  <InfoTip text="Besti tími, meðaltal og miðgildi, ásamt P10-P90 dreifingu fyrir hlaupara." />
                </h4>
                <div className="time-metric-grid">
                  {timeMetricCards.map((item) => (
                    <div className="time-metric-item" key={item.key}>
                      <span>{item.label}</span>
                      <strong>{formatDuration(item.value)}</strong>
                    </div>
                  ))}
                </div>
                {percentileDistribution.length ? (
                  <div className="percentile-track-wrap">
                    <div className="percentile-track-labels">
                      <span>Hraðari</span>
                      <span>Hægari</span>
                    </div>
                    <div className="percentile-track-line">
                      {percentileSegments.map((segment) => (
                        <div
                          className={`percentile-segment percentile-segment-${segment.index % 4}`}
                          key={`segment-${segment.key}`}
                          style={{
                            left: `${segment.start.toFixed(2)}%`,
                            width: `${segment.width.toFixed(2)}%`
                          }}
                        />
                      ))}
                      {percentileDistribution.map((marker) => (
                        <div
                          className="percentile-point"
                          key={marker.key}
                          style={{ left: `${marker.position.toFixed(1)}%` }}
                          title={`${marker.label}: ${formatDuration(marker.value)}`}
                        >
                          <div className="percentile-dot" />
                        </div>
                      ))}
                    </div>
                    <svg className="percentile-connector-svg" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
                      {percentileDistribution.map((marker) => (
                        <line
                          key={`connector-${marker.key}`}
                          x1={marker.position}
                          y1="0"
                          x2={marker.position}
                          y2="30"
                        />
                      ))}
                    </svg>
                    <div className="percentile-label-layer">
                      {percentileDistribution.map((marker) => (
                        <div
                          className="percentile-label"
                          key={`legend-${marker.key}`}
                          style={{ left: `${marker.position.toFixed(1)}%` }}
                          tabIndex={0}
                          aria-label={getPercentileExplanation(marker.label)}
                        >
                          <small>{marker.label}</small>
                          <em>{formatDuration(marker.value)}</em>
                          <span className="percentile-help-popup" role="tooltip">
                            {getPercentileExplanation(marker.label)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </article>
            </div>

            <details className="stats-details">
              <summary className="with-info">
                Aldurshópar
                <InfoTip text="Samanburður eftir aldurshópum: fjöldi, lokið, miðgildi, meðaltími og frávik frá heildarhlaupi." />
              </summary>
              <table className="results-table stats-table">
                <thead>
                  <tr>
                    <th>Aldurshópur</th>
                    <th>Alls</th>
                    <th>Lokið</th>
                    <th className="time-col">Miðgildi</th>
                    <th className="time-col">Meðaltími</th>
                    <th className="time-col">Δ Miðgildi</th>
                    <th className="time-col">Δ Meðaltal</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.age_breakdown?.map((row) => (
                    <tr key={row.label}>
                      <td>{row.label}</td>
                      <td>{row.total}</td>
                      <td>{row.finished}</td>
                      <td className="time-col">{formatDuration(row.median_time)}</td>
                      <td className="time-col">{formatDuration(row.average_time)}</td>
                      <td className="time-col">{formatDeltaDuration(row.median_time, overallMedian)}</td>
                      <td className="time-col">{formatDeltaDuration(row.average_time, overallAverage)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>

            <details className="stats-details">
              <summary className="with-info">
                Félagatafla
                <InfoTip text="Yfirlit félaga með flestum hlaupurum: miðgildi, meðaltími og frávik frá heildarhlaupi." />
              </summary>
              <table className="results-table stats-table">
                <thead>
                  <tr>
                    <th>Félag</th>
                    <th>Hlauparar</th>
                    <th className="time-col">Miðgildi</th>
                    <th className="time-col">Meðaltími</th>
                    <th className="time-col">Δ Miðgildi</th>
                    <th className="time-col">Δ Meðaltal</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.club_leaderboard?.length ? (
                    stats.club_leaderboard.map((row) => (
                      <tr key={row.club}>
                        <td>{row.club}</td>
                        <td>{row.finishers}</td>
                        <td className="time-col">{formatDuration(row.median_time)}</td>
                        <td className="time-col">{formatDuration(row.average_time)}</td>
                        <td className="time-col">{formatDeltaDuration(row.median_time, overallMedian)}</td>
                        <td className="time-col">{formatDeltaDuration(row.average_time, overallAverage)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="quiet">Engin félagagögn</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </details>
          </>
        ) : null}
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
        {resultsLoading ? (
          <p className="quiet">Hleð úrslit...</p>
        ) : null}
        {resultsError ? <p className="error">{resultsError}</p> : null}
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
              <th>Millitímar</th>
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
                  <td className="time-col">{birtaTimaEfLokid(row.finish_time, row.status)}</td>
                  <td className="time-col">{birtaTimaEfLokid(row.time_behind, row.status)}</td>
                  <td><SplitsCell splits={row.splits} /></td>
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
