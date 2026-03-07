export function parseDurationToSeconds(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  const raw = String(value).trim();

  // Python timedelta long form, e.g. "1 day, 02:03:04"
  const dayMatch = raw.match(
    /^(\d+)\s+day[s]?,\s*(\d{1,2}):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/
  );
  if (dayMatch) {
    const [, days, hours, minutes, seconds] = dayMatch;
    return (
      Number(days) * 86400 +
      Number(hours) * 3600 +
      Number(minutes) * 60 +
      Number(seconds)
    );
  }

  // HH:MM:SS(.ms) or MM:SS(.ms)
  const clockParts = raw.split(":");
  if (clockParts.length === 3 || clockParts.length === 2) {
    const parts = clockParts.map(Number);
    if (!parts.some((part) => Number.isNaN(part))) {
      if (parts.length === 3) {
        const [hours, minutes, seconds] = parts;
        return hours * 3600 + minutes * 60 + seconds;
      }
      const [minutes, seconds] = parts;
      return minutes * 60 + seconds;
    }
  }

  // ISO 8601 duration, e.g. "PT16M30S"
  const isoMatch = raw.match(
    /^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$/
  );
  if (isoMatch) {
    const [, days = "0", hours = "0", minutes = "0", seconds = "0"] = isoMatch;
    return (
      Number(days) * 86400 +
      Number(hours) * 3600 +
      Number(minutes) * 60 +
      Number(seconds)
    );
  }

  // Plain seconds as string.
  const asNumber = Number(raw);
  if (Number.isFinite(asNumber)) {
    return asNumber;
  }

  return null;
}

export function formatSecondsToDuration(totalSeconds) {
  if (totalSeconds === null || totalSeconds === undefined || Number.isNaN(totalSeconds)) {
    return "-";
  }

  const rounded = Math.round(totalSeconds);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const seconds = rounded % 60;

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function formatDuration(value) {
  const seconds = parseDurationToSeconds(value);
  if (seconds === null) {
    if (value === null || value === undefined || value === "") {
      return "-";
    }
    return String(value);
  }
  return formatSecondsToDuration(seconds);
}

export function formatIsoDate(value) {
  if (!value) {
    return "-";
  }

  const months = [
    "jan.",
    "feb.",
    "mars",
    "apr.",
    "maí",
    "jún.",
    "júl.",
    "ágú.",
    "sep.",
    "okt.",
    "nóv.",
    "des."
  ];

  const isoDateMatch = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoDateMatch) {
    const [, year, month, day] = isoDateMatch;
    const monthIndex = Number(month) - 1;
    if (monthIndex >= 0 && monthIndex < months.length) {
      return `${Number(day)} ${months[monthIndex]} ${year}`;
    }
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
}
