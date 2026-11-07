export type Building = { id: string; name: string; category: string; w: number; d: number; h: number; color: string; coins: number; materials: number; unlocked: boolean; lock_reason?: string };
export type Item = { id: number; type: string; x: number; z: number; rot: number; origin: string };
export type Chunk = { cx: number; cz: number; unlocked: boolean; h: number[]; t: number[] };
export type City = { username: string; name: string; level: number; seed: number; version: number; chunk_size: number; unlocked: number[][]; items: Item[]; chunks: Chunk[]; expandable: number[][] };
export type Balances = { energy: number; coins: number; materials: number; reputation: number };
export type Analysis = {
  identity: { dominant: string[]; secondary: string[]; shares: Record<string, number>; diversity: number; mixed_district: boolean; specialization: string | null; tech_facilities: { tech: string; facility: string; status: string; evidence: string[] }[] };
  activity: { score: number; level: number };
  community: { population: number };
  data_quality: { unavailable: string[]; inferred: string[]; notes: string[] };
  plan: { building: string; reason: string }[];
};
export type BannerInfo = { version: number; image_url: string; versioned_url: string; profile_url: string; markdown: string; width: number; height: number; display_width: number; display_height: number };
