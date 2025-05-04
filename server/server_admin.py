#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import json
import time
import argparse
import sys
import os
import threading
from typing import Dict, List, Any, Optional, Union

class ServerAdmin:
    """Socket服务器管理工具
    
    可以直接连接到运行中的服务器，查看和修改服务器内容
    """
    
    def __init__(self, host: str = 'localhost', port: int = 8889):
        """初始化管理工具
        
        Args:
            host: 服务器主机名
            port: 服务器管理端口（注意：这不是服务器主端口，而是管理端口）
        """
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.admin_id = None
        self.server_info = {}
    
    def connect(self) -> bool:
        """连接到服务器管理端口
        
        Returns:
            bool: 连接是否成功
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # 验证管理身份
            auth_response = self._send_command('admin_auth', {
                'admin_key': os.environ.get('SOCKET_ADMIN_KEY', 'admin_secret')
            })
            
            if auth_response.get('status') == 'success':
                self.admin_id = auth_response.get('admin_id')
                print(f"管理连接成功，管理员ID: {self.admin_id}")
                return True
            else:
                print(f"管理验证失败: {auth_response.get('message')}")
                self.disconnect()
                return False
                
        except Exception as e:
            print(f"连接服务器管理端口失败: {e}")
            self.socket = None
            self.connected = False
            return False
    
    def disconnect(self) -> None:
        """断开与服务器的连接"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            finally:
                self.socket = None
                self.connected = False
                self.admin_id = None
    
    def _send_command(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送管理命令到服务器
        
        Args:
            command: 命令名称
            params: 命令参数
            
        Returns:
            Dict[str, Any]: 服务器响应
        """
        if not self.connected:
            return {"status": "error", "message": "未连接到服务器"}
        
        request = {
            'admin_command': command,
            'admin_id': self.admin_id,
            'timestamp': time.time()
        }
        
        if params:
            request['params'] = params
        
        try:
            # 发送请求
            data = json.dumps(request).encode('utf-8')
            self.socket.sendall(data)
            
            # 接收响应
            response_data = self.socket.recv(8192)
            if not response_data:
                return {"status": "error", "message": "服务器已断开连接"}
            
            response = json.loads(response_data.decode('utf-8'))
            return response
            
        except Exception as e:
            return {"status": "error", "message": f"发送命令失败: {str(e)}"}
    
    def get_server_info(self) -> Dict[str, Any]:
        """获取服务器基本信息
        
        Returns:
            Dict[str, Any]: 服务器信息
        """
        response = self._send_command('get_server_info')
        if response.get('status') == 'success':
            self.server_info = response.get('server_info', {})
        return response
    
    def list_clients(self) -> Dict[str, Any]:
        """获取所有客户端连接信息
        
        Returns:
            Dict[str, Any]: 客户端列表
        """
        return self._send_command('list_clients')
    
    def list_identities(self) -> Dict[str, Any]:
        """获取所有身份信息
        
        Returns:
            Dict[str, Any]: 身份列表
        """
        return self._send_command('list_identities')
    
    def get_messages(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """获取消息历史
        
        Args:
            limit: 消息数量限制
            offset: 起始位置
            
        Returns:
            Dict[str, Any]: 消息列表
        """
        return self._send_command('get_messages', {
            'limit': limit,
            'offset': offset
        })
    
    def get_waiting_replies(self) -> Dict[str, Any]:
        """获取所有等待回复的消息
        
        Returns:
            Dict[str, Any]: 等待回复消息列表
        """
        return self._send_command('get_waiting_replies')
    
    def modify_message(self, msg_id: str, new_content: str = None, 
                      is_read: int = None, requires_reply: bool = None) -> Dict[str, Any]:
        """修改消息内容或状态
        
        Args:
            msg_id: 消息ID
            new_content: 新的消息内容
            is_read: 是否已读
            requires_reply: 是否需要回复
            
        Returns:
            Dict[str, Any]: 操作结果
        """
        params = {'msg_id': msg_id}
        if new_content is not None:
            params['content'] = new_content
        if is_read is not None:
            params['is_read'] = is_read
        if requires_reply is not None:
            params['requires_reply'] = requires_reply
            
        return self._send_command('modify_message', params)
    
    def send_system_message(self, target: str, content: str, 
                           is_waiting_reply: bool = False) -> Dict[str, Any]:
        """以系统身份发送消息
        
        Args:
            target: 目标用户
            content: 消息内容
            is_waiting_reply: 是否等待回复
            
        Returns:
            Dict[str, Any]: 操作结果
        """
        return self._send_command('send_system_message', {
            'target': target,
            'content': content,
            'is_waiting_reply': is_waiting_reply
        })
    
    def force_disconnect_client(self, client_id: str) -> Dict[str, Any]:
        """强制断开客户端连接
        
        Args:
            client_id: 客户端ID
            
        Returns:
            Dict[str, Any]: 操作结果
        """
        return self._send_command('force_disconnect', {
            'client_id': client_id
        })
    
    def clear_messages(self, target: str = None) -> Dict[str, Any]:
        """清除消息历史
        
        Args:
            target: 目标用户，不指定则清除所有消息
            
        Returns:
            Dict[str, Any]: 操作结果
        """
        params = {}
        if target:
            params['target'] = target
            
        return self._send_command('clear_messages', params)

    def modify_user_identity(self, old_identity: str, new_identity: str) -> Dict[str, Any]:
        """修改用户身份
        
        Args:
            old_identity: 旧身份
            new_identity: 新身份
            
        Returns:
            Dict[str, Any]: 操作结果
        """
        return self._send_command('modify_identity', {
            'old_identity': old_identity,
            'new_identity': new_identity
        })

def interactive_shell(admin: ServerAdmin):
    """交互式管理控制台
    
    Args:
        admin: ServerAdmin实例
    """
    print("==== Socket服务器管理控制台 ====")
    print("输入 'help' 查看可用命令")
    
    while True:
        try:
            cmd = input("\n管理控制台> ").strip()
            
            if cmd == 'exit' or cmd == 'quit':
                break
                
            elif cmd == 'help':
                print("\n可用命令:")
                print("  info           - 获取服务器信息")
                print("  clients        - 列出所有客户端")
                print("  identities     - 列出所有身份")
                print("  messages       - 查看消息历史")
                print("  waiting        - 查看等待回复的消息")
                print("  modify_msg     - 修改消息")
                print("  send_msg       - 发送系统消息")
                print("  disconnect     - 断开客户端")
                print("  clear_msgs     - 清除消息历史")
                print("  rename_user    - 修改用户身份")
                print("  exit/quit      - 退出管理控制台")
            
            elif cmd == 'info':
                result = admin.get_server_info()
                if result.get('status') == 'success':
                    info = result.get('server_info', {})
                    print("\n服务器信息:")
                    print(f"  运行时间: {info.get('uptime', 'N/A')}")
                    print(f"  客户端数: {info.get('client_count', 0)}")
                    print(f"  消息总数: {info.get('message_count', 0)}")
                    print(f"  版本: {info.get('version', 'N/A')}")
                else:
                    print(f"获取服务器信息失败: {result.get('message')}")
            
            elif cmd == 'clients':
                result = admin.list_clients()
                if result.get('status') == 'success':
                    clients = result.get('clients', [])
                    print(f"\n客户端列表 (共 {len(clients)} 个):")
                    for i, client in enumerate(clients):
                        print(f"  {i+1}. ID: {client.get('client_id')}")
                        print(f"     身份: {client.get('identity', '未设置')}")
                        print(f"     地址: {client.get('address', 'N/A')}")
                        print(f"     连接时间: {client.get('connected_at', 'N/A')}")
                else:
                    print(f"获取客户端列表失败: {result.get('message')}")
            
            elif cmd == 'identities':
                result = admin.list_identities()
                if result.get('status') == 'success':
                    identities = result.get('identities', [])
                    print(f"\n身份列表 (共 {len(identities)} 个):")
                    for i, identity in enumerate(identities):
                        print(f"  {i+1}. 身份: {identity.get('identity')}")
                        print(f"     客户端ID: {identity.get('client_id')}")
                        print(f"     连接时间: {identity.get('connected_at', 'N/A')}")
                else:
                    print(f"获取身份列表失败: {result.get('message')}")
            
            elif cmd == 'messages':
                limit = input("请输入要显示的消息数量 (默认20): ").strip()
                limit = int(limit) if limit.isdigit() else 20
                
                result = admin.get_messages(limit=limit)
                if result.get('status') == 'success':
                    messages = result.get('messages', [])
                    print(f"\n消息历史 (显示 {len(messages)}/{result.get('total', 0)} 条):")
                    for i, msg in enumerate(messages):
                        print(f"  {i+1}. ID: {msg.get('id')}")
                        print(f"     发送者: {msg.get('sender', 'N/A')}")
                        print(f"     目标: {msg.get('target', '广播')}")
                        print(f"     内容: {msg.get('content', '')[:50]}...")
                        print(f"     时间: {msg.get('timestamp', 'N/A')}")
                        print(f"     等待回复: {msg.get('is_waiting_reply', False)}")
                else:
                    print(f"获取消息历史失败: {result.get('message')}")
            
            elif cmd == 'waiting':
                result = admin.get_waiting_replies()
                if result.get('status') == 'success':
                    waiting = result.get('waiting_replies', [])
                    print(f"\n等待回复的消息 (共 {len(waiting)} 个):")
                    for i, msg in enumerate(waiting):
                        print(f"  {i+1}. ID: {msg.get('msg_id')}")
                        print(f"     发送者: {msg.get('sender', 'N/A')}")
                        print(f"     目标: {msg.get('target', 'N/A')}")
                        print(f"     内容: {msg.get('content', '')[:50]}...")
                        print(f"     创建时间: {msg.get('created_at', 'N/A')}")
                        print(f"     超时时间: {msg.get('timeout', 60)} 秒")
                        print(f"     回复数: {len(msg.get('reply_messages', []))}/{msg.get('max_replies', 1)}")
                else:
                    print(f"获取等待回复消息失败: {result.get('message')}")
            
            elif cmd == 'modify_msg':
                msg_id = input("请输入要修改的消息ID: ").strip()
                if not msg_id:
                    print("消息ID不能为空")
                    continue
                    
                new_content = input("请输入新的消息内容 (留空不修改): ").strip()
                if not new_content:
                    new_content = None
                
                is_read_input = input("设置已读状态 (0=未读, 1=已读, 留空不修改): ").strip()
                is_read = int(is_read_input) if is_read_input and is_read_input in ['0', '1'] else None
                
                requires_reply_input = input("设置需要回复 (true/false, 留空不修改): ").strip().lower()
                requires_reply = None
                if requires_reply_input == 'true':
                    requires_reply = True
                elif requires_reply_input == 'false':
                    requires_reply = False
                
                result = admin.modify_message(msg_id, new_content, is_read, requires_reply)
                if result.get('status') == 'success':
                    print("消息修改成功")
                else:
                    print(f"修改消息失败: {result.get('message')}")
            
            elif cmd == 'send_msg':
                target = input("请输入目标用户 (必填): ").strip()
                if not target:
                    print("目标用户不能为空")
                    continue
                
                content = input("请输入消息内容: ").strip()
                if not content:
                    print("消息内容不能为空")
                    continue
                
                wait_reply = input("是否等待回复 (true/false, 默认false): ").strip().lower() == 'true'
                
                result = admin.send_system_message(target, content, wait_reply)
                if result.get('status') == 'success':
                    print(f"系统消息发送成功，消息ID: {result.get('msg_id')}")
                else:
                    print(f"发送系统消息失败: {result.get('message')}")
            
            elif cmd == 'disconnect':
                client_id = input("请输入要断开的客户端ID: ").strip()
                if not client_id:
                    print("客户端ID不能为空")
                    continue
                
                confirm = input(f"确定要断开客户端 {client_id} 的连接吗? (yes/no): ").strip().lower()
                if confirm != 'yes':
                    print("操作已取消")
                    continue
                
                result = admin.force_disconnect_client(client_id)
                if result.get('status') == 'success':
                    print("客户端已断开连接")
                else:
                    print(f"断开客户端连接失败: {result.get('message')}")
            
            elif cmd == 'clear_msgs':
                target = input("请输入要清除消息的目标用户 (留空清除所有消息): ").strip()
                if not target:
                    confirm = input("确定要清除所有消息历史吗? (yes/no): ").strip().lower()
                else:
                    confirm = input(f"确定要清除用户 {target} 的所有消息吗? (yes/no): ").strip().lower()
                
                if confirm != 'yes':
                    print("操作已取消")
                    continue
                
                result = admin.clear_messages(target)
                if result.get('status') == 'success':
                    print(f"已清除 {result.get('count', 0)} 条消息")
                else:
                    print(f"清除消息失败: {result.get('message')}")
            
            elif cmd == 'rename_user':
                old_identity = input("请输入要修改的用户身份: ").strip()
                if not old_identity:
                    print("用户身份不能为空")
                    continue
                
                new_identity = input("请输入新的用户身份: ").strip()
                if not new_identity:
                    print("新身份不能为空")
                    continue
                
                result = admin.modify_user_identity(old_identity, new_identity)
                if result.get('status') == 'success':
                    print("用户身份修改成功")
                else:
                    print(f"修改用户身份失败: {result.get('message')}")
            
            else:
                print(f"未知命令: {cmd}")
                print("输入 'help' 查看可用命令")
                
        except KeyboardInterrupt:
            print("\n操作已取消")
        except Exception as e:
            print(f"执行命令出错: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Socket服务器管理工具')
    parser.add_argument('--host', default='localhost', help='服务器主机名')
    parser.add_argument('--port', type=int, default=8889, help='服务器管理端口')
    
    args = parser.parse_args()
    
    admin = ServerAdmin(host=args.host, port=args.port)
    try:
        if admin.connect():
            interactive_shell(admin)
        else:
            print("无法连接到服务器管理端口")
    finally:
        admin.disconnect()

if __name__ == '__main__':
    main() 