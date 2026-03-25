function convertDelimitedMath(content: string): string {
  return content
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, expr: string) => `$$${expr.trim()}$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, expr: string) => `$${expr.trim()}$`);
}

const BARE_URL_PATTERN = /(?<![\[\]\(<])https?:\/\/[^\s<]+/g;

function trimTrailingUrlPunctuation(value: string): { url: string; trailing: string } {
  let url = value;
  let trailing = "";

  while (/[),.;!?]$/.test(url)) {
    trailing = url.slice(-1) + trailing;
    url = url.slice(0, -1);
  }

  return { url, trailing };
}

function formatUrlLabel(url: string): string {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");
    const path = parsed.pathname.replace(/\/$/, "");
    if (!path || path === "/") {
      return host;
    }

    const compactPath = path.length > 24 ? `${path.slice(0, 21)}...` : path;
    return `${host}${compactPath}`;
  } catch {
    return url;
  }
}

function convertBareUrls(content: string): string {
  return content.replace(BARE_URL_PATTERN, (match: string) => {
    const { url, trailing } = trimTrailingUrlPunctuation(match);
    return `[${formatUrlLabel(url)}](${url})${trailing}`;
  });
}

function shouldWrapFormula(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed || trimmed.includes('$')) {
    return false;
  }
  if (!trimmed.includes('=') || !(trimmed.includes('_') || trimmed.includes('^') || trimmed.includes('\\'))) {
    return false;
  }
  return trimmed.length >= 6 && trimmed.length <= 120;
}

function wrapFormulaFragments(content: string): string {
  if (content.includes('$')) {
    return content;
  }

  return content
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return line;
      }

      if (shouldWrapFormula(trimmed)) {
        return line.replace(trimmed, `$${trimmed}$`);
      }

      const prefixedMatch = trimmed.match(/^(.*?:\s*)(.+)$/);
      if (prefixedMatch && shouldWrapFormula(prefixedMatch[2])) {
        return line.replace(trimmed, `${prefixedMatch[1]}$${prefixedMatch[2].trim()}$`);
      }

      return line;
    })
    .join('\n');
}

export function preprocessMarkdown(content: string): string {
  if (!content) {
    return '';
  }

  const segments = content.split(/(```[\s\S]*?```)/g);
  return segments
    .map((segment) => {
      if (segment.startsWith('```')) {
        return segment;
      }

      return convertBareUrls(wrapFormulaFragments(convertDelimitedMath(segment)));
    })
    .join('');
}
