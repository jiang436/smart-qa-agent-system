"""小米米家扫地机器人知识库生成器

产出格式: MD + TXT + HTML（UTF-8），7 大类全覆盖。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

OUTPUT = Path("data/knowledge")

XIAOMI_KNOWLEDGE = {
    # ═══════════════════════════════════════
    "02_user_manual/xiaomi_setup_guide.md": """# 小米米家扫拖机器人 使用指南

## 首次开机与配网

### 开箱装机步骤
1. 取出机器人主体和充电座，去除所有保护泡沫和胶带
2. 安装边刷：对准底部卡槽，按压至"咔哒"声（左右各一个，注意 L/R 标识）
3. 将充电座靠墙平放，左右各留 0.5 米空间，前方留 1 米进出通道
4. 充电座连接电源适配器，指示灯亮起
5. 将机器人靠入充电座，首次使用建议充满电（约 4-5 小时）
6. 长按电源键 3 秒开机

### APP 配网步骤
1. 下载"米家"APP（iOS App Store / 安卓应用商店）
2. 手机连接 2.4GHz WiFi（不支持 5GHz）
3. 打开米家 APP → 右上角"+" → 添加设备 → 自动搜索
4. 找到机器人后点击，按提示输入 WiFi 密码
5. 等待配网完成（约 1-2 分钟）
6. 配网成功后可在 APP 中给机器人命名（如"客厅小管家"）

### 配网失败排查
- 确认 WiFi 是 2.4GHz（可在路由器后台查看）
- WiFi 名称和密码不要有中文、特殊符号
- 关闭路由器的 AP 隔离功能
- 手机开启蓝牙（配网过程需要）
- 同时按住"回充键"和"电源键"5 秒重置 WiFi

## 快速建图
1. 首次使用建议先"快速建图"（不进行清扫）
2. 打开所有房门，收起地面的数据线、袜子等杂物
3. 把椅子倒扣在桌上（减少障碍干扰）
4. 在 APP 中点击"快速建图"，约 8-12 分钟完成
5. 建图后在 APP 中编辑房间名称（卧室、客厅、厨房等）
6. 80㎡ 户型约 10 分钟完成

## 清扫模式

### 全屋清扫
- 覆盖所有已建图区域
- 自动先沿边再弓字形清扫
- 支持断点续扫：电量不足时自动回充，满电后继续

### 选区清扫
- 在 APP 地图上勾选指定房间
- 可设置每个房间的扫地/拖地次数（1-2 次）
- 可单独设置每个房间的吸力档位

### 划区清扫
- 在 APP 地图上手指画矩形区域
- 适合餐后局部清扫、临时脏污

### 禁区设置
- 虚拟墙：禁止进入某个房间
- 拖地禁区：扫地可进入但不拖地（如地毯区）
- 禁区框：完全禁止进入（如宠物食盆区、玩具区）

## 拖地功能

### 水量档位
| 档位 | 适用地面 | 特点 |
|------|---------|------|
| 1 档 | 实木地板、地暖 | 微湿、快速干 |
| 2 档 | 瓷砖、大理石（默认） | 正常湿润 |
| 3 档 | 厨房、阳台 | 深层清洁 |

### 拖地注意
- 首次拖地前先全屋清扫一遍（去除表面灰尘）
- 木地板不要用 3 档（避免地板受潮变形）
- 拖地完成后及时取下拖布晾干（防止发霉）
- 拖布建议每 2-3 个月更换

## 多楼层管理
- 支持保存 2-3 张楼层地图
- 搬动机器人到新楼层后，APP 自动检测并切换地图
- 每层楼的禁区/虚拟墙独立设置
- 复式户型注意开启悬崖传感器

## 地面材质适配

### 木地板
- 水量用 1 档（最低）
- 避免拖布过湿（木地板怕受潮）
- 不要使用非官方清洁液

### 地砖/大理石
- 水量用 2 档
- 高水量拖地后建议开窗通风
- 注意瓷砖深色填缝剂可能被摩擦褪色

### 地毯
- 短毛地毯（<10mm）：自动识别，增压清扫
- 长毛地毯（>15mm）：设"拖地禁区"
- 流苏地毯：设禁区（可能缠绕边刷）
""",

    # ═══════════════════════════════════════
    "04_fault_troubleshooting/xiaomi_fault_codes.md": """# 小米米家扫拖机器人 故障码对照表

## 机身故障码

