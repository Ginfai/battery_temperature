"""mDNS 服务发布:向局域网广播监控服务地址,供 Android App 自动发现。

只广播 host+port(不含任何 token),token 由用户在 App 内手动输入。
"""
import logging
import socket

from zeroconf import IPVersion, ServiceInfo, Zeroconf

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
    """生命周期内发布 _battmon._tcp 服务。start 注册、stop 注销。"""

    def __init__(self, port: int):
        self.port = port
        self._zc: Zeroconf | None = None
        self._info: ServiceInfo | None = None

    def start(self) -> None:
        ip = _lan_ipv4()
        logger.info("发布 mDNS 服务 %s 在 %s:%d", SERVICE_NAME, ip, self.port)
        self._zc = Zeroconf(ip_version=IPVersion.V4Only)
        self._info = ServiceInfo(
            SERVICE_TYPE,
            f"{SERVICE_NAME}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=self.port,
            properties={"_": "battmon"},  # 只声明存在,不含 token
        )
        self._zc.register_service(self._info)

    def stop(self) -> None:
        if self._zc is not None:
            if self._info is not None:
                try:
                    self._zc.unregister_service(self._info)
                except Exception:
                    logger.warning("注销 mDNS 服务失败", exc_info=True)
            self._zc.close()
            self._zc = None
            self._info = None