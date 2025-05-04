import socket
import json
import threading
import time
from typing import List, Dict, Any, Optional, Callable

class SocketClient:
    def __init__(self):
        """初始化socket客户端"""
        self.socket = None
        self.server_address = None
        self.connected = False
        self.client_id = None
        self.identity = None
        self.receive_thread = None
        self.running = False
        self.callbacks = {}  # 存储事件回调函数
        self.notification_handlers = {}  # 存储不同类型通知的处理函数
    
    @property
    def current_identity(self) -> Optional[str]:
        """获取当前身份
        
        Returns:
            Optional[str]: 当前身份，未设置则为None
        """
        return self.identity
    
    def link_server(self, server_address: str) -> bool:
        """连接到服务器
        
        Args:
            server_address (str): 服务器地址，格式为 "host:port"
            
        Returns:
            bool: 连接是否成功
        """
        try:
            # 解析服务器地址
            if ':' in server_address:
                host, port_str = server_address.split(':')
                port = int(port_str)
            else:
                host = server_address
                port = 8888  # 默认端口
            
            # 创建套接字并连接
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            
            # 记录连接信息
            self.server_address = server_address
            self.connected = True
            self.running = True
            
            # 启动接收线程
            self.receive_thread = threading.Thread(target=self._receive_messages)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            
            print(f"已连接到服务器: {server_address}")
            return True
            
        except Exception as e:
            print(f"连接服务器失败: {e}")
            self.socket = None
            self.connected = False
            return False
    
    def test_connection(self) -> Dict[str, Any]:
        """测试与服务器的连接
        
        Returns:
            Dict[str, Any]: 测试结果，包含状态和延迟时间
        """
        if not self.is_connected():
            return {"status": "error", "message": "未连接到服务器"}
        
        try:
            start_time = time.time()
            response = self._send_request('test_connection')
            end_time = time.time()
            
            response['latency'] = end_time - start_time
            return response
            
        except Exception as e:
            print(f"测试连接失败: {e}")
            return {"status": "error", "message": f"测试连接失败: {str(e)}"}
    
    def set_identity(self, identity: str) -> Dict[str, Any]:
        """设置客户端身份
        
        Args:
            identity (str): 要设置的身份名
            
        Returns:
            Dict[str, Any]: 设置结果，成功时包含client_id
        """
        if not self.is_connected():
            return {"status": "error", "message": "未连接到服务器"}
        
        try:
            response = self._send_request('set_identity', {'identity': identity})
            
            if response.get('status') == 'success':
                self.identity = identity
                self.client_id = response.get('client_id')
            
            return response
            
        except Exception as e:
            print(f"设置身份失败: {e}")
            return {"status": "error", "message": f"设置身份失败: {str(e)}"}
    
    def send_message(self, message, target=None, is_waiting_reply=False, wait_for_sender=None, 
                    timeout_seconds=60, max_replies=1):
        """
        发送消息并可选择等待回复
        
        Args:
            message: 消息内容
            target: 目标接收者，不指定则广播
            is_waiting_reply: 是否等待回复
            wait_for_sender: 指定等待的回复发送者，不指定则接受任何人的回复
            timeout_seconds: 等待回复的超时时间
            max_replies: 最大接收的回复数量
            
        Returns:
            消息发送结果
        """
        params = {
            'message': message,
        }
        
        if target:
            params['target'] = target
            
        if is_waiting_reply:
            params['is_waiting_reply'] = True
            
        if wait_for_sender:
            params['wait_for_sender'] = wait_for_sender
            
        params['timeout_seconds'] = timeout_seconds
        params['max_replies'] = max_replies
        
        print(f"[调试] SocketClient.send_message: 发送消息参数: {params}")
        
        return self.send_command('send_message', params)
    
    def get_messages(self, limit: Optional[int] = None, offset: int = 0) -> Dict[str, Any]:
        """获取历史消息
        
        Args:
            limit (Optional[int], optional): 消息数量限制，默认为None（全部）
            offset (int, optional): 起始偏移量，默认为0
            
        Returns:
            Dict[str, Any]: 包含消息列表的结果
        """
        if not self.is_connected():
            return {"status": "error", "message": "未连接到服务器"}
        
        try:
            params = {'offset': offset}
            if limit is not None:
                params['limit'] = limit
                
            return self._send_request('get_messages', params)
            
        except Exception as e:
            print(f"获取消息失败: {e}")
            return {"status": "error", "message": f"获取消息失败: {str(e)}"}
    
    def list_identities(self) -> Dict[str, Any]:
        """获取所有身份列表
        
        Returns:
            Dict[str, Any]: 包含身份列表的结果
        """
        if not self.is_connected():
            return {"status": "error", "message": "未连接到服务器"}
        
        try:
            return self._send_request('list_identities')
            
        except Exception as e:
            print(f"获取身份列表失败: {e}")
            return {"status": "error", "message": f"获取身份列表失败: {str(e)}"}
    
    def register_notification_handler(self, event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """注册特定事件类型的通知处理函数
        
        Args:
            event_type (str): 事件类型
            handler (Callable): 处理函数，接收事件数据作为参数
        """
        self.notification_handlers[event_type] = handler
    
    def register_callback(self, event_name: str, callback: Callable) -> None:
        """注册事件回调函数
        
        Args:
            event_name (str): 事件名称
            callback (Callable): 回调函数
        """
        self.callbacks[event_name] = callback
    
    def disconnect(self) -> None:
        """断开与服务器的连接"""
        if self.socket:
            try:
                self.running = False
                self.socket.close()
            except:
                pass
            finally:
                self.socket = None
                self.connected = False
                self.server_address = None
                print("已断开与服务器的连接")
    
    def is_connected(self) -> bool:
        """检查是否已连接到服务器
        
        Returns:
            bool: 是否已连接
        """
        return self.connected and self.socket is not None
    
    def _send_request(self, command: str, params: Dict[str, Any] = None, timeout: float = 30.0) -> Dict[str, Any]:
        """发送请求到服务器并等待响应
        
        Args:
            command (str): 命令名称
            params (Dict[str, Any], optional): 命令参数，默认为None
            timeout (float): 等待响应的超时时间（秒），默认为30秒
            
        Returns:
            Dict[str, Any]: 服务器响应
        """
        if not self.is_connected():
            raise ConnectionError("未连接到服务器")
        
        request = {
            'command': command,
            'timestamp': time.time()
        }
        
        if params:
            request['params'] = params
        
        # 发送请求
        request_str = json.dumps(request)
        print(f"发送请求: {command}, 参数: {params}")
        data = request_str.encode('utf-8')
        self.socket.sendall(data)
        
        # 等待响应
        # 注意：这里是简化的实现，实际上应该使用更复杂的消息匹配机制
        # 该函数假设请求-响应是一对一对应的，这在多线程环境可能不成立
        event = threading.Event()
        self.response = None
        
        def response_handler(resp):
            print(f"收到响应: {resp.get('status', 'unknown')}")
            self.response = resp
            event.set()
        
        # 临时注册响应处理函数
        old_callback = self.callbacks.get('response')
        self.callbacks['response'] = response_handler
        
        # 等待响应，使用传入的超时时间
        is_set = event.wait(timeout)
        
        # 恢复原有的回调函数
        if old_callback:
            self.callbacks['response'] = old_callback
        else:
            del self.callbacks['response']
        
        if not is_set or self.response is None:
            raise TimeoutError(f"等待服务器响应超时 ({timeout}秒)")
        
        return self.response
    
    def _receive_messages(self) -> None:
        """接收服务器消息的后台线程"""
        while self.running and self.socket:
            try:
                data = self.socket.recv(4096)
                if not data:
                    # 服务器关闭了连接
                    self._trigger_callback('disconnected')
                    self.disconnect()
                    break
                
                # 解析响应
                response = json.loads(data.decode('utf-8'))
                
                # 处理不同类型的消息
                if response.get('type') == 'notification':
                    # 这是一个通知
                    self._handle_notification(response)
                else:
                    # 这是一个普通响应
                    self._trigger_callback('response', response)
                    
            except ConnectionError:
                # 连接已断开
                self._trigger_callback('disconnected')
                self.disconnect()
                break
            except Exception as e:
                print(f"接收消息出错: {e}")
    
    def _handle_notification(self, notification: Dict[str, Any]) -> None:
        """处理服务器发送的通知
        
        Args:
            notification (Dict[str, Any]): 通知内容
        """
        event_type = notification.get('event_type')
        data = notification.get('data', {})
        
        # 输出接收到的通知信息，便于调试
        print(f"接收到通知: {event_type}")
        
        # 增强对新消息的处理
        if event_type == 'new_message':
            sender = data.get('sender')
            target = data.get('target')
            content = data.get('content', '')
            # 只处理发送给当前用户的消息或广播消息
            if (target == self.identity or target is None) and sender != self.identity:
                print(f"收到新消息: [{sender} -> {target or '广播'}]: {content[:50]}...")
        
        # 触发通用通知回调
        self._trigger_callback('notification', notification)
        
        # 触发特定类型的通知回调
        if event_type:
            self._trigger_callback(f'notification_{event_type}', data)
            
            # 调用注册的处理函数
            handler = self.notification_handlers.get(event_type)
            if handler:
                try:
                    handler(data)
                except Exception as e:
                    print(f"处理通知时出错: {e}")
    
    def _trigger_callback(self, event_name: str, *args, **kwargs) -> None:
        """触发指定事件的回调函数
        
        Args:
            event_name (str): 事件名称
            *args, **kwargs: 传递给回调函数的参数
        """
        callback = self.callbacks.get(event_name)
        if callback:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"执行回调函数时出错: {e}")
    
    def get_pending_replies(self) -> Dict[str, Any]:
        """获取等待当前用户回复的未读消息
        
        Returns:
            Dict[str, Any]: 等待回复的消息列表
        """
        if not self.is_connected():
            return {"status": "error", "message": "未连接到服务器"}
            
        if not self.identity:
            return {"status": "error", "message": "未设置身份，无法获取消息"}
            
        try:
            # 发送获取待回复消息命令
            result = self._send_request('get_pending_replies', {})
            # 确保返回结果中包含消息数量
            if "count" not in result and "messages" in result:
                result["count"] = len(result["messages"])
            return result
        except Exception as e:
            return {"status": "error", "message": f"获取待回复消息失败: {str(e)}"}
    
    def mark_and_reply(self, msg_id: str, reply_message: str) -> Dict[str, Any]:
        """标记一条消息为已读并回复发送者
        
        Args:
            msg_id (str): 要回复的消息ID
            reply_message (str): 回复内容
            
        Returns:
            Dict[str, Any]: 回复结果
        """
        if not self.is_connected():
            return {"status": "error", "message": "未连接到服务器"}
            
        if not self.identity:
            return {"status": "error", "message": "未设置身份，无法回复消息"}
            
        try:
            # 发送标记并回复命令
            return self._send_request("mark_and_reply", {
                "msg_id": msg_id,
                "reply_message": reply_message
            })
        except Exception as e:
            return {"status": "error", "message": f"标记并回复消息失败: {str(e)}"}

    def send_command(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送命令到服务器并等待响应
        
        Args:
            command (str): 命令名称
            params (Dict[str, Any], optional): 命令参数
            
        Returns:
            Dict[str, Any]: 服务器响应
        """
        # 这是_send_request方法的别名，提供兼容性
        return self._send_request(command, params)


# 使用示例
if __name__ == '__main__':
    client = SocketClient()
    
    # 连接服务器
    if client.link_server('localhost:8888'):
        # 测试连接
        result = client.test_connection()
        print(f"连接测试结果: {result}")
        
        # 设置身份
        identity = input("请输入你的身份: ")
        result = client.set_identity(identity)
        print(f"设置身份结果: {result}")
        
        # 获取所有身份
        identities = client.list_identities()
        print(f"当前在线的身份: {identities}")
        
        # 注册新消息通知处理函数
        def handle_new_message(data):
            sender = data.get('sender')
            content = data.get('content')
            print(f"\n收到来自 {sender} 的消息: {content}")
        
        client.register_notification_handler('new_message', handle_new_message)
        
        # 简单的命令行聊天循环
        try:
            while True:
                print("\n可用命令: send <消息> [目标], list, history, quit")
                cmd = input("> ").strip()
                
                if cmd.startswith("send "):
                    parts = cmd[5:].split(" to ")
                    message = parts[0]
                    target = parts[1] if len(parts) > 1 else None
                    
                    result = client.send_message(message, target)
                    print(f"发送结果: {result}")
                    
                elif cmd == "list":
                    identities = client.list_identities()
                    print(f"当前在线的身份: {identities}")
                    
                elif cmd == "history":
                    messages = client.get_messages()
                    print(f"历史消息: {messages}")
                    
                elif cmd == "quit":
                    break
                    
                else:
                    print("未知命令")
                    
        except KeyboardInterrupt:
            pass
        
        # 断开连接
        client.disconnect()
    else:
        print("无法连接到服务器!") 