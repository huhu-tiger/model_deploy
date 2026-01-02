import time
import os
import logging
from nacos import NacosClient
from nacos.exception import NacosException

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_nacos_client(server_addresses, username, password, namespace):
    """创建带有重试机制的Nacos客户端（使用传入参数/环境变量，而非硬编码）。"""
    resolved_server = server_addresses or os.environ.get("NACOS_SERVER")
    resolved_user = username or os.environ.get("NACOS_USERNAME")
    resolved_pass = password or os.environ.get("NACOS_PASSWORD")
    resolved_ns = namespace or os.environ.get("NACOS_NAMESPACE", "public")

    if not resolved_server:
        raise Exception("NACOS_SERVER not set for create_nacos_client")

    max_retries = 3
    for i in range(max_retries):
        try:
            client = NacosClient(
                server_addresses=resolved_server,
                namespace=resolved_ns,
                username=resolved_user,
                password=resolved_pass,
            )
            # 简单连通性检查：读取一个不存在也无所谓的配置（会触发HTTP/鉴权流程）
            client.get_config("__ping__", "DEFAULT_GROUP")
            return client
        except Exception as e:
            logger.error(f"Failed to create Nacos client, attempt {i+1}: {e}")
            if i < max_retries - 1:
                time.sleep(2 ** i)  # 指数退避
    raise Exception("Failed to create Nacos client after retries")


import json
import threading

