import { expect, test } from 'vitest';

import { preprocessMarkdown } from '@/lib/markdown';

test('preprocessMarkdown — latex/url normalisation + fenced-code passthrough + idempotent links', () => {
  // 1. LaTeX delimiter conversion.
  expect(preprocessMarkdown('\\(a^2 + b^2 = c^2\\)')).toBe('$a^2 + b^2 = c^2$');
  expect(preprocessMarkdown('\\[x = y + z\\]')).toBe('$$x = y + z$$');

  // 2. Inline tex-like fragments get wrapped in $...$.
  expect(preprocessMarkdown('(R_m q)^T (R_n k) = q^T R_{n-m} k')).toBe(
    '$(R_m q)^T (R_n k) = q^T R_{n-m} k$',
  );

  // 3. Fenced code blocks must be left untouched.
  const fenced = '```tex\n(R_m q)^T (R_n k) = q^T R_{n-m} k\n```';
  expect(preprocessMarkdown(fenced)).toBe(fenced);

  // 4. Bare URLs become readable markdown links; existing markdown links are
  //    not double-wrapped (idempotency).
  expect(preprocessMarkdown('출처: https://openai.com/api/pricing/')).toBe(
    '출처: [openai.com/api/pricing](https://openai.com/api/pricing/)',
  );
  const existing = '[OpenAI pricing](https://openai.com/api/pricing/)';
  expect(preprocessMarkdown(existing)).toBe(existing);
});
