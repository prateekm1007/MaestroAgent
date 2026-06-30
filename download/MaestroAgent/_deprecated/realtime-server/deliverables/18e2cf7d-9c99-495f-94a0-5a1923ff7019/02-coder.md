I'll create a simple Python script that generates a two-sentence explanation of what an API is, following the plan from the context.

```python
def create_api_explanation():
    """
    Creates a two-sentence explanation of what an API is.
    Returns the explanation as a string.
    """
    # Research-based explanation of API in two simple sentences
    explanation = (
        "An API (Application Programming Interface) is a set of rules and protocols that allows different software applications to communicate with each other.\n"
        "It defines the methods and data formats that applications can use to request and exchange information, acting as an intermediary that simplifies complex functionality."
    )
    return explanation

def save_explanation_to_file(explanation, filename="api-explanation.txt"):
    """
    Saves the API explanation to a file.
    
    Args:
        explanation (str): The two-sentence explanation of an API
        filename (str): Name of the file to save the explanation to
    """
    try:
        with open(filename, 'w') as file:
            file.write(explanation)
        print(f"Explanation successfully saved to {filename}")
    except IOError as e:
        print(f"Error saving file: {e}")

def main():
    """Main function to generate and save the API explanation"""
    # Create the explanation
    api_explanation = create_api_explanation()
    
    # Save to file
    save_explanation_to_file(api_explanation)
    
    # Print to console
    print("\nAPI Explanation:")
    print(api_explanation)

if __name__ == "__main__":
    main()
```

How to run:
1. Save the code to a file named `api_explanation_generator.py`
2. Run the script using Python: `python api_explanation_generator.py`
3. The script will display the explanation in the console and save it to a file named `api-explanation.txt`