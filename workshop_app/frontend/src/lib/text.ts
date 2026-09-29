/** Collapse a step title to a clean one-liner by stripping a leading "<group>: " prefix - the
 *  pillar/accelerator name is already the section header, so repeating it ("Choice: …") just
 *  wastes the single line we show when a step is collapsed. Only strips when the prefix matches
 *  the group title, so titles that don't carry the prefix (every accelerator step) are untouched. */
export function shortTitle(title: string, group?: string): string {
  const t = title.trim();
  if (group) {
    const prefix = group.trim().toLowerCase() + ":";
    if (t.toLowerCase().startsWith(prefix)) {
      return t.slice(t.indexOf(":") + 1).trim();
    }
  }
  return t;
}
