import socket
import threading
import json
import uuid
import time
from typing import Dict, List, Set, Any, Optional, Callable, Tuple

class SocketServer:
    def __init__(self, host: str = 'localhost', port: int = 8888):
        """初始化socket服务器"""
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients: Dict[str, dict] = {}  # 客户端连接信息: {client_id: {socket, identity, etc}}
        self.identities: Dict[str, str] = {}  # 身份到客户端ID的映射: {identity: client_id}
        self.messages: List[dict] = []  # 消息历史
        self.running = False
        
        # 待回复消息跟踪系统
        self.waiting_replies: Dict[str, dict] = {}  # 格式: {消息ID: {sender, target, created_at, timeout, expired, reply_messages}}
        self.waiting_by_user: Dict[str, Set[str]] = {}  # 用户到等待消息ID的映射: {identity: {msg_id1, msg_id2...}}
        self.waiting_lock = threading.Lock()  # 线程锁保护并发访问
        
        # 未读消息系统
        # 格式: {接收者: [{'sender': 发送者, 'message': 消息内容, 'msg_id': 消息ID, 'created_at': 创建时间, 'is_read': 是否已读}]}
        self.unread_messages: Dict[str, List[dict]] = {}
        self.unread_lock = threading.Lock()
        
        # 启动待回复检查线程
        self.reply_checker_thread = None

    def start(self):
        """启动服务器"""
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        print(f"服务器启动成功，监听地址: {self.host}:{self.port}")
        
        # 启动接受客户端连接的线程
        accept_thread = threading.Thread(target=self._accept_clients)
        accept_thread.daemon = True
        accept_thread.start()
        
        # 启动待回复检查线程
        self.reply_checker_thread = threading.Thread(target=self._check_waiting_replies)
        self.reply_checker_thread.daemon = True
        self.reply_checker_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """停止服务器"""
        self.running = False
        for client_info in self.clients.values():
            client_socket = client_info.get('socket')
            if client_socket:
                try:
                    client_socket.close()
                except:
                    pass
        self.server_socket.close()
        print("服务器已关闭")
    
    def _check_waiting_replies(self):
        """检查待回复消息的状态，处理超时"""
        while self.running:
            try:
                current_time = time.time()
                expired_msgs = []
                
                # 获取已过期的消息
                with self.waiting_lock:
                    for msg_id, info in list(self.waiting_replies.items()):
                        if not info.get('expired', False):
                            created_at = info.get('created_at', 0)
                            timeout = info.get('timeout', 60)
                            
                            # 检查是否超时
                            if current_time - created_at > timeout:
                                # 标记为已过期
                                info['expired'] = True
                                info['expired_at'] = current_time
                                expired_msgs.append((msg_id, info))
                
                # 处理超时通知
                for msg_id, info in expired_msgs:
                    sender = info.get('sender')
                    if sender in self.identities:
                        sender_client_id = self.identities[sender]
                        # 通知发送者消息已超时
                        self._send_response(sender_client_id, {
                            'type': 'notification',
                            'event_type': 'reply_timeout',
                            'data': {
                                'msg_id': msg_id,
                                'target': info.get('target'),
                                'content': info.get('content'),
                                'created_at': info.get('created_at'),
                                'timeout': info.get('timeout'),
                                'reply_count': len(info.get('reply_messages', []))
                            }
                        })
                
                # 每5秒检查一次
                time.sleep(5)
            
            except Exception as e:
                print(f"检查待回复消息时出错: {e}")
                time.sleep(5)  # 出错时等待一下再继续
    
    def _accept_clients(self):
        """接受客户端连接"""
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                client_id = str(uuid.uuid4())
                
                # 存储客户端信息
                self.clients[client_id] = {
                    'socket': client_socket,
                    'address': client_address,
                    'identity': None,
                    'connected_at': time.time()
                }
                
                print(f"客户端 {client_address} 已连接，分配ID: {client_id}")
                
                # 为每个客户端创建处理线程
                client_thread = threading.Thread(target=self._handle_client, args=(client_id,))
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                print(f"接受客户端连接出错: {e}")
                if not self.running:
                    break
    
    def _handle_client(self, client_id: str):
        """处理客户端请求"""
        client_info = self.clients.get(client_id)
        if not client_info:
            return
        
        client_socket = client_info['socket']
        
        try:
            while self.running:
                data = client_socket.recv(4096)
                if not data:
                    break  # 客户端断开连接
                
                # 解析请求
                try:
                    request = json.loads(data.decode('utf-8'))
                    self._process_request(client_id, request)
                except json.JSONDecodeError:
                    self._send_response(client_id, {'status': 'error', 'message': '无效的JSON格式'})
                except Exception as e:
                    self._send_response(client_id, {'status': 'error', 'message': f'处理请求出错: {str(e)}'})
        except ConnectionError:
            pass
        except Exception as e:
            print(f"处理客户端 {client_id} 请求时出错: {e}")
        finally:
            # 清理客户端连接
            self._disconnect_client(client_id)
    
    def _disconnect_client(self, client_id: str):
        """断开客户端连接并清理资源"""
        if client_id in self.clients:
            client_info = self.clients[client_id]
            identity = client_info.get('identity')
            
            # 关闭套接字
            try:
                client_info['socket'].close()
            except:
                pass
            
            # 从身份映射中移除
            if identity and identity in self.identities:
                del self.identities[identity]
            
            # 从客户端列表中移除
            del self.clients[client_id]
            
            print(f"客户端 {client_id} ({identity if identity else '未设置身份'}) 已断开连接")
            
            # 发送客户端断开连接的通知
            self._broadcast_event('client_disconnect', {
                'client_id': client_id,
                'identity': identity
            })
    
    def _process_request(self, client_id: str, request: dict):
        """处理客户端请求"""
        command = request.get('command')
        params = request.get('params', {})
        
        # 处理不同的命令
        if command == 'test_connection':
            self._handle_test_connection(client_id)
        elif command == 'set_identity':
            self._handle_set_identity(client_id, params.get('identity'))
        elif command == 'send_message':
            # 增加对等待回复参数的支持
            self._handle_send_message(
                client_id, 
                params.get('message'), 
                params.get('target'),
                params.get('is_waiting_reply', False),
                params.get('wait_for_sender'),
                params.get('timeout_seconds', 60),
                params.get('max_replies', 1)
            )
        elif command == 'get_messages':
            self._handle_get_messages(client_id, params.get('limit'), params.get('offset'))
        elif command == 'list_identities':
            self._handle_list_identities(client_id)
        elif command == 'get_message_replies':
            self._handle_get_message_replies(
                client_id,
                params.get('msg_id')
            )
        elif command == 'get_task_replies':
            self._handle_get_task_replies(
                client_id,
                params.get('task_index', 0)
            )
        elif command == 'get_pending_replies':
            self._handle_get_pending_replies(client_id, params.get('identity'), params.get('max_count', 10))
        elif command == 'mark_and_reply':
            self._handle_mark_and_reply(client_id, params.get('msg_id'), params.get('reply_message'))
        else:
            self._send_response(client_id, {'status': 'error', 'message': f'未知命令: {command}'})
    
    def _send_response(self, client_id: str, response: dict):
        """向客户端发送响应"""
        client_info = self.clients.get(client_id)
        if not client_info:
            return
        
        client_socket = client_info['socket']
        try:
            data = json.dumps(response).encode('utf-8')
            client_socket.sendall(data)
        except Exception as e:
            print(f"向客户端 {client_id} 发送响应时出错: {e}")
            self._disconnect_client(client_id)
    
    def _broadcast_event(self, event_type: str, event_data: dict):
        """广播事件给所有客户端"""
        for client_id in list(self.clients.keys()):
            if client_id in self.clients:
                self._send_response(client_id, {
                    'type': 'notification',
                    'event_type': event_type,
                    'data': event_data
                })
    
    # 处理各种命令的方法
    def _handle_test_connection(self, client_id: str):
        """处理测试连接请求"""
        self._send_response(client_id, {
            'status': 'success',
            'message': '连接正常',
            'timestamp': time.time()
        })
    
    def _handle_set_identity(self, client_id: str, identity: str):
        """处理设置身份请求"""
        if not identity:
            self._send_response(client_id, {'status': 'error', 'message': '身份不能为空'})
            return
        
        # 检查身份是否已被使用
        if identity in self.identities and self.identities[identity] != client_id:
            self._send_response(client_id, {'status': 'error', 'message': '该身份已被使用'})
            return
        
        # 如果客户端之前设置了不同的身份，需要清除旧的映射
        old_identity = self.clients[client_id].get('identity')
        if old_identity and old_identity in self.identities:
            del self.identities[old_identity]
        
        # 设置新身份
        self.clients[client_id]['identity'] = identity
        self.identities[identity] = client_id
        
        self._send_response(client_id, {
            'status': 'success',
            'message': '身份设置成功',
            'client_id': client_id,
            'identity': identity
        })
        
        # 广播身份变更事件
        self._broadcast_event('identity_change', {
            'client_id': client_id,
            'identity': identity,
            'old_identity': old_identity
        })
    
    def _handle_send_message(self, client_id: str, message: str, target: Optional[str] = None,
                           is_waiting_reply: bool = False, wait_for_sender: Optional[str] = None,
                           timeout_seconds: int = 60, max_replies: int = 1):
        """处理发送消息请求"""
        if not message and not is_waiting_reply:  # 允许空消息用于纯等待回复场景
            self._send_response(client_id, {'status': 'error', 'message': '消息内容不能为空'})
            return
        
        sender_identity = self.clients[client_id].get('identity')
        if not sender_identity:
            self._send_response(client_id, {'status': 'error', 'message': '请先设置身份'})
            return
        
        # 打印详细参数信息，便于调试
        print(f"[调试] 发送消息: 发送者={sender_identity}, 目标={target}, 等待回复={is_waiting_reply}, 等待发送者={wait_for_sender}")
        
        # 创建消息对象
        msg_id = str(uuid.uuid4())
        msg_timestamp = time.time()
        msg_obj = {
            'id': msg_id,
            'sender': sender_identity,
            'sender_id': client_id,
            'content': message,
            'target': target,
            'timestamp': msg_timestamp,
            'is_waiting_reply': is_waiting_reply
        }
        
        # 如果是等待回复的消息，添加到等待系统
        if is_waiting_reply:
            print(f"[调试] 添加等待回复消息: ID={msg_id}, 发送者={sender_identity}, 目标={target}, 等待={wait_for_sender}, 超时={timeout_seconds}秒")
            with self.waiting_lock:
                # 创建待回复记录
                self.waiting_replies[msg_id] = {
                    'sender': sender_identity,
                    'target': target,
                    'wait_for_sender': wait_for_sender,
                    'content': message,
                    'created_at': msg_timestamp,
                    'timeout': timeout_seconds,
                    'max_replies': max_replies,
                    'expired': False,
                    'reply_messages': []
                }
                
                # 更新用户到消息的映射
                if sender_identity not in self.waiting_by_user:
                    self.waiting_by_user[sender_identity] = set()
                self.waiting_by_user[sender_identity].add(msg_id)
                
                # 打印当前等待回复的消息数量
                print(f"[调试] 当前等待回复的消息总数: {len(self.waiting_replies)}")
                print(f"[调试] 用户 {sender_identity} 的等待回复消息数: {len(self.waiting_by_user.get(sender_identity, set()))}")
        
        # 检查这个消息是否是对其他消息的回复
        self._check_if_reply(msg_obj)
        
        # 存储消息
        self.messages.append(msg_obj)
        
        # 如果有指定目标，添加到目标用户的未读消息列表
        if target:
            with self.unread_lock:
                if target not in self.unread_messages:
                    self.unread_messages[target] = []
                
                # 添加未读消息，根据is_waiting_reply设置is_read状态
                unread_msg = {
                    'sender': sender_identity,
                    'message': message,
                    'msg_id': msg_id,
                    'created_at': msg_timestamp,
                    'is_read': 0 if is_waiting_reply else 1,  # 等待回复的消息设为未读，否则设为已读
                    'requires_reply': is_waiting_reply
                }
                self.unread_messages[target].append(unread_msg)
                print(f"[调试] 已添加消息到 {target} 的未读列表，当前有 {len(self.unread_messages[target])} 条未读消息")
        
        # 回复发送者
        self._send_response(client_id, {
            'status': 'success',
            'message': '消息发送成功',
            'msg_id': msg_id,
            'is_waiting_reply': is_waiting_reply
        })
        
        # 如果有指定目标，只发送给指定身份
        if target and target in self.identities:
            target_client_id = self.identities[target]
            # 发送新消息通知
            self._send_response(target_client_id, {
                'type': 'notification',
                'event_type': 'new_message',
                'data': msg_obj
            })
            
            # 如果是等待回复的消息，发送附加通知
            if is_waiting_reply:
                print(f"[调试] 向目标 {target} 发送等待回复通知")
                self._send_response(target_client_id, {
                    'type': 'notification',
                    'event_type': 'waiting_reply_request',
                    'data': {
                        'msg_id': msg_id,
                        'sender': sender_identity,
                        'content': message,
                        'timestamp': msg_timestamp,
                        'timeout': timeout_seconds,
                        'is_waiting_reply': True
                    }
                })
        else:
            # 广播给所有客户端
            self._broadcast_event('new_message', msg_obj)
    
    def _check_if_reply(self, message: dict):
        """检查消息是否是对其他消息的回复"""
        msg_id = message.get('id', '')
        sender = message.get('sender', '')
        target = message.get('target', None)
        content = message.get('content', '')
        
        print(f"[调试] 检查消息是否为回复: ID={msg_id}, 发送者={sender}, 目标={target}")
        
        # 如果没有目标，则不可能是回复
        if not target:
            print(f"[调试] 消息无目标，不是回复")
            return False
        
        with self.waiting_lock:
            # 打印当前等待回复的消息状态
            print(f"[调试] 当前等待回复消息: {len(self.waiting_replies)}个")
            for waiting_id, waiting_info in self.waiting_replies.items():
                wait_sender = waiting_info.get('sender', '')
                wait_target = waiting_info.get('target', None)
                wait_for = waiting_info.get('wait_for_sender', None)
                print(f"[调试] - 等待ID={waiting_id}, 发送者={wait_sender}, 目标={wait_target}, 等待回复者={wait_for}")
            
            # 寻找匹配的等待回复消息
            for waiting_id, waiting_info in list(self.waiting_replies.items()):
                # 已过期的不处理
                if waiting_info.get('expired', False):
                    continue
                
                wait_sender = waiting_info.get('sender', '')
                wait_target = waiting_info.get('target', None)
                wait_for = waiting_info.get('wait_for_sender', None)
                wait_time = waiting_info.get('created_at', 0)
                timeout = waiting_info.get('timeout', 60)
                max_replies = waiting_info.get('max_replies', 1)
                replies = waiting_info.get('reply_messages', [])
                
                # 检查是否超时
                current_time = time.time()
                if (current_time - wait_time) > timeout:
                    print(f"[调试] 消息ID={waiting_id}已超时，不再接受回复")
                    waiting_info['expired'] = True
                    continue
                
                # 验证是否为回复:
                # 1. 目标用户必须是等待回复的发送者
                # 2. 如果指定了特定的回复者，则发送者必须匹配
                is_reply = (target == wait_sender)
                if wait_for and sender != wait_for:
                    is_reply = False
                
                if wait_target and wait_target != sender:
                    is_reply = False
                
                if is_reply:
                    print(f"[调试] 找到匹配的回复! 原消息ID={waiting_id}, 回复ID={msg_id}")
                    
                    # 添加到回复列表
                    reply_obj = {
                        'id': msg_id,
                        'sender': sender,
                        'content': content,
                        'timestamp': message.get('timestamp', time.time())
                    }
                    waiting_info['reply_messages'].append(reply_obj)
                    
                    # 检查是否达到最大回复数
                    current_replies = len(waiting_info['reply_messages'])
                    print(f"[调试] 当前回复数: {current_replies}/{max_replies}")
                    
                    # 如果达到最大回复数，标记为完成
                    if current_replies >= max_replies:
                        print(f"[调试] 达到最大回复数，标记消息为已完成")
                        waiting_info['expired'] = True
                    
                    # 发送回复通知给原始发送者
                    if wait_sender in self.identities:
                        original_sender_client = self.identities[wait_sender]
                        print(f"[调试] 向原始发送者 {wait_sender} 发送回复通知")
                        self._send_response(original_sender_client, {
                            'type': 'notification',
                            'event_type': 'reply_received',
                            'data': {
                                'original_msg_id': waiting_id,
                                'reply_msg_id': msg_id,
                                'sender': sender,
                                'content': content,
                                'timestamp': message.get('timestamp', time.time()),
                                'reply_count': current_replies,
                                'max_replies': max_replies
                            }
                        })
                    
                    # 如果有目标用户，添加到未读列表
                    with self.unread_lock:
                        if target not in self.unread_messages:
                            self.unread_messages[target] = []
                        
                        # 添加回复消息，设置为已读
                        unread_reply = {
                            'sender': sender,
                            'message': content,
                            'msg_id': msg_id,
                            'created_at': message.get('timestamp', time.time()),
                            'is_read': 1,  # 回复消息默认已读
                            'requires_reply': False,
                            'in_reply_to': waiting_id
                        }
                        self.unread_messages[target].append(unread_reply)
                    
                    return True
        
        return False
    
    def _handle_get_messages(self, client_id: str, limit: int = None, offset: int = 0):
        """处理获取消息历史请求"""
        limit = limit if limit is not None else len(self.messages)
        offset = max(0, offset)
        
        filtered_messages = self.messages[offset:offset+limit] if offset + limit <= len(self.messages) else self.messages[offset:]
        
        self._send_response(client_id, {
            'status': 'success',
            'messages': filtered_messages,
            'total': len(self.messages),
            'limit': limit,
            'offset': offset
        })
    
    def _handle_list_identities(self, client_id: str):
        """处理列出身份请求"""
        identity_list = []
        for identity, cid in self.identities.items():
            client_info = self.clients.get(cid, {})
            identity_list.append({
                'identity': identity,
                'client_id': cid,
                'connected_at': client_info.get('connected_at')
            })
        
        self._send_response(client_id, {
            'status': 'success',
            'identities': identity_list,
            'count': len(identity_list)
        })

    # 添加获取消息回复的处理方法
    def _handle_get_message_replies(self, client_id: str, msg_id: str):
        """处理获取指定消息回复的请求
        
        Args:
            client_id: 客户端ID
            msg_id: 消息ID
        """
        sender_identity = self.clients[client_id].get('identity')
        if not sender_identity:
            self._send_response(client_id, {'status': 'error', 'message': '请先设置身份'})
            return
        
        if not msg_id:
            self._send_response(client_id, {'status': 'error', 'message': '消息ID不能为空'})
            return
        
        with self.waiting_lock:
            # 检查消息是否存在且属于当前用户
            if msg_id not in self.waiting_replies:
                self._send_response(client_id, {'status': 'error', 'message': '找不到指定消息'})
                return
            
            waiting_info = self.waiting_replies[msg_id]
            
            # 检查消息是否属于当前用户
            if waiting_info.get('sender') != sender_identity:
                self._send_response(client_id, {'status': 'error', 'message': '无权查看此消息的回复'})
                return
            
            # 获取回复信息
            reply_messages = waiting_info.get('reply_messages', [])
            is_expired = waiting_info.get('expired', False)
            is_completed = waiting_info.get('completed', False)
            
            # 构造响应
            self._send_response(client_id, {
                'status': 'success',
                'message': f'获取到 {len(reply_messages)} 条回复',
                'msg_id': msg_id,
                'target': waiting_info.get('target'),
                'content': waiting_info.get('content'),
                'created_at': waiting_info.get('created_at'),
                'timeout': waiting_info.get('timeout'),
                'max_replies': waiting_info.get('max_replies'),
                'expired': is_expired,
                'completed': is_completed,
                'replies': reply_messages,
                'reply_count': len(reply_messages)
            })
    
    def _handle_get_task_replies(self, client_id: str, task_index: int):
        """处理获取任务回复的请求，通过任务索引
        
        Args:
            client_id: 客户端ID
            task_index: 任务索引
        """
        sender_identity = self.clients[client_id].get('identity')
        if not sender_identity:
            self._send_response(client_id, {'status': 'error', 'message': '请先设置身份'})
            return
        
        with self.waiting_lock:
            if sender_identity not in self.waiting_by_user:
                self._send_response(client_id, {'status': 'error', 'message': '没有待办任务'})
                return
            
            # 获取用户的所有任务
            msg_ids = list(self.waiting_by_user.get(sender_identity, set()))
            
            if task_index < 0 or task_index >= len(msg_ids):
                self._send_response(client_id, {
                    'status': 'error', 
                    'message': f'无效的任务索引 {task_index}，当前有 {len(msg_ids)} 个任务'
                })
                return
            
            # 获取指定任务ID
            msg_id = msg_ids[task_index]
            
            # 使用消息ID获取回复
            waiting_info = self.waiting_replies.get(msg_id)
            if not waiting_info:
                self._send_response(client_id, {'status': 'error', 'message': '任务不存在'})
                return
            
            # 获取回复信息
            reply_messages = waiting_info.get('reply_messages', [])
            is_expired = waiting_info.get('expired', False)
            is_completed = waiting_info.get('completed', False)
            
            # 构造响应
            self._send_response(client_id, {
                'status': 'success',
                'message': f'获取到 {len(reply_messages)} 条回复',
                'task_index': task_index,
                'msg_id': msg_id,
                'target': waiting_info.get('target'),
                'content': waiting_info.get('content'),
                'created_at': waiting_info.get('created_at'),
                'timeout': waiting_info.get('timeout'),
                'max_replies': waiting_info.get('max_replies'),
                'expired': is_expired,
                'completed': is_completed,
                'replies': reply_messages,
                'reply_count': len(reply_messages)
            })

    def _handle_get_pending_replies(self, client_id: str, identity: str = None, max_count: int = 10):
        """处理获取待回复消息请求"""
        # 验证身份
        if not identity:
            identity = self.clients[client_id].get('identity')
            if not identity:
                self._send_response(client_id, {'status': 'error', 'message': '请先设置身份'})
                return
        
        print(f"[调试] 获取用户 {identity} 的待回复消息，最大数量: {max_count}")
        
        # 获取用户的未读消息
        with self.unread_lock:
            if identity not in self.unread_messages:
                print(f"[调试] 用户 {identity} 没有未读消息")
                self._send_response(client_id, {
                    'status': 'success',
                    'message': '没有待回复的消息',
                    'messages': [],
                    'count': 0
                })
                return
            
            # 过滤需要回复的消息
            pending_messages = []
            for msg in self.unread_messages[identity]:
                # 优先返回需要回复的消息
                if msg.get('requires_reply', False):
                    pending_messages.append(msg)
                # 如果不够，返回普通未读消息
                elif len(pending_messages) < max_count:
                    pending_messages.append(msg)
                
                if len(pending_messages) >= max_count:
                    break
            
            # 标记这些消息为已读
            for msg in pending_messages:
                msg['is_read'] = 1
            
            # 清理已读消息
            self.unread_messages[identity] = [msg for msg in self.unread_messages[identity] if msg['is_read'] == 0]
            
            print(f"[调试] 为用户 {identity} 返回 {len(pending_messages)} 条待回复消息，剩余 {len(self.unread_messages[identity])} 条未读消息")
            
            # 返回消息
            self._send_response(client_id, {
                'status': 'success',
                'message': f'获取到 {len(pending_messages)} 条待回复的消息',
                'messages': pending_messages,
                'count': len(pending_messages)
            })

    def _handle_mark_and_reply(self, client_id: str, msg_id: str, reply_message: str):
        """处理标记消息为已读并回复的请求"""
        identity = self.clients[client_id].get('identity')
        if not identity:
            self._send_response(client_id, {'status': 'error', 'message': '请先设置身份'})
            return
        
        # 查找消息并标记为已读
        found_message = None
        sender_identity = None
        
        with self.unread_lock:
            if identity in self.unread_messages:
                for msg in self.unread_messages[identity]:
                    if msg.get('msg_id') == msg_id:
                        msg['is_read'] = 1  # 标记为已读
                        found_message = msg.copy()
                        sender_identity = msg.get('sender')
                        break
                
                # 清除已读消息
                self.unread_messages[identity] = [msg for msg in self.unread_messages[identity] if msg['is_read'] == 0]
                
                # 如果没有未读消息了，删除此用户的记录
                if not self.unread_messages[identity]:
                    del self.unread_messages[identity]
        
        if not found_message:
            self._send_response(client_id, {"status": "error", "message": "找不到指定消息"})
            return
        
        # 发送回复
        if sender_identity:
            # 使用找到的发送者作为目标，发送回复消息
            # 创建回复消息对象
            reply_id = str(uuid.uuid4())
            reply_timestamp = time.time()
            reply_obj = {
                'id': reply_id,
                'sender': identity,
                'sender_id': client_id,
                'content': reply_message,
                'target': sender_identity,
                'timestamp': reply_timestamp,
                'is_waiting_reply': False,
                'in_reply_to': msg_id
            }
            
            # 存储消息
            self.messages.append(reply_obj)
            
            # 添加到发送者的未读消息列表
            with self.unread_lock:
                if sender_identity not in self.unread_messages:
                    self.unread_messages[sender_identity] = []
                
                # 添加未读消息
                unread_reply = {
                    'sender': identity,
                    'message': reply_message,
                    'msg_id': reply_id,
                    'created_at': reply_timestamp,
                    'is_read': 0,  # 默认未读
                    'requires_reply': False,
                    'in_reply_to': msg_id
                }
                self.unread_messages[sender_identity].append(unread_reply)
            
            # 检查原始消息是否是等待回复的消息
            self._check_if_reply(reply_obj)
            
            # 如果原始发送者在线，发送通知
            if sender_identity in self.identities:
                sender_client_id = self.identities[sender_identity]
                self._send_response(sender_client_id, {
                    'type': 'notification',
                    'event_type': 'new_message',
                    'data': reply_obj
                })
            
            # 返回成功结果
            self._send_response(client_id, {
                "status": "success",
                "message": "已标记消息为已读并发送回复",
                "original_message": found_message,
                "reply_id": reply_id
            })
        else:
            self._send_response(client_id, {"status": "error", "message": "无法确定消息发送者，无法回复"})


if __name__ == '__main__':
    server = SocketServer()
    try:
        # 初始化管理接口
        import socket_server_admin
        admin_interface = socket_server_admin.add_admin_interface(server, port=8889)
        if admin_interface:
            print("服务器管理接口已启动，可使用server_admin.py进行管理")
        else:
            print("警告: 服务器管理接口启动失败")
            
        # 启动主服务器
        server.start()
    except KeyboardInterrupt:
        print("接收到终止信号，正在关闭服务器...")
        server.stop() 