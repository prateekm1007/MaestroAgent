'use client';

import { useState, ReactNode } from 'react';
import CommitmentDetail from './CommitmentDetail';

interface Commitment {
  commitment_id: string;
  entity: string;
  text: string;
  state: string;
  confidence: number;
  deadline_text?: string;
  source_signal_id?: string;
}

interface ClickableCardProps {
  children: ReactNode;
  commitment: Commitment;
  apiBase: string;
  token: string;
}

export default function ClickableCard({ children, commitment, apiBase, token }: ClickableCardProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div
        onClick={() => setOpen(true)}
        className="cursor-pointer transition-colors hover:bg-gray-50"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(true); } }}
      >
        {children}
      </div>

      {open && (
        <CommitmentDetail
          commitment={commitment}
          onClose={() => setOpen(false)}
          apiBase={apiBase}
          token={token}
        />
      )}
    </>
  );
}
