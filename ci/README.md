# CI/CD 配置目录
# 支持 Jenkins / GitHub Actions / GitLab CI / Azure DevOps

## 使用方式

### Jenkins
将 `jenkins/Jenkinsfile` 配置到 Jenkins 流水线

### GitHub Actions
将 `github_actions/workflow.yml` 复制到 `.github/workflows/`

### 运行示例
```bash
# 冒烟测试
pytest -m smoke --env ci --vehicle-model default

# 座舱全量测试
pytest test_cases/cockpit/ --env hil --vehicle-model xiaomi_su7

# 并行执行
pytest -n auto --env ci