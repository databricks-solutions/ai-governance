import { describe, it, expect } from 'vitest';
import { formatHeadline, formatMoney, formatPerQuery, formatLatency, formatTokens } from './format';

// P0-3 - number precision policy.
describe('formatHeadline', () => {
  it('153_900 → $154K', () => expect(formatHeadline(153_900)).toBe('$154K'));
  it('26_100 → $26.1K', () => expect(formatHeadline(26_100)).toBe('$26.1K'));
  it('2_175 → $2,175', () => expect(formatHeadline(2_175)).toBe('$2,175'));
  it('0 → $0', () => expect(formatHeadline(0)).toBe('$0'));
  it('1_840_000 → $1.84M', () => expect(formatHeadline(1_840_000)).toBe('$1.84M'));
  it('never renders $0.0000', () => expect(formatHeadline(0.0044)).not.toContain('0.0000'));
});

describe('formatMoney', () => {
  it('2_175 → $2,175', () => expect(formatMoney(2_175)).toBe('$2,175'));
  it('71.51 → $71.51', () => expect(formatMoney(71.51)).toBe('$71.51'));
  it('0 → $0 (never $0.00 / $0.0000)', () => expect(formatMoney(0)).toBe('$0'));
});

describe('formatPerQuery', () => {
  it('0.0087 → $0.0087', () => expect(formatPerQuery(0.0087)).toBe('$0.0087'));
  it('tiny cost keeps sig figs, never $0', () => {
    expect(formatPerQuery(0.000017)).toBe('$0.000017');
    expect(formatPerQuery(0.000017)).not.toBe('$0');
  });
});

describe('formatMoney tiny values', () => {
  it('sub-$0.0001 keeps sig figs, never $0', () => {
    expect(formatMoney(0.0000356)).not.toBe('$0');
    expect(formatMoney(0.0000356)).toContain('0.0000');
  });
  it('0.0044 → $0.0044', () => expect(formatMoney(0.0044)).toBe('$0.0044'));
});

describe('formatLatency', () => {
  it('1_400 → 1.4s', () => expect(formatLatency(1_400)).toBe('1.4s'));
  it('820 → 820ms', () => expect(formatLatency(820)).toBe('820ms'));
});

describe('formatTokens', () => {
  it('18_200 → 18.2K', () => expect(formatTokens(18_200)).toBe('18.2K'));
  it('1_240 → 1,240', () => expect(formatTokens(1_240)).toBe('1,240'));
});
