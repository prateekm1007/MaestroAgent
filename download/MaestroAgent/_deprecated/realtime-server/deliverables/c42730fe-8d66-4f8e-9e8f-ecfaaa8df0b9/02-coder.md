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