// Integration test: Decisions API — full HTTP path with real DB

import { POST, PATCH } from '@/app/api/decisions/[id]/route';
import { prisma } from '@/lib/db';

function mockRequest(body: any, headers: Record<string, string> = {}): Request {
  return new Request('http://localhost/api/decisions/test-id/simulate', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-user-id': 'user-test-1',
      'x-org-id': 'org-test-1',
      'x-user-role': 'CEO',
      'x-request-id': 'req-test-1',
      ...headers,
    },
    body: JSON.stringify(body),
  });
}

describe('Decisions API (integration)', () => {
  let testDecision: any;

  beforeAll(async () => {
    const org = await prisma.organization.create({
      data: { name: 'Test Org', domain: `test-${Date.now()}.com`, plan: 'DESIGN_PARTNER' },
    });

    testDecision = await prisma.decision.create({
      data: {
        orgId: org.id,
        title: 'Test Decision',
        description: 'Test',
        status: 'PROPOSED',
        decisionQuestion: 'What must I decide today?',
        predictedState: {},
        recommendation: 'Approve',
        confidence: 0.78,
        proposerId: 'user-test-1',
        stakeholders: [],
        linkedLaws: { connect: [] },
        simulatorConfig: {},
        simulatorOutputs: {},
      },
    });
  });

  afterAll(async () => {
    await prisma.decision.deleteMany({ where: { orgId: testDecision.orgId } });
    await prisma.organization.delete({ where: { id: testDecision.orgId } });
    await prisma.$disconnect();
  });

  test('POST /simulate returns predicted state', async () => {
    const req = mockRequest({
      config: { emea: 5, apac: 6, na: 2, parameters: {} },
      horizonDays: 90,
    });
    const res = await POST(req as any, { params: { id: testDecision.id } });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.outputs.emeaCapacity).toBeDefined();
    expect(data.outputs.confidence).toBeGreaterThan(0.5);
  });

  test('PATCH approve creates prediction atomically', async () => {
    const req = new Request(`http://localhost/api/decisions/${testDecision.id}`, {
      method: 'PATCH',
      headers: {
        'content-type': 'application/json',
        'x-user-id': 'user-test-1',
        'x-org-id': testDecision.orgId,
        'x-user-role': 'CEO',
        'x-request-id': 'req-test-2',
        'idempotency-key': `test-${Date.now()}`,
      },
      body: JSON.stringify({ action: 'APPROVE' }),
    });

    const res = await PATCH(req as any, { params: { id: testDecision.id } });
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.decision.status).toBe('APPROVED');
    expect(data.prediction).toBeDefined();
    expect(data.prediction.verifyDate).toBeDefined();

    const audit = await prisma.auditEvent.findFirst({
      where: { entityId: testDecision.id, action: 'decision.approve' },
    });
    expect(audit).not.toBeNull();
  });
});