class NacosServiceRegistry:
    def __init__(self, client, service_name, ip, port):
        self.client = client
        self.service_name = service_name
        self.ip = ip
        self.port = port
        self.heartbeat_thread = None
        self.heartbeat_running = False
        self.metadata = {}
        
    def register_service(self, metadata=None, ttl=5):
        """
        注册服务到Nacos
        
        Args:
            metadata (dict): 服务元数据
            ttl (int): 心跳间隔时间(秒)，用于维持服务存活状态
        """
        try:
            # 设置元数据
            self.metadata = metadata or {}
            self.metadata['preserved.register.source'] = 'PYTHON'
            
            # 注册服务实例
            self.client.add_naming_instance(
                service_name=self.service_name,
                ip=self.ip,
                port=self.port,
                metadata=self.metadata,
                ephemeral=True  # 临时实例，需要心跳维持
            )
            
            logger.info(f"Service registered: {self.service_name} at {self.ip}:{self.port}")
            
            # 启动心跳线程
            self.start_heartbeat(ttl)
            
        except NacosException as e:
            # 更友好的权限提示
            if "Insufficient privilege" in str(e):
                logger.error(
                    "Failed to register service: Insufficient privilege. 请检查 Nacos 账号是否具有该命名空间/分组的写入权限、用户名/密码是否正确。"
                )
            else:
                logger.error(f"Failed to register service (nacos): {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to register service: {e}")
            raise
            
    def start_heartbeat(self, ttl):
        """启动心跳线程"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
            
        self.heartbeat_running = True
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_worker, 
            args=(ttl,),
            daemon=True
        )
        self.heartbeat_thread.start()
        logger.info(f"Heartbeat started with TTL: {ttl}s")
        
    def _heartbeat_worker(self, ttl):
        """心跳工作线程"""
        while self.heartbeat_running:
            try:
                # 发送心跳
                self.client.send_heartbeat(
                    service_name=self.service_name,
                    ip=self.ip,
                    port=self.port,
                    cluster_name="DEFAULT",
                    metadata=self.metadata
                )
                logger.debug(f"Heartbeat sent for {self.service_name}")
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                
            # 等待下次心跳
            time.sleep(ttl)
            
    def deregister_service(self):
        """注销服务"""
        try:
            self.heartbeat_running = False
            self.client.remove_naming_instance(
                service_name=self.service_name,
                ip=self.ip,
                port=self.port
            )
            logger.info(f"Service deregistered: {self.service_name}")
        except Exception as e:
            logger.error(f"Failed to deregister service: {e}")
        

def create_client_from_env(
    server_addresses: str | None = None,
    username: str | None = None,
    password: str | None = None,
    namespace: str | None = None,
):
    """根据环境变量创建 NacosClient。
    可覆盖传参，未提供的从环境读取：
      - NACOS_SERVER, NACOS_USERNAME, NACOS_PASSWORD, NACOS_NAMESPACE
    """
    server_addresses = server_addresses or os.environ.get("NACOS_SERVER")
    username = username or os.environ.get("NACOS_USERNAME")
    password = password or os.environ.get("NACOS_PASSWORD")
    namespace = namespace or os.environ.get("NACOS_NAMESPACE", "public")

    if not server_addresses:
        raise Exception("NACOS_SERVER not set for create_client_from_env")

    return NacosClient(
        server_addresses=server_addresses,
        namespace=namespace,
        username=username,
        password=password,
    )

class IdleBusyNacosRegistrar:
    """根据空闲/忙碌状态切换 Nacos 注册的门面类。"""
    def __init__(self, nacos_client: NacosClient, service_name: str, ip: str, port: int, metadata: dict | None = None, ttl: int = 5):
        self._registry = NacosServiceRegistry(nacos_client, service_name, ip, port)
        self._registered = False
        self._metadata = metadata or {}
        self._ttl = ttl

    def update(self, is_idle: bool):
        """当空闲时确保已注册，忙碌时确保注销。"""
        try:
            if is_idle and not self._registered:
                self._registry.register_service(metadata=self._metadata, ttl=self._ttl)
                self._registered = True
            elif (not is_idle) and self._registered:
                self._registry.deregister_service()
                self._registered = False
        except Exception as e:
            logger.warning(f"IdleBusyNacosRegistrar.update error: {e}")

def build_idle_busy_registrar_from_env(bound_ip: str, bound_port: int):
    """若启用则从环境变量构建 IdleBusyNacosRegistrar，否则返回 None。
    需要：NACOS_ENABLE=1 且 NACOS_SERVER 存在。
    可选：NACOS_SERVICE、NACOS_USERNAME、NACOS_PASSWORD、NACOS_NAMESPACE、NACOS_IP、NACOS_PORT
    """
    if os.environ.get("NACOS_ENABLE", "1") != "1":
        return None
    if not os.environ.get("NACOS_SERVER"):
        logger.warning("NACOS_ENABLE=1 but NACOS_SERVER not set, skip registrar")
        return None

    service_name = os.environ.get("NACOS_SRV_NAME", "comfyui")

    self_srv = os.environ.get("SELF_REGISTER_IP", bound_ip)
    # 优先使用进程绑定端口，其次环境变量；避免误把Nacos端口(如8848)当作服务端口注册
    env_port = os.environ.get("SELF_REGISTER_PORT")
    self_port = int(env_port) if env_port else int(bound_port or 0)

    # 基本防呆：当自注册端口与Nacos服务端口相同，提示风险
    nacos_server = os.environ.get("NACOS_SERVER", "")
    logger.info(f"NACOS_SERVER:{os.environ.get('NACOS_SERVER')}, NACOS_USERNAME:{os.environ.get('NACOS_USERNAME')},NACOS_PASSWORD:{os.environ.get('NACOS_PASSWORD')}")
    logger.info(f"self_srv:{self_srv}, self_port:{self_port}")
    try:
        if nacos_server:
            # 提取 Nacos 端口进行比对
            from urllib.parse import urlparse

            parsed = urlparse(nacos_server)
            nacos_port = parsed.port
            if nacos_port and self_port == nacos_port:
                logger.warning(
                    "SELF_REGISTER_PORT 与 NACOS_SERVER 端口相同，疑似将 Nacos 自身端口作为业务服务端口注册，请确认。"
                )
    except Exception:
        pass
    try:
        client = create_client_from_env()
        metadata = {"source": "comfyui", "service": service_name, "self_srv": self_srv, "self_port": self_port}
        return IdleBusyNacosRegistrar(client, service_name, self_srv, self_port, metadata=metadata, ttl=5)
    except Exception as e:
        logger.warning(f"Failed to build IdleBusyNacosRegistrar: {e}")
        return None


class SimulatedNacosClient:
    """模拟Nacos客户端行为，用于演示"""
    def __init__(self, client_id):
        self.client_id = client_id
        self.registered_instances = {}
        
    def add_naming_instance(self, service_name, ip, port, metadata=None, ephemeral=True):
        instance_key = f"{service_name}:{ip}:{port}"
        self.registered_instances[instance_key] = {
            'service_name': service_name,
            'ip': ip,
            'port': port,
            'metadata': metadata,
            'ephemeral': ephemeral
        }
        logger.info(f"[Client-{self.client_id}] Registered instance: {instance_key}")
        
    def send_heartbeat(self, service_name, ip, port, cluster_name, metadata):
        instance_key = f"{service_name}:{ip}:{port}"
        if instance_key in self.registered_instances:
            logger.debug(f"[Client-{self.client_id}] Heartbeat sent for {instance_key}")
        else:
            logger.warning(f"[Client-{self.client_id}] Heartbeat for unregistered instance: {instance_key}")
            
    def remove_naming_instance(self, service_name, ip, port):
        instance_key = f"{service_name}:{ip}:{port}"
        if instance_key in self.registered_instances:
            del self.registered_instances[instance_key]
            logger.info(f"[Client-{self.client_id}] Deregistered instance: {instance_key}")

            
# 使用示例
# 使用示例
if __name__ == "__main__":
    '''
    export NACOS_ENABLE=1
    export NACOS_SERVER=http://192.168.0.2:8848
    export NACOS_USERNAME=nacos
    export NACOS_PASSWORD='Nacos!2025'
    export NACOS_NAMESPACE=public
    export NACOS_SRV_NAME=comfyui-api-service
    export SELF_REGISTER_SCHEMA=http
    export SELF_REGISTER_IP=192.168.0.2
    export SELF_REGISTER_PORT=8810
    '''
    
    # 创建客户端
    nacso_client = create_nacos_client(server_addresses= 'http://192.168.0.2:8848',username='nacos',password='Nacos!2025',namespace='public')

    
    # 注册服务
    group = "vnet-multimodal"
    service_name = "comfyui-api-service"
    ip = "39.155.179.4"  # 替换为实际SRVIP
    port = 8180       # 替换为实际端口
    service_registry = NacosServiceRegistry(nacso_client, service_name, ip, port)
    
    # 服务元数据
    metadata = {
        "version": "1.0.0",
        "env": "test",
        "ip": ip,
    }
    
    # 注册服务并设置TTL为5秒
    service_registry.register_service(metadata=metadata, ttl=5)
    
    try:
        # 模拟服务运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # 程序退出时注销服务
        service_registry.deregister_service()
        logger.info("Application shutdown")

