# Deliverable: Write a Python function to check if a number is prime, with tests

**Produced by:** MaestroAgent
**Run ID:** c42730fe-8d66-4f8e-9e8f-ecfaaa8df0b9
**Generated:** 2026-06-27T18:36:04.960Z
**Team:** Planner → Coder → Reviewer
**Average specialist confidence:** 93%
**Disagreements resolved:** 0

---

## Orchestration Summary

This deliverable was produced by a team of 3 specialists, coordinated by Maestro's Conductor. No disagreements were raised — the team was aligned throughout.

---

## Specialist Work

### Planner output
## Plan
1. **Design prime-checking algorithm** — Create a function that efficiently determines primality
2. **Implement Python function** — Write the is_prime() function with edge cases handled
3. **Write test cases** — Develop comprehensive tests covering various scenarios
4. **Validate implementation** — Run tests to ensure correctness

## Specialists Needed
- Python Developer
- Software Tester

## Deliverables
- is_prime() Python function
- Test suite (e.g., pytest or unittest cases)

## Confidence
**Score:** 95%
**Reason:** The goal is well-defined and has a clear, standard implementation approach.
**Alternatives considered:** 1 (Using probabilistic primality tests for very large numbers)

## Disagreements
None

### Coder output
# Prime Number Checker in Python

This implementation provides an efficient function to check if a number is prime. The function handles edge cases (numbers less than 2, even numbers) and uses a square root optimization to reduce the number of checks needed. It includes comprehensive tests to verify correctness across various scenarios including small primes, composites, edge cases, and larger numbers.

```python
import math

def is_prime(n):
    """
    Check if a number is prime.
    
    Args:
        n (int): The number to check for primality
        
    Returns:
        bool: True if the number is prime, False otherwise
    """
    # Handle edge cases
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    
    # Check odd divisors up to square root of n
    max_divisor = math.isqrt(n) + 1
    for i in range(3, max_divisor, 2):
        if n % i == 0:
            return False
    
    return True
```

## How to run
1. Save the code to a file named `prime_checker.py`
2. Run the tests using: `python -m pytest prime_checker.py -v`
3. Or run directly with: `python prime_checker.py`

```python
import unittest

class TestPrimeChecker(unittest.TestCase):
    def test_small_primes(self):
        self.assertTrue(is_prime(2))
        self.assertTrue(is_prime(3))
        self.assertTrue(is_prime(5))
        self.assertTrue(is_prime(7))
        self.assertTrue(is_prime(11))
        self.assertTrue(is_prime(13))
    
    def test_small_composites(self):
        self.assertFalse(is_prime(1))
        self.assertFalse(is_prime(4))
        self.assertFalse(is_prime(6))
        self.assertFalse(is_prime(8))
        self.assertFalse(is_prime(9))
        self.assertFalse(is_prime(10))
    
    def test_edge_cases(self):
        self.assertFalse(is_prime(0))
        self.assertFalse(is_prime(-1))
        self.assertFalse(is_prime(-7))
    
    def test_larger_primes(self):
        self.assertTrue(is_prime(7919))
        self.assertTrue(is_prime(104729))
        self.assertTrue(is_prime(15485863))
    
    def test_larger_composites(self):
        self.assertFalse(is_prime(10000))
        self.assertFalse(is_prime(9999))
        self.assertFalse(is_prime(5040))
    
    def test_even_numbers(self):
        self.assertFalse(is_prime(22))
        self.assertFalse(is_prime(44))
        self.assertFalse(is_prime(66))
    
    def test_odd_composites(self):
        self.assertFalse(is_prime(15))
        self.assertFalse(is_prime(21))
        self.assertFalse(is_prime(27))
        self.assertFalse(is_prime(33))
        self.assertFalse(is_prime(35))

if __name__ == "__main__":
    unittest.main()
```

## Confidence
**Score:** 95%
**Reason:** The implementation follows standard primality testing best practices with proper edge case handling.
**Alternatives considered:** 1 (Miller-Rabin probabilistic test for very large numbers, but deterministic test is more appropriate for general use)

## Disagreements
None

### Reviewer output
## Verdict
APPROVED_WITH_NOTES

## Strengths
- The implementation correctly handles edge cases (numbers less than 2, even numbers)
- The algorithm efficiently checks for primality by only testing divisors up to the square root of n and skipping even numbers after checking for 2
- The test suite is comprehensive, covering small primes, composites, edge cases, larger numbers, and specific categories like even and odd composites

## Issues Found
- The function doesn't handle the case where n is a float, which could cause a TypeError
- There's no documentation explaining why the function returns False for numbers less than 2 (which is mathematically correct but could be clarified)

## Suggested Improvements
- Add input validation to ensure n is an integer, either by raising a TypeError or converting to int
- Add a brief explanation in the docstring about why numbers less than 2 are not considered prime
- Consider adding a special case for n=2 to make the code flow slightly cleaner (though the current implementation is correct)

## Confidence
**Score:** 90%
**Reason:** The implementation is correct and well-tested but could benefit from better input validation and documentation.
**Alternatives considered:** 1 (Using a more sophisticated primality test for very large numbers, but the current approach is optimal for general use cases)

## Disagreements
None

---

## Artifacts Produced

- **01-planner.md** (732 bytes) — by Planner [confidence: 95%]
- **02-coder.md** (2996 bytes) — by Coder [confidence: 95%]
- **03-reviewer.md** (1372 bytes) — by Reviewer [confidence: 90%]
