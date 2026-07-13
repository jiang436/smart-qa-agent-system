"""CoT Prompt 加载器"""

import os

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))

_CACHE = {}


def load_cot_prompt(name: str) -> str:
    """加载 CoT 思维链提示模板"""
    if name in _CACHE:
        return _CACHE[name]

    path = os.path.join(_PROMPTS_DIR, f"cot_{name}.txt")
    if not os.path.exists(path):
        raise FileNotFoundError(f"CoT prompt not found: {path}")

    with open(path, encoding="utf-8") as f:
        content = f.read().strip()

    _CACHE[name] = content
    return content
