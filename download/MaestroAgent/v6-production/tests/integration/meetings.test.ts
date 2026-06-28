// Integration test: Meetings API — consent gate, sanitization, idempotency

import { POST } from '@/app/api/meetings/[id]/route';
import { prisma } from '@/lib/db';

function makeRequest(meetingId: string, chunk: any, headers: Record<string, string> = {}): Request {
  return new Request(`http://localhost/api/meetings/${meetingId}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-user-id': 'user-test-1',
      'x-org-id': 'org-test-1',
      'x-user-role': 'CEO',
      'x-request-id': 'req-test-1',
      ...headers,
    },
    body: JSON.stringify({ meetingId, chunk }),
  });
}

describe('Meetings API (integration)', () => {
  let orgId: string;
  let meetingWithConsent: any;
  let meetingWithoutConsent: any;

  beforeAll(async () => {
    const org = await prisma.organization.create({
      data: { name: 'Test Org', domain: `test-meetings-${Date.now()}.com`, plan: 'DESIGN_PARTNER' },
    });
    orgId = org.id;

    meetingWithConsent = await prisma.meeting.create({
      data: {
        orgId,
        title: 'Test Meeting (consented)',
        startedAt: new Date(),
        status: 'ACTIVE',
        participants: [
          { entityId: 'user-test-1', name: 'Jane', role: 'CEO', isExternal: false,
            consentMethod: 'EXPLICIT', consentedAt: new Date().toISOString() },
          { entityId: 'user-test-2', name: 'Chris', role: 'CTO', isExternal: false,
            consentMethod: 'EXPLICIT', consentedAt: new Date().toISOString() },
        ],
        consentLoggedAt: new Date(),
        transcript: [],
        synthesisStatus: 'PENDING',
      },
    });

    meetingWithoutConsent = await prisma.meeting.create({
      data: {
        orgId,
        title: 'Test Meeting (no consent)',
        startedAt: new Date(),
        status: 'ACTIVE',
        participants: [
          { entityId: 'user-test-1', name: 'Jane', role: 'CEO', isExternal: false,
            consentMethod: 'EXPLICIT', consentedAt: new Date().toISOString() },
          { entityId: 'user-test-2', name: 'Chris', role: 'CTO', isExternal: false,
            consentMethod: 'EXPLICIT' }, // no consentedAt
        ],
        transcript: [],
        synthesisStatus: 'PENDING',
      },
    });
  });

  afterAll(async () => {
    await prisma.meeting.deleteMany({ where: { orgId } });
    await prisma.organization.delete({ where: { id: orgId } });
    await prisma.$disconnect();
  });

  test('rejects transcript chunk when consent not complete', async () => {
    const req = makeRequest(meetingWithoutConsent.id, {
      ts: '09:01', speakerId: 'u1', speakerName: 'Jane', text: 'Hello',
    });
    const res = await POST(req as any, { params: { id: meetingWithoutConsent.id } });
    expect(res.status).toBe(403);
    const data = await res.json();
    expect(data.code).toBe('CONSENT_REQUIRED');
  });

  test('accepts transcript chunk when consent complete', async () => {
    const req = makeRequest(meetingWithConsent.id, {
      ts: '09:01', speakerId: 'user-test-1', speakerName: 'Jane', text: 'Hello world',
    }, { 'idempotency-key': `chunk-${Date.now()}` });
    const res = await POST(req as any, { params: { id: meetingWithConsent.id } });
    expect(res.status).toBe(200);
  });

  test('sanitizes XSS in transcript text', async () => {
    const req = makeRequest(meetingWithConsent.id, {
      ts: '09:02', speakerId: 'user-test-1', speakerName: 'Jane',
      text: '<script>alert("xss")</script>Hello',
    }, { 'idempotency-key': `xss-${Date.now()}` });
    const res = await POST(req as any, { params: { id: meetingWithConsent.id } });
    expect(res.status).toBe(200);

    // Verify script tag was stripped
    const meeting = await prisma.meeting.findUnique({ where: { id: meetingWithConsent.id } });
    const transcript = meeting?.transcript as any[];
    const lastLine = transcript[transcript.length - 1];
    expect(lastLine.text).not.toContain('<script>');
    expect(lastLine.text).toContain('Hello');
  });

  test('rejects non-participant', async () => {
    const req = new Request(`http://localhost/api/meetings/${meetingWithConsent.id}`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-user-id': 'user-not-participant',
        'x-org-id': orgId,
        'x-user-role': 'CEO',
        'x-request-id': 'req-x',
      },
      body: JSON.stringify({
        meetingId: meetingWithConsent.id,
        chunk: { ts: '09:03', speakerId: 'x', speakerName: 'X', text: 'hi' },
      }),
    });
    const res = await POST(req as any, { params: { id: meetingWithConsent.id } });
    expect(res.status).toBe(403);
  });

  test('idempotency: same key returns cached response', async () => {
    const idemKey = 'idem-meeting-1';
    const chunk = { ts: '09:04', speakerId: 'user-test-1', speakerName: 'Jane', text: 'Test' };

    const req1 = makeRequest(meetingWithConsent.id, chunk, { 'idempotency-key': idemKey });
    const res1 = await POST(req1 as any, { params: { id: meetingWithConsent.id } });
    expect(res1.status).toBe(200);

    const req2 = makeRequest(meetingWithConsent.id, chunk, { 'idempotency-key': idemKey });
    const res2 = await POST(req2 as any, { params: { id: meetingWithConsent.id } });
    expect(res2.status).toBe(200);

    // Both should return the same body
    const data1 = await res1.json();
    const data2 = await res2.json();
    expect(data1).toEqual(data2);
  });
});
