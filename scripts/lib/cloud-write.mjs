import { loadEnvLocal } from './env.mjs';

/**
 * 本地优化与语雀云端编辑解耦：默认禁止写回云端。
 * 语雀在线编辑器使用 Lake 格式；用 markdown + body 写回会破坏保存。
 *
 * 仅在明确需要时设置 YUQUE_CLOUD_WRITE=1，且不推荐对已有 Lake 文档写回。
 */
export function isCloudWriteEnabled(env = loadEnvLocal()) {
  const v = (env.YUQUE_CLOUD_WRITE || '0').trim().toLowerCase();
  return v === '1' || v === 'true' || v === 'yes';
}

export function assertCloudWriteAllowed(env = loadEnvLocal()) {
  if (isCloudWriteEnabled(env)) return;
  throw new Error(
    [
      '已禁用写回语雀云端（YUQUE_CLOUD_WRITE 未开启）。',
      '本项目优化仅作用于本地 Markdown 镜像，不会影响语雀在线编辑。',
      '',
      '如需拉取云端最新内容：npm run sync-all',
      '如确需写回（不推荐，可能破坏 Lake 格式）：在 .env.local 设置 YUQUE_CLOUD_WRITE=1',
    ].join('\n'),
  );
}

export const CLOUD_WRITE_WARNING =
  '警告：写回云端可能将 Lake 文档转为 Markdown，导致语雀网页端无法保存。';
