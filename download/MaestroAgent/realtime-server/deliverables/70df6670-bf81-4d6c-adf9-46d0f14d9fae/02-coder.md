# Palindrome Checker Function

This code implements a Python function that checks if a given string is a palindrome. A palindrome is a word, phrase, number, or other sequence of characters that reads the same forward and backward, ignoring spaces, punctuation, and capitalization. The function includes proper error handling and is case-insensitive, ignoring non-alphanumeric characters.

```python
import re

def is_palindrome(s: str) -> bool:
    """
    Check if a string is a palindrome.
    
    This function ignores case, spaces, and non-alphanumeric characters.
    
    Args:
        s: The string to check
        
    Returns:
        bool: True if the string is a palindrome, False otherwise
        
    Raises:
        TypeError: If the input is not a string
    """
    if not isinstance(s, str):
        raise TypeError("Input must be a string")
    
    # Remove non-alphanumeric characters and convert to lowercase
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', s).lower()
    
    # Check if the cleaned string reads the same forwards and backwards
    return cleaned == cleaned[::-1]
```

# How to run

To run the function and its tests:

1. Save the function in `palindrome_function.py`
2. Save the tests in `test_palindrome.py`
3. Run the tests using: `python -m unittest test_palindrome.py`

Here's the test file:

```python
import unittest
from palindrome_function import is_palindrome

class TestPalindrome(unittest.TestCase):
    
    def test_simple_palindrome(self):
        self.assertTrue(is_palindrome("racecar"))
    
    def test_case_insensitivity(self):
        self.assertTrue(is_palindrome("RaceCar"))
    
    def test_with_spaces(self):
        self.assertTrue(is_palindrome("A man a plan a canal Panama"))
    
    def test_with_punctuation(self):
        self.assertTrue(is_palindrome("A man, a plan, a canal: Panama!"))
    
    def test_non_palindrome(self):
        self.assertFalse(is_palindrome("hello world"))
    
    def test_empty_string(self):
        self.assertTrue(is_palindrome(""))
    
    def test_single_character(self):
        self.assertTrue(is_palindrome("a"))
    
    def test_numbers(self):
        self.assertTrue(is_palindrome("12321"))
    
    def test_mixed_characters(self):
        self.assertTrue(is_palindrome("1a2b3c3b2a1"))
    
    def test_non_palindrome_with_numbers(self):
        self.assertFalse(is_palindrome("123abc"))
    
    def test_non_string_input(self):
        with self.assertRaises(TypeError):
            is_palindrome(123)
        with self.assertRaises(TypeError):
            is_palindrome(["racecar"])

if __name__ == '__main__':
    unittest.main()
```