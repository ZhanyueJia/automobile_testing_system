# Automotive Test Framework - 汽车智能化自动测试平台

## 简介

基于 Python + pytest 构建的工程级、可扩展、多车型与多域功能的汽车自动化测试平台。

## 覆盖领域

- **智能座舱 (Cockpit)**: 语音交互、多屏联动、娱乐系统、远程控制、OTA升级
- **智能驾驶 (ADAS)**: 感知系统、规划控制、功能特性（ACC/AEB/LKA/NOA）、功能安全
- **整车控制 (VCU)**: 动力系统、底盘、车身控制、热管理、充电系统、诊断
- **跨域集成**: 座舱-ADAS、座舱-VCU、ADAS-VCU、端到端场景

## 快速开始

### 环境要求

- Python 3.10+
- pip 或 pip-tools

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd automobile_testing_system

# 创建虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 运行测试

```bash
# 运行冒烟测试
pytest -m smoke -v

# 运行智能座舱测试
pytest test_cases/cockpit/ -v

# 运行 ADAS 测试
pytest test_cases/adas/ -v

# 运行 VCU 车身控制测试
pytest test_cases/vcu/body_control/ -v

# 运行唤醒率测试示例
pytest test_cases/cockpit/voice_interaction/test_wakeup.py -v

# 运行中控锁测试
pytest test_cases/vcu/body_control/door_system/ -v
```

### 生成报告

```bash
# Allure 报告
pytest --alluredir=reports/allure_reports
allure serve reports/allure_reports

# HTML 报告 (pytest-html)
pytest --html=reports/html_report.html --self-contained-html

# JSON 结果
pytest --json-report --json-report-file=reports/results.json
```

### 多车型配置

```bash
# 小米 SU7
pytest --vehicle-model=xiaomi_su7 -v

# 蔚来 ET7
pytest --vehicle-model=nio_et7 -v

# 使用模拟环境
pytest --env=simulation -v

# 使用 HIL 设备
pytest --env=hil --vehicle-model=xiaomi_su7 -v
```

## 项目结构

```
automobile_testing_system/
├── test_cases/              # 测试用例层
│   ├── adas/               # ADAS 测试
│   ├── cockpit/            # 智能座舱测试
│   ├── vcu/                # VCU 测试
│   └── integration/         # 跨域集成测试
├── drivers/                 # 驱动/协议层
│   ├── base_driver.py      # 驱动基类
│   ├── protocol_drivers/   # 协议驱动 (CAN, ADB, etc.)
│   ├── hardware_drivers/   # 硬件驱动
│   └── simulation_drivers/ # 仿真驱动
├── common/                  # 通用基础层
│   ├── config/             # 配置管理
│   ├── constants/          # 常量定义
│   ├── decorators/         # 装饰器
│   ├── exceptions/         # 自定义异常
│   ├── fixtures/           # pytest fixtures
│   └── utils/              # 工具类
├── data/                    # 测试数据层
│   ├── dbc_files/          # CAN DBC 文件
│   ├── golden_references/  # 参考数据
│   └── scenario_definitions/ # 场景定义
├── tools/                   # 工具集
├── reports/                 # 测试报告输出
├── ci/                      # CI/CD 配置
├── conftest.py             # pytest 全局配置
├── pyproject.toml          # 项目配置
└── requirements.txt        # Python 依赖
```

## 硬件连接

### CAN-FD 连接

```
1. 将 Vector CAN 接口卡 (如 VN1640) 连接到车载 CAN-FD 总线
2. 配置 CAN 接口:
   - 接口类型: socketcan (Linux) / PCAN (Windows)
   - 波特率: 500kbps (CAN) / 2Mbps (CAN-FD)
3. 在测试配置中设置 can.interface 和 can.channel
```

### ADB 连接 (Android 座舱)

```
1. 确保车机已开启开发者选项和 USB 调试
2. 通过 USB 或 WiFi 连接:
   - USB: adb devices 应显示设备
   - WiFi: adb connect <车机IP>:5555
3. 验证连接: adb shell ls /sdcard
```

### HIL 设备连接

```
1. 连接 HIL 硬件接口 (如 Vector VH6501)
2. 配置串口: pyserial 波特率 115200
3. 在测试命令中添加 --env=hil
```

## 驱动使用示例

### CAN-FD 驱动

```python
from drivers.protocol_drivers.can_bus.can_fd_driver import CANFDDriver

# 创建驱动 (模拟模式)
can = CANFDDriver(
    interface="socketcan",
    channel="can0",
    bitrate=500000,
    fd=True,
    data_bitrate=2000000,
    mock=True  # 启用模拟
)

can.connect()

# 发送 CAN 报文
from drivers.protocol_drivers.can_bus.can_fd_driver import CANMessage
msg = CANMessage(arbitration_id=0x310, data=bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
can.send(msg)

# 接收 CAN 报文
received = can.receive(timeout=1.0)
print(f"Received ID: 0x{received.arbitration_id:03X}, Data: {received.data.hex()}")

can.disconnect()
```

