'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, ArrowRight, ArrowLeft, Loader2, Sparkles } from 'lucide-react'
import { maestroApi, getToken, setToken, clearToken } from '@/lib/maestro-api'
import { Login } from '@/components/maestro/Login'

const API_BASE = typeof window !== 'undefined'
  ? (window.location.origin === 'https://web-production-d5c26.up.railway.app'
    ? 'https://maestroagent-production.up.railway.app'
    : 'http://localhost:8766')
  : 'https://maestroagent-production.up.railway.app'

interface CommitmentEntry {
  text: string
  entity: string
}

export default function OnboardingPage() {
  const [authenticated, setAuthenticated] = useState(false)
  const [step, setStep] = useState(1)
  const [commitments, setCommitments] = useState<CommitmentEntry[]>([
    { text: '', entity: '' },
    { text: '', entity: '' },
  ])
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (getToken()) setAuthenticated(true)
  }, [])

  const handleAuth = (token: string) => {
    setToken(token)
    setAuthenticated(true)
  }

  const updateCommitment = (i: number, field: 'text' | 'entity', value: string) => {
    const next = [...commitments]
    next[i] = { ...next[i], [field]: value }
    setCommitments(next)
  }

  const addCommitment = () => {
    if (commitments.length < 5) {
      setCommitments([...commitments, { text: '', entity: '' }])
    }
  }

  const removeCommitment = (i: number) => {
    if (commitments.length > 1) {
      setCommitments(commitments.filter((_, idx) => idx !== i))
    }
  }

  const validCommitments = commitments.filter(c => c.text.trim() && c.entity.trim())

  const handleSubmit = async () => {
    setSubmitting(true)
    setError('')
    try {
      const token = getToken()
      if (!token) {
        setError('Not authenticated')
        return
      }
      for (const c of validCommitments) {
        const res = await fetch(`${API_BASE}/api/signals`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            entity: c.entity.trim(),
            text: c.text.trim(),
            signal_type: 'commitment_made',
            timestamp: new Date().toISOString(),
          }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail || `Failed to create commitment for ${c.entity}`)
        }
      }
      setSubmitted(true)
      setStep(3)
    } catch (e: any) {
      setError(e.message || 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  if (!authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="max-w-md w-full">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Welcome to Maestro</h1>
            <p className="text-gray-500 mt-2">Let's get you set up in under 5 minutes.</p>
          </div>
          <Login onAuth={handleAuth} />
        </div>
      </div>
    )
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="max-w-md w-full text-center"
        >
          <div className="mx-auto w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-6">
            <Check className="h-8 w-8 text-green-600" />
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-gray-900">You're ready!</h1>
          <p className="text-gray-500 mt-2 mb-8">
            {validCommitments.length} commitment{validCommitments.length !== 1 ? 's' : ''} added to your ledger.
            Maestro will track these and remind you when they need attention.
          </p>
          <a
            href="/"
            className="inline-flex items-center gap-2 px-6 py-3 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors min-h-[44px]"
          >
            Go to Today
            <ArrowRight className="h-4 w-4" />
          </a>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-12">
      <div className="max-w-2xl mx-auto">
        {/* Progress indicator */}
        <div className="flex items-center gap-2 mb-8">
          {[1, 2].map((s) => (
            <div
              key={s}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                step >= s ? 'bg-gray-900' : 'bg-gray-200'
              }`}
            />
          ))}
        </div>

        <AnimatePresence mode="wait">
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
            >
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="h-5 w-5 text-blue-500" />
                <span className="text-sm font-medium text-blue-500">Step 1 of 2</span>
              </div>
              <h1 className="text-3xl font-semibold tracking-tight text-gray-900 mb-2">
                What have you promised recently?
              </h1>
              <p className="text-gray-500 mb-8">
                Enter 1-2 commitments you've made. These become the foundation of your Maestro ledger.
              </p>

              <div className="space-y-4">
                {commitments.map((c, i) => (
                  <div key={i} className="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-400">Commitment #{i + 1}</span>
                      {commitments.length > 1 && (
                        <button
                          onClick={() => removeCommitment(i)}
                          className="text-xs text-gray-400 hover:text-red-500 min-h-[44px] px-2"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                    <input
                      type="text"
                      placeholder="I will send the Q3 report by Friday"
                      value={c.text}
                      onChange={(e) => updateCommitment(i, 'text', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 min-h-[44px]"
                    />
                    <input
                      type="text"
                      placeholder="Who is it for? (e.g., Alex Chen)"
                      value={c.entity}
                      onChange={(e) => updateCommitment(i, 'entity', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 min-h-[44px]"
                    />
                  </div>
                ))}
              </div>

              {commitments.length < 5 && (
                <button
                  onClick={addCommitment}
                  className="mt-4 text-sm text-gray-500 hover:text-gray-700 min-h-[44px] px-2"
                >
                  + Add another
                </button>
              )}

              <div className="mt-8 flex justify-end">
                <button
                  onClick={() => setStep(2)}
                  disabled={validCommitments.length === 0}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors min-h-[44px]"
                >
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
            >
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="h-5 w-5 text-blue-500" />
                <span className="text-sm font-medium text-blue-500">Step 2 of 2</span>
              </div>
              <h1 className="text-3xl font-semibold tracking-tight text-gray-900 mb-2">
                Review and save
              </h1>
              <p className="text-gray-500 mb-8">
                Here's what Maestro will track. You can add more later.
              </p>

              <div className="bg-white rounded-lg border border-gray-200 divide-y">
                {validCommitments.map((c, i) => (
                  <div key={i} className="p-4 flex items-start gap-3">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                      <span className="text-xs font-medium text-blue-600">{i + 1}</span>
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">{c.text}</p>
                      <p className="text-xs text-gray-500 mt-1">To: {c.entity}</p>
                    </div>
                  </div>
                ))}
              </div>

              {error && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
                  {error}
                </div>
              )}

              <div className="mt-8 flex justify-between">
                <button
                  onClick={() => setStep(1)}
                  className="inline-flex items-center gap-2 px-4 py-3 text-gray-500 hover:text-gray-700 min-h-[44px]"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={submitting}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-40 transition-colors min-h-[44px]"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Check className="h-4 w-4" />
                      Save commitments
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
