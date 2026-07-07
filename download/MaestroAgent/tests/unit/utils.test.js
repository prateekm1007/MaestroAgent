import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

// Load utils.js into global scope
const utilsSrc = fs.readFileSync(path.join(process.cwd(), 'static/js/utils.js'), 'utf8');
const fn = new Function(utilsSrc + '; return { escapeHtml, escapeJs, formatConfidence, formatTimestamp, errorHTML, announce };');
const { escapeHtml, escapeJs, formatConfidence, formatTimestamp } = fn();

describe('escapeHtml', () => {
  it('escapes < and >', () => {
    expect(escapeHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;');
  });
  it('escapes quotes', () => {
    expect(escapeHtml('he said "hello"')).toBe('he said &quot;hello&quot;');
  });
  it('handles null/undefined', () => {
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(undefined)).toBe('');
  });
  it('handles empty string', () => {
    expect(escapeHtml('')).toBe('');
  });
  it('escapes ampersand', () => {
    expect(escapeHtml('a & b')).toBe('a &amp; b');
  });
});

describe('escapeJs', () => {
  it('escapes single quotes', () => {
    expect(escapeJs("O'Brien")).toBe("O\\'Brien");
  });
  it('escapes double quotes', () => {
    expect(escapeJs('say "hi"')).toBe('say \\"hi\\"');
  });
  it('escapes backslashes', () => {
    expect(escapeJs('path\\to\\file')).toBe('path\\\\to\\\\file');
  });
  it('handles null/undefined', () => {
    expect(escapeJs(null)).toBe('');
    expect(escapeJs(undefined)).toBe('');
  });
});

describe('formatConfidence', () => {
  it('formats decimal as percentage', () => {
    expect(formatConfidence(0.85)).toBe('85%');
  });
  it('formats 1.0 as 100%', () => {
    expect(formatConfidence(1.0)).toBe('100%');
  });
  it('formats 0 as 0%', () => {
    expect(formatConfidence(0)).toBe('0%');
  });
  it('handles null/undefined', () => {
    expect(formatConfidence(null)).toBe('—');
    expect(formatConfidence(undefined)).toBe('—');
  });
  it('handles string input', () => {
    expect(formatConfidence('0.9')).toBe('90%');
  });
});

describe('formatTimestamp', () => {
  it('handles null/undefined', () => {
    expect(formatTimestamp(null)).toBe('');
    expect(formatTimestamp(undefined)).toBe('');
  });
  it('formats ISO timestamp', () => {
    const result = formatTimestamp('2024-11-01T10:00:00Z');
    expect(result).toContain('2024');
  });
});