### ADB 驱动

```python
from drivers.protocol_drivers.adb_driver import ADBDriver

# 创建驱动
adb = ADBDriver(serial="192.168.1.100:5555")  # WiFi 连接
# 或: adb = ADBDriver()  # 自动查找第一个设备

adb.connect()

# 执行 shell 命令
output = adb.shell("dumpsys activity activities | grep mResumedActivity")
print(output)

# 启动应用
adb.start_app("com.android.settings", ".Settings")

# 获取屏幕截图
adb.screenshot("screenshot.png")

adb.disconnect()
```

### 中控锁测试引擎

```python
from test_cases.vcu.body_control.door_system._central_lock_engine import (
    CentralLockEngine, LockCommand, LockStatus
)

# 创建测试引擎
engine = CentralLockEngine(
    can=can_driver,
    cmd_id=0x310,
    status_id=0x311,
    door_status_id=0x312,
    response_timeout_ms=500
)

# 执行上锁操作
engine.single_lock_attempt(attempt_id=1, command="lock")

# 检查状态
status = engine.read_lock_status()
print(f"Lock status: {'LOCKED' if status == LockStatus.LOCKED else 'UNLOCKED'}")

# 获取四门状态
door_states = engine.read_door_states()
for door, locked in door_states.items():
    print(f"{door}: {'锁定' if locked else '解锁'}")
```

## 测试标记

### 域标记

| 标记 | 说明 |
|------|------|
| `@pytest.mark.cockpit` | 智能座舱测试 |
| `@pytest.mark.adas` | ADAS 测试 |
| `@pytest.mark.vcu` | VCU 测试 |

### 优先级标记

| 标记 | 说明 |
|------|------|
| `@pytest.mark.p0` | 核心功能测试 |
| `@pytest.mark.p1` | 重要功能测试 |
| `@pytest.mark.p2` | 一般功能测试 |
| `@pytest.mark.p3` | 探索性测试 |

### 类型标记

| 标记 | 说明 |
|------|------|
| `@pytest.mark.smoke` | 冒烟测试 |
| `@pytest.mark.regression` | 回归测试 |
| `@pytest.mark.safety` | 安全相关测试 |
| `@pytest.mark.performance` | 性能测试 |

### 环境标记

| 标记 | 说明 |
|------|------|
| `@pytest.mark.hil` | 需要 HIL 设备 |
| `@pytest.mark.simulation` | 仿真环境 |
| `@pytest.mark.real_vehicle` | 真车测试 |

## CI/CD 集成

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest --env=ci -m smoke -v
      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: allure-reports
          path: reports/allure_reports/
```

### 本地持续集成

```bash
# 运行完整测试套件
pytest --env=ci -v --tb=short

# 带覆盖率
pytest --cov=. --cov-report=html --env=ci

# 并行执行
pytest -n auto --env=ci
```

## 配置管理

### 车型配置

配置文件位于 `common/config/vehicle_profiles.yaml`

```yaml
vehicle_profiles:
  xiaomi_su7:
    brand: "小米"
    vcu:
      battery_voltage: 800
      # ... 更多配置
```

### 环境变量覆盖

以 `ATF_` 前缀的环境变量会覆盖配置文件:

```bash
export ATF_env=simulation
export ATF_can_interface=socketcan
pytest
```

## 开发指南

### 添加新测试用例

1. 在 `test_cases/` 下创建测试文件
2. 使用 appropriate fixtures (参考 `conftest.py`)
3. 添加合适的 pytest 标记
4. 使用 Allure 装饰器记录测试步骤

```python
import allure
import pytest

@allure.epic("整车控制")
@allure.feature("车身控制")
@allure.story("中控锁")
@pytest.mark.vcu
class TestMyFeature:
    @pytest.fixture(autouse=True)
    def setup(self, can, door_config):
        self.engine = CentralLockEngine(can, **door_config)

    @allure.title("测试场景描述")
    @pytest.mark.p1
    def test_scenario(self):
        # 测试步骤
        pass
```

### 添加新驱动

1. 继承 `BaseDriver`
2. 实现 `connect`, `disconnect`, `is_connected`
3. 添加到 `drivers/protocol_drivers/`

```python
from drivers.base_driver import BaseDriver

class MyDriver(BaseDriver):
    def connect(self, **kwargs) -> None:
        # 实现连接逻辑
        self._connected = True

    def disconnect(self) -> None:
        # 实现断开逻辑
        self._connected = False
```

## 许可证

本项目仅供内部使用。
