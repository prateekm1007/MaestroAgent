// app/receipts/[id]/page.tsx — Receipt detail page.

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { receipts as receiptsApi } from '@/lib/api';
import { relativeTime, formatBytes } from '@/lib/utils';
import type { ExecutionReceipt } from '@/types';
import { Shield, FileCheck, AlertTriangle, Hash } from 'lucide-react';

export default function ReceiptDetailPage() {
  const params = useParams();
  const receiptId = params.id as string;
  const [receipt, setReceipt] = useState<ExecutionReceipt | null>(null);
  const [verified, setVerified] = useState<boolean | null>(null);

  useEffect(() => {
    receiptsApi.get(receiptId).then(setReceipt).catch(() => {});
    receiptsApi.verify(receiptId).then((r: any) => setVerified(r.valid)).catch(() => {});
  }, [receiptId]);

  if (!receipt) return <div className="p-6 text-fg-400">Loading receipt...</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <div className="text-[10px] font-bold text-fg-500 uppercase tracking-wider mb-1">Execution Receipt</div>
        <h1 className="text-xl font-bold text-white">{receipt.goal}</h1>
        <div className="flex items-center gap-2 mt-2">
          <div className="flex items-center gap-1 text-xs text-fg-400 font-mono"><Hash className="w-3 h-3" />{receipt.receiptHash.slice(0, 24)}...</div>
          {verified !== null && (
            <span className={`tag ${verified ? 'tag-cyan' : 'tag-rose'}`}>{verified ? 'Verified' : 'Tampered'}</span>
          )}
        </div>
      </div>

      {receipt.plan && (
        <div className="panel p-4">
          <h2 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-3">Plan</h2>
          <pre className="text-xs text-fg-300 font-mono overflow-x-auto">{JSON.stringify(receipt.plan, null, 2)}</pre>
        </div>
      )}

      {receipt.policiesApplied && receipt.policiesApplied.length > 0 && (
        <div className="panel p-4">
          <h2 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-3">Policies Applied ({receipt.policiesApplied.length})</h2>
          <div className="space-y-2">
            {receipt.policiesApplied.map((p, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <FileCheck className="w-3.5 h-3.5 text-brand-cyan flex-shrink-0" />
                <span className="text-fg-200 flex-1">{p.rule}</span>
                <span className={`tag ${p.enforcement === 'constitutional' ? 'tag-rose' : p.enforcement === 'mandatory' ? 'tag-amber' : 'tag-gray'}`}>{p.enforcement}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {receipt.evidence && receipt.evidence.length > 0 && (
        <div className="panel p-4">
          <h2 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-3">Evidence ({receipt.evidence.length})</h2>
          <div className="space-y-2">
            {receipt.evidence.map((ev, i) => (
              <div key={i} className="flex items-start gap-2 text-sm bg-white/[0.02] rounded p-2 border-l-2 border-brand-cyan/30">
                <span className="tag tag-cyan flex-shrink-0">{ev.type}</span>
                <span className="text-fg-300 flex-1">{ev.description}</span>
                {ev.reviewer && <span className="text-fg-500 text-xs">{ev.reviewer}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {receipt.exceptions && receipt.exceptions.length > 0 && (
        <div className="panel p-4 border-brand-rose/20">
          <h2 className="text-xs font-bold text-brand-rose uppercase tracking-wider mb-3">Exceptions ({receipt.exceptions.length})</h2>
          <div className="space-y-2">
            {receipt.exceptions.map((ex, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <AlertTriangle className="w-3.5 h-3.5 text-brand-rose" />
                <span className="text-fg-200">{ex.policyId}: {ex.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {receipt.execution && (
        <div className="panel p-4">
          <h2 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-3">Execution Details</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div><span className="text-fg-500">Duration:</span> <span className="text-fg-100">{(receipt.execution.durationMs / 1000).toFixed(1)}s</span></div>
            <div><span className="text-fg-500">Artifacts:</span> <span className="text-fg-100">{receipt.execution.artifactCount}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}
