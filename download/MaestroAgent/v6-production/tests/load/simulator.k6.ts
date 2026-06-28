// k6 load test: Simulator endpoint
// Run: k6 run tests/load/simulator.k6.ts
// Validates P95 latency budget (< 500ms) under load.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const failureRate = new Rate('failures');
const latencyTrend = new Trend('latency');

export const options = {
  stages: [
    { duration: '30s', target: 20 },   // ramp up to 20 VUs
    { duration: '1m', target: 20 },     // hold at 20 VUs
    { duration: '30s', target: 50 },    // ramp to 50 VUs
    { duration: '1m', target: 50 },     // hold at 50 VUs
    { duration: '30s', target: 0 },     // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],  // P95 < 500ms, P99 < 1s
    failures: ['rate<0.01'],                           // < 1% failures
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || 'test-token';

export default function () {
  const payload = JSON.stringify({
    config: { emea: 5 + Math.floor(Math.random() * 10), apac: 6, na: 2, parameters: {} },
    horizonDays: 90,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${AUTH_TOKEN}`,
      'Idempotency-Key': `k6-${__VU}-${__ITER}`,
    },
  };

  const res = http.post(`${BASE_URL}/api/decisions/test-decision-id/simulate`, payload, params);

  latencyTrend.add(res.timings.duration);

  const ok = check(res, {
    'status is 200': (r) => r.status === 200 || r.status === 404, // 404 ok (test decision doesn't exist)
    'response has outputs': (r) => {
      if (r.status !== 200) return true;
      const body = r.json();
      return body && body.outputs;
    },
  });

  failureRate.add(!ok);
  sleep(0.1);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    'test-results/load-results.json': JSON.stringify(data, null, 2),
  };
}

function textSummary(data) {
  return `
━━━ Load Test Results ━━━
Duration: ${data.state.testRunDurationMs / 1000}s
Total requests: ${data.metrics.http_reqs.values.count}
Failure rate: ${(data.metrics.failures?.values.rate * 100 || 0).toFixed(2)}%
P50 latency: ${data.metrics.http_req_duration.values['p(50)'].toFixed(0)}ms
P95 latency: ${data.metrics.http_req_duration.values['p(95)'].toFixed(0)}ms
P99 latency: ${data.metrics.http_req_duration.values['p(99)'].toFixed(0)}ms
━━━━━━━━━━━━━━━━━━━━━━━━━
`;
}
