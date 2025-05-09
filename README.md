
# AI-DevCollab-MCP

[![English](https://img.shields.io/badge/English-Click-yellow)](README.md)
[![简体中文](https://img.shields.io/badge/中文文档-点击查看-orange)](docs/README-zh.md)


* This is an MCP-based tool designed specifically for front-end/back-end separated projects. When you're unable to clearly describe development scenarios, this system enables direct conversations between AI agents to collaboratively solve the issue.
* The system is built on socket communication, providing a real-time messaging interface for multiple AI instances. It supports identity management, message exchange, and synchronous replies—simulating realistic development team communication workflows.
* Architecture-separated projects can all use this MCP to handle task handoffs.
## Quick Start

### Installation & Startup
1. Download both the client and server files.
2. Start the server: run `socket_server.py`
   - You can manage the server using `server_admin.py`
3. Inside your IDE: run `python socket_mcp.py`
4. Please prompt AI: Connect to the server localhost:8888
5. Please prompt AI: Set the AI identity (e.g., "Front-End Developer", "Back-End Developer", "UI Designer")
6. Begin role-based conversations

## Core Features

### Connection Management
* **link_server** - Connect to the specified server (param: server address:post)
* **test_connection** - Test current connection status and latency
* **connection_status** - Get detailed connection information
* **disconnect** - Disconnect from the server

### Identity Management
* **set_identity** - Set the current AI's developer role identity
* **list_identities** - List all currently online identities

### Message Interaction
* **send_message** - Send a message, with optional synchronous reply waiting
  - Supports targeted messages and broadcasting
  - Supports blocking until a reply is received
  - Timeout and max reply count can be configured
  - Supports message referencing and reply chaining
* **get_messages** - Retrieve the message history
* **get_pending_replies** - Get messages awaiting replies

## Use Cases

* **API Design Discussion**: Front-end AI consults with back-end AI on API specifications and data structures
* **Data Flow Confirmation**: Back-end AI verifies data handling logic with front-end AI
* **UI/UX Coordination**: Design AI collaborates with development AI on interface implementation details
* **Cross-Role Requirement Alignment**: Quickly resolve misunderstandings between different roles
* 
# IDE & Claude
* This configuration is for only Windows
```json
{
  "mcpServers": {
    "AI-DevCollab-MCP": {
       "command": "cmd",
       "args": [
         "/c",
         "python",
         "socket_mcp.py"
       ]
     }
  }
}
```

# Demo Video Link
- [【AI-DevCollab-MCP】](https://www.bilibili.com/video/BV1M8VNzLEhB/?share_source=copy_web&vd_source=09c93e3ecc1959d0046ae256f1442eb9)


# Updates

* 2025.05.04 — Version 0.1: Debugging code still present; updates pending
