# 测试用例执行指南

## 目录结构

```
test_cases/
├── cockpit/                    # 智能座舱测试
│   └── voice_interaction/      # 语音交互
│       ├── conftest.py         # 局部 fixture (ADB驱动/音频播放器)
│       └── test_wakeup.py      # 唤醒率测试 (16 条用例)
├── adas/                       # 智能驾驶测试 (待扩展)
├── vcu/                        # 整车控制测试 (待扩展)
└── integration/                # 跨域集成测试 (待扩展)
```

---

## 1. 自定义命令行参数

框架在 `conftest.py` 中注册了 3 个自定义参数，可在所有 pytest 命令中使用：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--vehicle-model` | `default` | 目标车型：`xiaomi_su7` / `nio_et7` / `default` |
| `--env` | `simulation` | 运行环境：`simulation` / `hil` / `real_vehicle` / `ci` |
| `--test-rounds` | `0`（使用配置值） | 覆盖每项测试的执行轮次 |

**环境说明：**
- `simulation` — 仿真模式，所有硬件驱动自动 Mock，无需连接真实设备
- `hil` — 硬件在环，连接 dSPACE/NI 等 HIL 设备
- `real_vehicle` — 实车环境，通过 ADB/CAN 连接真实车辆
- `ci` — CI/CD 流水线，自动 Mock 全部外部依赖

---

## 2. 基本执行命令

### 2.1 运行全部测试
```bash
pytest
```

### 2.2 运行指定目录
```bash
# 智能座舱全部测试
pytest test_cases/cockpit/

# 语音交互测试
pytest test_cases/cockpit/voice_interaction/

# ADAS 测试
pytest test_cases/adas/
```

### 2.3 运行指定文件
```bash
pytest test_cases/cockpit/voice_interaction/test_wakeup.py
```

### 2.4 运行指定类 / 指定用例
```bash
# 运行某个测试类
pytest test_cases/cockpit/voice_interaction/test_wakeup.py::TestVoiceWakeup

# 运行单条用例
pytest test_cases/cockpit/voice_interaction/test_wakeup.py::TestVoiceWakeup::test_basic_wakeup_rate

# 参数化用例需要带上参数 ID
pytest "test_cases/cockpit/voice_interaction/test_wakeup.py::TestVoiceWakeup::test_noise_wakeup_rate[70dB-高速公路]"
```

---

## 3. 按标记 (Marker) 筛选

框架为用例定义了多维度标记，通过 `-m` 参数筛选：

### 3.1 按业务域
```bash
pytest -m cockpit          # 智能座舱
pytest -m adas             # 智能驾驶
pytest -m vcu              # 整车控制
pytest -m integration      # 跨域集成
```

### 3.2 按测试类型
```bash
pytest -m smoke            # 冒烟测试 (快速验证核心功能)
pytest -m regression       # 回归测试
pytest -m performance      # 性能测试
pytest -m safety           # 安全测试
```

### 3.3 按优先级
```bash
pytest -m p0               # 最高优先级 (阻塞级)
pytest -m p1               # 高优先级
pytest -m p2               # 中优先级
pytest -m "p0 or p1"       # P0 + P1
```

### 3.4 按执行环境
```bash
pytest -m hil              # 需要 HIL 硬件
pytest -m simulation       # 仿真环境
pytest -m real_vehicle      # 实车测试
```

### 3.5 组合筛选
```bash
# 座舱域的冒烟测试
pytest -m "cockpit and smoke"

# P0 + P1 但排除需要 HIL 的用例
pytest -m "(p0 or p1) and not hil"

# 座舱域的非性能测试
pytest -m "cockpit and not performance"
```

---

## 4. 指定车型和环境

### 4.1 典型场景
```bash
# 小米 SU7 仿真测试
pytest --vehicle-model xiaomi_su7 --env simulation

# 蔚来 ET7 HIL 环境
pytest --vehicle-model nio_et7 --env hil

# CI 流水线 (默认车型)
pytest --env ci -m smoke
```

### 4.2 覆盖测试轮次
```bash
# 快速验证：每项只跑 5 轮
pytest test_cases/cockpit/voice_interaction/test_wakeup.py --test-rounds 5

