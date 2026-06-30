# Real-time Chat App Implementation using WebSockets

This implementation creates a real-time chat application using WebSockets. The solution includes both client-side and server-side components, allowing users to join chat rooms, send messages, and receive real-time updates. The server maintains chat history and supports multiple concurrent users. WebSockets were chosen over Server-Sent Events (SSE) because they provide full bidirectional communication, which is essential for a chat application where users need to both send and receive messages efficiently.

## Code

```javascript
// server.js
const http = require('http');
const WebSocket = require('ws');
const url = require('url');
const crypto = require('crypto');

class ChatServer {
  constructor() {
    this.server = http.createServer();
    this.wss = new WebSocket.Server({ noServer: true });
    this.rooms = new Map(); // room_id -> { name, messages: [{id, user, text, timestamp}] }
    this.users = new Map(); // user_id -> { id, name, room_id }
    this.userCount = 0;
    
    this.setupServer();
    this.setupWebSocket();
  }
  
  setupServer() {
    this.server.on('request', (req, res) => {
      const pathname = url.parse(req.url).pathname;
      
      if (pathname === '/' || pathname === '/index.html') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(this.getHTML());
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    });
  }
  
  setupWebSocket() {
    this.wss.on('connection', (ws, req) => {
      const userId = this.generateUserId();
      let currentRoom = null;
      
      // Send initial data to the client
      ws.send(JSON.stringify({
        type: 'init',
        userId,
        rooms: Array.from(this.rooms.entries()).map(([id, room]) => ({
          id,
          name: room.name,
          userCount: this.getRoomUserCount(id)
        }))
      }));
      
      // Handle incoming messages
      ws.on('message', (message) => {
        try {
          const data = JSON.parse(message);
          
          switch (data.type) {
            case 'join':
              this.handleJoinRoom(ws, userId, data.roomId, data.userName);
              currentRoom = data.roomId;
              break;
              
            case 'leave':
              this.handleLeaveRoom(ws, userId, currentRoom);
              currentRoom = null;
              break;
              
            case 'message':
              if (currentRoom) {
                this.handleMessage(ws, userId, currentRoom, data.text);
              }
              break;
              
            case 'createRoom':
              this.handleCreateRoom(ws, userId, data.roomName);
              break;
          }
        } catch (error) {
          console.error('Error processing message:', error);
          ws.send(JSON.stringify({
            type: 'error',
            message: 'Invalid message format'
          }));
        }
      });
      
      // Handle disconnection
      ws.on('close', () => {
        if (currentRoom) {
          this.handleLeaveRoom(ws, userId, currentRoom);
        }
        this.users.delete(userId);
      });
    });
    
    this.server.on('upgrade', (request, socket, head) => {
      this.wss.handleUpgrade(request, socket, head, (ws) => {
        this.wss.emit('connection', ws, request);
      });
    });
  }
  
  generateUserId() {
    return `user_${crypto.randomBytes(8).toString('hex')}`;
  }
  
  generateMessageId() {
    return `msg_${crypto.randomBytes(8).toString('hex')}`;
  }
  
  getRoomUserCount(roomId) {
    return Array.from(this.users.values()).filter(user => user.room_id === roomId).length;
  }
  
  handleJoinRoom(ws, userId, roomId, userName) {
    if (!roomId || !userName) {
      ws.send(JSON.stringify({
        type: 'error',
        message: 'Room ID and user name are required'
      }));
      return;
    }
    
    // Create room if it doesn't exist
    if (!this.rooms.has(roomId)) {
      this.rooms.set(roomId, {
        name: roomId,
        messages: []
      });
    }
    
    // Add user to the room
    this.users.set(userId, {
      id: userId,
      name: userName,
      room_id: roomId
    });
    
    // Notify all users in the room
    this.broadcastToRoom(roomId, {
      type: 'userJoined',
      userId,
      userName,
      userCount: this.getRoomUserCount(roomId)
    });
    
    // Send chat history to the new user
    const room = this.rooms.get(roomId);
    ws.send(JSON.stringify({
      type: 'history',
      messages: room.messages
    }));
  }
  
  handleLeaveRoom(ws, userId, roomId) {
    if (!roomId || !this.users.has(userId)) return;
    
    const user = this.users.get(userId);
    this.users.delete(userId);
    
    // Notify all users in the room
    this.broadcastToRoom(roomId, {
      type: 'userLeft',
      userId,
      userName: user.name,
      userCount: this.getRoomUserCount(roomId)
    });
  }
  
  handleMessage(ws, userId, roomId, text) {
    if (!roomId || !text.trim()) return;
    
    const user = this.users.get(userId);
    if (!user) return;
    
    const message = {
      id: this.generateMessageId(),
      user: user.name,
      text: text.trim(),
      timestamp: new Date().toISOString()
    };
    
    // Add message to room history
    const room = this.rooms.get(roomId);
    room.messages.push(message);
    
    // Broadcast message to all users in the room
    this.broadcastToRoom(roomId, {
      type: 'message',
      message
    });
  }
  
  handleCreateRoom(ws, userId, roomName) {
    if (!roomName) {
      ws.send(JSON.stringify({
        type: 'error',
        message: 'Room name is required'
      }));
      return;
    }
    
    const roomId = roomName.replace(/\s+/g, '-').toLowerCase();
    this.rooms.set(roomId, {
      name: roomName,
      messages: []
    });
    
    // Notify the client about the created room
    ws.send(JSON.stringify({
      type: 'roomCreated',
      roomId,
      roomName
    }));
  }
  
  broadcastToRoom(roomId, data) {
    const message = JSON.stringify(data);
    
    this.wss.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        const user = this.users.get(client.userId);
        if (user && user.room_id === roomId) {
          client.send(message);
        }
      }
    });
  }
  
  getHTML() {
    return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Real-time Chat</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        #chat-container {
            display: flex;
            flex-direction: column;
            height: 500px;
            border: 1px solid #ddd;
            border-radius: 5px;
            overflow: hidden;
        }
        #room-selector {
            padding: 10px;
            background-color: #f1f1f1;
            border-bottom: 1px solid #ddd;
        }
        #messages {
            flex-grow: 1;
            overflow-y: auto;
            padding: 10px;
        }
        .message {
            margin-bottom: 10px;
            padding: 5px;
            border-radius: 5px;
            background-color: #f9f9f9;
        }
        .message .user {
            font-weight: bold;
            color: #2c3e50;
        }
        .message .timestamp {
            font-size: 0.8em;
            color: #7f8c8d;
        }
        #input-container {
            display: flex;
            padding: 10px;
            border-top: 1px solid #ddd;
        }
        #message-input {
            flex-grow: 1;
            padding: 5px;
            border: 1px solid #ddd;
            border-radius: 3px;
        }
        button {
            padding: 5px 10px;
            background-color: #3498db;
            color: white;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            margin-left: 5px;
        }
        button:hover {
            background-color: #2980b9;
        }
        #user-info {
            margin-bottom: 10px;
            padding: 10px;
            background-color: #ecf0f1;
            border-radius: 5px;
        }
        .room {
            padding: 5px;
            margin: 5px 0;
            background-color: #f9f9f9;
            border-radius: 3px;
            cursor: pointer;
        }
        .room:hover {
            background-color: #e9e9e9;
        }
        .room.active {
            background-color: #3498db;
            color: white;
        }
        #error-message {
            color: #e74c3c;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <h1>Real-time Chat</h1>
    
    <div id="user-info">
        <span id="user-name">Not connected</span>
    </div>
    
    <div id="chat-container">
        <div id="room-selector">
            <h3>Rooms</h3>
            <div id="rooms-list"></div>
            <div>
                <input type="text" id="new-room-input" placeholder="New room name">
                <button id="create-room-btn">Create</button>
            </div>
        </div>
        
        <div id="messages"></div>
        
        <div id="input-container">
            <input type="text" id="message-input" placeholder="Type your message...">
            <button id="send-btn">Send</button>
        </div>
    </div>
    
    <div id="error-message"></div>
    
    <script>
        document.addEventListener('DOMContentLoaded', () => {
            const messagesContainer = document.getElementById('messages');
            const messageInput = document.getElementById('message-input');
            const sendButton = document.getElementById('send-btn');
            const roomsList = document.getElementById('rooms-list');
            const createRoomBtn = document.getElementById('create-room-btn');
            const newRoomInput = document.getElementById('new-room-input');
            const userNameSpan = document.getElementById('user-name');
            const errorMessage = document.getElementById('error-message');
            
            let userId = null;
            let currentRoom = null;
            let userName = null;
            
            // Connect to WebSocket server
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(\`\${protocol}//\${window.location.host}\`);
            
            ws.onopen = () => {
                console.log('Connected to chat server');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                switch (data.type) {
                    case 'init':
                        userId = data.userId;
                        userName = \`User_\${Math.floor(Math.random() * 1000)}\`;
                        userNameSpan.textContent = \`Connected as: \${userName}\`;
                        updateRoomsList(data.rooms);
                        break;
                        
                    case 'history':
                        messagesContainer.innerHTML = '';
                        data.messages.forEach(msg => {
                            addMessageToUI(msg);
                        });
                        break;
                        
                    case 'message':
                        addMessageToUI(data.message);
                        break;
                        
                    case 'userJoined':
                        addSystemMessage(\`\${data.userName} joined the chat\`);
                        updateRoomUserCount(data.roomId, data.userCount);
                        break;
                        
                    case 'userLeft':
                        addSystemMessage(\`\${data.userName} left the chat\`);
                        updateRoomUserCount(data.roomId, data.userCount);
                        break;
                        
                    case 'roomCreated':
                        addSystemMessage(\`Room "\${data.roomName}" created\`);
                        updateRoomsList();
                        break;
                        
                    case 'error':
                        errorMessage.textContent = data.message;
                        setTimeout(() => {
                            errorMessage.textContent = '';
                        }, 5000);
                        break;
                }
            };
            
            ws.onclose = () => {
                console.log('Disconnected from chat server');
                userNameSpan.textContent = 'Disconnected';
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                errorMessage.textContent = 'Connection error occurred';
            };
            
            sendButton.addEventListener('click', () => {
                const message = messageInput.value.trim();
                if (message && currentRoom) {
                    ws.send(JSON.stringify({
                        type: 'message',
                        text: message
                    }));
                    messageInput.value = '';
                }
            });
            
            messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && messageInput.value.trim()) {
                    sendButton.click();
                }
            });
            
            createRoomBtn.addEventListener('click', () => {
                const roomName = newRoomInput.value.trim();
                if (roomName) {
                    ws.send(JSON.stringify({
                        type: 'createRoom',
                        roomName: roomName
                    }));
                    newRoomInput.value = '';
                }
            });
            
            function updateRoomsList(rooms) {
                roomsList.innerHTML = '';
                const roomsData = rooms || Array.from(window.chatServer?.rooms?.entries() || []);
                
                roomsData.forEach(([roomId, room]) => {
                    const roomDiv = document.createElement('div');
                    roomDiv.className = 'room';
                    if (roomId === currentRoom) {
                        roomDiv.classList.add('active');
                    }
                    roomDiv.textContent = \`\${room.name} (\${window.chatServer?.getRoomUserCount(roomId) || 0})\`;
                    roomDiv.addEventListener('click', () => {
                        if (currentRoom !== roomId) {
                            if (currentRoom) {
                                ws.send(JSON.stringify({
                                    type: 'leave',
                                    roomId: currentRoom
                                }));
                            }
                            
                            ws.send(JSON.stringify({
                                type: 'join',
                                roomId: roomId,
                                userName: userName
                            }));
                            currentRoom = roomId;
                            updateRoomsList();
                        }
                    });
                    roomsList.appendChild(roomDiv);
                });
            }
            
            function addMessageToUI(message) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message';
                
                const userSpan = document.createElement('span');
                userSpan.className = 'user';
                userSpan.textContent = message.user;
                
                const textSpan = document.createElement('span');
                textSpan.textContent = message.text;
                
                const timestampSpan = document.createElement('span');
                timestampSpan.className = 'timestamp';
                timestampSpan.textContent = new Date(message.timestamp).toLocaleTimeString();
                
                messageDiv.appendChild(userSpan);
                messageDiv.appendChild(document.createTextNode(': '));
                messageDiv.appendChild(textSpan);
                messageDiv.appendChild(document.createElement('br'));
                messageDiv.appendChild(timestampSpan);
                
                messagesContainer.appendChild(messageDiv);
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            function addSystemMessage(text) {
                const messageDiv = document.createElement('div');
                messageDiv.style.textAlign = 'center';
                messageDiv.style.fontStyle = 'italic';
                messageDiv.style.color = '#7f8c8d';
                messageDiv.textContent = text;
                
                messagesContainer.appendChild(messageDiv);
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            function updateRoomUserCount(roomId, count) {
                const roomElements = roomsList.querySelectorAll('.room');
                roomElements.forEach(element => {
                    if (element.textContent.includes(roomId)) {
                        const match = element.textContent.match(/\\((\\d+)\\)/);
                        if (match) {
                            element.textContent = element.textContent.replace(/\\((\\d+)\\)/, \`(\${count})\`);
                        }
                    }
                });
            }
        });
    </script>
</body>
</html>
    `;
  }
  
  start(port = 3000) {
    this.server.listen(port, () => {
      console.log(`Chat server running on port ${port}`);
    });
  }
}

