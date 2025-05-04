from mcp.server.fastmcp import FastMCP, Image, Context
from socket_client import SocketClient
from typing import Dict, List, Any, Optional, Union
import asyncio
import json
import threading
import time
import datetime
import queue
import logging
import os

# 配置日志系统
logger = logging.getLogger("socket_mcp")
logger.setLevel(logging.DEBUG)

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# 创建文件处理器
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
log_file = os.path.join(log_dir, "socket_mcp.log")
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# 添加处理器到日志记录器
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# 创建MCP服务器
mcp = FastMCP("Socket通信工具")

# 维护全局客户端连接
_client = None
# 全局变量
_connected = False
_identity = None
# 消息缓存
_recent_messages = []
_message_lock = threading.Lock()
_message_listener_running = False

# 消息回复通知系统
# 格式: {(发送者, 接收者): 事件对象}，用于等待特定用户的回复
_reply_events = {}
_reply_events_lock = threading.Lock()

def get_client() -> SocketClient:
    """获取共享的SocketClient实例"""
    global _client
    if _client is None or not _client.is_connected():
        _client = SocketClient()
    return _client

def start_message_listener():
    """启动消息监听线程"""
    global _message_listener_running
    if _message_listener_running:
        return
    
    client = get_client()
    if not client.is_connected():
        return
    
    def handle_new_message(data):
        """处理新收到的消息"""
        with _message_lock:
            _recent_messages.append(data)
            # 只保留最近50条消息
            if len(_recent_messages) > 50:
                _recent_messages.pop(0)
            
            # 提取消息信息
            sender = data.get('sender')
            target = data.get('target')  # 目标接收者
            content = data.get('content', '')
            timestamp = data.get('timestamp', time.time())
            msg_id = data.get('id', '')
            
            logger.info(f"处理新消息: [{sender} -> {target or '广播'}]: {content[:50]}... (消息ID: {msg_id})")
            
            # 判断当前用户是否是消息接收者
            current_identity = client.current_identity if client else None
            is_target_current_user = (target == current_identity)
            
            # 检查是否有线程在等待这个发送者的回复
            with _reply_events_lock:
                # 输出当前等待中的事件
                if _reply_events:
                    logger.debug(f"当前等待事件: {list(_reply_events.keys())}")
                
                # 检查所有可能的等待键
                possible_keys = []
                
                # 只考虑发送给当前用户的消息触发等待事件
                if is_target_current_user:
                    possible_keys.append((target, sender))  # 精确匹配：目标用户等待这个发送者的回复
                    possible_keys.append((target, None))    # 模糊匹配：目标用户等待任何人的回复
                    
                    # 打印可能的匹配键
                    logger.debug(f"检查可能的等待事件键: {possible_keys}")
                
                events_to_notify = []
                for key in possible_keys:
                    if key in _reply_events:
                        # 收集需要通知的事件
                        events_to_notify.append(_reply_events[key])
                        logger.debug(f"找到等待事件: {key[0]} 正在等待 {key[1] or '任何人'} 的回复")
                
                # 通知所有等待的线程
                for event in events_to_notify:
                    logger.debug(f"触发等待事件: 新消息来自 {sender}, 消息ID: {msg_id}")
                    event.set()
    
    def handle_reply_received(data):
        """处理收到的回复通知"""
        with _message_lock:
            # 保存通知到最近消息列表
            notification = {
                'event_type': 'reply_received',
                'data': data
            }
            _recent_messages.append(notification)
            # 只保留最近50条消息
            if len(_recent_messages) > 50:
                _recent_messages.pop(0)
            
            original_msg_id = data.get('original_msg_id')
            reply_msg_id = data.get('reply_msg_id')
            sender = data.get('sender')
            
            logger.info(f"处理回复通知: 原消息ID: {original_msg_id}, 回复ID: {reply_msg_id}, 发送者: {sender}")
    
    # 注册消息处理函数
    client.register_notification_handler('new_message', handle_new_message)
    client.register_notification_handler('reply_received', handle_reply_received)
    
    _message_listener_running = True

# 连接服务器
@mcp.tool()
def link_server(server_address: str) -> Dict[str, Any]:
    """连接到socket服务器
    
    Args:
        server_address: 服务器地址，格式为 "host:port"
        
    Returns:
        连接结果
    """
    global _connected
    client = get_client()
    success = client.link_server(server_address)
    if success:
        # 连接成功后设置全局连接状态
        _connected = True
        # 连接成功后启动消息监听
        start_message_listener()
        return {"status": "success", "message": f"成功连接到服务器: {server_address}"}
    else:
        return {"status": "error", "message": "连接服务器失败"}

