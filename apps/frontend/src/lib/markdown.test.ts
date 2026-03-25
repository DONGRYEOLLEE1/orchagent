import { expect, test } from 'vitest';

import { preprocessMarkdown } from '@/lib/markdown';

test('converts latex delimiters to remark-math friendly syntax', () => {
  expect(preprocessMarkdown('\\(a^2 + b^2 = c^2\\)')).toBe('$a^2 + b^2 = c^2$');
  expect(preprocessMarkdown('\\[x = y + z\\]')).toBe('$$x = y + z$$');
});

test('wraps plain tex-like formula fragments with math delimiters', () => {
  expect(
    preprocessMarkdown('(R_m q)^T (R_n k) = q^T R_{n-m} k')
  ).toBe('$(R_m q)^T (R_n k) = q^T R_{n-m} k$');
});

test('does not touch fenced code blocks', () => {
  const input = '```tex\n(R_m q)^T (R_n k) = q^T R_{n-m} k\n```';
  expect(preprocessMarkdown(input)).toBe(input);
});

test('converts bare urls into markdown links with readable labels', () => {
  expect(
    preprocessMarkdown('출처: https://openai.com/api/pricing/')
  ).toBe('출처: [openai.com/api/pricing](https://openai.com/api/pricing/)');
});

test('does not break existing markdown links', () => {
  const input = '[OpenAI pricing](https://openai.com/api/pricing/)';
  expect(preprocessMarkdown(input)).toBe(input);
});
