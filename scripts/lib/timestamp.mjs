/**
 * 语雀 updated_at 在不同 API 间精度不一致（毫秒 vs 秒），
 * 用容差比较避免误判冲突。
 */
export function updatedAtMatches(local, remote, toleranceMs = 1000) {
  if (!local || !remote) return true;
  const a = new Date(local).getTime();
  const b = new Date(remote).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return local === remote;
  return Math.abs(a - b) <= toleranceMs;
}

export function normalizeUpdatedAt(iso) {
  if (!iso) return iso;
  const ms = new Date(iso).getTime();
  if (Number.isNaN(ms)) return iso;
  return new Date(ms).toISOString();
}