# 测试连接
@mcp.tool()
def test_connection() -> Dict[str, Any]:
    """测试与服务器的连接状态
    
    Returns:
        测试结果，包含状态和延迟时间
    """
    client = get_client()
    
    # 检查客户端是否已初始化
    if not client:
        logger.error("客户端未初始化")
        return {"status": "error", "message": "客户端未初始化"}
    
    # 检查是否已连接
    if not client.is_connected():
        logger.error("客户端未连接到服务器")
        return {"status": "error", "message": "未连接到服务器"}
    
    logger.info(f"正在测试与服务器 {client.server_address} 的连接...")
    
    try:
        start_time = time.time()
        response = client.test_connection()
        end_time = time.time()
        latency = end_time - start_time
        
        # 添加延迟信息
        response['latency'] = latency
        logger.info(f"连接测试完成，状态: {response.get('status')}, 延迟: {latency:.3f}秒")
        
        return response
    except Exception as e:
        logger.exception(f"测试连接时发生错误: {e}")
        return {"status": "error", "message": f"测试连接失败: {str(e)}"}

# 设置身份
@mcp.tool()
def set_identity(identity: str) -> Dict[str, Any]:
    """设置客户端身份
    
    Args:
        identity: 要设置的身份名
    
    注意，这是您需要扮演的身份，并且代入该身份。完成该身份的任务内容
        
    Returns:
        设置结果，成功时包含client_id
    """
    global _identity, _connected
    client = get_client()
    result = client.set_identity(identity)
    
    # 如果身份设置成功，确保启动消息监听
    if result.get("status") == "success":
        _identity = identity
        _connected = True
        start_message_listener()
    
    return result

