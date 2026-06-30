# CI 与质量门禁使用指南

本文档说明项目的最小 CI、质量门禁范围、本地复现方式和常见失败处理方法。

## 适用范围

默认 CI 面向日常开发和 PR 校验，目标是尽早发现会阻塞项目运行的基础问题，包括：

- Python 语法或导入级编译错误
- Ruff 代码质量问题
- CI 环境下的冒烟测试失败

默认 CI 不连接 HIL、实车、真实 ADB 设备或真实 CAN 设备。涉及硬件的测试需要在专用环境里手动运行。

## 触发条件

GitHub Actions 会在以下场景触发：

- push 到 `main`
- push 到 `chore/**`
- push 到 `fix/**`
- push 到 `improve/**`
- 向 `main` 发起 pull request

Workflow 文件位于：

```text
.github/workflows/ci.yml
```

## CI 执行步骤

当前 workflow 使用 Python 3.12，在 Ubuntu runner 上执行以下步骤：

1. 拉取仓库代码。
2. 安装 `requirements.txt` 中的项目依赖。
3. 安装 `ruff`。
4. 编译核心 Python 源码。
5. 运行 Ruff 检查。
6. 运行 CI 冒烟测试。

等价命令如下：

```bash
python -m compileall -q common drivers tools test_cases conftest.py
python -m ruff check .
pytest -m smoke --env ci --test-rounds 3 -q
```

## 本地复现

在项目根目录执行：

```bash
python -m pip install -r requirements.txt
python -m pip install ruff
python -m compileall -q common drivers tools test_cases conftest.py
python -m ruff check .
pytest -m smoke --env ci --test-rounds 3 -q
```

Windows PowerShell、Linux shell 和 GitHub Actions runner 中的命令保持一致。

## Ruff 门禁范围

当前 Ruff 门禁执行全量检查：

```bash
python -m ruff check .
```

Ruff 规则由 `pyproject.toml` 中的 `[tool.ruff]` 和 `[tool.ruff.lint]` 配置控制。当前启用 `E`、`F`、`W`、`I`、`N`、`UP`、`B`、`C4` 等规则族。

项目暂时忽略以下规则：

- `E501`：长行限制。项目中有中文说明、日志和测试数据，短期先不强制统一折行。
- `N818`：异常类名必须以 `Error` 结尾。现有 `VehicleException`、`NetworkException` 等是公开异常基类，直接改名会影响兼容性。

## 冒烟测试范围

默认 CI 使用：

```bash
pytest -m smoke --env ci --test-rounds 3 -q
```

这表示：

- 只运行带 `smoke` marker 的测试。
- 使用 `ci` 环境配置。
- 将测试轮次压到 3，保证 CI 反馈足够快。
- 使用 mock/仿真路径，不要求真实硬件。

## HIL 与实车测试

HIL 和实车测试不在默认 CI 中运行。需要硬件环境时，使用专用命令手动执行：

```bash
pytest -m hil --env hil
pytest -m real_vehicle --env real_vehicle
```

如果某个测试需要外部硬件，应显式标记为 `hil`、`real_vehicle` 或 `hardware`，避免在 CI 或本地仿真环境中误跑。

## 常见失败处理

### 编译失败

命令：

```bash
python -m compileall -q common drivers tools test_cases conftest.py
```

常见原因：

- Python 语法错误
- 合并冲突残留
- 文件编码或缩进异常

处理方式：按 CI 日志定位文件和行号，本地修复后重新运行该命令。

### Ruff 失败

命令：

```bash
python -m ruff check .
```

常见原因：

- 未使用导入或变量
- import 顺序不符合规则
- 未定义变量或作用域错误
- 异常链、循环变量、现代类型写法等代码质量问题

处理方式：优先修复 Ruff 输出中的文件和行号。只有涉及公共 API 兼容性或项目级风格策略的问题，才应通过 `pyproject.toml` 明确配置忽略。

### 冒烟测试失败

命令：

```bash
pytest -m smoke --env ci --test-rounds 3 -q
```

常见原因：

- mock 驱动行为改变
- fixture 配置变化
- marker 或 `--env` 处理逻辑异常
- 用例断言依赖随机结果或环境状态

处理方式：先本地复现同一命令，再按失败用例单独运行，例如：

```bash
pytest test_cases/path/to/test_file.py::TestClass::test_case --env ci --test-rounds 3 -q
```

## 后续收紧建议

当前 CI 已启用全量 Ruff 检查。后续可以逐步增加：

- `pytest tests/unit -q`，在单元测试分支合入后启用。
- `ruff format --check .`，在统一格式化策略后启用。
- Python 3.10 / 3.11 / 3.12 矩阵，验证最低版本兼容性。
- HTML 或 JSON 测试报告归档，便于追踪失败细节。
