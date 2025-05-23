
# AI-DevCollab-MCP

* 这是个给前后端分类项目使用的MCP，假如你在设计前后端分离项目的时候，无法描述场景问题的时候，用这个工具，让ai之间直接对话，从而解决问题。
* 本系统基于Socket通信构建，为多个AI实例提供实时通信接口，支持身份设置、消息传递、等待回复等功能
* 架构分离都可以使用该项目来完成任务交接

## 快速开始

### 安装与启动
1. 下载客户端和服务端文件
2. 启动服务端：运行`socket_server.py`
   - 可使用`server_admin.py`进行服务端管理
3. 启动MCP：运行`python socket_mcp.py`
4. 提示AI: 请你连接到服务器，地址为localhost:8888
5. 提示AI: 设置AI身份：如"前端开发"、"后端开发"、"UI设计师"等
6. 开始角色间对话

## 核心功能

### 连接管理
* **link_server** - 连接到指定服务器（参数：服务器地址）
* **test_connection** - 测试当前连接状态及延迟
* **connection_status** - 获取连接详情
* **disconnect** - 断开服务器连接

### 身份管理
* **set_identity** - 设置当前AI的开发角色身份
* **list_identities** - 获取所有在线角色列表

### 消息互动
* **send_message** - 发送消息并可选等待回复
  - 支持定向消息和广播
  - 支持同步等待回复（自动阻塞直到收到回复）
  - 可设置超时和最大回复数量
  - 支持消息引用回复
* **get_messages** - 获取历史消息记录
* **get_pending_replies** - 获取待回复的消息

## 应用场景

* **接口设计讨论**：前端AI向后端AI询问API规范和数据结构
* **数据流程确认**：后端AI向前端AI确认用户数据处理流程
* **UI/UX协调**：设计师AI与开发AI讨论界面实现细节
* **跨角色需求澄清**：不同角色间快速对齐需求理解

# IDE 配置 & Claude 配置
* 这个配置是在Windows下的配置
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

# 演示视频链接
- [【AI-DevCollab-MCP】](https://www.bilibili.com/video/BV1M8VNzLEhB/?share_source=copy_web&vd_source=09c93e3ecc1959d0046ae256f1442eb9)

# QQ群
* 975707810

# 更新

* 2025年5月4日 0.1 版本，调试代码未删除，等待更新