# 完整测试：每项跑 100 轮
pytest test_cases/cockpit/voice_interaction/test_wakeup.py --test-rounds 100
```

---

## 5. 输出与报告

### 5.1 控制台输出级别
```bash
pytest -v                  # 详细模式 (显示每条用例名)
pytest -vv                 # 更详细 (显示参数化详情)
pytest -s                  # 显示 print/logger 输出 (不捕获 stdout)
pytest -v -s               # 详细 + 实时日志 (推荐调试时使用)
pytest --tb=long           # 完整错误堆栈
pytest --tb=short          # 简短堆栈 (默认)
pytest --tb=no             # 不显示堆栈
```

### 5.2 生成 HTML 报告
```bash
pytest --html=reports/html_reports/report.html --self-contained-html
```

### 5.3 生成 Allure 报告
```bash
# 第一步：运行测试并收集数据
pytest --alluredir=reports/allure_reports

# 第二步：启动 Allure 服务查看报告
allure serve reports/allure_reports

# 或生成静态报告
allure generate reports/allure_reports -o reports/allure_html --clean
```

### 5.4 生成 JUnit XML (CI 集成)
```bash
pytest --junitxml=reports/junit_reports/result.xml
```

---

## 6. 并行执行

使用 `pytest-xdist` 插件并行执行，大幅缩短测试时间：

```bash
# 自动检测 CPU 核数并行
pytest -n auto

# 指定 4 个进程并行
pytest -n 4

# 按文件分组并行
pytest -n auto --dist loadfile

# 座舱测试 4 进程并行
pytest test_cases/cockpit/ -n 4
```

---

## 7. 失败处理

```bash
# 遇到第 1 个失败立即停止
pytest -x

# 遇到第 3 个失败停止
pytest --maxfail=3

# 只重跑上次失败的用例
pytest --lf

# 优先跑上次失败的，再跑其余
pytest --ff

# 失败自动重试 2 次
pytest --reruns 2 --reruns-delay 3
```

---

## 8. 查看用例信息

```bash
# 只收集用例，不执行 (查看有哪些用例)
pytest --collect-only

# 查看所有已注册的 marker
pytest --markers

# 查看所有可用的 fixture
pytest --fixtures
```

---

## 9. 完整示例

```bash
# 🚀 日常开发：快速跑冒烟测试
pytest -m smoke --env simulation -s --test-rounds 5

# 🔍 调试单条用例：详细输出 + 实时日志
pytest test_cases/cockpit/voice_interaction/test_wakeup.py::TestVoiceWakeup::test_basic_wakeup_rate \
  --env simulation --vehicle-model xiaomi_su7 --test-rounds 5 -v -s

# 📊 完整回归测试 + Allure 报告
pytest -m "cockpit and (p0 or p1)" \
  --vehicle-model xiaomi_su7 --env hil --test-rounds 100 \
  --alluredir=reports/allure_reports

# 🏭 CI 流水线
pytest -m "smoke and not real_vehicle" \
  --env ci --junitxml=reports/junit_reports/ci_result.xml -n auto

# 🎯 唤醒率专项测试 (全条件覆盖)
pytest test_cases/cockpit/voice_interaction/test_wakeup.py \
  --vehicle-model nio_et7 --env hil --test-rounds 50 \
  --alluredir=reports/allure_reports -v
```

---

## 10. 用例编写规范

新增用例时请遵守以下规范：

1. **文件命名**：`test_*.py`
2. **类命名**：`Test*`（如 `TestVoiceWakeup`）
3. **方法命名**：`test_*`（如 `test_basic_wakeup_rate`）
4. **必须添加 marker**：至少标注优先级（`@pytest.mark.p0` ~ `p3`）
5. **使用 Allure 注解**：`@allure.title()` / `@allure.severity()` / `@allure.story()`
6. **放置于正确目录**：框架会根据目录自动添加域标记（`cockpit`/`adas`/`vcu`/`integration`）

```python
import allure
import pytest

@allure.epic("智能座舱")
@allure.feature("语音交互")
@allure.story("多音区识别")
@pytest.mark.cockpit
class TestMultiZone:

    @allure.title("主副驾音区识别准确率")
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_driver_passenger_zone(self):
        ...
```
