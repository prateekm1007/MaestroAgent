// Maestro v6 — Prediction Ledger & SHR
// GET /api/predictions — list predictions (with filters)
// GET /api/predictions/shr — current Surprise Hit Rate + calibration curve

import { NextRequest, NextResponse } from 'next/server';
import { requireUser, ApiError, prisma, computeShr, isWithinShrBand, confidenceBucket, log } from '@/lib/server';

export async function GET(req: NextRequest) {
  try {
    const ctx = await requireUser();
    const url = new URL(req.url);
    const filter = url.searchParams.get('filter'); // 'pending' | 'verified' | 'all'
    const surface = url.searchParams.get('surface'); // 'shr' | 'calibration' | 'list'

    if (surface === 'shr') {
      // Compute current SHR + calibration curve
      const verified = await prisma.prediction.findMany({
        where: { orgId: ctx.orgId, result: { in: ['HIT', 'MISS'] } },
        orderBy: { verifiedAt: 'desc' },
        take: 100, // last 100 verified predictions
      });

      const hits = verified.filter(p => p.result === 'HIT').length;
      const misses = verified.filter(p => p.result === 'MISS').length;
      const shr = computeShr(hits, misses);
      const withinBand = isWithinShrBand(shr);

      // Build calibration curve: 10 buckets
      const buckets = Array.from({ length: 10 }, (_, i) => ({
        bucket: i,
        range: `${(i / 10).toFixed(1)}–${((i + 1) / 10).toFixed(1)}`,
        hits: 0, misses: 0, pending: 0,
      }));

      // All predictions (including pending) for calibration
      const all = await prisma.prediction.findMany({
        where: { orgId: ctx.orgId },
      });
      for (const p of all) {
        const b = buckets[p.bucket];
        if (p.result === 'HIT') b.hits++;
        else if (p.result === 'MISS') b.misses++;
        else b.pending++;
      }

      return NextResponse.json({
        shr30d: shr,
        totalVerified: verified.length,
        hits, misses,
        withinBand,
        targetBand: { min: 0.80, max: 0.88 },
        calibrationCurve: buckets,
      });
    }

    // Default: list predictions
    const where: any = { orgId: ctx.orgId };
    if (filter === 'pending') where.result = 'PENDING';
    else if (filter === 'verified') where.result = { in: ['HIT', 'MISS'] };

    const predictions = await prisma.prediction.findMany({
      where,
      orderBy: { madeAt: 'desc' },
      take: 50,
    });

    return NextResponse.json({ data: predictions });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message, code: err.code }, { status: err.status });
    }
    log.error({ err }, 'predictions fetch failed');
    return NextResponse.json({ error: 'Internal error', code: 'INTERNAL' }, { status: 500 });
  }
}
