import { parseDurationToSeconds } from "./time";

const SURFACE_CATEGORIES = [
  { key: "road", label: "Götuhlaup" },
  { key: "trail", label: "Utanvega" },
  { key: "mixed", label: "Blandað" },
  { key: "unknown", label: "Óþekkt" }
];

const SURFACE_BY_KEY = Object.fromEntries(
  SURFACE_CATEGORIES.map((surface) => [surface.key, surface])
);

export function categorizeDistance(distanceKm) {
  const distance = Number(distanceKm);
  if (!Number.isFinite(distance)) {
    return { key: "other", label: "Annað" };
  }

  if (distance > 43.5) {
    return { key: "ultra", label: "Ofurhlaup" };
  }
  if (distance >= 41 && distance <= 43.5) {
    return { key: "marathon", label: "Maraþon" };
  }
  if (distance >= 20 && distance <= 22.5) {
    return { key: "half", label: "Hálfmaraþon" };
  }
  if (distance >= 9 && distance <= 11) {
    return { key: "10k", label: "10 km" };
  }
  if (distance >= 4 && distance <= 6) {
    return { key: "5k", label: "5 km" };
  }

  return { key: "other", label: "Annað" };
}

export function normalizeSurfaceType(surfaceType) {
  const key = String(surfaceType || "unknown").trim().toLowerCase();
  return SURFACE_BY_KEY[key] || SURFACE_BY_KEY.unknown;
}

export function getSurfaceCategories() {
  return SURFACE_CATEGORIES;
}

export function buildTrends(raceHistory) {
  const byCategory = {};

  raceHistory.forEach((race) => {
    const normalizedStatus = String(race.status ?? "").trim().toLowerCase();
    const isFinished =
      normalizedStatus === "" ||
      normalizedStatus === "finished" ||
      normalizedStatus === "lokid";
    if (!isFinished) {
      return;
    }

    const category = categorizeDistance(race.distance_km);
    const surface = normalizeSurfaceType(race.surface_type);
    const finishSeconds = parseDurationToSeconds(race.finish_time);
    if (finishSeconds === null) {
      return;
    }

    const combinedKey = `${surface.key}:${category.key}`;
    if (!byCategory[combinedKey]) {
      byCategory[combinedKey] = {
        key: combinedKey,
        surface,
        category,
        points: []
      };
    }

    byCategory[combinedKey].points.push({
      raceId: race.race_id,
      date: race.race_date,
      dateValue: new Date(race.race_date).getTime(),
      finishTime: race.finish_time,
      finishSeconds,
      raceName: race.race_name,
      eventName: race.event_name,
      distanceKm: race.distance_km,
      status: race.status
    });
  });

  const trends = Object.values(byCategory)
    .map((group) => ({
      ...group,
      points: group.points
        .filter((point) => Number.isFinite(point.dateValue))
        .sort((a, b) => a.dateValue - b.dateValue)
    }))
    .filter((group) => group.points.length > 0)
    .sort((a, b) => {
      const surfaceOrder =
        SURFACE_CATEGORIES.findIndex((item) => item.key === a.surface.key) -
        SURFACE_CATEGORIES.findIndex((item) => item.key === b.surface.key);
      if (surfaceOrder !== 0) {
        return surfaceOrder;
      }
      return b.points.length - a.points.length;
    });

  return trends;
}

export function getPersonalBest(points) {
  if (!points?.length) {
    return null;
  }

  return points.reduce((best, current) =>
    current.finishSeconds < best.finishSeconds ? current : best
  );
}
