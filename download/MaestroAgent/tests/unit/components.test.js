import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const utilsSrc = fs.readFileSync(path.join(process.cwd(), 'static/js/utils.js'), 'utf8');
const humanizeSrc = fs.readFileSync(path.join(process.cwd(), 'static/js/humanize.js'), 'utf8');
const cardSrc = fs.readFileSync(path.join(process.cwd(), 'static/js/components/card.js'), 'utf8');
const fn = new Function(utilsSrc + '\n' + humanizeSrc + '\n' + cardSrc + '; return { RecommendationCard, MetricTile, ErrorState, LoadingState, EmptyState, LawCard, WhisperCard };');
const { RecommendationCard, MetricTile, ErrorState, LoadingState, EmptyState, LawCard, WhisperCard } = fn();

describe('RecommendationCard', () => {
  it('renders with title and urgency', () => {
    const html = RecommendationCard({ title: 'Fix SSO', urgency: 'urgent', evidence_count: 5 });
    expect(html).toContain('Fix SSO');
    expect(html).toContain('urgent');
    expect(html).toContain('5 signals');
  });
  it('has data-action for drilldown', () => {
    const html = RecommendationCard({ title: 'Test', urgency: 'normal' });
    expect(html).toContain('data-action="openDrilldown"');
  });
  it('handles null fields', () => {
    const html = RecommendationCard({});
    expect(html).toContain('class="card');
  });
});

describe('MetricTile', () => {
  it('renders label and value', () => {
    const html = MetricTile('Laws', 6, 'laws');
    expect(html).toContain('Laws');
    expect(html).toContain('6');
  });
});

describe('ErrorState', () => {
  it('renders error message', () => {
    const html = ErrorState('Something broke');
    expect(html).toContain('Something broke');
    expect(html).toContain('role="alert"');
  });
  it('can include retry action', () => {
    const html = ErrorState('Failed', 'retryLoad');
    expect(html).toContain('Retry');
    expect(html).toContain('data-action');
  });
});

describe('LoadingState', () => {
  it('renders with default text', () => {
    const html = LoadingState();
    expect(html).toContain('Loading');
    expect(html).toContain('spinner');
  });
});

describe('EmptyState', () => {
  it('renders with text', () => {
    const html = EmptyState('No data yet');
    expect(html).toContain('No data yet');
  });
});

describe('LawCard', () => {
  it('renders law with confidence', () => {
    const html = LawCard({ code: 'L-0001', statement: 'Bottleneck detected', confidence: 0.9, status: 'validated', evidence_count: 3 });
    expect(html).toContain('Bottleneck detected');
    expect(html).toContain('90%');
    expect(html).toContain('validated');
  });
});

describe('WhisperCard', () => {
  it('renders whisper with insight', () => {
    const html = WhisperCard({ insight: 'SSO at risk', priority: 'urgent', evidence: [1,2,3] });
    expect(html).toContain('SSO at risk');
    expect(html).toContain('urgent');
    expect(html).toContain('3 evidence signals');
  });
});