### 传感器类
| 故障码 | 含义 | 常见原因 | 自助处理 |
|--------|------|---------|---------|
| 错误1 | 激光测距传感器异常 | 雷达罩脏污、被压住 | 擦拭顶部雷达罩，检查是否自由转动 |
| 错误2 | 碰撞传感器异常 | 防撞条卡住 | 按压防撞条测试回弹 |
| 错误3 | 悬崖传感器异常 | 底部传感器脏了 | 擦拭底部 4-6 个透明窗口 |
| 错误4 | 陀螺仪异常 | 机器受到撞击 | 放平整地面重启 |

### 运动类
| 故障码 | 含义 | 自助处理 |
|--------|------|---------|
| 错误5 | 左轮异常 | 检查左轮是否有缠绕物，清理后重启 |
| 错误6 | 右轮异常 | 检查右轮是否有缠绕物，清理后重启 |
| 错误7 | 边刷异常 | 取下边刷清理缠绕毛发，重新安装 |
| 错误8 | 主刷异常 | 打开底部盖板，取出滚刷清理缠绕物 |
| 错误9 | 风机异常 | 检查尘盒气路是否堵塞、清理风机口 |

### 系统类
| 故障码 | 含义 | 处理方案 |
|--------|------|---------|
| 错误10 | 电池异常 | 确认电池接触正常，充电 30 分钟后重启。若反复出现，需更换电池 |
| 错误11 | 充电异常 | 清洁充电触点、检查充电座供电、确认适配器没坏 |
| 错误12 | WiFi 模块异常 | 重启机器和路由器，重新配网。若反复出现，联系售后 |

## 基站故障码（全能基站机型）

| 故障码 | 含义 | 自助处理 |
|--------|------|---------|
| 错误21 | 清水箱缺水 | 加清水到水箱，确认水箱安装到位 |
| 错误22 | 污水箱已满 | 倒掉污水，清洗污水箱 |
| 错误23 | 集尘袋已满 | 更换一次性集尘袋 |
| 错误24 | 烘干异常 | 检查烘干出风口是否堵塞 |
| 错误25 | 上下水堵塞 | 检查进水管和排水管 |
| 错误26 | 洗拖布异常 | 清洗基站底盘，检查排水口 |

## 高频故障自助排查

### 地图丢失/偏移
**原因**: 激光雷达被遮挡（最常见）/ 搬运后未切换楼层 / 固件问题
**解决**:
1. 检查顶部激光雷达罩是否有灰尘、水渍
2. 确认未手动搬动机器人位置
3. APP 内手动切换正确的楼层地图
4. 重新"快速建图"

### 回充失败
**排查步骤**:
1. 充电座指示灯是否亮？不亮→检查电源
2. 充电座周围是否有障碍物？
3. 阳光直射会影响红外回充信号→挪位置
4. 清洁机器底部的充电触片和基站触点
5. 把机器搬到充电座前 1 米，APP 内点"回充"

### 拖地不出水
**排查**:
1. 清水箱是否有水？→加水
2. 拖布是否过脏导致无法渗透？→换干净拖布
3. APP 水量是否设为 1 档？→调到 2-3 档
4. 出水泵是否堵塞？→用细针疏通

### 噪音突然变大
1. 检查滚刷是否缠绕头发→清理
2. 检查边刷是否碰到硬物
3. 检查风机口是否有异物
4. 万向轮是否卡入异物

### 续航断崖下跌
- 新机器（<6 个月）：软件问题→固件升级→重置
- 老机器（>1 年）：电池老化→售后更换
- 冬天低温：正常现象（<5℃ 时电池活性降低）
""",

    # ═══════════════════════════════════════
    "03_maintenance/xiaomi_maintenance_guide.md": """# 小米米家扫拖机器人 养护维护指南

## 日常维护（每次清扫后）

### 尘盒清理
1. 打开机器人顶部盖板
2. 取出尘盒，倒掉灰尘和杂物
3. 用清洁刷轻扫滤网表面（HEPA 滤网不要水洗！）
4. 尘盒可以用清水冲洗，必须完全晾干后再装回
5. 滤网每 3-4 个月更换

### 滚刷/边刷检查
1. 按压底部盖板卡扣，取出滚刷
2. 用剪刀或自带清洁工具割断缠绕的毛发
3. 清理滚刷两端轴承处的头发团
4. 边刷同样取下清理缠绕物
5. 边刷如刷毛变形或缩短 1/3 以上→更换

### 传感器清洁
每次清扫后用干布擦拭：
- 顶部激光雷达罩（最关键，影响建图和导航）
- 底部悬崖传感器（4-6 个透明窗口）
- 充电触片（机器底部和基站）
- 沿墙传感器（侧面窗口）

