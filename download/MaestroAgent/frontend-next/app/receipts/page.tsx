// app/receipts/page.tsx — Receipts list page.

'use client';

import { useEffect, useState } from 'react';
import { receipts as receiptsApi } from '@/lib/api';
import { relativeTime } from '@/lib/utils';
import type { ExecutionReceipt } from '@/types';
import Link from 'next/link';
import { FileText, Shield } from 'lucide-react';

export default function ReceiptsPage() {
  const [receipts, setReceipts] = useState<ExecutionReceipt[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { receiptsApi.list().then(setReceipts).catch(() => {}).finally(() => setLoading(false)); }, []);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center gap-2 mb-6">
        <FileText className="w-5 h-5 text-brand-cyan" />
        <h1 className="text-2xl font-bold text-white">Receipts</h1>
        <span className="tag tag-cyan">{receipts.length}</span>
      </div>
      {loading ? <p className="text-fg-400">Loading...</p> : receipts.length === 0 ? <p className="text-fg-400">No receipts yet.</p> : (
        <div className="space-y-3">
          {receipts.map((r) => (
            <Link key={r.receiptId} href={`/receipts/${r.receiptId}`} className="panel panel-hover p-4 block">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-lg bg-brand-cyan/12 text-brand-cyan flex items-center justify-center"><Shield className="w-4 h-4" /></div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-fg-100 truncate">{r.goal}</div>
                  <div className="flex items-center gap-3 mt-1 text-[10px] text-fg-500">
                    <span className="font-mono">{r.receiptHash.slice(0, 16)}...</span>
                    <span>{relativeTime(r.createdAt)}</span>
                    <span>{r.policiesApplied?.length || 0} policies</span>
                    <span>{r.evidence?.length || 0} evidence</span>
                    <span className={`tag ${(r.outcome?.result === 'accepted') ? 'tag-cyan' : (r.outcome?.result === 'rejected') ? 'tag-rose' : 'tag-gray'}`}>{r.outcome?.result || 'pending'}</span>
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
