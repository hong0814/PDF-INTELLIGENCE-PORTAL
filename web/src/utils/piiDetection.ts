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
  /\d{2}-\d{2}-\d{6}-\d{2}/,
  /[A-Z]{1,2}\d{7,8}/,
  /[A-HJ-NPR-Z0-9]{17}/,
  /(?:[가-힣]{2}\s?)?\d{2,3}[가-힣]\s?\d{4}/,
  /(?:\d[ -]?){13,19}/,
  /01[016789][ -]?\d{2,4}[ -]?\d{3,4}/,
  /(?:02|0[3-6][1-5]|070|050[2-8])[ -]?\d{3,4}[ -]?\d{4}/,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/,
];

function textItemContainsPII(text: string): boolean {
  for (const pat of PII_PATTERNS) {
    if (pat.test(text)) return true;
  }
  return false;
}

export function drawPIIMasks(
  canvas: HTMLCanvasElement,
  spans: { text: string; x: number; y: number; w: number; h: number }[],
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  for (const span of spans) {
    if (textItemContainsPII(span.text)) {
      ctx.fillStyle = "rgba(200, 200, 200, 1)";
      ctx.fillRect(span.x, span.y, span.w, span.h);
    }
  }
}
