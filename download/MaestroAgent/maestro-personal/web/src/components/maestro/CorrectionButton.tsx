'use client'

import { useState, useRef, useEffect } from 'react'
import { MoreVertical, Check, X, AlertTriangle, Edit3, Loader2 } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface CorrectionButtonProps {
  signalId: string
  apiBase: string
  token: string
  onCorrected?: () => void
}

type Action = 'dismiss' | 'dispute' | 'edit_text'
type ActionStatus = 'idle' | 'submitting' | 'success' | 'error'

const ACTIONS: { id: Action; label: string; icon: typeof Check; color: string }[] = [
  { id: 'dismiss', label: 'Not a commitment', icon: X, color: '#6B7280' },
  { id: 'dispute', label: 'This is wrong', icon: AlertTriangle, color: '#DC2626' },
  { id: 'edit_text', label: 'Edit text', icon: Edit3, color: '#2563EB' },
]

export function CorrectionButton({ signalId, apiBase, token, onCorrected }: CorrectionButtonProps) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState('')
  const [status, setStatus] = useState<ActionStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
        setEditing(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const submitCorrection = async (action: Action, newText?: string) => {
    setStatus('submitting')
    setErrorMsg('')
    try {
      const params = new URLSearchParams({ action })
      if (newText) params.set('new_text', newText)
      const res = await fetch(
        `${apiBase}/api/signals/${signalId}/correct?${params}`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` } }
      )
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      setStatus('success')
      setOpen(false)
      setEditing(false)
      onCorrected?.()
      // Reset status after 2s
      setTimeout(() => setStatus('idle'), 2000)
    } catch (e: any) {
      setStatus('error')
      setErrorMsg(e.message || 'Correction failed')
      setTimeout(() => setStatus('idle'), 3000)
    }
  }

  if (status === 'submitting') {
    return (
      <div className="flex items-center gap-1 text-xs text-gray-400">
        <Loader2 className="h-3 w-3 animate-spin" />
        <span>Saving...</span>
      </div>
    )
  }

  if (status === 'success') {
    return (
      <div className="flex items-center gap-1 text-xs text-green-600">
        <Check className="h-3 w-3" />
        <span>Corrected</span>
      </div>
    )
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen(!open)}
        className="p-1 rounded hover:bg-gray-200 transition-colors"
        title="Correct this commitment"
      >
        <MoreVertical className="h-3.5 w-3.5 text-gray-400" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="absolute right-0 top-7 z-20 bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[180px]"
          >
            {!editing ? (
              ACTIONS.map((a) => (
                <button
                  key={a.id}
                  onClick={() => {
                    if (a.id === 'edit_text') {
                      setEditing(true)
                      setEditText('')
                    } else {
                      submitCorrection(a.id)
                    }
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors text-left"
                >
                  <a.icon className="h-3.5 w-3.5" style={{ color: a.color }} />
                  <span>{a.label}</span>
                </button>
              ))
            ) : (
              <div className="p-3 space-y-2">
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  placeholder="Corrected text..."
                  className="w-full text-sm border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                  rows={3}
                  autoFocus
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => submitCorrection('edit_text', editText)}
                    disabled={!editText.trim()}
                    className="flex-1 px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
            {errorMsg && (
              <div className="px-3 py-1 text-xs text-red-500">{errorMsg}</div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
