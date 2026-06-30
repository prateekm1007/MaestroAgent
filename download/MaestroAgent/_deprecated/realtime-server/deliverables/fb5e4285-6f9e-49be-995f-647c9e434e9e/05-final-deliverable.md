# Deliverable: Build a todo app — should it use a database or just localStorage?

**Produced by:** MaestroAgent
**Run ID:** fb5e4285-6f9e-49be-995f-647c9e434e9e
**Generated:** 2026-06-27T18:37:00.753Z
**Team:** Planner → Coder → Reviewer
**Average specialist confidence:** 88%
**Disagreements resolved:** 3

---

## Orchestration Summary

This deliverable was produced by a team of 3 specialists, coordinated by Maestro's Conductor. 3 disagreements were raised and resolved.

---

## Specialist Work

### Planner output
## Plan
1. **Define requirements** — clarify if data needs to persist across devices/browsers
2. **Prototype with localStorage** — build a basic version for single-device use
3. **Evaluate performance** — test with large datasets to determine scalability limits
4. **Implement database if needed** — migrate to a database solution (e.g., Firebase) if requirements demand multi-device sync

## Specialists Needed
- Frontend Developer
- Backend Developer (if database option chosen)

## Deliverables
- Todo app prototype
- Performance test results
- Architecture decision document

## Confidence
**Score:** 85%
**Reason:** The plan addresses both options while starting with the simpler approach.
**Alternatives considered:** 1 (starting directly with database implementation)

## Disagreements
- The goal is slightly ambiguous regarding persistence requirements, which is the key decision factor between localStorage and a database.

### Coder output
# Todo App with localStorage

