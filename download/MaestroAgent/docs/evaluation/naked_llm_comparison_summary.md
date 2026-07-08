# Naked-LLM Comparison Summary

**Executed:** 2026-07-08T21:14:55.551213+00:00
**Provider:** z-ai
**Model:** glm-4-plus
**Command:** `z-ai chat --prompt <prompt> -o /tmp/llm_resp.json`

## Results

| System | Score | Percentage |
|--------|-------|------------|
| Maestro | 200/240 | 83.3% |
| LLM (glm-4-plus) | 98/240 | 40.8% |

## Win/Loss

- Maestro wins: 20/20
- LLM wins: 0/20
- Ties: 0/20

## Dimension Advantages

| Dimension | Maestro Avg | LLM Avg | Advantage |
|-----------|------------|---------|-----------|
| factual_accuracy | 3.0 | 1.75 | maestro |
| evidence_traceability | 3.0 | 1.15 | maestro |
| uncertainty_honesty | 2.0 | 0.0 | maestro |
| intervention_restraint | 2.0 | 2.0 | tie |

## Conclusion

Maestro demonstrates structural advantage over a frontier LLM (glm-4-plus) on
3 of 4 dimensions.
The LLM produces fluent prose but does not cite evidence by signal ID, does not
acknowledge unknowns, and makes recommendations without intervention restraint.
