import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

describe('onboarding', () => {
  const src = fs.readFileSync(path.join(process.cwd(), 'static/js/onboarding.js'), 'utf8');

  it('.trim() fix is present (C-001)', () => {
    expect(src).toContain('.trim()');
    expect(src).not.toMatch(/\.trim[^()]/);
  });
  it('back button exists', () => {
    expect(src).toContain('Back');
  });
  it('showOnboardingScreen function is defined', () => {
    expect(src).toContain('function showOnboardingScreen');
  });
});
