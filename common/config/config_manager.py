"""
ConfigManager - 统一配置管理器
支持 YAML 配置文件加载、环境变量覆盖、多车型配置切换
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigManager:
    """统一配置管理，支持多车型切换和环境变量覆盖"""

    _instance: Optional[ConfigManager] = None

    # 框架根目录
    FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent.parent

    def __new__(cls) -> ConfigManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = {}  # 实例属性，避免类级共享
            cls._instance._loaded = False
        return cls._instance

    def __init__(self) -> None:
        # 避免重复初始化: 单例模式下 __init__ 可能被多次调用
        if hasattr(self, "_initialized"):
            return
        self._config: dict = {}
        self._loaded = False
        self._initialized = True

    def load(
        self,
        vehicle_model: str | None = None,
        env: str = "default",
        extra_files: list[str] | None = None,
    ) -> None:
        """
        加载配置文件

        Args:
            vehicle_model: 车型名称 (如 "xiaomi_su7", "nio_et7")
            env: 运行环境 (default / ci / hil / real_vehicle)
            extra_files: 额外配置文件列表
        """
        config_dir = self.FRAMEWORK_ROOT / "common" / "config"

        # 0. 清空旧配置，防止多次 load() 时数据残留
        self._config = {}

        # 1. 加载基础测试配置
        self._merge(self._read_yaml(config_dir / "test_config.yaml"))

        # 2. 加载网络配置
        self._merge(self._read_yaml(config_dir / "network_config.yaml"))

        # 3. 加载环境配置
        self._merge(self._read_yaml(config_dir / "environment_config.yaml"))

        # 4. 加载车型配置
        if vehicle_model:
            self._merge(self._read_yaml(config_dir / "vehicle_profiles.yaml"))
            # 选择具体车型
            profiles = self._config.get("vehicle_profiles", {})
            if vehicle_model in profiles:
                self._config["current_vehicle"] = profiles[vehicle_model]
                self._config["current_vehicle"]["model"] = vehicle_model

        # 5. 加载额外配置
        if extra_files:
            for fpath in extra_files:
                self._merge(self._read_yaml(Path(fpath)))

        # 6. 环境变量覆盖 (ATF_ 前缀)
        self._apply_env_overrides()

        self._config["env"] = env
        self._loaded = True

    # ---- 读取接口 ----
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        通过点号分隔的路径获取配置值

        Args:
            key_path: 配置路径，如 "cockpit.voice.wakeup_threshold"
            default: 默认值

        Returns:
            配置值
        """
        keys = key_path.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def get_vehicle(self, key: str | None = None, default: Any = None) -> Any:
        """获取当前车型配置"""
        vehicle = self._config.get("current_vehicle", {})
        if key is None:
            return vehicle
        return vehicle.get(key, default)

    def set(self, key_path: str, value: Any) -> None:
        """
        通过点号分隔的路径设置配置值

        Args:
            key_path: 配置路径，如 "cockpit.voice.wakeup.test_rounds"
            value: 要设置的值
        """
        keys = key_path.split(".")
        d = self._config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    @property
    def raw(self) -> dict[str, Any]:
        return self._config

    # ---- 内部方法 ----
    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _merge(self, new: dict[str, Any]) -> None:
        self._deep_merge(self._config, new)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """
        深度合并 override 到 base（原地修改 base）。
        为避免外部意外修改内部状态，调用前应做深拷贝。
        """
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConfigManager._deep_merge(base[k], v)
            else:
                base[k] = v

    def _apply_env_overrides(self) -> None:
        """用 ATF_ 前缀的环境变量覆盖配置"""
        prefix = "ATF_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower().replace("__", ".")
                keys = config_key.split(".")
                d = self._config
                for k in keys[:-1]:
                    d = d.setdefault(k, {})
                d[keys[-1]] = value

    def reset(self) -> None:
        """重置配置（用于测试）"""
        self._config = {}
        self._loaded = False
        self._initialized = False