## 每周维护

### 全能基站清洁
1. 取出污水箱，倒掉污水，清水冲洗
2. 用湿布擦拭基站底盘（洗拖布区域）
3. 检查洗拖布盘的排水口是否堵塞
4. 清水箱每周换一次水（防止细菌滋生）
5. 清洁基站充电触片

### 拖布保养
1. 从支架上取下拖布
2. 用清水或中性洗涤剂手洗
3. 自然晾干，不要用烘干机
4. 拖布纤维变硬或变色→更换

## 每月维护

### 滤网深度清洁
1. 取下 HEPA 滤网
2. 在垃圾桶边轻轻敲击，去除表面灰尘
3. 放在阳光下晒 2-3 小时（紫外线杀菌）
4. 不要水洗！不要用吸尘器吸！
5. 滤网建议 3-4 个月更换

### 滚刷深度清洁
1. 取下滚刷，检查橡胶刮条磨损情况
2. 用湿布擦拭滚刷仓内部
3. 检查滚刷轴承是否需要润滑
4. 滚刷建议 6-12 个月更换

### 基站水箱清洁
1. 清水箱用稀释的白醋水（1:10）浸泡 30 分钟
2. 冲洗干净后晾干
3. 污水箱同样清洗
4. 检查水箱密封圈是否完好

## 季度维护

### 耗材更换检查清单
| 耗材 | 检查方法 | 更换标准 | 推荐周期 |
|------|---------|---------|---------|
| 边刷 | 目视刷毛 | 刷毛缩短 1/3 以上 | 3-6 月 |
| 滚刷 | 查刷毛+橡胶条 | 刷毛脱落/橡胶磨损 | 6-12 月 |
| HEPA滤网 | 透光检查 | 不透光/颜色深灰 | 3-4 月 |
| 拖布 | 手感+颜色 | 变硬/发黄/洗不净 | 2-3 月 |
| 集尘袋 | APP 提示 | 装满/吸力下降 | 60-90 天 |
| 银离子模块 | 到期 | 12 个月强制更换 | 12 月 |

### 电池养护
- 长期不用：保持 50-70% 电量存放
- 每 2-3 个月充一次电（防止过放）
- 冬季（<5℃）续航下降属正常现象
- 电池寿命 2-3 年，续航低于新机的 50% 时建议更换

## 耗材选购指南

### 米家官方耗材价格参考
| 配件 | 适用机型 | 价格 |
|------|---------|------|
| 边刷 | 通用 | ¥19-29/对 |
| 主滚刷 | 按型号 | ¥69-99 |
| HEPA滤网 | 按型号 | ¥39-59 |
| 拖布 | 通用 | ¥19-29/对 |
| 集尘袋 | 全能基站机型 | ¥39/3个 |
| 清洁液 | 通用 | ¥29-49/瓶 |

### 购买渠道
- 小米商城（mi.com）— 官方正品
- 小米之家线下门店
- 小米天猫/京东旗舰店
- 第三方品牌（清蜓、MR.ROBOT 等）— 性价比高

### 选购注意事项
- 边刷/拖布：第三方性价比高、够用
- 滤网/滚刷：建议原厂（影响清洁效果大）
- 清洁液：必须原厂（第三方可能腐蚀水箱管路）
- 不要用 84 消毒液或酒精（会腐蚀机器内部管路）
""",

    # ═══════════════════════════════════════
    "06_smart_home/xiaomi_mijia_iot.md": """# 小米米家扫拖机器人 智能家居联动

## 小爱同学语音控制

### 清扫指令
| 语音指令 | 操作 |
|---------|------|
| "小爱同学，扫地" | 启动全屋清扫 |
| "小爱同学，让扫地机开始打扫" | 启动全屋清扫 |
| "小爱同学，停止清扫" | 暂停/停止 |
| "小爱同学，让扫地机回去充电" | 返回充电座 |
| "小爱同学，让扫地机清扫客厅" | 指定房间清扫 |
| "小爱同学，扫地机强力模式" | 切换吸力 |

### 状态查询
- "小爱同学，扫地机还有多少电？"
- "小爱同学，扫地机扫完了吗？"
- "小爱同学，扫地机在哪里？"（部分机型支持查找机器人）

## 米家 APP 自动化场景

### 离家自动清扫
**条件**: 配合米家门锁/人体传感器
**触发**: 门锁上提反锁 ↔ 所有家庭成员离开
**动作**: 机器人自动开始全屋清扫

