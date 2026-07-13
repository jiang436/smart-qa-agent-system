"""故障排查场景 — 引导式多轮对话故障诊断

文档第 2.3 节:
  用户: "扫地机器人不工作了怎么办？"
  -> 意图识别 -> RAG 检索常见原因 -> 引导式排查（多轮对话）
  -> 精确匹配错误码 -> 输出解决方案

故障排查状态机:
  INIT -> 收集症状 -> 列出可能原因 -> 逐轮验证 -> 定位根因 -> 输出方案
                                                      ↓ (3轮未果)
                                                   转人工客服

技术要点:
  - 多轮对话状态追踪（task_memory 跟踪排查进度）
  - 故障决策树（按优先级排查）
  - 引导式排查（Agent 每轮问一个验证性问题）
  - 精确匹配（错误码直接匹配 ERROR_CODE_MAP）
  - 异常降级（3轮以上未定位 -> 建议人工客服）
"""

# 错误码映射表（从 vision_agent 迁移）
ERROR_CODE_MAP = {
    "E01": {"cause": "跌落传感器异常", "solution": "将扫地机放回平整地面，清洁底部悬崖传感器"},
    "E02": {"cause": "轮子卡住", "solution": "检查轮子是否被线缆/头发缠绕，清理异物后重启"},
    "E03": {"cause": "边刷不转", "solution": "拔出边刷，用剪刀清理刷轴上缠绕的头发，重新安装"},
    "E04": {"cause": "尘盒未安装", "solution": "确认尘盒完全推入，听到咔哒声"},
    "E05": {"cause": "电池过热", "solution": "将设备移至阴凉处冷却后重启，检查充电触点是否干净"},
    "E06": {"cause": "激光雷达异常", "solution": "检查激光雷达是否有异物遮挡，清洁雷达表面后重启"},
    "E07": {"cause": "Wi-Fi 连接失败", "solution": "检查路由器2.4G信号，长按Wi-Fi键5秒重新配网"},
    "E08": {"cause": "水箱未安装", "solution": "安装水箱支架后再使用拖地功能"},
}

