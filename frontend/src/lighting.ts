export type LightingPreference = "auto" | "day" | "dusk" | "night";
export type LightingMode = Exclude<LightingPreference, "auto">;

export function automaticLighting(date = new Date()): LightingMode {
  const hour = date.getHours();
  if (hour >= 6 && hour < 18) return "day";
  if (hour >= 18 && hour < 21) return "dusk";
  return "night";
}

export function timezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}
