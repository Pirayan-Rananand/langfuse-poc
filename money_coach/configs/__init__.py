import os
import yaml

from money_coach.configs.model import AppConfig


def load_config() -> AppConfig:
    config_dir = os.path.dirname(__file__)

    with open(os.path.join(config_dir, "agents.yaml"), "r", encoding="utf-8") as f:
        agents_data = yaml.load(f, Loader=yaml.FullLoader)

    config_data = {**agents_data}
    return AppConfig(**config_data)


agent_config = load_config()
