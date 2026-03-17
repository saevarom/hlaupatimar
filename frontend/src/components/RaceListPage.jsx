import { useEffect, useRef, useState } from "react";
import { browseRaces } from "../api";
import { formatDuration, formatIsoDate } from "../lib/time";

const PAGE_SIZE = 50;

function normalizeBrowseFilters(filters = {}) {
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

export default function RaceListPage({ initialBrowse, onPersistBrowse, onOpenRace }) {
  const [query, setQuery] = useState(initialBrowse?.q || "");
  const [year, setYear] = useState(initialBrowse?.year || "");
  const [order, setOrder] = useState(initialBrowse?.order || "date_desc");
  const [pageData, setPageData] = useState({
    items: [],
    total: 0,
    limit: PAGE_SIZE,
    offset: 0,
    has_next: false,
    has_previous: false
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestRef = useRef(0);

  useEffect(() => {
    const normalized = normalizeBrowseFilters(initialBrowse);
    setQuery(normalized.q);
    setYear(normalized.year);
    setOrder(normalized.order);

    const requestId = requestRef.current + 1;
    requestRef.current = requestId;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const response = await browseRaces({
          q: normalized.q.trim() || undefined,
          year: normalized.year ? Number(normalized.year) : undefined,
          order_by: normalized.order,
          limit: PAGE_SIZE,
          offset: (normalized.page - 1) * PAGE_SIZE
        });
        if (requestRef.current === requestId) {
          setPageData(response);
        }
      } catch (loadError) {
        if (requestRef.current === requestId) {
          setError(loadError.message || "Ekki tókst að sækja hlaup.");
          setPageData({
            items: [],
            total: 0,
            limit: PAGE_SIZE,
            offset: 0,
            has_next: false,
            has_previous: false
          });
        }
      } finally {
        if (requestRef.current === requestId) {
          setLoading(false);
        }
      }
    }

    void load();
  }, [initialBrowse]);

  const currentPage = Math.max(1, Math.floor((pageData.offset || 0) / PAGE_SIZE) + 1);
  const totalPages = Math.max(1, Math.ceil((pageData.total || 0) / PAGE_SIZE));

  function updateBrowse(nextFilters, historyMode = "push") {
    onPersistBrowse?.(normalizeBrowseFilters(nextFilters), historyMode);
  }

  function onSubmit(event) {
    event.preventDefault();
    updateBrowse({ q: query, year, order, page: 1 }, "push");
  }

  function clearFilters() {
    setQuery("");
    setYear("");
    setOrder("date_desc");
    updateBrowse({ q: "", year: "", order: "date_desc", page: 1 }, "push");
  }

  function goToPage(nextPage) {
    updateBrowse({ q: query, year, order, page: nextPage }, "push");
  }

  return (
    <section className="panel enter-up">
      <div className="panel-header">
        <p className="kicker">Öll hlaup</p>
        <h2>Skoðaðu öll hlaup í tímaröð</h2>
      </div>

      <form className="race-browse-form" onSubmit={onSubmit}>
        <label>
          Nafn eða staður
          <input
            type="search"
            placeholder="Prófaðu: Reykjavíkurmaraþon, Mosfellsbær..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label>
          Ár
          <input
            type="number"
            min="1900"
            max="2100"
            placeholder="2025"
            value={year}
            onChange={(event) => setYear(event.target.value)}
          />
        </label>
        <label>
          Röðun
          <select
            value={order}
            onChange={(event) => {
              const nextOrder = event.target.value;
              setOrder(nextOrder);
              updateBrowse({ q: query, year, order: nextOrder, page: 1 }, "push");
            }}
          >
            <option value="date_desc">Nýjust fyrst</option>
            <option value="date_asc">Elst fyrst</option>
            <option value="speed_fastest">Hraðari hlaup fyrst</option>
            <option value="speed_slowest">Hægari hlaup fyrst</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Sæki..." : "Sía"}
        </button>
        <button className="ghost" type="button" onClick={clearFilters}>
          Hreinsa
        </button>
      </form>

      <div className="browse-summary">
        <span>{pageData.total} hlaup fundust</span>
        <span>
          Síða {currentPage} af {totalPages}
        </span>
      </div>
      <p className="quiet">
        Hraðastuðull er nú reiknaður fyrir 5 km, 10 km, hálfmaraþon og maraþon á vegi/blönduðu yfirborði.
        `100` er dæmigert sambærilegt hlaup. Lægra gildi er hraðara, hærra gildi hægara.
      </p>

      {error ? <p className="error">{error}</p> : null}

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
            {pageData.items.map((race) => (
              <tr key={race.id}>
                <td>{formatIsoDate(race.date)}</td>
                <td className="time-col">{formatDuration(race.winning_time)}</td>
                <td className="time-col">
                  {race.speed_index !== null && race.speed_index !== undefined ? (
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
                  ) : (
                    "-"
                  )}
                </td>
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
        {!loading && !pageData.items.length ? (
          <p className="quiet">Engin hlaup fundust fyrir þessa síu.</p>
        ) : null}
      </div>

      <div className="pagination-row">
        <button
          className="ghost"
          type="button"
          disabled={loading || !pageData.has_previous}
          onClick={() => goToPage(Math.max(1, currentPage - 1))}
        >
          Fyrri síða
        </button>
        <span className="quiet">
          {pageData.total > 0
            ? `${pageData.offset + 1}-${Math.min(pageData.offset + pageData.limit, pageData.total)} af ${pageData.total}`
            : "0 niðurstöður"}
        </span>
        <button
          className="ghost"
          type="button"
          disabled={loading || !pageData.has_next}
          onClick={() => goToPage(currentPage + 1)}
        >
          Næsta síða
        </button>
      </div>
    </section>
  );
}
