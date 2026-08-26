"""mDNS 服务发布:向局域网广播监控服务地址,供 Android App 自动发现。

只广播 host+port(不含任何 token),token 由用户在 App 内手动输入。
注册/注销走 AsyncZeroconf,复用调用方事件循环 —— 在 FastAPI lifespan(async)里同步调用
阻塞的 Zeroconf 会 EventLoopBlocked,故必须用异步 API。
"""
import asyncio
import logging
import socket

from zeroconf import IPVersion
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_battmon._tcp.local."
SERVICE_NAME = "battmon"


def _lan_ipv4() -> str:
    """取第一块非 loopback 网卡的 IPv4 地址,作为对外发布地址。

    服务绑定 0.0.0.0,若 mDNS 广播 127.0.0.1,App 会连到手机自己 —— 必须用局域网 IP。
    通过连接一个 UDP 广播地址让内核选择默认出口 IP(不发任何真实数据)。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # 不发送包,仅触发路由选择
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()


class MDNSAdvertiser:
    """生命周期内发布 _battmon._tcp 服务。async start 注册、async stop 注销。"""

    def __init__(self, port: int):
        self.port = port
        self._zc: AsyncZeroconf | None = None
        self._info: AsyncServiceInfo | None = None

    async def start(self) -> None:
        ip = _lan_ipv4()
        logger.info("发布 mDNS 服务 %s 在 %s:%d", SERVICE_NAME, ip, self.port)
        self._zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        self._info = AsyncServiceInfo(
            SERVICE_TYPE,
            f"{SERVICE_NAME}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=self.port,
            properties={"_": "battmon"},  # 只声明存在,不含 token
        )
        await self._zc.async_register_service(self._info)

    async def stop(self) -> None:
        if self._zc is not None:
            if self._info is not None:
                await self._zc.async_unregister_service(self._info)
            await self._zc.async_close()
            self._zc = None
            self._info = None
            logger.info("mDNS 服务已注销")