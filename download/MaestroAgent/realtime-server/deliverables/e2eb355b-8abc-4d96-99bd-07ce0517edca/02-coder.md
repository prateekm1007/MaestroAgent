# API Explanation Generator

This code creates a simple script that generates a clear, two-sentence explanation of what an API is. The explanation is designed to be accessible to both technical and non-technical readers by using relatable analogies and avoiding unnecessary jargon.

```python
def generate_api_explanation():
    """
    Generates a two-sentence explanation of what an API is.
    
    Returns:
        str: A two-sentence explanation of APIs
    """
    # First sentence explains the core function of an API
    sentence1 = "An API (Application Programming Interface) is a set of rules and tools that allows different software applications to communicate with each other."
    
    # Second sentence provides a relatable analogy
    sentence2 = "Think of it as a waiter in a restaurant that takes your order (request) and brings back the food (response) from the kitchen (system)."
    
    return f"{sentence1} {sentence2}"

def save_to_file(content, filename):
    """
    Saves the given content to a file.
    
    Args:
        content (str): The content to save
        filename (str): The name of the file to save to
    """
    try:
        with open(filename, 'w') as file:
            file.write(content)
        print(f"Successfully saved explanation to {filename}")
    except IOError as e:
        print(f"Error saving file: {e}")

def main():
    # Generate the API explanation
    explanation = generate_api_explanation()
    
    # Save to both deliverable files
    save_to_file(explanation, "api-explanation-draft.md")
    save_to_file(explanation, "final-api-explanation.txt")
    
    # Also print to console
    print("\nAPI Explanation:")
    print(explanation)

if __name__ == "__main__":
    main()
```

## How to run

1. Save the code to a file named `api_explanation_generator.py`
2. Run the script using Python: `python api_explanation_generator.py`
3. The script will generate the explanation and save it to both `api-explanation-draft.md` and `final-api-explanation.txt` files, while also displaying the explanation in the console.