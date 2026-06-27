# Todo App Implementation

This code implements a todo application using localStorage for persistence. The app features a clean, responsive interface with core functionality including adding, editing, deleting, and marking tasks as complete. Since the plan suggests starting with localStorage, this implementation focuses on client-side storage which provides immediate benefits like offline capability and no server setup required. The app uses modern JavaScript with ES6+ features and includes error handling for storage operations.

```javascript
class TodoApp {
  constructor() {
    this.todos = this.loadTodos();
    this.appElement = document.getElementById('app');
    this.render();
  }

  loadTodos() {
    try {
      const storedTodos = localStorage.getItem('todos');
      return storedTodos ? JSON.parse(storedTodos) : [];
    } catch (error) {
      console.error('Failed to load todos:', error);
      return [];
    }
  }

  saveTodos() {
    try {
      localStorage.setItem('todos', JSON.stringify(this.todos));
    } catch (error) {
      console.error('Failed to save todos:', error);
      // Handle storage quota exceeded or other errors
      alert('Unable to save todos. Your browser storage might be full.');
    }
  }

  addTodo(text) {
    if (!text.trim()) return;
    
    const newTodo = {
      id: Date.now(),
      text: text.trim(),
      completed: false,
      createdAt: new Date().toISOString()
    };
    
    this.todos.unshift(newTodo);
    this.saveTodos();
    this.render();
  }

  toggleTodo(id) {
    const todo = this.todos.find(t => t.id === id);
    if (todo) {
      todo.completed = !todo.completed;
      this.saveTodos();
      this.render();
    }
  }

  deleteTodo(id) {
    this.todos = this.todos.filter(t => t.id !== id);
    this.saveTodos();
    this.render();
  }

  editTodo(id, newText) {
    if (!newText.trim()) return;
    
    const todo = this.todos.find(t => t.id === id);
    if (todo) {
      todo.text = newText.trim();
      this.saveTodos();
      this.render();
    }
  }

  render() {
    const todosHtml = this.todos.map(todo => `
      <li class="todo-item ${todo.completed ? 'completed' : ''}" data-id="${todo.id}">
        <div class="todo-content">
          <input type="checkbox" ${todo.completed ? 'checked' : ''} 
                 onchange="app.toggleTodo(${todo.id})">
          <span class="todo-text">${this.escapeHtml(todo.text)}</span>
        </div>
        <div class="todo-actions">
          <button class="edit-btn" onclick="app.startEdit(${todo.id})">Edit</button>
          <button class="delete-btn" onclick="app.deleteTodo(${todo.id})">Delete</button>
        </div>
      </li>
    `).join('');

    this.appElement.innerHTML = `
      <div class="container">
        <h1>Todo App</h1>
        <div class="input-container">
          <input type="text" id="todo-input" placeholder="Add a new task..." 
                 onkeypress="if(event.key === 'Enter') app.addTodo(this.value)">
          <button id="add-btn" onclick="app.addTodo(document.getElementById('todo-input').value)">
            Add
          </button>
        </div>
        <ul id="todo-list">
          ${todosHtml || '<li class="empty">No tasks yet. Add one above!</li>'}
        </ul>
      </div>
    `;
  }

  startEdit(id) {
    const todo = this.todos.find(t => t.id === id);
    if (!todo) return;

    const todoElement = document.querySelector(`[data-id="${id}"] .todo-text`);
    const currentText = todo.text;
    
    todoElement.innerHTML = `
      <input type="text" id="edit-input-${id}" value="${this.escapeHtml(currentText)}" 
             onkeypress="if(event.key === 'Enter') app.editTodo(${id}, this.value)"
             onblur="app.editTodo(${id}, this.value)">
    `;
    
    document.getElementById(`edit-input-${id}`).focus();
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize the app
const app = new TodoApp();
```

## How to run
1. Create an HTML file with a container element having id="app"
2. Add the JavaScript code above to a script tag in your HTML
3. Open the HTML file in a web browser

## Tests
```javascript
// Test suite for TodoApp
class TestTodoApp {
  constructor() {
    // Create a mock environment for testing
    this.originalLocalStorage = localStorage;
    this.storage = {};
    this.mockLocalStorage = {
      getItem: (key) => this.storage[key] || null,
      setItem: (key, value) => { this.storage[key] = value; },
      clear: () => { this.storage = {}; }
    };
    window.localStorage = this.mockLocalStorage;
  }

  restoreLocalStorage() {
    window.localStorage = this.originalLocalStorage;
  }

  testAddTodo() {
    const app = new TodoApp();
    app.addTodo("Test task");
    
    if (app.todos.length !== 1 || app.todos[0].text !== "Test task") {
      throw new Error("Add todo test failed");
    }
    
    if (this.storage.todos === undefined) {
      throw new Error("Todo not saved to localStorage");
    }
    
    this.mockLocalStorage.clear();
    console.log("Add todo test passed");
  }

  testToggleTodo() {
    const app = new TodoApp();
    app.addTodo("Test task");
    app.toggleTodo(app.todos[0].id);
    
    if (!app.todos[0].completed) {
      throw new Error("Toggle todo test failed");
    }
    
    this.mockLocalStorage.clear();
    console.log("Toggle todo test passed");
  }

  testDeleteTodo() {
    const app = new TodoApp();
    app.addTodo("Test task");
    const id = app.todos[0].id;
    app.deleteTodo(id);
    
    if (app.todos.length !== 0) {
      throw new Error("Delete todo test failed");
    }
    
    this.mockLocalStorage.clear();
    console.log("Delete todo test passed");
  }

  testEditTodo() {
    const app = new TodoApp();
    app.addTodo("Original text");
    app.editTodo(app.todos[0].id, "Updated text");
    
    if (app.todos[0].text !== "Updated text") {
      throw new Error("Edit todo test failed");
    }
    
    this.mockLocalStorage.clear();
    console.log("Edit todo test passed");
  }

  testEscapeHtml() {
    const app = new TodoApp();
    const escaped = app.escapeHtml("<script>alert('xss')</script>");
    
    if (escaped !== "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;") {
      throw new Error("HTML escaping test failed");
    }
    
    console.log("HTML escaping test passed");
  }

  runAllTests() {
    try {
      this.testAddTodo();
      this.testToggleTodo();
      this.testDeleteTodo();
      this.testEditTodo();
      this.testEscapeHtml();
      console.log("All tests passed!");
    } catch (error) {
      console.error("Test failed:", error.message);
    } finally {
      this.restoreLocalStorage();
    }
  }
}

// Run tests
const testApp = new TestTodoApp();
testApp.runAllTests();
```

## Confidence
**Score:** 90%
**Reason:** The implementation follows the plan by starting with localStorage and includes comprehensive functionality.
**Alternatives considered:** 2 (using a class vs functional approach, implementing local storage with IndexedDB for larger datasets)

## Disagreements
None