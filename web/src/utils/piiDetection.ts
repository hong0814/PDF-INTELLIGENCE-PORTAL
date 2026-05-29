export interface PIISpan {
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

const PII_PATTERNS: RegExp[] = [
  /\d{6}[- ]?[1-4]\d{6}/,
  /\d{6}[- ]?[5-8]\d{6}/,
  /\d{3}-\d{2}-\d{5}/,
  /[A-Z]{1,2}\d{7,8}/,
  /[A-HJ-NPR-Z0-9]{17}/,
  /01[016789][ -]?\d{2,4}[ -]?\d{3,4}/,
  /(?:02|0[3-6][1-5]|070|050[2-8])[ -]?\d{3,4}[ -]?\d{4}/,
  /\d{4}-\d{4}-\d{4}-\d{4}/,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/,
];

const LINE_Y_TOLERANCE = 4;
const COLUMN_GAP_THRESHOLD = 15;

interface SpanWithOffset {
  idx: number;
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  charStart: number;
}

export function drawPIIMasks(
  canvas: HTMLCanvasElement,
  spans: { text: string; x: number; y: number; w: number; h: number }[],
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const indexed: SpanWithOffset[] = [];
  let charOffset = 0;
  for (let i = 0; i < spans.length; i++) {
    indexed.push({ idx: i, charStart: charOffset, ...spans[i] });
    charOffset += spans[i].text.length;
  }

  const byLine = new Map<number, SpanWithOffset[]>();
  for (const span of indexed) {
    let placed = false;
    for (const [ly] of byLine) {
      if (Math.abs(span.y - ly) < LINE_Y_TOLERANCE) {
        byLine.get(ly)!.push(span);
        placed = true;
        break;
      }
    }
    if (!placed) byLine.set(span.y, [span]);
  }

  const piiCharRanges: [number, number][] = [];

  for (const [, lineSpans] of byLine) {
    lineSpans.sort((a, b) => a.x - b.x);

    const segments: SpanWithOffset[][] = [];
    let current: SpanWithOffset[] = [lineSpans[0]];

    for (let i = 1; i < lineSpans.length; i++) {
      const prevRight = lineSpans[i - 1].x + lineSpans[i - 1].w;
      if (lineSpans[i].x - prevRight <= COLUMN_GAP_THRESHOLD) {
        current.push(lineSpans[i]);
      } else {
        segments.push(current);
        current = [lineSpans[i]];
      }
    }
    segments.push(current);

    for (const seg of segments) {
      const segText = seg.map((s) => s.text).join("");
      const baseOffset = seg[0].charStart;

      for (const pat of PII_PATTERNS) {
        let match: RegExpExecArray | null;
        const regex = new RegExp(pat.source, "g");
        while ((match = regex.exec(segText)) !== null) {
          piiCharRanges.push([baseOffset + match.index, baseOffset + match.index + match[0].length]);
        }
      }
    }
  }

  const piiSpanIndices = new Set<number>();
  for (const span of indexed) {
    const start = span.charStart;
    const end = span.charStart + span.text.length;
    for (const [rs, re] of piiCharRanges) {
      if (start < re && end > rs) {
        piiSpanIndices.add(span.idx);
        break;
      }
    }
  }

  for (const span of indexed) {
    if (piiSpanIndices.has(span.idx)) {
      ctx.fillStyle = "rgba(200, 200, 200, 1)";
      ctx.fillRect(span.x, span.y, span.w, span.h);
    }
  }
}
