#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import threading
import json
import uuid
import time
import os
from typing import Dict, List, Any, Optional

class SocketServerAdmin:
    """Socket服务器管理模块
    
    为运行中的Socket服务器提供管理功能
    """
    
    def __init__(self, server, host: str = 'localhost', port: int = 8889):
        """初始化服务器管理模块
        
        Args:
            server: Socket服务器实例
            host: 管理接口主机名
            port: 管理接口端口
        """
        self.server = server
        self.host = host
        self.port = port
        self.admin_socket = None
        self.running = False
        self.admin_clients = {}  # 管理员连接信息: {admin_id: {socket, connected_at, etc}}
        self.admin_key = os.environ.get('SOCKET_ADMIN_KEY', 'admin_secret')  # 管理员密钥
        self.server_start_time = time.time()
        
        # 初始化管理命令处理器
        self.command_handlers = {
            'admin_auth': self._handle_admin_auth,
            'get_server_info': self._handle_get_server_info,
            'list_clients': self._handle_list_clients,
            'list_identities': self._handle_list_identities,
            'get_messages': self._handle_get_messages,
            'get_waiting_replies': self._handle_get_waiting_replies,
            'modify_message': self._handle_modify_message,
            'send_system_message': self._handle_send_system_message,
            'force_disconnect': self._handle_force_disconnect,
            'clear_messages': self._handle_clear_messages,
            'modify_identity': self._handle_modify_identity
        }
    
    def start(self):
        """启动管理服务"""
        if self.running:
            return
        
        try:
            self.admin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.admin_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.admin_socket.bind((self.host, self.port))
            self.admin_socket.listen(5)
            
            self.running = True
            print(f"服务器管理接口已启动，监听地址: {self.host}:{self.port}")
            
            # 启动接受管理连接的线程
            admin_thread = threading.Thread(target=self._accept_admin_clients)
            admin_thread.daemon = True
            admin_thread.start()
            
            return True
        except Exception as e:
            print(f"启动管理接口失败: {e}")
            if self.admin_socket:
                try:
                    self.admin_socket.close()
                except:
                    pass
            self.admin_socket = None
            self.running = False
            return False
    
    def stop(self):
        """停止管理服务"""
        self.running = False
        
        # 关闭所有管理连接
        for admin_info in list(self.admin_clients.values()):
            try:
                admin_info.get('socket').close()
            except:
                pass
        
        self.admin_clients.clear()
        
        # 关闭管理套接字
        if self.admin_socket:
            try:
                self.admin_socket.close()
            except:
                pass
            self.admin_socket = None
        
        print("服务器管理接口已关闭")
    
    def _accept_admin_clients(self):
        """接受管理客户端连接"""
        while self.running and self.admin_socket:
            try:
                client_socket, client_address = self.admin_socket.accept()
                admin_id = str(uuid.uuid4())
                
                # 存储管理员信息
                self.admin_clients[admin_id] = {
                    'socket': client_socket,
                    'address': client_address,
                    'connected_at': time.time(),
                    'authenticated': False
                }
                
                print(f"管理客户端 {client_address} 已连接，分配ID: {admin_id}")
                
                # 为每个管理客户端创建处理线程
                admin_thread = threading.Thread(target=self._handle_admin_client, args=(admin_id,))
                admin_thread.daemon = True
                admin_thread.start()
            except Exception as e:
                if self.running:
                    print(f"接受管理连接出错: {e}")
    
    def _handle_admin_client(self, admin_id: str):
        """处理管理客户端请求"""
        admin_info = self.admin_clients.get(admin_id)
        if not admin_info:
            return
        
        admin_socket = admin_info['socket']
        
        try:
            while self.running:
                try:
                    data = admin_socket.recv(8192)
                    if not data:
                        break  # 客户端断开连接
                    
                    # 解析请求
                    request = json.loads(data.decode('utf-8'))
                    self._process_admin_request(admin_id, request)
                except json.JSONDecodeError:
                    self._send_admin_response(admin_id, {'status': 'error', 'message': '无效的JSON格式'})
                except Exception as e:
                    self._send_admin_response(admin_id, {'status': 'error', 'message': f'处理请求出错: {str(e)}'})
        except Exception as e:
            print(f"处理管理客户端 {admin_id} 请求时出错: {e}")
        finally:
            # 清理管理客户端连接
            self._disconnect_admin_client(admin_id)
    
    def _disconnect_admin_client(self, admin_id: str):
        """断开管理客户端连接"""
        admin_info = self.admin_clients.pop(admin_id, None)
        if admin_info:
            try:
                admin_info['socket'].close()
            except:
                pass
            print(f"管理客户端 {admin_id} 已断开连接")
    
    def _send_admin_response(self, admin_id: str, response: dict):
        """向管理客户端发送响应"""
        admin_info = self.admin_clients.get(admin_id)
        if not admin_info:
            return
        
        admin_socket = admin_info['socket']
        try:
            data = json.dumps(response).encode('utf-8')
            admin_socket.sendall(data)
        except Exception as e:
            print(f"向管理客户端 {admin_id} 发送响应出错: {e}")
            self._disconnect_admin_client(admin_id)
    
    def _process_admin_request(self, admin_id: str, request: dict):
        """处理管理请求"""
        command = request.get('admin_command')
        params = request.get('params', {})
        
        # 身份验证检查（仅admin_auth命令可在未认证状态下执行）
        if command != 'admin_auth' and not self.admin_clients.get(admin_id, {}).get('authenticated', False):
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': '未经身份验证，请先进行身份验证'
            })
            return
        
        # 执行相应的命令处理函数
        handler = self.command_handlers.get(command)
        if handler:
            try:
                handler(admin_id, params)
            except Exception as e:
                self._send_admin_response(admin_id, {
                    'status': 'error',
                    'message': f'执行命令 {command} 时出错: {str(e)}'
                })
        else:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': f'未知命令: {command}'
            })
    
    # 管理命令处理函数
    def _handle_admin_auth(self, admin_id: str, params: dict):
        """处理管理员身份验证"""
        admin_key = params.get('admin_key')
        
        if admin_key == self.admin_key:
            # 验证成功
            if admin_id in self.admin_clients:
                self.admin_clients[admin_id]['authenticated'] = True
                
                self._send_admin_response(admin_id, {
                    'status': 'success',
                    'message': '身份验证成功',
                    'admin_id': admin_id
                })
                print(f"管理客户端 {admin_id} 验证通过")
        else:
            # 验证失败
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': '身份验证失败，密钥无效'
            })
            # 延迟断开连接，防止暴力破解
            threading.Timer(1.0, lambda: self._disconnect_admin_client(admin_id)).start()
    
    def _handle_get_server_info(self, admin_id: str, params: dict):
        """处理获取服务器信息请求"""
        uptime = time.time() - self.server_start_time
        client_count = len(self.server.clients)
        message_count = len(self.server.messages)
        
        server_info = {
            'uptime': uptime,
            'client_count': client_count,
            'message_count': message_count,
            'version': '1.0.0',  # 服务器版本
            'start_time': self.server_start_time
        }
        
        self._send_admin_response(admin_id, {
            'status': 'success',
            'server_info': server_info
        })
    
    def _handle_list_clients(self, admin_id: str, params: dict):
        """处理列出客户端请求"""
        clients_info = []
        
        for client_id, client_info in self.server.clients.items():
            clients_info.append({
                'client_id': client_id,
                'identity': client_info.get('identity'),
                'address': client_info.get('address'),
                'connected_at': client_info.get('connected_at')
            })
        
        self._send_admin_response(admin_id, {
            'status': 'success',
            'clients': clients_info,
            'count': len(clients_info)
        })
    
    def _handle_list_identities(self, admin_id: str, params: dict):
        """处理列出身份请求"""
        identities_info = []
        
        for identity, client_id in self.server.identities.items():
            client_info = self.server.clients.get(client_id, {})
            identities_info.append({
                'identity': identity,
                'client_id': client_id,
                'connected_at': client_info.get('connected_at')
            })
        
        self._send_admin_response(admin_id, {
            'status': 'success',
            'identities': identities_info,
            'count': len(identities_info)
        })
    
    def _handle_get_messages(self, admin_id: str, params: dict):
        """处理获取消息历史请求"""
        limit = params.get('limit', 50)
        offset = params.get('offset', 0)
        
        # 获取消息历史
        messages = self.server.messages
        total = len(messages)
        
        if offset >= total:
            filtered_messages = []
        else:
            end = offset + limit if offset + limit <= total else total
            filtered_messages = messages[offset:end]
        
        self._send_admin_response(admin_id, {
            'status': 'success',
            'messages': filtered_messages,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    
    def _handle_get_waiting_replies(self, admin_id: str, params: dict):
        """处理获取等待回复消息请求"""
        waiting_replies = []
        
        for msg_id, info in self.server.waiting_replies.items():
            waiting_replies.append({
                'msg_id': msg_id,
                'sender': info.get('sender'),
                'target': info.get('target'),
                'content': info.get('content'),
                'created_at': info.get('created_at'),
                'timeout': info.get('timeout'),
                'max_replies': info.get('max_replies'),
                'expired': info.get('expired', False),
                'reply_messages': info.get('reply_messages', [])
            })
        
        self._send_admin_response(admin_id, {
            'status': 'success',
            'waiting_replies': waiting_replies,
            'count': len(waiting_replies)
        })
    
    def _handle_modify_message(self, admin_id: str, params: dict):
        """处理修改消息请求"""
        msg_id = params.get('msg_id')
        if not msg_id:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': '消息ID不能为空'
            })
            return
        
        # 在消息历史中查找消息
        found_in_history = False
        for idx, msg in enumerate(self.server.messages):
            if msg.get('id') == msg_id:
                # 更新消息内容
                if 'content' in params:
                    self.server.messages[idx]['content'] = params['content']
                found_in_history = True
                break
        
        # 在未读消息中查找
        found_in_unread = False
        with self.server.unread_lock:
            for identity, messages in self.server.unread_messages.items():
                for idx, msg in enumerate(messages):
                    if msg.get('msg_id') == msg_id:
                        # 更新消息内容
                        if 'content' in params:
                            self.server.unread_messages[identity][idx]['message'] = params['content']
                        
                        # 更新消息状态
                        if 'is_read' in params:
                            self.server.unread_messages[identity][idx]['is_read'] = params['is_read']
                        
                        if 'requires_reply' in params:
                            self.server.unread_messages[identity][idx]['requires_reply'] = params['requires_reply']
                        
                        found_in_unread = True
                        break
        
        # 在等待回复的消息中查找
        found_in_waiting = False
        with self.server.waiting_lock:
            if msg_id in self.server.waiting_replies:
                # 更新消息内容
                if 'content' in params:
                    self.server.waiting_replies[msg_id]['content'] = params['content']
                found_in_waiting = True
        
        if found_in_history or found_in_unread or found_in_waiting:
            self._send_admin_response(admin_id, {
                'status': 'success',
                'message': '消息修改成功',
                'found_in': {
                    'history': found_in_history,
                    'unread': found_in_unread,
                    'waiting': found_in_waiting
                }
            })
        else:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': '未找到指定消息'
            })
    
    def _handle_send_system_message(self, admin_id: str, params: dict):
        """处理发送系统消息请求"""
        target = params.get('target')
        content = params.get('content')
        is_waiting_reply = params.get('is_waiting_reply', False)
        
        if not target:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': '目标用户不能为空'
            })
            return
        
        if not content:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': '消息内容不能为空'
            })
            return
        
        # 检查目标用户是否存在
        if target not in self.server.identities:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': f'目标用户 {target} 不存在'
            })
            return
        
        # 创建系统消息
        msg_id = str(uuid.uuid4())
        msg_timestamp = time.time()
        
        # 构造消息对象
        msg_obj = {
            'id': msg_id,
            'sender': 'System',
            'content': content,
            'target': target,
            'timestamp': msg_timestamp,
            'is_waiting_reply': is_waiting_reply,
            'is_system_message': True
        }
        
        # 存储消息
        self.server.messages.append(msg_obj)
        
        # 添加到用户未读消息列表
        with self.server.unread_lock:
            if target not in self.server.unread_messages:
                self.server.unread_messages[target] = []
            
            unread_msg = {
                'sender': 'System',
                'message': content,
                'msg_id': msg_id,
                'created_at': msg_timestamp,
                'is_read': 0 if is_waiting_reply else 1,
                'requires_reply': is_waiting_reply,
                'is_system_message': True
            }
            self.server.unread_messages[target].append(unread_msg)
        
        # 如果需要等待回复，添加到等待回复列表
        if is_waiting_reply:
            with self.server.waiting_lock:
                self.server.waiting_replies[msg_id] = {
                    'sender': 'System',
                    'target': target,
                    'content': content,
                    'created_at': msg_timestamp,
                    'timeout': 300,  # 默认5分钟超时
                    'max_replies': 1,
                    'expired': False,
                    'reply_messages': [],
                    'is_system_message': True
                }
        
        # 发送消息给目标用户
        target_client_id = self.server.identities.get(target)
        if target_client_id:
            self.server._send_response(target_client_id, {
                'type': 'notification',
                'event_type': 'new_message',
                'data': msg_obj
            })
            
            # 如果需要等待回复，发送等待回复通知
            if is_waiting_reply:
                self.server._send_response(target_client_id, {
                    'type': 'notification',
                    'event_type': 'waiting_reply_request',
                    'data': {
                        'msg_id': msg_id,
                        'sender': 'System',
                        'content': content,
                        'timestamp': msg_timestamp,
                        'timeout': 300,
                        'is_waiting_reply': True,
                        'is_system_message': True
                    }
                })
        
        self._send_admin_response(admin_id, {
            'status': 'success',
            'message': '系统消息发送成功',
            'msg_id': msg_id
        })
    
    def _handle_force_disconnect(self, admin_id: str, params: dict):
        """处理强制断开客户端请求"""
        client_id = params.get('client_id')
        if not client_id:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': '客户端ID不能为空'
            })
            return
        
        # 检查客户端是否存在
        if client_id not in self.server.clients:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': f'客户端 {client_id} 不存在'
            })
            return
        
        # 断开客户端连接
        self.server._disconnect_client(client_id)
        
        self._send_admin_response(admin_id, {
            'status': 'success',
            'message': f'客户端 {client_id} 已断开连接'
        })
    
    def _handle_clear_messages(self, admin_id: str, params: dict):
        """处理清除消息请求"""
        target = params.get('target')
        
        if target:
            # 清除特定用户的消息
            count = 0
            
            # 清除历史消息
            self.server.messages = [msg for msg in self.server.messages if msg.get('target') != target]
            
            # 清除未读消息
            with self.server.unread_lock:
                if target in self.server.unread_messages:
                    count += len(self.server.unread_messages[target])
                    del self.server.unread_messages[target]
            
            # 清除等待回复消息
            with self.server.waiting_lock:
                for msg_id in list(self.server.waiting_replies.keys()):
                    if self.server.waiting_replies[msg_id].get('target') == target:
                        count += 1
                        del self.server.waiting_replies[msg_id]
                
                # 更新用户等待回复映射
                for identity in list(self.server.waiting_by_user.keys()):
                    self.server.waiting_by_user[identity] = {
                        msg_id for msg_id in self.server.waiting_by_user[identity]
                        if msg_id in self.server.waiting_replies
                    }
            
            self._send_admin_response(admin_id, {
                'status': 'success',
                'message': f'已清除用户 {target} 的消息',
                'count': count
            })
        else:
            # 清除所有消息
            count = len(self.server.messages)
            
            # 清除历史消息
            self.server.messages = []
            
            # 清除未读消息
            with self.server.unread_lock:
                self.server.unread_messages.clear()
            
            # 清除等待回复消息
            with self.server.waiting_lock:
                self.server.waiting_replies.clear()
                self.server.waiting_by_user.clear()
            
            self._send_admin_response(admin_id, {
                'status': 'success',
                'message': '已清除所有消息',
                'count': count
            })
    
    def _handle_modify_identity(self, admin_id: str, params: dict):
        """处理修改用户身份请求"""
        old_identity = params.get('old_identity')
        new_identity = params.get('new_identity')
        
        if not old_identity or not new_identity:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': '原身份和新身份不能为空'
            })
            return
        
        # 检查原身份是否存在
        if old_identity not in self.server.identities:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': f'身份 {old_identity} 不存在'
            })
            return
        
        # 检查新身份是否已被使用
        if new_identity in self.server.identities and self.server.identities[new_identity] != self.server.identities[old_identity]:
            self._send_admin_response(admin_id, {
                'status': 'error',
                'message': f'身份 {new_identity} 已被使用'
            })
            return
        
        # 获取用户的客户端ID
        client_id = self.server.identities[old_identity]
        
        # 更新身份映射
        del self.server.identities[old_identity]
        self.server.identities[new_identity] = client_id
        
        # 更新客户端信息
        self.server.clients[client_id]['identity'] = new_identity
        
        # 更新消息中的发送者和目标
        for msg in self.server.messages:
            if msg.get('sender') == old_identity:
                msg['sender'] = new_identity
            if msg.get('target') == old_identity:
                msg['target'] = new_identity
        
        # 更新未读消息
        with self.server.unread_lock:
            # 修改发送者
            for target, messages in self.server.unread_messages.items():
                for msg in messages:
                    if msg.get('sender') == old_identity:
                        msg['sender'] = new_identity
            
            # 修改目标
            if old_identity in self.server.unread_messages:
                messages = self.server.unread_messages.pop(old_identity)
                self.server.unread_messages[new_identity] = messages
        
        # 更新等待回复消息
        with self.server.waiting_lock:
            for msg_id, info in self.server.waiting_replies.items():
                if info.get('sender') == old_identity:
                    info['sender'] = new_identity
                if info.get('target') == old_identity:
                    info['target'] = new_identity
            
            # 更新用户等待回复映射
            if old_identity in self.server.waiting_by_user:
                waiting_msgs = self.server.waiting_by_user.pop(old_identity)
                self.server.waiting_by_user[new_identity] = waiting_msgs
        
        # 通知客户端身份已更改
        self.server._send_response(client_id, {
            'type': 'notification',
            'event_type': 'identity_change',
            'data': {
                'client_id': client_id,
                'old_identity': old_identity,
                'new_identity': new_identity
            }
        })
        
        # 广播身份变更通知
        self.server._broadcast_event('identity_change', {
            'client_id': client_id,
            'old_identity': old_identity,
            'new_identity': new_identity
        })
        
        self._send_admin_response(admin_id, {
            'status': 'success',
            'message': f'身份已从 {old_identity} 修改为 {new_identity}',
            'client_id': client_id
        })

def add_admin_interface(server, host='localhost', port=8889):
    """为Socket服务器添加管理接口
    
    Args:
        server: Socket服务器实例
        host: 管理接口主机名
        port: 管理接口端口
        
    Returns:
        SocketServerAdmin: 管理接口实例
    """
    admin = SocketServerAdmin(server, host, port)
    if admin.start():
        # 添加关闭钩子
        original_stop = server.stop
        
        def new_stop():
            admin.stop()
            original_stop()
        
        server.stop = new_stop
        
        return admin
    return None 