# -- 故障排查决策树 --
DIAGNOSIS_TREE = {
    "不工作/不开机": {
        "conditions": ["电源键", "充电座", "指示灯"],
        "causes": ["电量耗尽", "电源键接触不良", "电池故障", "主板故障"],
        "steps": [
            {
                "question": "设备放在充电座上时，充电指示灯是否亮起？",
                "if_yes": "充电通路正常，排除供电问题。",
                "if_no": "请您先完成3项简易自检：\n1. 用干纸巾擦拭机身底部和充电座的金属触点\n2. 充电座插头换到另一个墙面插座\n3. 机器平稳推到底座，静置充电30分钟激活亏电电池",
            },
            {
                "question": "完成以上自检操作后，指示灯恢复亮起了吗？",
                "if_yes": "指示灯恢复正常，说明是触点脏污或深度亏电导致。",
                "if_no": "自检后指示灯仍无反应，充电底座或电池存在硬件异常。",
            },
            {
                "question": "充满电后按下机身电源键，设备能正常启动吗？",
                "if_yes": "能正常启动！故障原因是充电触点脏污接触不良，问题已解决。建议每周用干布清洁一次充电触点。",
                "if_no": "充电指示灯不亮、按键无法开机，可能是电池或充电主板硬件故障，建议联系售后专业检测维修。客服热线：400-XXX-XXXX。平常定期清洁充电触点，可避免同类问题。",
            },
        ],
    },
    "清扫不干净": {
        "conditions": ["边刷", "主刷", "尘盒", "吸力模式", "滤网"],
        "causes": ["边刷磨损", "主刷缠绕", "尘盒已满", "吸力模式过低", "滤网堵塞"],
        "steps": [
            {
                "question": "您当前用的是安静模式吗？",
                "if_yes": "安静模式吸力较低，建议切换到标准或强力模式，清洁效果会明显提升。",
                "if_no": "了解。非安静模式的话我们排除吸力不足的问题，继续往下排查。",
            },
            {
                "question": "检查边刷和主刷是否有头发或线缆缠绕？",
                "if_yes": "清理缠绕物后应该能恢复正常。",
                "if_no": "请检查尘盒是否已满。",
            },
            {
                "question": "尘盒是否已满？滤网是否超过3个月未更换？",
                "if_yes": "清空尘盒或更换滤网即可。",
                "if_no": "建议尝试深度清洁模式，如果仍不理想，可以联系售后进一步检查。",
            },
        ],
    },
    "无法回充": {
        "conditions": ["充电座", "红外传感器", "充电触点"],
        "causes": ["充电座无电", "充电座周围有障碍", "传感器脏污", "充电触点氧化"],
        "steps": [
            {
                "question": "充电座的指示灯是否亮着？",
                "if_yes": "充电座供电正常。",
                "if_no": "请检查充电座电源是否接通。",
            },
            {
                "question": "充电座两侧是否有0.5米以上的空间、前方无遮挡？",
                "if_yes": "位置没问题。",
                "if_no": "请清理周围障碍物，留出足够空间。",
            },
            {
                "question": "用干布擦拭设备底部和充电座的金属触点后，能正常回充吗？",
                "if_yes": "触点脏污导致接触不良，清理后就好了。建议每个月清洁一次。",
                "if_no": "可能是红外传感器故障，建议联系售后进一步检测。客服热线：400-XXX-XXXX。",
            },
        ],
    },
    "异常噪音": {
        "conditions": ["主刷", "边刷", "滚轮", "尘盒"],
        "causes": ["异物缠绕", "滚轮磨损", "风机异物", "尘盒未装好"],
        "steps": [
            {
                "question": "翻转设备，检查主刷和边刷是否有异物缠绕？",
                "if_yes": "清理后噪音应该会消失。",
                "if_no": "请检查滚轮是否卡了异物。",
            },
            {
                "question": "取出尘盒重新安装到位后，噪音是否减小？",
                "if_yes": "是尘盒未安装到位导致的，重新装好就行了。",
                "if_no": "可能是风机故障，建议联系售后。客服热线：400-XXX-XXXX。",
            },
        ],
    },
    "Wi-Fi 连接失败": {
        "conditions": ["路由器", "频段", "密码"],
        "causes": ["路由器5G频段不支持", "Wi-Fi密码错误", "信号弱", "设备已离线"],
        "steps": [
            {
                "question": "您的路由器是否同时支持2.4G和5G？设备只支持2.4G频段。",
                "if_yes": "请连接到2.4G频段的Wi-Fi。",
                "if_no": "了解，路由器只有2.4G的话没问题，我们继续排查。",
            },
            {
                "question": "设备与路由器是否在同一房间？（距离5米以内）",
                "if_yes": "信号强度应该够。",
                "if_no": "请将设备移近路由器，然后重新配网。",
            },
            {
                "question": "长按Wi-Fi键5秒进入配网模式后，App能搜索到设备吗？",
                "if_yes": "重新输入Wi-Fi密码试试。",
                "if_no": "尝试重启路由器和设备后重新配网。如果仍然不行，建议联系售后。客服热线：400-XXX-XXXX。",
            },
        ],
    },
    "边刷异常": {
        "conditions": ["边刷", "电机", "卡扣"],
        "causes": ["边刷卡扣脱落", "边刷电机卡死", "边刷头发缠绕", "边刷断裂"],
        "steps": [
            {
                "question": "边刷是完全不转，还是转动时有异响？",
                "if_yes": "转动有异响通常是头发缠绕，清洁即可。",
                "if_no": "完全不转可能是卡扣脱落或电机故障。",
            },
            {
                "question": "尝试把边刷拔下来，检查卡扣是否完好、轴上是否缠绕头发？",
                "if_yes": "清理缠绕物、重新安装即可。",
                "if_no": "卡扣或轴损坏，建议购买原装边刷更换。X30 Pro型号：X30-SB-01，¥29.9。",
            },
        ],
    },
    "开机无反应": {
        "conditions": ["电源键", "电池", "充电座"],
        "causes": ["电池深度亏电", "电源键损坏", "主板故障"],
        "steps": [
            {
                "question": "设备放上充电座后，充电指示灯有亮起吗？",
                "if_yes": "充电通路正常，可能是电池亏电。静置充电1小时后再试开机。",
                "if_no": "充电座或电池问题。请检查充电座电源、擦拭触点后重试。",
            },
            {
                "question": "充电1小时后，长按开机键10秒能启动吗？",
                "if_yes": "是深度亏电导致，问题解决。",
                "if_no": "电池或主板故障，建议联系售后检测。客服热线：400-XXX-XXXX。",
            },
        ],
    },
    "原地打转/不直走": {
        "conditions": ["传感器", "雷达", "轮子"],
        "causes": ["悬崖传感器脏污", "激光雷达遮挡", "单侧轮子卡死"],
        "steps": [
            {
                "question": "请检查设备底部的悬崖传感器（3个透明圆形窗口）是否有灰尘？用干布擦拭后重试。",
                "if_yes": "传感器清洁后应恢复正常。",
                "if_no": "传感器可能硬件故障，建议送修。",
            },
            {
                "question": "设备顶部的激光雷达（圆形凸起）能否自由旋转？上面是否有遮挡物？",
                "if_yes": "雷达正常，可能是单侧轮子问题。",
                "if_no": "清洁雷达罩，移除遮挡物后重启。",
            },
        ],
    },
    "拖地不出水/水量异常": {
        "conditions": ["清水箱", "出水孔", "拖布", "水量设置"],
        "causes": ["清水箱缺水", "出水孔堵塞", "拖布过脏", "水量设置过低", "水泵故障"],
        "steps": [
            {
                "question": "请检查清水箱是否有水？水箱是否推入到位（听到咔哒声）？",
                "if_yes": "水箱正常，继续排查。",
                "if_no": "请加满清水，重新推入水箱到底。",
            },
            {
                "question": "在 App 中将水量调至高档，拖布是否有变湿？",
                "if_yes": "水量设置过低导致，调到合适档位即可。",
                "if_no": "可能是出水孔堵塞或水泵故障。请用细针清理基站清洗盘的出水孔，再试一次。",
            },
            {
                "question": "清理出水孔后，拖地出水恢复正常了吗？",
                "if_yes": "出水孔堵塞已解决。建议每月清理一次出水孔，使用纯净水可减少堵塞。",
                "if_no": "出水孔通畅但仍不出水，可能是水泵故障，建议联系售后检修。客服热线：400-XXX-XXXX。",
            },
        ],
    },
    "基站漏水": {
        "conditions": ["污水箱", "清水箱", "清洗盘", "防水胶条"],
        "causes": ["污水箱已满溢出", "清水箱破裂", "清洗盘排水堵塞", "防水胶条老化"],
        "steps": [
            {
                "question": "请检查污水箱是否已满？",
                "if_yes": "立即倒掉污水，冲洗污水箱后装回。以后每次拖地完成后及时倒掉。",
                "if_no": "污水箱未满，检查其他可能。",
            },
            {
                "question": "取出基站底部清洗盘，检查排水孔是否被污垢堵塞？清洗盘有无破损？",
                "if_yes": "清理排水孔，清洗盘破损需更换（X30-BC-01，¥79）。",
                "if_no": "清洗盘正常，检查水箱和防水胶条。",
            },
            {
                "question": "检查清水箱是否有裂缝？基站与水箱对接处的防水胶条是否老化变形？",
                "if_yes": "清水箱破裂需更换（X30-WT-01，¥89），防水胶条老化更换（X30-WS-01，¥9）。",
                "if_no": "以上都正常但仍漏水，可能是内部水管破损，建议联系售后检修。",
            },
        ],
    },
    "烘干功能异常": {
        "conditions": ["烘干设置", "通风环境", "加热元件"],
        "causes": ["烘干时长设置过短", "基站通风不良", "加热元件故障"],
        "steps": [
            {
                "question": "请在 App 中检查烘干时长设置，是否设为2小时？",
                "if_yes": "建议调至4小时，潮湿环境下短时烘干可能不彻底。",
                "if_no": "设置正常，继续排查。",
            },
            {
                "question": "基站是否放在密闭角落或柜子里？周围通风是否良好？",
                "if_yes": "请将基站移到通风处，密闭空间湿气无法排出。",
                "if_no": "通风良好但仍不热，可能是烘干加热元件故障。",
            },
            {
                "question": "调至4小时烘干并确保通风后，拖布能完全烘干吗？",
                "if_yes": "问题解决。以后潮湿天气建议用4小时烘干时长。",
                "if_no": "加热元件可能故障，建议联系售后检修。客服热线：400-XXX-XXXX。",
            },
        ],
    },
    "集尘异常": {
        "conditions": ["集尘袋", "集尘管道", "基站风机", "尘盒"],
        "causes": ["集尘袋已满", "集尘袋安装不严", "集尘管道堵塞", "基站风机故障", "尘盒出口堵塞"],
        "steps": [
            {
                "question": "打开基站顶盖，集尘袋是否已明显鼓胀？",
                "if_yes": "集尘袋满了，请更换新袋（X30-DB-02，3只装 ¥49）。",
                "if_no": "集尘袋未满，检查安装和管道。",
            },
            {
                "question": "重新安装集尘袋（确保纸板卡口完全卡入风道接口），然后手动触发一次集尘，效果改善了吗？",
                "if_yes": "集尘袋安装不严密导致漏气，重新装好就解决了。",
                "if_no": "集尘袋和安装都正常，可能是集尘管道堵塞。",
            },
            {
                "question": "检查基站底部集尘口和管道是否有堵塞物？清理后再试一次集尘。",
                "if_yes": "管道堵塞物清理后恢复正常。建议每月检查一次管道。",
                "if_no": "管道通畅但仍集尘无力，可能是基站风机故障，建议联系售后检修。",
            },
        ],
    },
    "App 控制异常": {
        "conditions": ["网络", "App版本", "设备在线状态", "服务器"],
        "causes": ["Wi-Fi信号弱", "App版本过旧", "设备离线", "服务器维护"],
        "steps": [
            {
                "question": "请检查设备指示灯是否为蓝色长亮（在线状态）？",
                "if_yes": "设备在线，可能是 App 或网络问题。",
                "if_no": "设备离线了。请检查路由器是否正常、设备是否在 Wi-Fi 覆盖范围内。",
            },
            {
                "question": "尝试退出 App 重新登录，或清除 App 缓存后重试，能控制了吗？",
                "if_yes": "App 缓存问题导致，清理后恢复正常。",
                "if_no": "App 和网络都正常，可能是设备端通信模块异常。",
            },
            {
                "question": "尝试重启路由器和设备（长按开机键10秒），之后能正常控制吗？",
                "if_yes": "设备通信模块临时异常，重启后恢复。",
                "if_no": "多次重启仍无法远程控制，可能是 Wi-Fi 模块硬件故障，建议联系售后。",
            },
        ],
    },
    "固件更新失败": {
        "conditions": ["电量", "网络稳定性", "存储空间"],
        "causes": ["电量不足", "网络中断", "固件包损坏"],
        "steps": [
            {
                "question": "更新前设备电量是否 > 30%？",
                "if_yes": "电量充足，继续排查。",
                "if_no": "请将设备放回基站充满电后再更新。",
            },
            {
                "question": "更新时设备和手机是否在同一 Wi-Fi 下且信号稳定？",
                "if_yes": "网络正常。",
                "if_no": "请靠近路由器，确保 Wi-Fi 稳定后重新触发更新。",
            },
            {
                "question": "长按开机键10秒强制重启设备后，App 中重新触发更新，能成功吗？",
                "if_yes": "上次更新因网络波动中断，重启后重新更新成功。",
                "if_no": "多次更新失败，可能是固件包异常或设备存储问题，建议联系售后处理。",
            },
        ],
    },
    "电池续航骤降": {
        "conditions": ["电池健康", "清扫模式", "地面环境"],
        "causes": ["电池老化", "长期使用MAX模式", "地毯/复杂环境耗电增加"],
        "steps": [
            {
                "question": "请检查 App 中清扫记录：续航下降前是否长期使用 MAX 或强力模式？",
                "if_yes": "高吸力模式耗电量大，日常用标准模式即可，深度清洁时再用强力模式。",
                "if_no": "模式正常，可能是电池老化。",
            },
            {
                "question": "设备购买使用是否超过1年？续航是否降到新机的一半以下？",
                "if_yes": "电池正常衰减。若续航严重不足影响使用，可联系售后更换电池。",
                "if_no": "使用不到1年续航骤降，可能有电池质量问题。",
            },
            {
                "question": "尝试将电量用到自动关机，再充满一次（电池校准），续航改善了吗？",
                "if_yes": "电池计量偏差导致，校准后恢复正常。",
                "if_no": "校准无效，电池可能存在问题。建议联系售后检测。客服热线：400-XXX-XXXX。",
            },
        ],
    },
}