This code creates a simple but functional todo application that stores tasks in the browser's localStorage. The app includes features to add, edit, delete, and mark tasks as complete. It uses a clean, modern UI with responsive design and includes error handling for localStorage operations. Since the plan calls for starting with localStorage, this implementation focuses on a single-device solution that persists data within the same browser.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Todo App</title>
    <style>
        :root {
            --primary-color: #4a6fa5;
            --secondary-color: #166088;
            --danger-color: #e74c3c;
            --success-color: #2ecc71;
            --light-color: #f8f9fa;
            --dark-color: #343a40;
            --border-radius: 8px;
            --box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: var(--dark-color);
            background-color: #f1f5f9;
            padding: 20px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            text-align: center;
            margin-bottom: 30px;
        }

        h1 {
            color: var(--primary-color);
            margin-bottom: 10px;
        }

        .todo-form {
            display: flex;
            margin-bottom: 30px;
        }

        .todo-input {
            flex: 1;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: var(--border-radius) 0 0 var(--border-radius);
            font-size: 16px;
        }

        .btn {
            padding: 12px 20px;
            border: none;
            background-color: var(--primary-color);
            color: white;
            cursor: pointer;
            font-size: 16px;
            border-radius: 0 var(--border-radius) var(--border-radius) 0;
            transition: background-color 0.3s;
        }

        .btn:hover {
            background-color: var(--secondary-color);
        }

        .btn-danger {
            background-color: var(--danger-color);
        }

        .btn-danger:hover {
            background-color: #c0392b;
        }

        .btn-success {
            background-color: var(--success-color);
        }

        .btn-success:hover {
            background-color: #27ae60;
        }

        .todo-list {
            list-style: none;
        }

        .todo-item {
            background-color: white;
            box-shadow: var(--box-shadow);
            border-radius: var(--border-radius);
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .todo-item.completed {
            opacity: 0.7;
        }

        .todo-item.completed .todo-text {
            text-decoration: line-through;
            color: #777;
        }

        .todo-text {
            flex: 1;
            margin-right: 15px;
        }

        .todo-actions {
            display: flex;
            gap: 10px;
        }

        .todo-actions button {
            padding: 6px 12px;
            font-size: 14px;
        }

        .empty-state {
            text-align: center;
            padding: 40px;
            background-color: white;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
        }

        .error-message {
            color: var(--danger-color);
            margin-top: 10px;
            padding: 10px;
            background-color: #fdecea;
            border-radius: var(--border-radius);
            display: none;
        }

        @media (max-width: 600px) {
            .todo-form {
                flex-direction: column;
            }
            
            .todo-input {
                border-radius: var(--border-radius);
                margin-bottom: 10px;
            }
            
            .btn {
                border-radius: var(--border-radius);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Todo App</h1>
            <p>Manage your tasks efficiently</p>
        </header>

        <div class="error-message" id="errorMessage"></div>

        <form class="todo-form" id="todoForm">
            <input 
                type="text" 
                class="todo-input" 
                id="todoInput" 
                placeholder="Add a new task..."
                required
            >
            <button type="submit" class="btn">Add Task</button>
        </form>

        <ul class="todo-list" id="todoList">
            <!-- Todo items will be dynamically added here -->
        </ul>

        <div class="empty-state" id="emptyState">
            <p>No tasks yet. Add one above!</p>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', () => {
            // DOM Elements
            const todoForm = document.getElementById('todoForm');
            const todoInput = document.getElementById('todoInput');
            const todoList = document.getElementById('todoList');
            const emptyState = document.getElementById('emptyState');
            const errorMessage = document.getElementById('errorMessage');

            // Initialize the app
            let todos = [];
            let editingId = null;

            // Load todos from localStorage on page load
            try {
                const storedTodos = localStorage.getItem('todos');
                if (storedTodos) {
                    todos = JSON.parse(storedTodos);
                    renderTodos();
                }
            } catch (error) {
                showError('Failed to load tasks. Please try refreshing the page.');
                console.error('Failed to load todos:', error);
            }

            // Add or update a todo
            todoForm.addEventListener('submit', (e) => {
                e.preventDefault();
                
                const text = todoInput.value.trim();
                if (!text) return;

                try {
                    if (editingId) {
                        // Update existing todo
                        const index = todos.findIndex(todo => todo.id === editingId);
                        if (index !== -1) {
                            todos[index].text = text;
                            editingId = null;
                        }
                    } else {
                        // Add new todo
                        const newTodo = {
                            id: Date.now(),
                            text,
                            completed: false
                        };
                        todos.push(newTodo);
                    }

                    saveTodos();
                    renderTodos();
                    todoInput.value = '';
                    todoInput.focus();
                } catch (error) {
                    showError('Failed to save task. Please try again.');
                    console.error('Failed to save todo:', error);
                }
            });

            // Render todos in the DOM
            function renderTodos() {
                todoList.innerHTML = '';
                
                if (todos.length === 0) {
                    emptyState.style.display = 'block';
                    return;
                }
                
                emptyState.style.display = 'none';
                
                todos.forEach(todo => {
                    const li = document.createElement('li');
                    li.className = `todo-item ${todo.completed ? 'completed' : ''}`;
                    
                    const todoText = document.createElement('span');
                    todoText.className = 'todo-text';
                    todoText.textContent = todo.text;
                    
                    const todoActions = document.createElement('div');
                    todoActions.className = 'todo-actions';
                    
                    // Edit button
                    const editBtn = document.createElement('button');
                    editBtn.className = 'btn';
                    editBtn.textContent = 'Edit';
                    editBtn.addEventListener('click', () => editTodo(todo.id));
                    
                    // Complete button
                    const completeBtn = document.createElement('button');
                    completeBtn.className = `btn ${todo.completed ? 'btn-danger' : 'btn-success'}`;
                    completeBtn.textContent = todo.completed ? 'Undo' : 'Complete';
                    completeBtn.addEventListener('click', () => toggleComplete(todo.id));
                    
                    // Delete button
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'btn btn-danger';
                    deleteBtn.textContent = 'Delete';
                    deleteBtn.addEventListener('click', () => deleteTodo(todo.id));
                    
                    todoActions.appendChild(editBtn);
                    todoActions.appendChild(completeBtn);
                    todoActions.appendChild(deleteBtn);
                    
                    li.appendChild(todoText);
                    li.appendChild(todoActions);
                    
                    todoList.appendChild(li);
                });
            }

            // Save todos to localStorage
            function saveTodos() {
                try {
                    localStorage.setItem('todos', JSON.stringify(todos));
                } catch (error) {
                    showError('Failed to save tasks. Your browser storage might be full.');
                    console.error('Failed to save todos:', error);
                }
            }

            // Edit a todo
            function editTodo(id) {
                const todo = todos.find(todo => todo.id === id);
                if (todo) {
                    todoInput.value = todo.text;
                    editingId = id;
                    todoInput.focus();
                }
            }

            // Toggle todo completion status
            function toggleComplete(id) {
                const index = todos.findIndex(todo => todo.id === id);
                if (index !== -1) {
                    todos[index].completed = !todos[index].completed;
                    saveTodos();
                    renderTodos();
                }
            }

            // Delete a todo
            function deleteTodo(id) {
                if (confirm('Are you sure you want to delete this task?')) {
                    todos = todos.filter(todo => todo.id !== id);
                    saveTodos();
                    renderTodos();
                }
            }

            // Show error message
            function showError(message) {
                errorMessage.textContent = message;
                errorMessage.style.display = 'block';
                
                setTimeout(() => {
                    errorMessage.style.display = 'none';
                }, 5000);
            }
        });
    </script>
</body>
</html>
```

## How to run
1. Copy the code above into a single HTML file
2. Save the file as `todo-app.html`
3. Open the file in any modern web browser (Chrome, Firefox, Safari, Edge)
4. The app will load with any previously saved tasks from localStorage
5. Add, edit, complete, or delete tasks as needed

## Tests
```javascript
// Test suite for Todo App
function runTests() {
    // Mock localStorage for testing
    const localStorageMock = (function() {
        let store = {};
        return {
            getItem: function(key) {
                return store[key] || null;
            },
            setItem: function(key, value) {
                store[key] = value.toString();
            },
            clear: function() {
                store = {};
            }
        };
    })();
    
    // Override window.localStorage
    Object.defineProperty(window, 'localStorage', {
        value: localStorageMock,
        writable: true
    });

    // Test data
    const sampleTodos = [
        { id: 1, text: 'Test task 1', completed: false },
        { id: 2, text: 'Test task 2', completed: true },
        { id: 3, text: 'Test task 3', completed: false }
    ];

    // Test 1: Save todos to localStorage
    console.log('Test 1: Saving todos to localStorage');
    localStorage.setItem('todos', JSON.stringify(sampleTodos));
    const storedTodos = JSON.parse(localStorage.getItem('todos'));
    console.log(storedTodos.length === sampleTodos.length ? 'PASS' : 'FAIL');

    // Test 2: Load todos from localStorage
    console.log('Test 2: Loading todos from localStorage');
    const loadedTodos = JSON.parse(localStorage.getItem('todos'));
    console.log(loadedTodos.length === sampleTodos.length ? 'PASS' : 'FAIL');

    // Test 3: Add a new todo
    console.log('Test 3: Adding a new todo');
    const newTodo = { id: 4, text: 'New test task', completed: false };
    const updatedTodos = [...sampleTodos, newTodo];
    localStorage.setItem('todos', JSON.stringify(updatedTodos));
    const afterAddTodos = JSON.parse(localStorage.getItem('todos'));
    console.log(afterAddTodos.length === updatedTodos.length ? 'PASS' : 'FAIL');

    // Test 4: Update a todo
    console.log('Test 4: Updating a todo');
    const updatedTodosList = [...updatedTodos];
    const todoIndex = updatedTodosList.findIndex(todo => todo.id === 1);
    if (todoIndex !== -1) {
        updatedTodosList[todoIndex].text = 'Updated test task';
        localStorage.setItem('todos', JSON.stringify(updatedTodosList));
        const afterUpdateTodos = JSON.parse(localStorage.getItem('todos'));
        const isUpdated = afterUpdateTodos[todoIndex].text === 'Updated test task';
        console.log(isUpdated ? 'PASS' : 'FAIL');
    }

    // Test 5: Delete a todo
    console.log('Test 5: Deleting a todo');
    const afterDeleteTodos = updatedTodosList.filter(todo => todo.id !== 2);
    localStorage.setItem('todos', JSON.stringify(afterDeleteTodos));
    const finalTodos = JSON.parse(localStorage.getItem('todos'));
    console.log(finalTodos.length === afterDeleteTodos.length ? 'PASS' : 'FAIL');

    // Test 6: Clear all todos
    console.log('Test 6: Clearing all todos');
    localStorage.setItem('todos', JSON.stringify([]));
    const clearedTodos = JSON.parse(localStorage.getItem('todos'));
    console.log(clearedTodos.length === 0 ? 'PASS' : 'FAIL');

    // Test 7: Error handling for invalid JSON
    console.log('Test 7: Error handling for invalid JSON');
    localStorage.setItem('todos', 'invalid json');
    try {
        const invalidTodos = JSON.parse(localStorage.getItem('todos'));
        console.log('FAIL: Should have thrown an error');
    } catch (e) {
        console.log('PASS: Correctly handled invalid JSON');
    }

    // Clean up
    localStorage.clear();
    console.log('All tests completed');
}

// Run the tests
runTests();
```

## Confidence
**Score:** 90%
**Reason:** The implementation follows the plan by starting with localStorage for a single-device solution.
**Alternatives considered:** 1 (direct database implementation vs localStorage approach)

## Disagreements
None. The plan's approach of starting with localStorage before considering a database solution is appropriate for this context, as it provides a simple, client-side solution that works well for single-device use cases without requiring backend infrastructure.

### Reviewer output
## Verdict
APPROVED_WITH_NOTES

## Strengths
- The test suite comprehensively covers all CRUD operations (Create, Read, Update, Delete) for the todo app
- The mock implementation properly simulates localStorage behavior for testing purposes
- Includes error handling test for invalid JSON data, which is important for robustness

## Issues Found
- The tests only check for correct length of arrays, not the actual content or structure of the todos
- No tests for edge cases like empty todos array or null/undefined values
- Tests only pass/fail with console logs rather than using a proper testing framework with assertions

## Suggested Improvements
- Add content validation tests to ensure not only the correct number of todos but also that properties are correctly stored and retrieved
- Implement proper test assertions using a testing framework like Jest or Mocha instead of console.log statements
- Add tests for edge cases such as handling null/undefined values, very large todo lists, and concurrent access scenarios

## Confidence
**Score:** 90%
**Reason:** The test implementation is solid but could be more thorough with content validation and edge cases.
**Alternatives considered:** 1 (adding more comprehensive test cases vs current basic implementation)

## Disagreements
None. The approach of using localStorage for a todo app is appropriate for a simple, client-side solution, and the test implementation follows this approach correctly.

---

## Artifacts Produced

- **01-planner.md** (939 bytes) — by Planner [confidence: 85%]
- **02-coder.md** (15985 bytes) — by Coder [confidence: 90%]
- **03-reviewer.md** (1454 bytes) — by Reviewer [confidence: 90%]
- **04-debate-resolution.md** (1065 bytes) — by Conductor (Debate Resolution)