// Start the server
const chatServer = new ChatServer();
chatServer.start(3000);
```

## How to Run

1. Install dependencies:
   ```
   npm install ws
   ```

2. Save the code as `server.js`

3. Run the server:
   ```
   node server.js
   ```

4. Open your browser and navigate to `http://localhost:3000`

5. Open multiple browser tabs to test real-time communication between users

## Tests

```javascript
// tests.js
const WebSocket = require('ws');
const http = require('http');
const { assert } = require('chai');

describe('Chat Server', () => {
  let server;
  let port;
  let wss;
  
  before((done) => {
    // Start the server
    server = new (require('./server'))();
    port = 3001; // Use a different port for tests
    server.start(port);
    
    // Wait for server to start
    setTimeout(() => {
      wss = new WebSocket.Server({ 
        clientTracking: true,
        port: port 
      });
      done();
    }, 100);
  });
  
  after((done) => {
    server.server.close();
    wss.close();
    done();
  });
  
  it('should allow client to connect', (done) => {
    const ws = new WebSocket(`ws://localhost:${port}`);
    
    ws.on('open', () => {
      assert.isTrue(ws.readyState === WebSocket.OPEN);
      ws.close();
      done();
    });
  });
  
  it('should send initial data on connection', (done) => {
    const ws = new WebSocket(`ws://localhost:${port}`);
    
    ws.on('message', (message) => {
      const data = JSON.parse(message);
      assert.equal(data.type, 'init');
      assert.property(data, 'userId');
      assert.isArray(data.rooms);
      ws.close();
      done();
    });
  });
  
  it('should handle joining a room', (done) => {
    const ws1 = new WebSocket(`ws://localhost:${port}`);
    const ws2 = new WebSocket(`ws://localhost:${port}`);
    
    let receivedHistory = false;
    let receivedUserJoined = false;
    
    ws1.on('message', (message) => {
      const data = JSON.parse(message);
      
      if (data.type === 'init') {
        // Join a room
        ws1.send(JSON.stringify({
          type: 'join',
          roomId: 'test-room',
          userName: 'User1'
        }));
      } else if (data.type === 'history') {
        receivedHistory = true;
        assert.isArray(data.messages);
      } else if (data.type === 'userJoined')