function convertDelimitedMath(content: string): string {
  return content
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, expr: string) => `$$${expr.trim()}$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, expr: string) => `$${expr.trim()}$`);
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

      return wrapFormulaFragments(convertDelimitedMath(segment));
    })
    .join('');
}
