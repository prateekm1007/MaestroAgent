import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const utilsSrc = fs.readFileSync(path.join(process.cwd(), 'static/js/utils.js'), 'utf8');
const humanizeSrc = fs.readFileSync(path.join(process.cwd(), 'static/js/humanize.js'), 'utf8');
const fn = new Function(utilsSrc + '\n' + humanizeSrc + '; return { humanize };');
const { humanize } = fn();

describe('humanize', () => {
  it('is defined', () => {
    expect(typeof humanize).toBe('function');
  });
  it('handles null/undefined', () => {
    expect(humanize(null)).toBe('');
    expect(humanize(undefined)).toBe('');
  });
  it('handles empty string', () => {
    expect(humanize('')).toBe('');
  });
  it('replaces OEM with Maestro', () => {
    const result = humanize('OEM is online');
    expect(result.toLowerCase()).toContain('maestro');
  });
});
