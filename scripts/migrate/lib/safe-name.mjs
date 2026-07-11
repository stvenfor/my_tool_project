/** 文件名安全化，保留中文与常见字符 */
export function safeFileName(name) {
  return name
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 180) || 'untitled';
}

export function safeFileBase(title) {
  return `${safeFileName(title)}.md`;
}
