"""Smoke test — 验证所有修改文件可正常 import"""
from src.agent.persona import get_system_prompt, PERSONA, get_polish_prompt
print('1. persona.py OK')

from src.agent.agents.reflection import ReflectionAgent
print('2. reflection.py OK')

from src.agent.agents.rag_agent import RAGAgent
print('3. rag_agent.py OK')

from src.app.scenarios.troubleshoot_scenario import TroubleshootScenario
print('4. troubleshoot_scenario.py OK')

from src.app.scenarios.consumables_scenario import ConsumablesScenario
print('5. consumables_scenario.py OK')

# 验证 persona 功能
qa_prompt = get_system_prompt('qa')
assert '小智' in qa_prompt, 'persona name missing'
assert '您' in qa_prompt, 'persona 您 missing'
print('6. persona qa prompt OK')

ts_prompt = get_system_prompt('troubleshoot')
assert '别急' in ts_prompt, 'persona troubleshoot missing'
print('7. persona troubleshoot prompt OK')

cs_prompt = get_system_prompt('consumables')
assert '设备型号' in cs_prompt, 'persona consumables missing'
print('8. persona consumables prompt OK')

polish = get_polish_prompt('测试文本')
assert '润色后' in polish
print('9. get_polish_prompt OK')

print()
print('=== ALL IMPORTS PASS ===')