# 发送消息
@mcp.tool()
def send_message(message, target: str = None, wait_for_reply: bool = False,
                wait_for_sender: str = None, timeout_seconds: int = 60, max_replies: int = 1,
                reply_to_msg_id: str = None) -> Dict[str, Any]:
    """发送消息给服务器
    
    Args:
        message: 消息内容，可以是字符串或字典
        target: 目标接收者，不指定则广播
        wait_for_reply: 是否等待对方回复
        wait_for_sender: 指定等待回复的发送者身份
        timeout_seconds: 等待回复的超时秒数
        max_replies: 最大接收的回复数量
        reply_to_msg_id: 回复的消息ID（如果是回复某条消息）
        
    Returns:
        发送结果
    """
    client = get_client()
    
    # 记录接收到的参数类型，帮助诊断参数类型错误
    logger.info(f"send_message 被调用，参数类型检查:")
    logger.info(f"message 类型: {type(message)}, 值: {message}")
    logger.info(f"target 类型: {type(target)}, 值: {target}")
    logger.info(f"wait_for_reply 类型: {type(wait_for_reply)}, 值: {wait_for_reply}")
    logger.info(f"wait_for_sender 类型: {type(wait_for_sender)}, 值: {wait_for_sender}")
    logger.info(f"timeout_seconds 类型: {type(timeout_seconds)}, 值: {timeout_seconds}")
    logger.info(f"max_replies 类型: {type(max_replies)}, 值: {max_replies}")
    logger.info(f"reply_to_msg_id 类型: {type(reply_to_msg_id)}, 值: {reply_to_msg_id}")
    
    # 检查message参数的类型并尝试修复
    if message is None:
        logger.error("message参数不能为None")
        return {'status': 'error', 'message': 'message参数不能为None'}
    
    if not isinstance(message, (str, dict)):
        logger.warning(f"message参数类型 {type(message)} 不是预期的str或dict类型，尝试转换...")
        try:
            if hasattr(message, '__str__'):
                message = str(message)
                logger.info(f"已将message转换为字符串: {message}")
            else:
                logger.error(f"无法将message参数转换为有效类型")
                return {'status': 'error', 'message': f'message参数类型无效: {type(message)}'}
        except Exception as e:
            logger.exception(f"转换message参数类型时出错: {e}")
            return {'status': 'error', 'message': f'转换message参数类型失败: {str(e)}'}
    
    if not client or not client.is_connected():
        logger.error("客户端未连接到服务器")
        return {'status': 'error', 'message': '未连接到服务器'}
    
    if not client.current_identity:
        logger.error("客户端未设置身份")
        return {'status': 'error', 'message': '未设置身份'}
    
    # 打印参数，便于调试
    logger.debug(f"send_message 调用参数: message={message}, target={target}, wait_for_reply={wait_for_reply}")
    logger.debug(f"附加参数: wait_for_sender={wait_for_sender}, timeout={timeout_seconds}, max_replies={max_replies}")
    
    # 准备消息参数
    params = {
        'message': message
    }
    
    if target:
        params['target'] = target
    
    # 重要：确保参数类型正确
    try:
        # 转换布尔值类型参数
        wait_for_reply = bool(wait_for_reply)
        
        # 转换整数类型参数
        if timeout_seconds is not None:
            timeout_seconds = int(timeout_seconds)
        else:
            timeout_seconds = 60
            
        if max_replies is not None:
            max_replies = int(max_replies)
        else:
            max_replies = 1
    except (ValueError, TypeError) as e:
        logger.exception(f"参数类型转换出错: {e}")
        return {'status': 'error', 'message': f'参数类型转换失败: {str(e)}'}
    
    # 确保is_waiting_reply参数被正确设置
    if wait_for_reply:
        params['is_waiting_reply'] = True
        logger.debug(f"设置等待回复参数 is_waiting_reply=True")
    
    if wait_for_sender:
        params['wait_for_sender'] = wait_for_sender
    
    params['timeout_seconds'] = timeout_seconds
    params['max_replies'] = max_replies
    
    if reply_to_msg_id:
        params['reply_to_msg_id'] = reply_to_msg_id
    
    logger.debug(f"最终发送参数: {params}")
    
    # 发送消息
    try:
        logger.info(f"正在发送消息到服务器...")
        response = client.send_command('send_message', params)
        logger.info(f"服务器响应: {response}")
        
        if response.get('status') != 'success':
            logger.error(f"发送消息失败: {response.get('message', '未知错误')}")
            return response
        
        msg_id = response.get('msg_id')
        logger.debug(f"消息发送成功: ID={msg_id}, 等待回复={wait_for_reply}")
        
        # 如果需要等待回复且成功发送
        if wait_for_reply and response.get('is_waiting_reply'):
            logger.debug(f"准备等待回复，超时={timeout_seconds}秒")
            
            # 设置一个事件，用于等待通知
            reply_event = threading.Event()
            reply_messages = []
            
            # 注册回复通知处理函数
            def handle_reply_notification(notification_data):
                logger.debug(f"收到通知: {notification_data}")
                if (notification_data.get('event_type') == 'reply_received' and 
                    notification_data.get('data', {}).get('original_msg_id') == msg_id):
                    
                    reply_data = notification_data.get('data', {})
                    reply_sender = reply_data.get('sender')
                    
                    # 检查回复发送者是否匹配要求
                    if not wait_for_sender or reply_sender == wait_for_sender:
                        logger.debug(f"收到匹配的回复通知: {reply_data}")
                        
                        # 添加到回复列表
                        reply_messages.append({
                            'id': reply_data.get('reply_msg_id'),
                            'sender': reply_sender,
                            'content': reply_data.get('content'),
                            'timestamp': reply_data.get('timestamp')
                        })
                        
                        # 如果达到最大回复数，触发事件并退出
                        if len(reply_messages) >= max_replies:
                            logger.debug(f"已达到最大回复数 {max_replies}，解除等待")
                            reply_event.set()
            
            # 注册通知处理函数
            old_callback = client.callbacks.get('notification')
            def notification_callback(notification):
                logger.debug(f"收到通知: {notification.get('event_type')}")
                # 处理回复通知
                if notification.get('event_type') == 'reply_received':
                    handle_reply_notification(notification)
                # 调用原有的回调
                if old_callback:
                    old_callback(notification)
            
            # 设置回调
            client.callbacks['notification'] = notification_callback
            
            # 等待事件触发或超时
            logger.info(f"开始等待回复，超时时间={timeout_seconds}秒...")
            wait_result = reply_event.wait(timeout_seconds)
            logger.info(f"等待结束，是否收到回复: {wait_result}")
            
            # 恢复原有的回调
            if old_callback:
                client.callbacks['notification'] = old_callback
            else:
                client.callbacks.pop('notification', None)
            
            # 如果没有收到回复，可能是超时或者消息被处理但回调没有触发
            # 尝试从最近消息中查找回复
            if not reply_messages:
                logger.debug(f"等待超时或未通过回调接收到回复，检查最近消息")
                with _message_lock:
                    for msg in list(_recent_messages):
                        if (msg.get('event_type') == 'reply_received' and 
                            msg.get('data', {}).get('original_msg_id') == msg_id):
                            
                            reply_data = msg.get('data', {})
                            reply_sender = reply_data.get('sender')
                            
                            # 检查是否匹配
                            if not wait_for_sender or reply_sender == wait_for_sender:
                                logger.debug(f"在最近消息中找到匹配回复: {reply_data}")
                                reply_messages.append({
                                    'id': reply_data.get('reply_msg_id'),
                                    'sender': reply_sender,
                                    'content': reply_data.get('content'),
                                    'timestamp': reply_data.get('timestamp')
                                })
                                _recent_messages.remove(msg)
            
            # 构建返回结果
            response['reply_messages'] = reply_messages
            response['reply_count'] = len(reply_messages)
            if len(reply_messages) == 0:
                response['reply_status'] = 'timeout'
                logger.warning(f"等待回复超时，未收到任何回复")
            else:
                response['reply_status'] = 'received'
                logger.info(f"成功收到 {len(reply_messages)} 条回复")
        
        return response
    except Exception as e:
        logger.exception(f"发送消息过程中出错: {str(e)}")
        return {'status': 'error', 'message': f'发送消息失败: {str(e)}'}

