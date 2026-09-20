import requests
from flask import current_app

from alrayyan.services.semantic_search import semantic_search


SYSTEM_PROMPT = """
أنت المعلّم الذكي في منصة الريان للدراسات التاريخية.

مهمتك مساعدة طلبة الصف الحادي عشر على فهم منهج الدراسات التاريخية.

قواعد الإجابة:
1. اعتمد فقط على السياق المرسل من المنهج.
2. لا تخترع معلومات غير موجودة في السياق.
3. اشرح بالعربية الواضحة والمبسطة.
4. ابدأ بإجابة مباشرة ثم أضف التوضيح عند الحاجة.
5. لا تذكر أنك نموذج ذكاء اصطناعي.
6. إذا لم تكفِ المصادر، قل بوضوح:
   "لا أجد معلومات كافية للإجابة عن هذا السؤال ضمن المصادر المتاحة."
7. عند وجود اختلاف، أعطِ الأولوية لملزمة الريان، ثم الكتاب الرسمي.
8. لا تنشئ مصادر أو أرقام صفحات غير موجودة.
"""


def build_context(search_results):
    """
    Convert semantic-search results into curriculum context
    that can be read by the language model.
    """
    sections = []

    for index, result in enumerate(search_results, start=1):
        source_name = result["source_title"]
        page_number = result.get("page_number")
        lesson_title = result.get("lesson_title")

        metadata = [
            f"المصدر: {source_name}",
        ]

        if lesson_title:
            metadata.append(f"الدرس: {lesson_title}")

        if page_number is not None:
            metadata.append(f"الصفحة: {page_number}")

        sections.append(
            f"""
المقطع رقم {index}
{" | ".join(metadata)}
النص:
{result["text"]}
""".strip()
        )

    return "\n\n---\n\n".join(sections)


def prepare_sources(search_results):
    """
    Return unique sources for display in the interface.
    """
    sources = []
    seen = set()

    for result in search_results:
        key = (
            result["source_id"],
            result.get("page_number"),
            result.get("lesson_id"),
        )

        if key in seen:
            continue

        seen.add(key)

        sources.append(
            {
                "title": result["source_title"],
                "page_number": result.get("page_number"),
                "lesson_title": result.get("lesson_title"),
                "is_primary": result.get("is_primary", False),
                "similarity": round(
                    result["similarity"],
                    4,
                ),
            }
        )

    return sources


def ask_ai_teacher(question):
    """
    Search the active curriculum and generate a grounded answer.
    """
    question = (question or "").strip()

    if not question:
        raise ValueError("يرجى كتابة سؤال أولًا.")

    if len(question) > 1000:
        raise ValueError("السؤال طويل جدًا. يرجى اختصاره.")

    search_results = semantic_search(
        query=question,
        top_k=5,
        min_similarity=0.20,
    )

    if not search_results:
        return {
            "answer": (
                "لا أجد معلومات كافية للإجابة عن هذا السؤال "
                "ضمن المصادر المتاحة."
            ),
            "sources": [],
            "grounded": False,
        }

    context = build_context(search_results)

    api_key = current_app.config.get(
        "OPENROUTER_API_KEY"
    )

    model = current_app.config.get(
        "OPENROUTER_MODEL",
        "openai/gpt-4o-mini",
    )

    if not api_key:
        raise RuntimeError(
            "مفتاح OPENROUTER_API_KEY غير موجود."
        )

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.2,
            "max_tokens": 700,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"سؤال الطالب:\n{question}\n\n"
                        f"السياق المستخرج من المنهج:\n{context}\n\n"
                        "أجب عن السؤال اعتمادًا على السياق فقط."
                    ),
                },
            ],
        },
        timeout=60,
    )

    try:
        response_data = response.json()
    except ValueError as error:
        raise RuntimeError(
            "وصل رد غير صالح من خدمة الذكاء الاصطناعي."
        ) from error

    if not response.ok:
        error_message = (
            response_data.get("error", {}).get("message")
            or "فشل الاتصال بخدمة الذكاء الاصطناعي."
        )
        raise RuntimeError(error_message)

    try:
        answer = response_data[
            "choices"
        ][0]["message"]["content"].strip()
    except (
        KeyError,
        IndexError,
        TypeError,
        AttributeError,
    ) as error:
        raise RuntimeError(
            "لم تصل إجابة صحيحة من الموديل."
        ) from error

    return {
        "answer": answer,
        "sources": prepare_sources(search_results),
        "grounded": True,
        "model": model,
    }