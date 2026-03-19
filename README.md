# Automotive Test Framework - 汽车智能化自动测试平台

## 简介
基于 Python + pytest 构建的工程级、可扩展、多车型与多域功能的汽车自动化测试平台。

## 覆盖领域
- **智能座舱 (Cockpit)**: 语音交互、多屏联动、娱乐系统、远程控制、OTA升级
- **智能驾驶 (ADAS)**: 感知系统、规划控制、功能特性（ACC/AEB/LKA/NOA）、功能安全
- **整车控制 (VCU)**: 动力系统、底盘、车身控制、热管理、充电系统、诊断
- **跨域集成**: 座舱-ADAS、座舱-VCU、ADAS-VCU、端到端场景

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行冒烟测试
pytest -m smoke -v

# 运行智能座舱测试
pytest test_cases/cockpit/ -v

# 运行唤醒率测试示例
pytest test_cases/cockpit/voice_interaction/test_wakeup.py -v

# 生成Allure报告
pytest --alluredir=reports/allure_reports
allure serve reports/allure_reports
```

## 项目结构
```
automotive_test_framework/
├── test_cases/       # 测试用例层
├── drivers/          # 驱动/协议层
├── common/           # 通用基础层
├── data/             # 测试数据层
├── tools/            # 工具集
├── reports/          # 报告输出
├── ci/               # CI/CD配置
└── conftest.py       # pytest全局配置
```