# 获取历史消息
@mcp.tool()
def get_messages(limit = None, offset = 0) -> Dict[str, Any]:
    """获取历史消息
    
    Args:
        limit: 消息数量限制，默认为全部
        offset: 起始偏移量，默认为0
        
    Returns:
        包含消息列表的结果
    """
    client = get_client()
    
    # 记录接收到的参数类型，帮助诊断参数类型错误
    logger.info(f"get_messages 被调用，参数类型检查:")
    logger.info(f"limit 类型: {type(limit)}, 值: {limit}")
    logger.info(f"offset 类型: {type(offset)}, 值: {offset}")
    
    # 处理参数类型问题
    params = {}
    
    # 转换offset参数
    try:
        if offset is not None:
            offset = int(offset)
        else:
            offset = 0
            
        if offset < 0:
            logger.warning(f"offset参数 {offset} 为负值，将使用默认值0")
            offset = 0
            
        params['offset'] = offset
    except (ValueError, TypeError) as e:
        logger.warning(f"转换offset参数 '{offset}' 为整数失败: {e}，将使用默认值0")
        params['offset'] = 0
    
    # 转换limit参数
    try:
        if limit is not None:
            limit = int(limit)
            params['limit'] = limit
            logger.debug(f"limit参数已转换为整数: {limit}")
        else:
            logger.debug(f"limit参数为None，将获取全部消息")
    except (ValueError, TypeError) as e:
        logger.warning(f"转换limit参数 '{limit}' 为整数失败: {e}，将忽略此参数获取全部消息")
    
    # 记录最终使用的参数
    logger.debug(f"最终参数: {params}")
    
    # 使用解包方式调用客户端方法
    try:
        logger.info(f"正在获取历史消息...")
        result = client.get_messages(**params)
        logger.info(f"获取消息成功，共 {len(result.get('messages', []))} 条消息")
        return result
    except Exception as e:
        logger.exception(f"获取历史消息失败: {e}")
        return {'status': 'error', 'message': f'获取历史消息失败: {str(e)}'}

