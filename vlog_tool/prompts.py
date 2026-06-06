ANALYZE_PROMPT = """请分析这段旅行 vlog 原始素材视频，用中文回复。

请严格按以下 JSON 格式输出（不要 markdown 代码块，只输出 JSON）：
{
  "title": "10字以内的简短标题，适合作为文件名",
  "summary": "2-3句话的内容简介",
  "location": "地点（若无法判断填未知）",
  "mood": "氛围/情绪关键词",
  "timeline": [
    {"start": "00:00", "end": "00:15", "description": "该时间段画面内容"},
    {"start": "00:15", "end": "00:30", "description": "..."}
  ],
  "highlights": ["值得保留的亮点1", "亮点2"],
  "suggested_use": "适合放在日 vlog 的哪个环节（开场/途中/美食/结尾等）"
}

要求：
- timeline 尽量覆盖主要画面变化，时间格式 MM:SS 或 HH:MM:SS
- title 不要含特殊符号
"""

SCRIPT_PROMPT = """你是旅行 vlog 口播文案写手。根据以下素材分析结果和口播模板，为编号 {index} 的片段写口播文案。

## 口播模板
{template}

## 素材信息
编号: {index}
标题: {title}
简介: {summary}
地点: {location}
时间轴:
{timeline_text}

请输出 JSON（不要 markdown 代码块）：
{{
  "index": "{index}",
  "title": "{title}",
  "voiceover": "口播正文，约{target_words}字，第一人称，自然口语化",
  "duration_hint_sec": 20,
  "edit_tip": "给剪辑师的一句建议（选哪个时间段、要不要加速等）"
}}
"""

PLAN_PROMPT = """你是旅行 vlog 剪辑策划。用户以「一天行程 = 一条 vlog」来剪辑。

以下是当天所有素材的摘要（JSON 数组）：
{clips_json}

目标：选出不超过 {max_clips} 个片段，总时长约 {target_duration_sec} 秒，排成有叙事感的顺序。

请输出 JSON（不要 markdown 代码块）：
{{
  "day_title": "这一天 vlog 的标题",
  "theme": "主题一句话",
  "total_estimated_sec": 180,
  "sequence": [
    {{
      "index": "001",
      "title": "...",
      "reason": "为什么选这段、放这里的叙事作用",
      "use_timeline": "建议使用的时间轴片段，如 00:10-00:45",
      "voiceover_hint": "口播方向提示"
    }}
  ],
  "opening_tip": "开场建议",
  "ending_tip": "结尾建议"
}}
"""
