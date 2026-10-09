"""Grounded AI drafts for teacher-reviewed learning content."""

import json
import re

import requests
from flask import current_app

from alrayyan.services.ai_teacher import build_context
from alrayyan.services.semantic_search import semantic_search


def _json_payload(text):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start:end + 1])


def _grounded_request(lesson, task_prompt):
    results = semantic_search(
        f"{lesson.title} مفاهيم شخصيات أحداث أسباب نتائج",
        top_k=6,
        min_similarity=0.12,
        lesson_id=lesson.id,
    )
    if not results:
        raise RuntimeError("لا توجد مقاطع مفهرسة كافية لهذا الدرس.")
    api_key = current_app.config.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("مفتاح خدمة الذكاء الاصطناعي غير مضبوط.")
    request_body = {
            "model": current_app.config.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            "temperature": 0.15,
            "max_tokens": 1300,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "أنت مساعد إعداد محتوى تعليمي متعدد المواد. اعتمد فقط على السياق. "
                        "أعد JSON صالحًا فقط. لا تخترع أسماء أو صفحات أو حقائق. "
                        "المحتوى مسودة ستراجعها المعلمة قبل النشر."
                    ),
                },
                {
                    "role": "user",
                    "content": f"الدرس: {lesson.title}\n\nالمطلوب:\n{task_prompt}\n\nالسياق:\n{build_context(results)}",
                },
            ],
        }
    last_error = None
    for attempt in range(3):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=request_body,
                timeout=90,
            )
            data = response.json()
            if not response.ok:
                raise RuntimeError(data.get("error", {}).get("message") or "فشل مزود الذكاء الاصطناعي.")
            return _json_payload(data["choices"][0]["message"]["content"]), results
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, RuntimeError) as error:
            last_error = error
            current_app.logger.warning("Learning content generation attempt %s failed: %s", attempt + 1, error)
            request_body["temperature"] = 0.05
            request_body["messages"].append({"role": "user", "content": "أعد JSON صالحًا مختصرًا فقط، دون Markdown أو مقدمة."})
    raise RuntimeError("تعذر إكمال المسودة الآن. حُفظت بيانات النموذج؛ حاولي مرة أخرى بعد قليل.") from last_error


def generate_concept_map_draft(lesson):
    payload, results = _grounded_request(
        lesson,
        (
            "أنشئ خريطة مفاهيمية شجرية متفرعة. اجعل لها جذرًا واحدًا واضحًا، ثم فروعًا رئيسية وفرعية متوازنة، ولا تجعلها قائمة مسطحة. JSON: "
            '{"title":"...","nodes":[{"key":"n1","label":"...","description":"..."}],'
            '"edges":[{"source":"n1","target":"n2","label":"..."}]}. '
            "من 5 إلى 9 عقد وروابط صحيحة فقط. اجعل الروابط تبدأ من الجذر إلى الفروع ثم الفروع الفرعية، وتجنب الدورات وتعدد الآباء للعقدة الواحدة."
        ),
    )
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or len(nodes) < 2 or not isinstance(edges, list):
        raise RuntimeError("مسودة الخريطة غير مكتملة.")
    payload["citations"] = list(dict.fromkeys(result["citation"] for result in results))[:5]
    return payload


def generate_character_drafts(lesson):
    payload, results = _grounded_request(
        lesson,
        (
            "استخرج الشخصيات المذكورة صراحة في السياق. JSON: "
            '{"characters":[{"name":"...","period":"...","summary":"...",'
            '"key_events":["..."],"who_am_i_clues":["...","...","..."]}]}. '
            "إذا لم توجد شخصية صريحة أعد قائمة فارغة. لا تستنتج شخصية غير مذكورة."
        ),
    )
    characters = payload.get("characters", [])
    if not isinstance(characters, list):
        raise RuntimeError("صيغة الشخصيات المقترحة غير صالحة.")
    citations = list(dict.fromkeys(result["citation"] for result in results))[:5]
    return characters, citations
