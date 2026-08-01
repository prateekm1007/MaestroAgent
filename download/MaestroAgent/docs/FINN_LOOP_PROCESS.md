# The Finn Loop - Continuous Development Process

## Overview
The Finn Loop is a systematic process for continuous feature development, testing, and deployment.

## The Loop Structure

1. IDENTIFY - What is the next highest-leverage feature/fix?
2. DESIGN - How will it work? What principles apply?
3. IMPLEMENT - Write the code
4. TEST - Verify it works locally
5. PUSH - Commit to main
6. DEPLOY - Railway auto-deploys
7. VERIFY - Test in production
8. DOCUMENT - Update docs, close tickets
9. NEXT - Return to step 1

## Step 1: IDENTIFY - What to Work On Next

### Priority Framework
P0 - Critical (Do Now): Production down, security vulnerability, data loss
P1 - High (Do This Week): Major feature broken, performance regression
P2 - Medium (Do This Sprint): Feature requests, UX improvements
P3 - Low (Backlog): Nice-to-have features, refactoring

### How to Identify
1. Check production monitoring (500 errors, latency spikes)
2. Check auditor reports (S1/S2 findings)
3. Check user feedback (requests, complaints)
4. Check governance principles (violations, new patterns)
5. Check strategic roadmap (next milestone, blocking issues)

## Step 2: DESIGN - How Will It Work

Before writing code:
1. Read relevant governance principles
2. Check for contradictions with existing principles
3. Design the solution (simplest approach, trade-offs, test plan)
4. Document the design (GitHub issue, acceptance criteria)

## Step 3: IMPLEMENT - Write the Code

Coding standards:
- Small, focused commits (one logical change per commit)
- Follow existing patterns (read similar code first)
- Write tests (unit, integration, regression)
- Document as you go (comments, docstrings)

## Step 4: TEST - Verify Locally

Test checklist:
- Unit tests pass
- Integration tests pass
- No linting errors
- No type errors
- Manual testing (if UI change)
- Edge cases tested
- Error cases tested

## Step 5: PUSH - Commit to Main

Commit message format:
type(scope): description

Types: feat, fix, perf, refactor, test, docs, chore

Example:
perf(ask): add Redis caching to reduce latency
- Check cache before computing response
- Cache with 5-minute TTL
- Expected improvement: 30-75s to <1s for cached queries
Closes #123

## Step 6: DEPLOY - Railway Auto-Deploys

Verify deployment:
1. Check Railway dashboard (service -> Deployments)
2. Check health endpoint
3. Check for errors in logs

If deployment fails:
1. Check logs for errors
2. Fix the issue
3. Push fix to main
4. Railway will auto-redeploy

## Step 7: VERIFY - Test in Production

Verification checklist:
- Feature works in production
- No new errors in logs
- Performance meets targets
- No regressions in existing features
- Monitoring shows healthy metrics

If verification fails:
1. Identify the issue
2. Decide: fix forward or rollback
3. If fix forward: implement fix, push, redeploy
4. If rollback: git revert HEAD, push, wait for redeploy

## Step 8: DOCUMENT - Update Docs

Documentation checklist:
- Update README if needed
- Update API docs if endpoints changed
- Update deployment checklist if needed
- Close GitHub issue
- Comment on issue with results
- Update governance principles if new patterns emerged

## Step 9: NEXT - Return to Step 1

Review what we learned:
1. What worked well? (design, tests, deployment)
2. What could be improved? (edge cases, unexpected issues)
3. What is the next priority? (check priority framework again)

## Automation Hooks

### Continuous Integration (runs on every push)
1. Nora Test - commitment intelligence accuracy
2. Performance Test - Ask latency <3s
3. Sanitization Test - no leaked guard strings

### Continuous Monitoring (runs every 6 hours)
1. Production Health Check - all endpoints return 200
2. Data Hygiene Check - no PII, no token leaks

### Alerting (triggers on failures)
- Any endpoint returns 500
- Latency exceeds targets
- Nora test fails
- Sanitization test fails
- PII detected in responses

## Governance Integration

### Before Each Loop
1. Read relevant principles
2. Check for contradictions
3. Decide if new principles needed

### After Each Loop
1. Document learnings
2. Update governance if needed

## Example Loop Executions

### Loop 1: Fix Ask Latency
1. IDENTIFY: Auditor found 30-75s latency (P1)
2. DESIGN: Add caching, pre-computation, streaming
3. IMPLEMENT: Write caching code, add tests
4. TEST: Run tests locally, verify <3s
5. PUSH: Commit to main
6. DEPLOY: Railway auto-deploys
7. VERIFY: Test in production, confirm <3s
8. DOCUMENT: Close issue, update docs
9. NEXT: What is next?

### Loop 2: Fix Commitment Intelligence
1. IDENTIFY: Nora test 3/7 (P1)
2. DESIGN: Patch classifier
3. IMPLEMENT: Write classifier patch
4. TEST: Run Nora test, verify 7/7
5. PUSH: Commit to main
6. DEPLOY: Railway auto-deploys
7. VERIFY: Test in production, confirm 7/7
8. DOCUMENT: Close issue, update docs
9. NEXT: What is next?

### Loop 3: Add Email Composition
1. IDENTIFY: Users want follow-up emails (P2)
2. DESIGN: Clickable cards, thread view, draft generation
3. IMPLEMENT: Backend API, frontend components
4. TEST: Test all endpoints, test UI
5. PUSH: Commit to main
6. DEPLOY: Railway auto-deploys
7. VERIFY: Test full flow in production
8. DOCUMENT: Update docs, create deployment checklist
9. NEXT: What is next?

## Success Metrics

### Per Loop
- Feature works as designed
- All tests pass
- No regressions
- Documentation updated
- Issue closed

### Per Sprint (5 loops)
- 5 features/fixes shipped
- All P0/P1 issues resolved
- Performance improved
- User satisfaction increased

### Per Quarter (30 loops)
- Product at 9/10 on all benchmarks
- No P0/P1 issues in production
- 50+ features/fixes shipped
- Strong user retention
- Ready for scale

## Conclusion

The Finn Loop is a discipline. Every loop:
- Starts with identification (what matters most?)
- Ends with documentation (what did we learn?)
- Is governed by principles (not ad-hoc decisions)
- Is verified in production (not just local tests)
- Feeds into the next loop (continuous improvement)

The loop never stops. The product never stops improving.
