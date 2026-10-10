/** Markdown → one line of plain text, for previews that can't render Markdown. */
export function plainText(md: string | null | undefined): string {
  if (!md) return "";
  return md
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1") // links and images keep their text
    .replace(/(\*\*|\*|~~|`)(?=\S)([\s\S]*?\S)\1/g, "$2") // emphasis, code (not `_`: it appears in ids)
    .replace(/^\s{0,3}(#{1,6}\s+|>\s?|[-*+]\s+|\d+\.\s+)/gm, "") // block markers
    .replace(/\s+/g, " ")
    .trim();
}
