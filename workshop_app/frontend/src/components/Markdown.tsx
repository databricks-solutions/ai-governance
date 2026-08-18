import type { ReactNode } from "react";

// The one markdown renderer for the whole app.
//
// There were previously two near-identical copies (Intro and Faq) and step concepts used no
// markdown at all — they rendered with `whitespace-pre-line`, so every `- bullet`, `**bold**`
// and table in config/steps.yaml showed as literal punctuation. Step concepts are the largest
// body of prose in the product, so that was the most-read text in the app rendering wrong.
//
// Supports exactly what the content actually uses: headings, bullet and numbered lists, GFM
// tables, fenced code, blockquotes, and inline bold/code/links. Deliberately not a full
// CommonMark implementation — a dependency-free renderer we can reason about beats correctness
// on syntax nobody writes here.
//
// All text passes through escape() before any tag is emitted, so customer-edited YAML cannot
// inject markup.

function escape(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Inline formatting: `code`, **bold**, *italic*, and [text](url). */
export function inline(s: string): string {
  let out = escape(s);
  // Code first: its contents must not be re-processed as bold/italic/links.
  const code: string[] = [];
  out = out.replace(/`([^`]+)`/g, (_m, c) => {
    code.push(c);
    return `\u0000${code.length - 1}\u0000`;
  });
  out = out
    .replace(/\*\*([^*]+)\*\*/g, "<strong class='font-semibold text-navy'>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    // Links: only http(s), so a crafted javascript: URL cannot ride in from config.
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      "<a href='$2' target='_blank' rel='noreferrer' class='font-semibold text-navy underline decoration-lava decoration-2 underline-offset-2 hover:text-lava'>$1</a>",
    );
  return out.replace(
    /\u0000(\d+)\u0000/g,
    (_m, i) =>
      `<code class='rounded bg-navy/[0.06] px-1.5 py-0.5 text-[0.9em] text-navy'>${code[Number(i)]}</code>`,
  );
}

const H = (s: string) => <span dangerouslySetInnerHTML={{ __html: inline(s) }} />;

function isTableSep(line: string): boolean {
  // |---|:--:|---| — the row that makes a GFM table a table.
  return /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(line) && line.includes("-");
}

function splitRow(line: string): string[] {
  const t = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return t.split("|").map((c) => c.trim());
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="my-4 overflow-x-auto rounded-xl border border-navy/10">
      <table className="w-full border-collapse text-left text-[13.5px]">
        {head.length > 0 && (
          <thead className="bg-oat">
            <tr>
              {head.map((c, i) => (
                <th key={i} className="px-3.5 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  {H(c)}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-navy/[0.07] align-top">
              {r.map((c, k) => (
                <td key={k} className="px-3.5 py-2.5 leading-relaxed text-muted">
                  {H(c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Markdown({
  text,
  className,
  compact = false,
}: {
  text: string;
  className?: string;
  /** Smaller type for markdown inside a card (step concepts) rather than a full page. */
  compact?: boolean;
}) {
  // Set on the wrapper would not work: every block below carries its own text-[15px], which
  // beats an inherited size. So the size is threaded explicitly.
  const body = compact ? "text-[13.5px]" : "text-[15px]";
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;

  // Paragraph/list accumulation happens line-by-line rather than by splitting on blank lines,
  // because tables and fenced code need to survive single newlines inside a block.
  let para: string[] = [];
  const flushPara = () => {
    if (!para.length) return;
    out.push(
      <p key={key++} className={`${body} leading-relaxed text-muted`}>
        {H(para.join(" "))}
      </p>,
    );
    para = [];
  };

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      flushPara();
      i++;
      continue;
    }

    // Fenced code
    if (trimmed.startsWith("```")) {
      flushPara();
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) body.push(lines[i++]);
      i++; // closing fence
      out.push(
        <pre
          key={key++}
          className="my-4 overflow-x-auto rounded-xl bg-navy/[0.04] p-3.5 text-[12.5px] leading-relaxed text-navy/85"
        >
          {body.join("\n")}
        </pre>,
      );
      continue;
    }

    // Table: a header row followed by a |---| separator.
    if (trimmed.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flushPara();
      const head = splitRow(trimmed);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().includes("|") && lines[i].trim()) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      out.push(<Table key={key++} head={head} rows={rows} />);
      continue;
    }

    // Headings
    const h = /^(#{1,4})\s+(.*)$/.exec(trimmed);
    if (h) {
      flushPara();
      const level = h[1].length;
      const cls =
        level === 1
          ? "mt-6 text-2xl font-bold text-navy"
          : level === 2
            ? "mt-6 text-xl font-semibold text-navy"
            : "mt-4 text-base font-semibold text-navy";
      out.push(
        <div key={key++} className={cls}>
          {H(h[2])}
        </div>,
      );
      i++;
      continue;
    }

    // Blockquote
    if (trimmed.startsWith("> ")) {
      flushPara();
      const body: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        body.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      out.push(
        <blockquote
          key={key++}
          className="my-4 border-l-[3px] border-lava/50 bg-oat/60 px-4 py-3 text-[14.5px] leading-relaxed text-muted"
        >
          {H(body.join(" "))}
        </blockquote>,
      );
      continue;
    }

    // Lists — bulleted or numbered. Continuation lines (indented, no marker) join the item, so
    // a wrapped bullet in YAML stays one bullet.
    const bullet = /^[-*]\s+(.*)$/.exec(trimmed);
    const numbered = /^(\d+)[.)]\s+(.*)$/.exec(trimmed);
    if (bullet || numbered) {
      flushPara();
      const ordered = !!numbered;
      const items: string[] = [];
      while (i < lines.length) {
        const t = lines[i].trim();
        const b = /^[-*]\s+(.*)$/.exec(t);
        const n = /^(\d+)[.)]\s+(.*)$/.exec(t);
        if (b && !ordered) items.push(b[1]);
        else if (n && ordered) items.push(n[2]);
        else if (t && !b && !n && /^\s{2,}/.test(lines[i]) && items.length) items[items.length - 1] += " " + t;
        else break;
        i++;
      }
      out.push(
        ordered ? (
          <ol key={key++} className="my-3 space-y-1.5">
            {items.map((it, k) => (
              <li key={k} className={`flex gap-2.5 ${body} leading-relaxed text-muted`}>
                <span className="mt-px shrink-0 text-[13px] font-semibold text-lava">{k + 1}.</span>
                {H(it)}
              </li>
            ))}
          </ol>
        ) : (
          <ul key={key++} className="my-3 space-y-1.5">
            {items.map((it, k) => (
              <li key={k} className={`flex gap-2.5 ${body} leading-relaxed text-muted`}>
                <span className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-lava" />
                {H(it)}
              </li>
            ))}
          </ul>
        ),
      );
      continue;
    }

    para.push(trimmed);
    i++;
  }
  flushPara();

  return <div className={className}>{out}</div>;
}
