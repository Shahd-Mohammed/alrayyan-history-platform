import json
import re

import requests
from flask import current_app

from alrayyan.services.semantic_search import semantic_search


PROMPT_VERSION = "challenge-v1"

DIFFICULTY_GUIDANCE = {
    "beginner": "سؤال مباشر يعتمد على حقيقة واضحة واحدة.",
    "medium": "سؤال فهم يربط سببًا بنتيجة مع خيارات متقاربة.",
    "advanced": "سؤال تحليل أو مقارنة، دون معلومة خارج السياق.",
}

SYSTEM_PROMPT = """
أنت مصمم أسئلة تعليمي لمنصة الريان.
أنشئ سؤال اختيار من متعدد باللغة العربية اعتمادًا فقط على السياق.
لا تستخدم أي معلومة من خارج السياق.
أعد JSON صالحًا فقط بلا Markdown وبالحقول التالية:
question_text: string
options: array of exactly 4 strings
correct_option_index: integer from 0 to 3
explanation: short Arabic explanation
hint_one: general hint that does not reveal the answer
hint_two: more specific hint that still does not reveal the answer directly
concept: short Arabic concept name
source_chunk_ids: array containing only chunk IDs supplied in the context
اجعل الخيارات منطقية، ولا تستخدم "جميع ما سبق".
""".strip()


def _extract_json(text):
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _validate_payload(payload, allowed_chunk_ids):
    required = {
        "question_text",
        "options",
        "correct_option_index",
        "explanation",
        "hint_one",
        "hint_two",
        "concept",
        "source_chunk_ids",
    }
    if not required.issubset(payload):
        raise RuntimeError("رد مولد التحدي لا يحتوي جميع الحقول.")

    options = payload["options"]
    if not isinstance(options, list) or len(options) != 4:
        raise RuntimeError("يجب أن يحتوي السؤال أربعة خيارات.")

    correct_index = payload["correct_option_index"]
    if not isinstance(correct_index, int) or correct_index not in range(4):
        raise RuntimeError("فهرس الإجابة الصحيحة غير صالح.")

    valid_sources = []
    for raw_chunk_id in payload.get("source_chunk_ids", []):
        try:
            chunk_id = int(raw_chunk_id)
        except (TypeError, ValueError):
            continue

        if chunk_id in allowed_chunk_ids and chunk_id not in valid_sources:
            valid_sources.append(chunk_id)

    if not valid_sources:
        valid_sources = list(allowed_chunk_ids)[:2]

    payload["source_chunk_ids"] = valid_sources
    return payload


def generate_challenge_question(lesson, concept, difficulty):
    search_query = " ".join(
        part
        for part in [lesson.title, concept, "سؤال تعليمي"]
        if part
    )
    results = semantic_search(
        search_query,
        top_k=6,
        min_similarity=0.15,
        lesson_id=lesson.id,
    )
    if not results:
        raise RuntimeError("لا توجد مقاطع كافية لإنشاء سؤال لهذا الدرس.")

    context_sections = []
    for result in results:
        context_sections.append(
            f"CHUNK_ID: {result['chunk_id']}\n{result['text']}"
        )
    context = "\n\n---\n\n".join(context_sections)

    api_key = current_app.config.get("OPENROUTER_API_KEY")
    model = current_app.config.get(
        "OPENROUTER_MODEL", "openai/gpt-4o-mini"
    )
    if not api_key:
        raise RuntimeError("مفتاح خدمة الذكاء الاصطناعي غير مضبوط.")

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.25,
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"الدرس: {lesson.title}\n"
                        f"المفهوم: {concept or 'عام من الدرس'}\n"
                        f"المستوى: {difficulty}\n"
                        f"قاعدة الصعوبة: {DIFFICULTY_GUIDANCE[difficulty]}\n\n"
                        f"السياق:\n{context}"
                    ),
                },
            ],
        },
        timeout=60,
    )

    try:
        response_data = response.json()
    except ValueError as error:
        raise RuntimeError("وصل رد غير صالح من مزود الذكاء الاصطناعي.") from error

    if not response.ok:
        current_app.logger.error(
            "Challenge generation failed (%s): %s",
            response.status_code,
            response_data,
        )
        raise RuntimeError(
            "تعذر توليد سؤال التحدي الآن. حاولي مرة أخرى بعد قليل."
        )

    try:
        raw_content = response_data["choices"][0]["message"]["content"]
        payload = _extract_json(raw_content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("لم يرجع النموذج سؤالًا منظمًا صالحًا.") from error

    allowed = {result["chunk_id"] for result in results}
    payload = _validate_payload(payload, allowed)
    payload["model"] = model
    payload["prompt_version"] = PROMPT_VERSION
    return payload