class TroubleshootScenario:
    """故障排查场景"""

    STAGE_INIT = "init"
    STAGE_CAUSES = "causes"
    STAGE_DIAGNOSIS = "diagnosis"
    STAGE_RESOLVED = "resolved"
    STAGE_ESCALATED = "escalated"
    MAX_DIAGNOSIS_ROUNDS = 5

    @staticmethod
    async def _polish(text: str) -> str:
        """LLM 润色——软化语气，不改变步骤和结论"""
        try:
            from smart_qa.agent.persona import get_system_prompt
            from smart_qa.deps import get_llm_client

            llm = get_llm_client()
            persona = get_system_prompt("troubleshoot")
            prompt = (
                persona + "\n\n"
                "请把下面的排查话术改得口语化、亲切一些。\n"
                "要求：\n"
                "- 只能改语气和用词，不能增减步骤、不能提前下结论、不能新增问句\n"
                "- 不要再加'好的我来帮您看看'之类的开场白，直接进入排查内容\n"
                "- 只输出润色后的文本，不要加任何前缀标记\n\n"
                "原文：\n" + text + "\n"
            )
            resp = await llm.ainvoke(prompt)
            result = resp.content if hasattr(resp, "content") else str(resp)
            result = result.strip()
            # 去掉 LLM 可能加的前缀
            for prefix in ["润色后：", "润色后:", "润色后", "回答：", "回复："]:
                if result.startswith(prefix):
                    result = result[len(prefix) :].strip()
            return result if len(result) >= len(text) * 0.5 else text
        except Exception:
            return text

    @staticmethod
    async def _save_task(state: dict, task: dict):
        state["task_memory"] = task

    @staticmethod
    async def run(state: dict) -> dict:
        """执行故障排查场景"""
        query = TroubleshootScenario._extract_query(state)
        if not query:
            state["final_answer"] = (
                "请描述您的设备遇到了什么问题？比如：无法开机、清扫不干净、有错误码等，我来帮您排查。"
            )
            return state

        task_memory = state.get("task_memory") or {}
        stage = task_memory.get("diagnosis_stage", TroubleshootScenario.STAGE_INIT)
        round_num = task_memory.get("diagnosis_round", 0)

        error_code = TroubleshootScenario._extract_error_code(query)

        if error_code and error_code in ERROR_CODE_MAP:
            entry = ERROR_CODE_MAP[error_code]
            state["final_answer"] = (
                f"识别到错误码 {error_code}：\n"
                f"🔍 原因：{entry['cause']}\n"
                f"🔧 解决方法：{entry['solution']}\n\n"
                f"如按以上步骤操作后问题仍未解决，请联系售后客服。"
            )
            await TroubleshootScenario._save_task(state, {"diagnosis_stage": TroubleshootScenario.STAGE_RESOLVED})
            return state

        if stage == TroubleshootScenario.STAGE_INIT:
            return await TroubleshootScenario._handle_init(query, state)
        elif stage == TroubleshootScenario.STAGE_DIAGNOSIS:
            return await TroubleshootScenario._handle_diagnosis(query, state, task_memory, round_num)
        else:
            return await TroubleshootScenario._handle_init(query, state)

    @staticmethod
    async def _handle_init(query: str, state: dict) -> dict:
        """初始阶段: 匹配故障分类，开始排查"""
        fault_type = TroubleshootScenario._match_fault_type(query)
        tree = DIAGNOSIS_TREE.get(fault_type)

        if not tree:
            raw = (
                f"关于「{query[:30]}」这个问题，建议先试试这几步：\n\n"
                "1. 检查设备电量是否充足（>15%）\n"
                "2. 重启设备（长按开机键10秒）\n"
                "3. 查看App是否有固件更新\n"
                "4. 清洁所有传感器和充电触点\n\n"
                "如果问题还在，请告诉我更多细节（比如有没有错误码、指示灯什么状态），我可以帮您进一步看看。"
            )
            state["final_answer"] = await TroubleshootScenario._polish(raw)
            return state

        first_step = tree["steps"][0]
        causes = tree["causes"]
        raw = (
            "根据您的描述，可能的原因有几种，我来帮您一步步排查。\n\n"
            + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(causes))
            + f"\n\n第一步：{first_step['question']}"
        )
        state["final_answer"] = await TroubleshootScenario._polish(raw)

        await TroubleshootScenario._save_task(
            state,
            {
                "diagnosis_stage": TroubleshootScenario.STAGE_DIAGNOSIS,
                "diagnosis_round": 1,
                "fault_type": fault_type,
                "current_step": 0,
                "symptoms": query,
            },
        )
        return state

    @staticmethod
    async def _handle_diagnosis(user_response: str, state: dict, task_memory: dict, round_num: int) -> dict:
        """排查阶段: 处理用户回答，进入下一步"""
        if round_num >= TroubleshootScenario.MAX_DIAGNOSIS_ROUNDS:
            raw = (
                "经过多轮排查还没找到确切原因，建议您联系我们的售后团队进一步检测：\n\n"
                "1. 拨打客服热线：400-XXX-XXXX\n"
                "2. 在App中提交维修申请\n"
                "3. 到最近的授权维修点检测\n\n"
                "提交时请说明已经试过的排查步骤，能帮售后更快处理。"
            )
            state["final_answer"] = await TroubleshootScenario._polish(raw)
            await TroubleshootScenario._save_task(state, {"diagnosis_stage": TroubleshootScenario.STAGE_ESCALATED})
            return state

        fault_type = task_memory.get("fault_type", "")
        current_step_idx = task_memory.get("current_step", 0)
        tree = DIAGNOSIS_TREE.get(fault_type)

        if not tree:
            state["final_answer"] = "请重新描述一下您的问题，我帮您重新诊断。"
            await TroubleshootScenario._save_task(state, {"diagnosis_stage": TroubleshootScenario.STAGE_INIT})
            return state

        steps = tree["steps"]
        is_yes = TroubleshootScenario._is_positive_response(user_response)
        current_step = steps[current_step_idx]

        # 最后一步 -> 输出结论
        if current_step_idx >= len(steps) - 1:
            final_text = current_step.get("if_yes") if is_yes else current_step.get("if_no", "")
            if final_text:
                state["final_answer"] = await TroubleshootScenario._polish(final_text)
            else:
                state["final_answer"] = "已收集所有信息，建议联系售后进一步诊断。"
            await TroubleshootScenario._save_task(state, {"diagnosis_stage": TroubleshootScenario.STAGE_RESOLVED})
            return state

        # 推进到下一步
        next_idx = current_step_idx + 1
        next_step = steps[next_idx]

        if is_yes:
            feedback = current_step.get("if_yes", "")
        else:
            feedback = current_step.get("if_no", "")

        raw = f"{feedback}\n\n下一步：{next_step['question']}" if feedback else f"下一步：{next_step['question']}"
        state["final_answer"] = await TroubleshootScenario._polish(raw)

        await TroubleshootScenario._save_task(
            state,
            {
                "diagnosis_stage": TroubleshootScenario.STAGE_DIAGNOSIS,
                "diagnosis_round": round_num + 1,
                "fault_type": fault_type,
                "current_step": next_idx,
                "symptoms": task_memory.get("symptoms", ""),
            },
        )
        return state

    # -- 辅助方法 --

    @staticmethod
    def _extract_query(state: dict) -> str:
        from smart_qa.agent.state_utils import extract_user_query

        return extract_user_query(state)

    @staticmethod
    def _extract_error_code(text: str) -> str | None:
        import re

        match = re.search(r"[Ee](\d{2,3})", text)
        if match:
            code = f"E{match.group(1)}"
            return code if code in ERROR_CODE_MAP else None
        return None

    @staticmethod
    def _match_fault_type(query: str) -> str | None:
        keyword_map = {
            "开机无反应": ["开机没反应", "按了没反应", "开不起来", "启动不了", "死机", "电源键"],
            "不工作/不开机": ["不工作", "不开机", "没反应", "开不了"],
            "清扫不干净": ["不干净", "清扫不", "扫不", "漏扫", "灰尘"],
            "无法回充": ["回充", "充电", "回不去", "找不到充电", "不充电"],
            "异常噪音": ["噪音", "太吵", "声音大", "异响", "响声", "咔咔"],
            "Wi-Fi 连接失败": ["wifi", "wi-fi", "联网", "连不上", "配网", "掉线", "无网络"],
            "边刷异常": ["边刷", "侧刷", "边扫", "边轮"],
            "原地打转/不直走": ["原地", "打转", "转圈", "不直走", "走不直", "跑偏"],
            "拖地不出水/水量异常": ["不出水", "不拖地", "水量", "不出水", "拖地没水", "拖地干", "渗水"],
            "基站漏水": ["漏水", "基站有水", "渗水", "水箱漏"],
            "烘干功能异常": ["烘干", "不热", "不干", "烘干不热", "拖布湿", "烘干失效"],
            "集尘异常": ["集尘", "不集尘", "集尘袋", "集尘管道", "集尘失败", "尘盒不倒"],
            "App 控制异常": ["app", "应用", "控制", "远程", "手机控制", "连不上app", "app离线"],
            "固件更新失败": ["固件", "更新", "升级", "更新失败", "升级失败"],
            "电池续航骤降": ["续航", "电池不耐用", "耗电快", "电池下降", "续航短", "很快没电"],
        }
        query_lower = query.lower()
        for fault_type, keywords in keyword_map.items():
            if any(kw in query_lower for kw in keywords):
                return fault_type
        return None

    @staticmethod
    def _is_positive_response(response: str) -> bool:
        positive = [
            "是",
            "对",
            "有",
            "嗯",
            "好",
            "可以",
            "能",
            "亮",
            "正常",
            "够",
            "恢复",
            "改善",
            "解决",
            "yes",
            "y",
            "ok",
        ]
        negative = ["不", "没", "无", "否", "没有", "不行", "不能", "坏了", "还是", "仍然", "依旧", "依然", "no", "n"]
        resp_lower = response.lower().strip()
        for neg in negative:
            if resp_lower.startswith(neg):
                return False
        for pos in positive:
            if resp_lower.startswith(pos):
                return True
        # 兜底：有内容且不以否定开头，默认当正面
        return len(resp_lower) > 0