### 回家暂停
**条件**: 门锁开锁
**动作**: 正在清扫的机器人暂停并回充

### 定时清扫
**设置路径**: 米家 APP → 扫地机 → 定时清扫 → 添加
**支持**: 每天/每周几/自定义时间

### 晚安模式
**触发**: 语音"晚安"或床头按钮
**动作**: 关灯 + 空调调温 + 扫地机回充

## 米家 vs 小米澎湃OS 联动

### 支持设备
- 所有米家生态设备（灯、空调、窗帘、门锁、摄像头等）
- Xiaomi HyperOS 手机可查看扫地机实时地图
- 小米电视可弹窗显示清扫完成通知

### 摄像头联动（部分机型支持）
- 机器人自带摄像头可远程查看家中情况
- 可作为移动安防摄像头巡航
- 隐私模式：摄像头仅在用户主动开启时工作

## 第三方平台

### Apple HomeKit（部分机型通过 Matter 支持）
- 需 iOS 16.4+
- 需 HomePod/Apple TV 作为家居中枢
- Siri 可控制开始/停止清扫

### 小爱音箱推荐
| 音箱型号 | 推荐度 | 备注 |
|---------|:---:|------|
| Xiaomi Sound Pro | ⭐⭐⭐ | 音质好，远场拾音准 |
| 小米AI音箱 2代 | ⭐⭐⭐ | 性价比高 |
| Redmi 小爱触屏音箱 | ⭐⭐ | 带屏幕，可看状态 |
""",

    # ═══════════════════════════════════════
    "07_after_sales/xiaomi_warranty_policy.md": """# 小米米家扫拖机器人 售后保修政策

## 保修期限
| 部件 | 保修时长 | 备注 |
|------|---------|------|
| 整机 | 1 年 | 含主机和充电座 |
| 电池 | 6 个月 | 续航低于标称 50% 可免费换 |
| 电机(风机/轮毂) | 2 年 | 仅限电机 |
| 激光雷达模块 | 2 年 | 高端机型 |
| 边刷/滚刷 | 不保修 | 属易损耗材 |
| 滤网/拖布/集尘袋 | 不保修 | 属易损耗材 |
| 全能基站 | 1 年 | 与整机同步 |

## 退换货政策
| 时间 | 政策 |
|------|------|
| 签收 7 天内 | 无理由退货（包装完整、配件齐全、未使用） |
| 签收 15 天内 | 质量问题可换新（同型号） |
| 超过 15 天 | 走保修流程 |

## 售后渠道
- **小米商城 APP**: 我的 → 售后服务 → 申请维修
- **客服电话**: 400-100-5678
- **小米之家**: 全国 2000+ 门店可受理
- **寄修服务**: APP 内申请，顺丰上门取件（保内免运费）

## 上门服务
- **安装上下水**: 购买含安装服务的机型，免费上门
- **上门维修**: 保内免费，保外上门费 ¥50 + 配件费
- **覆盖范围**: 全国县级以上城市

## 配件购买
- **官方渠道**: mi.com、小米商城 APP、小米之家、天猫/京东旗舰店
- **官方耗材套餐**: 基础养护套（边刷×2+滤网×1+拖布×2）约 ¥99

## 常见售后问题

### 保修需要什么凭证？
电子发票（小米商城订单记录）或纸质发票。没有发票按出厂日期+3 个月计算保修期。

### 人为损坏保修吗？
不保修。包括：进水、摔落、私自拆卸、使用非原厂清洁液导致腐蚀。

