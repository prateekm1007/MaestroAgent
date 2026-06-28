// Maestro v6 — Unit tests for the meeting intelligence engine
// Tests transcript processing, objection detection, consent verification, synthesis.

import {
  processTranscriptChunk, verifyConsent, logConsent, enrichDossier, synthesizeMeeting,
  type TranscriptChunk, type MeetingParticipant,
} from '@/lib/meeting-engine';
import type { Meeting, OrgLaw } from '@/types/domain';

const mockLaws: OrgLaw[] = [
  {
    id: '1', orgId: 'org-1', code: 'L-0014',
    statement: 'APAC support ratio below 1:14 predicts churn +14% within 2 quarters',
    confidence: 0.81, evidenceCount: 9, counterExamples: 0,
    knownToLeadership: false, status: 'UNKNOWN_TO_LEADERSHIP',
    evidence: [],
  },
  {
    id: '2', orgId: 'org-1', code: 'L-0007',
    statement: 'Eng velocity drops 22% in weeks following >3 P1 incidents',
    confidence: 0.91, evidenceCount: 12, counterExamples: 0,
    knownToLeadership: true, status: 'VALIDATED',
    evidence: [],
  },
];

describe('Meeting Intelligence Engine', () => {

  describe('processTranscriptChunk()', () => {
    const baseChunk: TranscriptChunk = {
      ts: '09:01', speakerId: 'u1', speakerName: 'Jane', text: '',
    };

    it('detects objections', () => {
      const result = processTranscriptChunk(
        { ...baseChunk, text: 'I dissent. APAC pipeline is up 41% QoQ.' },
        mockLaws,
      );
      expect(result.objections.length).toBe(1);
      expect(result.objections[0].text).toContain('dissent');
    });

    it('detects action items', () => {
      const result = processTranscriptChunk(
        { ...baseChunk, text: "I'll update the hiring plan by Nov 13" },
        mockLaws,
      );
      expect(result.actionItems.length).toBeGreaterThan(0);
    });

    it('invokes laws when keywords appear', () => {
      const result = processTranscriptChunk(
        { ...baseChunk, text: 'APAC support is below threshold.' },
        mockLaws,
      );
      const codes = result.invokedLaws.map(l => l.lawCode);
      expect(codes).toContain('L-0014');
    });

    it('invokes L-0007 when P1 mentioned', () => {
      const result = processTranscriptChunk(
        { ...baseChunk, text: 'We had 3 P1 incidents last week.' },
        mockLaws,
      );
      const codes = result.invokedLaws.map(l => l.lawCode);
      expect(codes).toContain('L-0007');
    });

    it('detects region mentions', () => {
      const result = processTranscriptChunk(
        { ...baseChunk, text: 'EMEA and APAC are both growing.' },
        mockLaws,
      );
      const names = result.mentions.map(m => m.name);
      expect(names).toContain('EMEA');
      expect(names).toContain('APAC');
    });

    it('suggests simulation when compromise mentioned', () => {
      const result = processTranscriptChunk(
        { ...baseChunk, text: "What if we go with Priya's compromise?" },
        mockLaws,
      );
      expect(result.suggestions.some(s => s.kind === 'RUN_SIMULATION')).toBe(true);
    });

    it('logs predictions when approval detected', () => {
      const result = processTranscriptChunk(
        { ...baseChunk, text: 'Approved. Lets go with the compromise.' },
        mockLaws,
      );
      expect(result.predictions.length).toBeGreaterThan(0);
    });

    it('does not double-count repeated mentions in one chunk', () => {
      const result = processTranscriptChunk(
        { ...baseChunk, text: 'APAC APAC APAC' },
        mockLaws,
      );
      const apacMentions = result.mentions.filter(m => m.name === 'APAC');
      expect(apacMentions.length).toBe(1);
    });
  });

  describe('verifyConsent()', () => {
    it('returns false if any participant has not consented', () => {
      const participants: MeetingParticipant[] = [
        { entityId: '1', name: 'A', role: 'CEO', isExternal: false, consentMethod: 'EXPLICIT', consentedAt: '2024-01-01' },
        { entityId: '2', name: 'B', role: 'CTO', isExternal: false, consentMethod: 'EXPLICIT' },
      ];
      expect(verifyConsent(participants)).toBe(false);
    });

    it('returns true when all participants have consented', () => {
      const participants: MeetingParticipant[] = [
        { entityId: '1', name: 'A', role: 'CEO', isExternal: false, consentMethod: 'EXPLICIT', consentedAt: '2024-01-01' },
        { entityId: '2', name: 'B', role: 'CTO', isExternal: false, consentMethod: 'EXPLICIT', consentedAt: '2024-01-01' },
      ];
      expect(verifyConsent(participants)).toBe(true);
    });
  });

  describe('logConsent()', () => {
    it('sets consentLoggedAt only when all consented', () => {
      const unconsented: MeetingParticipant[] = [
        { entityId: '1', name: 'A', role: 'CEO', isExternal: false, consentMethod: 'EXPLICIT' },
      ];
      const result = logConsent('m1', unconsented);
      expect(result.allConsented).toBe(false);
      expect(result.consentLoggedAt).toBeUndefined();

      const consented: MeetingParticipant[] = [
        { entityId: '1', name: 'A', role: 'CEO', isExternal: false, consentMethod: 'EXPLICIT', consentedAt: '2024-01-01' },
      ];
      const result2 = logConsent('m1', consented);
      expect(result2.allConsented).toBe(true);
      expect(result2.consentLoggedAt).toBeDefined();
    });
  });

  describe('enrichDossier()', () => {
    it('calls external APIs when provided', async () => {
      const linkedin = jest.fn().mockResolvedValue('Ex-Stripe engineer');
      const twitter = jest.fn().mockResolvedValue('Active poster');
      const news = jest.fn().mockResolvedValue({ summary: 'Recent press', count: 3 });

      const result = await enrichDossier(
        { entityId: '1', name: 'Raj Patel', linkedinUrl: 'https://linkedin.com/in/raj', twitterHandle: 'rajpatel' },
        { linkedin, twitter, news },
      );

      expect(linkedin).toHaveBeenCalledWith('https://linkedin.com/in/raj');
      expect(twitter).toHaveBeenCalledWith('rajpatel');
      expect(news).toHaveBeenCalledWith('Raj Patel');
      expect(result.linkedin?.summary).toBe('Ex-Stripe engineer');
      expect(result.twitter?.summary).toBe('Active poster');
      expect(result.news?.mentionCount).toBe(3);
    });

    it('skips external APIs when URLs not provided', async () => {
      const result = await enrichDossier(
        { entityId: '1', name: 'Anonymous' },
        { linkedin: jest.fn(), twitter: jest.fn(), news: jest.fn() },
      );
      expect(result.linkedin).toBeUndefined();
      expect(result.twitter).toBeUndefined();
    });
  });

  describe('synthesizeMeeting()', () => {
    it('extracts decisions from approval lines', () => {
      const meeting: Meeting = {
        id: 'm1', orgId: 'org-1', title: 'Q3 Hiring',
        startedAt: '2024-11-12T09:00:00Z', status: 'ENDED',
        participants: [], transcript: [
          { ts: '09:01', speakerId: '1', speakerName: 'Jane', text: 'Discussion', highlights: [] },
          { ts: '09:09', speakerId: '1', speakerName: 'Jane', text: 'Approved. -3 EMEA, +2 APAC.', highlights: [] },
        ],
        synthesisStatus: 'PENDING',
      };

      const result = synthesizeMeeting(meeting, [], 0.83);
      expect(result.decisions.length).toBe(1);
      expect(result.decisions[0].description).toContain('Approved');
      expect(result.followUpDrafts.length).toBe(4);
      expect(result.followUpDrafts.map(d => d.type)).toEqual(
        expect.arrayContaining(['SLACK', 'EMAIL', 'JIRA', 'CALENDAR'])
      );
    });

    it('projects SHR impact', () => {
      const meeting: Meeting = {
        id: 'm1', orgId: 'org-1', title: 'Test',
        startedAt: '2024-11-12T09:00:00Z', status: 'ENDED',
        participants: [], transcript: [], synthesisStatus: 'PENDING',
      };
      const result = synthesizeMeeting(meeting, [
        {
          highlights: [], objections: [], actionItems: [],
          invokedLaws: [], mentions: [],
          predictions: [
            { statement: 'P1', confidence: 0.78, verifyDate: '2025-02-12' },
            { statement: 'P2', confidence: 0.84, verifyDate: '2025-02-12' },
          ],
          suggestions: [],
        },
      ], 0.83);

      expect(result.shrImpact.currentShr).toBe(0.83);
      expect(result.shrImpact.projectedShr).toBeGreaterThan(0);
    });
  });
});