# 获取待回复消息
@mcp.tool()
def get_pending_replies(max_count = 10) -> dict:
    """获取当前用户的未读消息（等待回复的消息）
    
    Args:
        max_count: 最大消息数量
        
    Returns:
        包含未读消息的结果
    """
    client = get_client()
    
    # 记录接收到的参数类型
    logger.info(f"get_pending_replies 被调用，参数类型检查:")
    logger.info(f"max_count 类型: {type(max_count)}, 值: {max_count}")
    
    # 转换max_count参数
    try:
        if max_count is not None:
            max_count = int(max_count)
            if max_count <= 0:
                logger.warning(f"max_count参数 {max_count} 不是正整数，将使用默认值10")
                max_count = 10
        else:
            logger.debug(f"max_count参数为None，将使用默认值10")
            max_count = 10
    except (ValueError, TypeError) as e:
        logger.warning(f"转换max_count参数 '{max_count}' 为整数失败: {e}，将使用默认值10")
        max_count = 10
    
    if not client or not client.is_connected():
        logger.error("客户端未连接到服务器")
        return {'status': 'error', 'message': '未连接到服务器'}
    
    if not client.current_identity:
        logger.error("客户端未设置身份")
        return {'status': 'error', 'message': '未设置身份'}
    
    logger.debug(f"获取当前用户 {client.current_identity} 的待回复消息，最大数量: {max_count}")
    
    # 调用服务器的获取未读消息接口
    try:
        logger.info(f"正在从服务器获取待回复消息...")
        response = client.send_command("get_pending_replies", {
            "identity": client.current_identity,
            "max_count": max_count
        })
        
        if response.get('status') == 'success':
            messages = response.get('messages', [])
            count = len(messages)
            logger.info(f"成功获取到 {count} 条等待回复的消息")
            
            # 打印消息详情
            for i, msg in enumerate(messages):
                sender = msg.get('sender', '未知')
                msg_id = msg.get('msg_id', '未知')
                is_read = msg.get('is_read', 0)
                requires_reply = msg.get('requires_reply', False)
                logger.debug(f"消息 {i+1}/{count}: 发送者={sender}, ID={msg_id}, 已读={is_read}, 需要回复={requires_reply}")
            
            return {
                'status': 'success',
                'message': f'获取到 {count} 条等待回复的消息',
                'count': count,
                'messages': messages
            }
        else:
            error_msg = response.get('message', '未知错误')
            logger.error(f"获取待回复消息失败: {error_msg}")
            return response
    except Exception as e:
        logger.exception(f"获取待回复消息出错: {str(e)}")
        return {'status': 'error', 'message': f'获取消息出错: {str(e)}'}

# 列出所有身份
@mcp.tool()
def list_identities() -> Dict[str, Any]:
    """获取所有在线用户的身份列表
    
    Returns:
        包含身份列表的结果
    """
    client = get_client()
    
    # 检查连接状态
    if not client or not client.is_connected():
        logger.error("客户端未连接到服务器")
        return {'status': 'error', 'message': '未连接到服务器'}
    
    logger.info("正在获取在线用户身份列表...")
    
    try:
        result = client.list_identities()
        identities = result.get('identities', [])
        logger.info(f"成功获取到 {len(identities)} 个在线用户")
        
        # 记录详细信息
        for i, identity in enumerate(identities):
            logger.debug(f"用户 {i+1}: {identity.get('identity')}, 客户端ID: {identity.get('client_id')}")
        
        return result
    except Exception as e:
        logger.exception(f"获取身份列表失败: {e}")
        return {'status': 'error', 'message': f'获取身份列表失败: {str(e)}'}

# 断开连接
@mcp.tool()
def disconnect() -> Dict[str, Any]:
    """断开与服务器的连接
    
    Returns:
        操作结果
    """
    global _client, _message_listener_running, _connected, _identity
    if _client and _client.is_connected():
        _client.disconnect()
        _client = None
        _message_listener_running = False
        _connected = False
        _identity = None
        with _message_lock:
            _recent_messages.clear()
        return {"status": "success", "message": "已断开连接"}
    return {"status": "info", "message": "当前未连接到服务器"}

# 获取连接状态
@mcp.tool()
def connection_status() -> Dict[str, Any]:
    """获取当前连接状态
    
    Returns:
        连接状态信息
    """
    global _client
    if _client and _client.is_connected():
        return {
            "status": "success", 
            "connected": True, 
            "server_address": _client.server_address,
            "identity": _client.identity,
            "client_id": _client.client_id,
            "listening_for_messages": _message_listener_running
        }
    else:
        return {"status": "info", "connected": False}

@mcp.prompt()
def monitor_chat() -> str:
    return """请帮我监控聊天消息，当有新消息时通知我并显示消息内容。

你应该：
1. 使用send_message工具来指定消息，并且默认等待对方回复 (使用send_message工具)
2. 当获取新消息内容时，默认使用get_pending_replies工具

## 操作指南
1. 当收到消息时：
   - 首先在当前工作区记录完整消息内容
   - 分析消息目的和所需的操作
   
2. 解决方案处理：
   - 所有代码、分析和详细解决方案必须仅在本地工作区完成
   - 禁止直接将解决方案内容发送给对方
   
3. 回复准则：
   - 只发送简短的确认、澄清问题或必要回应
   - 回复应简洁专业，不包含技术细节或解决方案
   - 使用正式但友好的语气

## 消息处理流程
1. 接收消息 → 在工作区记录并分析
2. 在工作区完成所有技术工作
3. 向用户发送简短专业的回应
4. 等待用户进一步指示
"""

if __name__ == "__main__":
    # 直接运行此文件启动MCP服务器
    logger.info("正在启动Socket通信工具服务器...")
    mcp.run() 
