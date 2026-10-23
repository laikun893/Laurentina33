"""配置层。

职责：从 config.ini 读取模型服务配置，并包装为强类型的 Config 对象。
该层是 core 的入口依赖，UI 层无需关心配置文件的具体格式与校验逻辑。
"""

import configparser
import os
from dataclasses import dataclass


class ConfigError(Exception):
    """配置加载或校验失败时抛出的异常。"""


@dataclass(frozen=True)
class Config:
    """模型服务配置。"""

    base_url: str
    model: str
    api_key: str


def load_config(path) -> Config:
    """读取并校验配置文件。

    :param path: config.ini 的路径（str 或 os.PathLike）。
    :raises ConfigError: 文件缺失 / 缺少 [default] 段 / 缺少必需字段。
    """
    parser = configparser.ConfigParser()
    if not parser.read(os.fspath(path)):
        raise ConfigError(f"找不到配置文件：{os.fspath(path)}")

    if not parser.has_section("default"):
        raise ConfigError("配置文件缺少 [default] section")

    try:
        base_url = parser.get("default", "base_url")
        model = parser.get("default", "model")
        api_key = parser.get("default", "api_key")
    except configparser.NoOptionError as e:
        raise ConfigError(f"配置文件缺少字段 {e.option}") from e

    return Config(base_url=base_url, model=model, api_key=api_key)
