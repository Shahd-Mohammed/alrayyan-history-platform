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
                        "لا تخترع أسماء أو صفحات أو حقائق. اجعل المخرجات مستندة إلى السياق، وميّز بين مسودات المعلمة وبطاقات المراجعة الذاتية التي ينشئها الطالب."
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


def generate_historical_date_drafts(lesson):
    """Create student-facing date-recall cards grounded only in the selected lesson."""
    payload, results = _grounded_request(
        lesson,
        (
            "أنشئ بطاقات مراجعة للتلميذ من التواريخ والأحداث المذكورة صراحة في سياق الدرس فقط. "
            "لا تخترع تاريخًا أو حدثًا، ولا تستنتج سنة غير مذكورة. "
            "أعد JSON فقط بالشكل: "
            '{"dates":[{"date_label":"التاريخ كما ورد","sort_year":1948,'
            '"event_title":"اسم الحدث","event_description":"شرح قصير من السياق",'
            '"memory_hint":"تلميح قصير لا يكشف الإجابة"}]}. '
            "أنشئ من 3 إلى 6 بطاقات إن كان السياق يدعمها، وإلا أعد البطاقات المتاحة فقط. "
            "إذا لم يرد أي تاريخ أو سنة صريحة فأعد قائمة فارغة. "
            "استخدم أرقامًا صحيحة في sort_year أو null عند عدم توفر سنة رقمية."
        ),
    )
    items = payload.get("dates", [])
    if not isinstance(items, list):
        raise RuntimeError("صيغة بطاقات التواريخ غير صالحة.")
    cleaned = []
    seen = set()
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        date_label = str(item.get("date_label") or "").strip()[:100]
        event_title = str(item.get("event_title") or "").strip()[:250]
        if not date_label or not event_title:
            continue
        key = (date_label.casefold(), event_title.casefold())
        if key in seen:
            continue
        seen.add(key)
        try:
            sort_year = int(item.get("sort_year")) if item.get("sort_year") is not None else None
        except (TypeError, ValueError):
            sort_year = None
        cleaned.append({
            "date_label": date_label,
            "sort_year": sort_year,
            "event_title": event_title,
            "event_description": str(item.get("event_description") or "").strip()[:2000] or None,
            "memory_hint": str(item.get("memory_hint") or "").strip()[:500] or None,
        })
    if not cleaned:
        raise RuntimeError("لم يعثر الدرس على تواريخ وأحداث صريحة كافية لصنع بطاقات مراجعة.")
    return cleaned
