// __tests__/utils.test.ts — Tests for lib/utils.ts

import { describe, it, expect } from 'vitest';
import { cn, formatDuration, formatBytes, relativeTime, renderMarkdown, getGreeting } from '@/lib/utils';

describe('utils', () => {
  describe('cn', () => {
    it('should merge class names', () => {
      expect(cn('foo', 'bar')).toBe('foo bar');
    });
    it('should handle conditional classes', () => {
      expect(cn('base', false && 'hidden', true && 'visible')).toBe('base visible');
    });
  });

  describe('formatDuration', () => {
    it('should format milliseconds', () => {
      expect(formatDuration(500)).toBe('500ms');
    });
    it('should format seconds', () => {
      expect(formatDuration(5500)).toBe('5.5s');
    });
    it('should format minutes', () => {
      expect(formatDuration(125000)).toBe('2m 5s');
    });
  });

  describe('formatBytes', () => {
    it('should format bytes', () => { expect(formatBytes(500)).toBe('500 B'); });
    it('should format kilobytes', () => { expect(formatBytes(2048)).toBe('2.0 KB'); });
    it('should format megabytes', () => { expect(formatBytes(1048576)).toBe('1.0 MB'); });
  });

  describe('relativeTime', () => {
    it('should return "just now" for recent', () => {
      expect(relativeTime(new Date().toISOString())).toBe('just now');
    });
    it('should return minutes ago', () => {
      expect(relativeTime(new Date(Date.now() - 120000).toISOString())).toBe('2m ago');
    });
    it('should return hours ago', () => {
      expect(relativeTime(new Date(Date.now() - 7200000).toISOString())).toBe('2h ago');
    });
  });

  describe('renderMarkdown', () => {
    it('should render bold text', () => {
      const result = renderMarkdown('**bold**');
      expect(result).toContain('<strong');
      expect(result).toContain('bold');
    });
    it('should render code blocks', () => {
      const result = renderMarkdown('```js\nconsole.log(1)\n```');
      expect(result).toContain('<pre');
      expect(result).toContain('console.log(1)');
    });
    it('should render headings', () => {
      expect(renderMarkdown('# Title')).toContain('<h2');
      expect(renderMarkdown('## Section')).toContain('<h3');
      expect(renderMarkdown('### Sub')).toContain('<h4');
    });
    it('should escape HTML', () => {
      expect(renderMarkdown('<script>alert(1)</script>')).not.toContain('<script>');
    });
  });

  describe('getGreeting', () => {
    it('should return a greeting string', () => {
      const greeting = getGreeting();
      expect(['Good morning', 'Good afternoon', 'Good evening']).toContain(greeting);
    });
  });
});
