// Background job: Verify predictions whose verifyDate has passed.
// Runs daily via cron (BullMQ scheduler in production).

import { prisma } from '@/lib/db';
import { log } from '@/lib/logger';
import { confidenceBucket, computeShr, isWithinShrBand } from '@/lib/server';

export async function verifyDuePredictions(): Promise<{
  verified: number;
  hits: number;
  misses: number;
  errors: number;
}> {
  const now = new Date();
  const result = { verified: 0, hits: 0, misses: 0, errors: 0 };

  const due = await prisma.prediction.findMany({
    where: {
      result: 'PENDING',
      verifyDate: { lte: now },
    },
    include: { decision: true, law: true },
  });

  log().info({ count: due.length }, 'Verifying due predictions');

  for (const prediction of due) {
    try {
      const actualOutcome = await fetchActualOutcome(prediction);

      await prisma.$transaction(async (tx) => {
        await tx.prediction.update({
          where: { id: prediction.id },
          data: { result: actualOutcome, verifiedAt: now },
        });

        await tx.calibrationEntry.create({
          data: {
            orgId: prediction.orgId,
            predictionId: prediction.id,
            predictedConfidence: prediction.confidence,
            bucket: prediction.bucket,
            actualOutcome,
            verifiedAt: now,
          },
        });
      });

      result.verified++;
      if (actualOutcome === 'HIT') result.hits++;
      else result.misses++;
    } catch (err) {
      result.errors++;
      log().error({ err, predictionId: prediction.id }, 'Prediction verification failed');
    }
  }

  // Recompute SHR for each affected org
  const affectedOrgs = [...new Set(due.map((p) => p.orgId))];
  for (const orgId of affectedOrgs) {
    await recomputeShr(orgId, now);
  }

  log().info(result, 'Prediction verification complete');
  return result;
}

async function fetchActualOutcome(prediction: any): Promise<'HIT' | 'MISS'> {
  // Production: call OEM verification engine
  // Scaffold: deterministic mock based on hash + confidence
  const crypto = await import('crypto');
  const hash = crypto.createHash('sha256').update(prediction.id).digest('hex');
  const rand = parseInt(hash.slice(0, 8), 16) / 0xffffffff;
  return rand < prediction.confidence ? 'HIT' : 'MISS';
}

async function recomputeShr(orgId: string, date: Date): Promise<void> {
  const thirtyDaysAgo = new Date(date.getTime() - 30 * 24 * 60 * 60 * 1000);

  const verified = await prisma.prediction.findMany({
    where: {
      orgId,
      result: { in: ['HIT', 'MISS'] },
      verifiedAt: { gte: thirtyDaysAgo },
    },
  });

  const hits = verified.filter((p) => p.result === 'HIT').length;
  const misses = verified.filter((p) => p.result === 'MISS').length;
  const shr = computeShr(hits, misses);
  const withinBand = isWithinShrBand(shr);

  await prisma.surpriseHitRate.upsert({
    where: { orgId_date: { orgId, date } },
    create: { orgId, date, shr30d: shr, totalPredictions: verified.length, hits, misses, withinBand },
    update: { shr30d: shr, totalPredictions: verified.length, hits, misses, withinBand },
  });

  if (!withinBand) {
    log().warn({ orgId, shr, hits, misses }, 'SHR out of band — alert CSE + model team');
  }

  log().info({ orgId, shr, total: verified.length, hits, misses, withinBand }, 'SHR recomputed');
}

if (require.main === module) {
  verifyDuePredictions()
    .then((result) => { log().info(result, 'Job complete'); process.exit(0); })
    .catch((err) => { log().error({ err }, 'Job failed'); process.exit(1); });
}
