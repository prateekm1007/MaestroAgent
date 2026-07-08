# Naked-LLM Comparison Summary

**Executed:** 2026-07-08T22:51:48.989117+00:00
**Provider:** z-ai
**Model:** glm-4-plus
**Command:** `z-ai chat --prompt <prompt> -o /tmp/llm_resp.json (per query, 20 calls)`
**Maestro unique responses:** 19/20
**LLM unique responses:** 1/20

## Results

| System | Score | Percentage |
|--------|-------|------------|
| Maestro | 200/240 | 83.3% |
| LLM (glm-4-plus) | 120/240 | 50.0% |

## Win/Loss

- Maestro wins: 20/20
- LLM wins: 0/20
- Ties: 0/20

## Dimension Advantages

| Dimension | Maestro Avg | LLM Avg | Advantage |
|-----------|------------|---------|-----------|
| factual_accuracy | 3.0 | 2.0 | maestro |
| evidence_traceability | 3.0 | 2.0 | maestro |
| uncertainty_honesty | 2.0 | 0.0 | maestro |
| intervention_restraint | 2.0 | 2.0 | tie |

## Per-Query Maestro Responses (first 5)

### Q01 (factual_recall)
**Query:** What did we promise CustomerA?
**Response:** **Regarding your question about promises to CustomerA:**
  • Deliver SSO by Friday

**CustomerA: Deliver SSO by Friday**
State: material | Epistemic: ...
**Score:** 10/12 (evidence=4, unknowns=1)

### Q02 (factual_recall)
**Query:** When is the CustomerA renewal meeting?
**Response:** **Regarding the timing of the CustomerA meeting:**
  • Renewal meeting tomorrow (evidence: f3bbeff6-5aab-498a-80f7-6fe9557ef727)
  Query: 'When is the...
**Score:** 10/12 (evidence=4, unknowns=1)

### Q03 (factual_recall)
**Query:** What did Security say about the SSO?
**Response:** **Regarding unresolved issues for CustomerA (query: 'What did Security say about the SSO?'):**
  • Was the security condition for CustomerA cleared?

...
**Score:** 10/12 (evidence=4, unknowns=1)

### Q04 (factual_recall)
**Query:** What is the status of the SSO integration?
**Response:** **Regarding: What is the status of the SSO integration?**

**CustomerA: Deliver SSO by Friday**
State: material | Epistemic: disputed

**What's been r...
**Score:** 10/12 (evidence=4, unknowns=1)

### Q05 (factual_recall)
**Query:** What is happening with CustomerA?
**Response:** **Regarding: What is happening with CustomerA?**

**CustomerA: Deliver SSO by Friday**
State: material | Epistemic: disputed

**What's been reported (...
**Score:** 10/12 (evidence=4, unknowns=1)