### 保修期内出现故障怎么办？
1. 小米商城 APP → 售后服务 → 申请维修
2. 选择"上门取件"或"到店维修"
3. 顺丰免费上门取件（免运费）
4. 维修周期：3-7 个工作日
""",
}


def gen_txt(md_text: str) -> str:
    """MD → 格式清晰的 TXT 纯文本"""
    lines = md_text.split("\n")
    out = []
    for line in lines:
        if line.startswith("# "):
            out.append("")
            out.append("=" * 60)
            out.append(f"  {line[2:]}")
            out.append("=" * 60)
        elif line.startswith("## "):
            out.append("")
            out.append(f"--- {line[3:]} ---")
        elif line.startswith("### "):
            out.append("")
            out.append(f"  [{line[4:]}]")
        elif line.startswith("|") and "|" in line[1:]:
            # 表格：对齐列
            cells = [c.strip() for c in line.split("|") if c.strip()]
            out.append("  " + "  |  ".join(cells))
        elif line.startswith("- ") or line.startswith("* "):
            out.append(f"  • {line[2:]}")
        elif re.match(r"^\d+\.\s", line):
            out.append(f"  {line}")
        elif line.strip():
            out.append(f"  {line}")
        else:
            out.append("")
    return "\n".join(out)


def gen_html(md_text: str) -> str:
    """MD → UTF-8 HTML（VS Code 可读 + 浏览器可渲染）"""
    lines = md_text.split('\n')
    html = [
        '<!DOCTYPE html>', '<html lang="zh-CN"><head><meta charset="UTF-8">',
        '<style>',
        'body{font-family:"Microsoft YaHei",sans-serif;max-width:800px;margin:40px auto;line-height:1.8}',
        'h1{border-bottom:2px solid #333;padding-bottom:10px}',
        'h2{margin-top:30px;color:#333}',
        'h3{color:#555}',
        'table{border-collapse:collapse;width:100%;margin:10px 0}',
        'td,th{border:1px solid #ddd;padding:8px}',
        'th{background:#f5f5f5}',
        '.li{margin-left:20px}',
        '</style></head><body>',
    ]

    in_table = False
    for line in lines:
        if line.startswith('# '):
            html.append(f'<h1>{line[2:]}</h1>')
        elif line.startswith('## '):
            html.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('### '):
            html.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('|') and '|' in line[1:]:
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if not in_table:
                html.append('<table>')
                in_table = True
            # 跳过分隔行
            if all(c.startswith('---') or c.startswith(':--') for c in cells):
                continue
            html.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
        else:
            if in_table:
                html.append('</table>')
                in_table = False
            if line.startswith('- ') or line.startswith('* '):
                html.append(f'<div class="li">• {line[2:]}</div>')
            elif re.match(r'^\d+\.\s', line):
                html.append(f'<div class="li">{line}</div>')
            elif line.strip():
                html.append(f'<p>{line}</p>')
            else:
                html.append('<br>')
    if in_table:
        html.append('</table>')
    html.append('</body></html>')
    return '\n'.join(html)


def build():
    """生成全部知识库文档（MD + TXT + PDF）"""
    stats = {"md": 0, "txt": 0, "html": 0}

    for rel_path, md_content in XIAOMI_KNOWLEDGE.items():
        base = OUTPUT / rel_path
        base.parent.mkdir(parents=True, exist_ok=True)

        # 1. MD
        base.write_text(md_content, encoding="utf-8")
        stats["md"] += 1

        # 2. TXT
        txt_path = base.with_suffix(".txt")
        txt_path.write_text(gen_txt(md_content), encoding="utf-8")
        stats["txt"] += 1

        # 3. HTML
        html_path = base.with_suffix(".html")
        html_path.write_text(gen_html(md_content), encoding="utf-8")
        stats["html"] += 1

        print(f"  {rel_path} → .md + .txt + .html")

    # 同时给爬到的 xiaomi_products 也生成 txt/html
    for src in ["xiaomi_products", "xiaomi_accessories", "xiaomi_faq", "xiaomi_help_center", "xiaomi_community", "xiaomi_manuals", "xiaomi_search_results"]:
        for cat in ["01_product_specs", "02_user_manual", "03_maintenance", "04_fault_troubleshooting"]:
            md_path = OUTPUT / cat / f"{src}.md"
            if md_path.exists():
                md_content = md_path.read_text(encoding="utf-8")
                txt_path = md_path.with_suffix(".txt")
                html_path = md_path.with_suffix(".html")
                txt_path.write_text(gen_txt(md_content), encoding="utf-8")
                gen_html(md_content, str(html_path))
                stats["txt"] += 1
                stats["html"] += 1
                print(f"  [爬虫] {md_path.name} → .txt + .html")

    # 统计
    files = {"md": 0, "txt": 0, "html": 0}
    for root, dirs, fnames in os.walk(OUTPUT):
        for f in fnames:
            for ext in files:
                if f.endswith(f".{ext}"):
                    files[ext] += 1
    print(f"\n总计: {files['md']} MD + {files['txt']} TXT + {files['html']} PDF = {sum(files.values())} 文件")
    total_chars = sum(
        os.path.getsize(os.path.join(root, f))
        for root, dirs, fnames in os.walk(OUTPUT)
        for f in fnames
    )
    print(f"总字符: {total_chars}")


if __name__ == "__main__":
    print("=" * 50)
    print("  小米米家扫拖机器人知识库生成")
    print("=" * 50)
    build()
