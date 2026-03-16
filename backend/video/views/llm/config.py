import os
import sys
from pathlib import Path
from typing import Dict, Optional, Any

# 获取设置
def _get_config_path(config_path: Optional[str] = None) -> str:
    if config_path:
        return config_path

    backend_dir = Path(__file__).parent.parent.parent.parent
    config_file = backend_dir / "config" / "config.ini"

    if config_file.exists():
        return str(config_file)

    possible_paths = [
        "/app/config/config.ini",
        "./backend/config/config.ini",
        "../config/config.ini",
        "./config/config.ini",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    raise FileNotFoundError("Could not find config.ini file")


def _parse_config_value(value: str) -> Any:
    value = value.strip()

    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]

    return value


def load_provider_config(
    provider_name: str, config_path: Optional[str] = None
) -> Dict[str, Any]:
    config_file = _get_config_path(config_path)

    config = {}
    current_section = None

    with open(config_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or line.startswith(";"):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                continue

            if "=" in line and current_section:
                key, value = line.split("=", 1)
                key = key.strip()
                value = _parse_config_value(value)

                section_provider = current_section.replace("model:", "")
                if section_provider == provider_name:
                    config[key] = value
                elif current_section == "DEFAULT":
                    if key.startswith(f"{provider_name}_"):
                        new_key = key.replace(f"{provider_name}_", "")
                        config[new_key] = value

    return config


def get_default_provider_name(config_path: Optional[str] = None) -> str:
    config_file = _get_config_path(config_path)

    with open(config_file, "r", encoding="utf-8") as f:
        content = f.read()
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("selected_model_provider"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return _parse_config_value(parts[1])

    return "openai"


def save_provider_config(
    provider_name: str, config: Dict[str, Any], config_path: Optional[str] = None
) -> None:
    config_file = _get_config_path(config_path)

    section_name = f"model:{provider_name}"

    with open(config_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    section_start = None
    section_end = None
    in_target_section = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            if in_target_section:
                section_end = i
                break
            if stripped[1:-1] == section_name:
                section_start = i
                in_target_section = True

    new_section_lines = [f"[{section_name}]\n"]
    for key, value in config.items():
        if isinstance(value, bool):
            value_str = "true" if value else "false"
        else:
            value_str = str(value)
        new_section_lines.append(f"{key} = {value_str}\n")
    new_section_lines.append("\n")

    if section_start is not None:
        if section_end is None:
            section_end = len(lines)
        lines = lines[:section_start] + new_section_lines + lines[section_end:]
    else:
        lines.extend(new_section_lines)

    with open(config_file, "w", encoding="utf-8") as f:
        f.writelines(lines)


def list_configured_providers(config_path: Optional[str] = None) -> list:
    config_file = _get_config_path(config_path)
    providers = []

    with open(config_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[model:") and line.endswith("]"):
                provider_name = line[7:-1]
                providers.append(provider_name)

    return providers
