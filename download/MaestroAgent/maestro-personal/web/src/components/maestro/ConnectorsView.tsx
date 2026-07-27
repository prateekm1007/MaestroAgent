'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Mail, Calendar, MessageSquare, Github, Globe, CheckCircle2, Plus } from 'lucide-react'

interface Connector {
  id: string
  name: string
  description: string
  icon: React.ReactNode
  connected: boolean
  connectedAt?: string
  commitmentsIngested?: number
  category: 'email' | 'calendar' | 'chat' | 'code' | 'custom'
}

const connectors: Connector[] = [
  {
    id: 'gmail',
    name: 'Gmail',
    description: 'Sync emails and extract commitments from your inbox',
    icon: <Mail className="h-5 w-5" />,
    connected: true,
    connectedAt: '2026-07-26',
    commitmentsIngested: 5,
    category: 'email',
  },
  {
    id: 'calendar',
    name: 'Google Calendar',
    description: 'Upcoming meetings, pre-call briefings, deadline tracking',
    icon: <Calendar className="h-5 w-5" />,
    connected: true,
    connectedAt: '2026-07-23',
    commitmentsIngested: 0,
    category: 'calendar',
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Extract commitments from Slack messages and threads',
    icon: <MessageSquare className="h-5 w-5" />,
    connected: false,
    category: 'chat',
  },
  {
    id: 'github',
    name: 'GitHub',
    description: 'Track code commitments from issues and pull requests',
    icon: <Github className="h-5 w-5" />,
    connected: false,
    category: 'code',
  },
  {
    id: 'yahoo_mail',
    name: 'Yahoo Mail',
    description: 'Sync Yahoo Mail and extract commitments',
    icon: <Mail className="h-5 w-5" />,
    connected: false,
    category: 'email',
  },
  {
    id: 'microsoft_mail',
    name: 'Outlook / Hotmail',
    description: 'Sync Microsoft Mail and extract commitments',
    icon: <Mail className="h-5 w-5" />,
    connected: false,
    category: 'email',
  },
  {
    id: 'work_email',
    name: 'Work Email (IMAP)',
    description: 'Connect any work email via IMAP — ProtonMail, custom domain, etc.',
    icon: <Globe className="h-5 w-5" />,
    connected: false,
    category: 'custom',
  },
]

const categoryLabels: Record<string, string> = {
  email: 'Email',
  calendar: 'Calendar',
  chat: 'Chat',
  code: 'Code',
  custom: 'Custom',
}

export function ConnectorsView() {
  const connected = connectors.filter((c) => c.connected)
  const available = connectors.filter((c) => !c.connected)

  // Group available by category
  const grouped = available.reduce((acc, c) => {
    if (!acc[c.category]) acc[c.category] = []
    acc[c.category].push(c)
    return acc
  }, {} as Record<string, Connector[]>)

  return (
    <div className="max-w-2xl mx-auto space-y-10">
      {/* Connected — Tufte: direct, minimal */}
      {connected.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">
            Connected ({connected.length})
          </p>
          <div className="space-y-3">
            {connected.map((c, i) => (
              <ConnectorCard key={c.id} connector={c} index={i} connected />
            ))}
          </div>
        </div>
      )}

      {/* Available — grouped by category */}
      {Object.entries(grouped).map(([category, items]) => (
        <div key={category}>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">
            {categoryLabels[category] || category}
          </p>
          <div className="space-y-3">
            {items.map((c, i) => (
              <ConnectorCard key={c.id} connector={c} index={i} connected={false} />
            ))}
          </div>
        </div>
      ))}

      {/* Empty state messaging — Tufte: calm, not broken */}
      {connected.length === 0 && (
        <div className="text-center py-12">
          <p className="text-lg text-gray-500 mb-2">No connectors yet.</p>
          <p className="text-sm text-gray-400 max-w-md mx-auto">
            Connect Gmail, Calendar, or Slack to start tracking your real commitments.
            MaestroAgent extracts promises from your actual communications.
          </p>
        </div>
      )}
    </div>
  )
}

function ConnectorCard({
  connector,
  index,
  connected,
}: {
  connector: Connector
  index: number
  connected: boolean
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: index * 0.04, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        'flex items-center gap-4 py-4 px-5 rounded-xl transition-colors',
        connected
          ? 'bg-white border border-gray-100'
          : 'bg-gray-50/50 hover:bg-gray-50 cursor-pointer',
      )}
    >
      {/* Icon — Bertin: visual variable for category */}
      <div className={cn(
        'flex-shrink-0 flex items-center justify-center h-10 w-10 rounded-lg',
        connected ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-500',
      )}>
        {connector.icon}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-sm text-gray-900">{connector.name}</h3>
          {connected && (
            <div className="flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              <span className="text-xs text-green-600 font-medium">Active</span>
            </div>
          )}
        </div>
        <p className="text-xs text-gray-400 mt-0.5 leading-relaxed">
          {connector.description}
        </p>
        {connected && connector.commitmentsIngested !== undefined && (
          <p className="text-xs text-gray-400 mt-1 tabular-nums">
            {connector.commitmentsIngested} commitments ingested · connected {connector.connectedAt}
          </p>
        )}
      </div>

      {/* Action */}
      <div className="flex-shrink-0">
        {connected ? (
          <button className="text-xs text-gray-400 hover:text-gray-600 transition-colors px-3 py-1.5 rounded-lg hover:bg-gray-50">
            Disconnect
          </button>
        ) : (
          <button className="flex items-center gap-1 text-xs font-medium text-gray-600 hover:text-gray-900 transition-colors px-3 py-1.5 rounded-lg bg-white border border-gray-200 hover:border-gray-300">
            <Plus className="h-3 w-3" />
            Connect
          </button>
        )}
      </div>
    </motion.div>
  )
}
