"""温度换算单元测试。"""
from server.manager import celsius_from_ioregistry


def test_conversion_real_device_value():
    # 实测真机原始值 3219 → 32.19 °C
    assert celsius_from_ioregistry(3219) == 32.19


def test_conversion_typical_values():
    assert celsius_from_ioregistry(3000) == 30.0
    assert celsius_from_ioregistry(3650) == 36.5


def test_conversion_rounding_to_two_decimals():
    assert celsius_from_ioregistry(3267) == 32.67
