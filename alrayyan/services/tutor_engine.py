import json
import re

import requests
from flask import current_app

from alrayyan.services.ai_teacher import build_context, prepare_sources
from alrayyan.services.semantic_search import semantic_search


PROMPT_VERSION = "tutor-v8-strict-learning-evaluation"
VALID_ACTIONS = {
    "explain",
    "ask_diagnostic",
    "ask_follow_up",
    "give_hint",
    "simplify",
    "give_example",
    "review",
    "advance",
}
VALID_EVALUATIONS = {
    "not_evaluated",
    "correct",
    "partially_correct",
    "incorrect",
    "needs_explanation",
    "off_topic",
}
MASTERY_DELTAS = {
    "correct": 8,
    "partially_correct": 3,
    "incorrect": -6,
    "needs_explanation": -2,
    "off_topic": 0,
    "not_evaluated": 0,
}


NON_LEARNING_MESSAGE_PATTERNS = (
    r"^(?:هلا|أهلًا|اهلا|أهلا|مرحبا|السلام عليكم)\b",
    r"^(?:هههه+|ههه+|خخخ+|lol+)\b",
    r"بمزح معك|أنا بمزح|انا بمزح|كنت بمزح|جامد انت|جامد إنت",
    r"^(?:حبيبي(?:\s+انت|\s+إنت)?|حبيبتي(?:\s+انتي|\s+إنتِ)?|يا\s*خوي|يا\s*خيو|لا\s+عنجد|مش\s+غلط|عنجد|يسلمو|تسلم|تسلمي|تمام|خلص|طيب|حلو|منيح|ماشي|الله\s+يسعدك)[.!؟،\s]*$",
    r"بطلت اعرف اجاوب|بطلت أعرف أجاوب|بطلت الأجواء حلوة|بطلت الاجواء حلوة",
    r"راح تحفزني|تحكي كلام منيح|شجعيني|شجعني",
    r"على اي اساس|على أي أساس|إتقان المفهوم صار|اتقان المفهوم صار|نسبة الإتقان|نسبة الاتقان",
    r"ليش.*(?:اتقان|إتقان|نقاط|النسبة)|كيف.*(?:اتقان|إتقان|النسبة)",
    r"^(?:اممم\s*)?(?:اليوم\s+)?متحمسة(?:\s+يا عيني)?[.!؟،\s]*$",
    r"^(?:(?:يلا+|يلاا+)\s*)?(?:ابشر|أبشر|تمام|جاهزة|جاهزين|خلينا نبدأ|يلا نبدأ)[.!؟،\s]*$",
)


def is_non_learning_message(text):
    """Keep social chat and meta-feedback from changing mastery scores."""
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    return any(re.search(pattern, normalized) for pattern in NON_LEARNING_MESSAGE_PATTERNS)


SYSTEM_PROMPT = """
أنت معلّم الريان التفاعلي. هدفك الأساسي هو التعليم: الشرح، التدريب، قياس الفهم، والتشجيع، اعتمادًا فقط على سياق المنهج النشط المرسل.

قواعدك التربوية:
1. تذكّر سياق المحادثة القصير المرسل إليك.
2. إذا كانت الرسالة ردًا على سؤال تعليمي سابق، يجب تقييمها أولًا، ولا تستخدم not_evaluated.
3. لا تعطِ الحل الكامل دائمًا؛ استخدم سؤالًا سقراطيًا أو تلميحًا عندما يناسب.
4. بعد الشرح، اسأل سؤال تحقق قصيرًا عندما يكون ذلك مفيدًا لقياس الفهم، ولا تجعل كل رد ينتهي بسؤال.
5. إذا أخطأ الطالب، بسّط الفكرة ولا تُشعره بالإحراج.
6. إذا أتقن الفكرة، انتقل إلى سؤال أعمق أو مفهوم تالٍ.
7. لا تستخدم معلومة من خارج السياق ولا تخترع مصدرًا أو صفحة.
8. اجعل الرد مختصرًا وواضحًا ومناسبًا لطالب مدرسة، واكتب كمعلم قريب من طلابه لا كنشرة رسمية.
9. كن دافئًا، لطيفًا، مشجعًا، وخفيف الظل، لكن ابقَ معلمًا ومحور التفاعل هو التعلّم. يمكن استخدام تعبير فلسطيني خفيف مثل «يسعد قلبك»، «هيك ممتاز»، «يا سلام»، «قربتِ» أو «ولا يهمك» عندما يناسب السياق، دون مبالغة أو تكرار.
10. إذا مزح الطالب أو قال إنه مرتاح، ردّ بشكل طبيعي ومرح لفترة قصيرة، ثم اربط الجو بخطوة تعليمية خفيفة أو خيار تعليمي بسيط. لا تحوّل المعلم إلى صديق دردشة.
11. إذا اشتكى الطالب أو تحدث عن أمر شخصي، اعترف بذلك باختصار واحترام، ثم أعد توجيه التفاعل نحو التعلّم أو نشاط منخفض الضغط. لا تطلب منه شرح مشاعره أو مشاكله، ولا تتقمص دور المعالج أو المستشار النفسي.
12. إذا قال الطالب إنه لا يريد الدراسة الآن، لا تجبره على سؤال صعب؛ اعرض خيارًا تعليميًا خفيفًا مثل مراجعة سريعة، مثال بسيط، أو العودة لاحقًا.
13. لا تكثر من «حبيبتي» أو «قلبي» أو العبارات الحميمة. استخدم اسم الطالب أو تعبيرًا دافئًا عند الحاجة فقط.
14. نوّع التشجيع واجعله مرتبطًا بما فعله الطالب، ولا تمدح إجابة خاطئة كأنها صحيحة.
15. لا تبدأ كل رد بتحية رسمية، ولا تختم كل رد بسؤال دراسي. اجعل المحادثة طبيعية ومتنوعة مع بقاء التعليم هو المحور.
16. لا تقيّم التحية أو المزاح أو المجاملة أو الشكوى أو الحديث عن النقاط/نسبة الإتقان أو طلب التشجيع على أنها إجابة علمية.
17. لا تمنح أي زيادة أو نقصان في إتقان المفهوم إلا عندما تكون رسالة الطالب إجابة فعلية عن سؤال تعليمي واضح في الرسالة السابقة. إذا كانت دردشة أو تعليقًا جانبيًا، استخدم evaluation=not_evaluated وmastery_delta=0.
18. لا تستنتج أن الطالبة أتقنت مفهومًا من مجرد استمرار المحادثة أو من نبرة كلامها. التقييم مبني على مضمون الإجابة ومدى مطابقته للسياق التعليمي.
19. عند أول إجابة صحيحة عن سؤال تعليمي، اطرح سؤال تحقق قصيرًا ثانيًا من سياق الدرس. لا تعتبر المفهوم متقنًا ولا تمنح نقاطًا في هذه المرحلة؛ التحقق الناجح التالي هو الذي يثبت الفهم.

أعد JSON صالحًا فقط دون Markdown، بالحقول:
reply: رد المعلم بالعربية، ويمكن أن ينتهي بسؤال تفاعلي واحد
action: واحدة من explain, ask_diagnostic, ask_follow_up, give_hint,
        simplify, give_example, review, advance
evaluation: واحدة من not_evaluated, correct, partially_correct,
            incorrect, needs_explanation, off_topic
concept: اسم عربي قصير للمفهوم الجاري
mastery_delta: عدد صحيح بين -10 و10
source_chunk_ids: قائمة من أرقام المقاطع المرسلة فقط
suggest_quick_quiz: true أو false
""".strip()
def _extract_json(value):
    if isinstance(value, dict):
        return value

    if isinstance(value, list):
        value = "".join(
            str(item.get("text") or "")
            for item in value
            if isinstance(item, dict)
        )

    cleaned = str(value or "").strip().lstrip("\ufeff")
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace == -1 or last_brace <= first_brace:
            raise
        payload = json.loads(cleaned[first_brace:last_brace + 1])

    if not isinstance(payload, dict):
        raise TypeError("Tutor response must be a JSON object.")

    return payload


def _history_text(messages):
    rows = []
    for message in messages[-8:]:
        speaker = "الطالب" if message.role == "student" else "المعلم"
        rows.append(f"{speaker}: {message.content}")
    return "\n".join(rows) or "لا توجد رسائل سابقة."


def _validate_payload(payload, allowed_chunk_ids):
    reply = str(payload.get("reply") or "").strip()
    if not reply:
        raise RuntimeError("لم يُرجع المعلم ردًا صالحًا.")

    action = payload.get("action", "explain")
    if action not in VALID_ACTIONS:
        action = "explain"

    evaluation = payload.get("evaluation", "not_evaluated")
    if evaluation not in VALID_EVALUATIONS:
        evaluation = "not_evaluated"

    # Mastery changes are controlled by the application, not by arbitrary model output.
    # Social/off-topic messages can never change the score.
    mastery_delta = MASTERY_DELTAS.get(evaluation, 0)

    source_ids = []
    for raw_id in payload.get("source_chunk_ids", []):
        try:
            chunk_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if chunk_id in allowed_chunk_ids and chunk_id not in source_ids:
            source_ids.append(chunk_id)

    return {
        "reply": reply,
        "action": action,
        "evaluation": evaluation,
        "concept": str(payload.get("concept") or "المفهوم العام").strip()[:250],
        "mastery_delta": mastery_delta,
        "source_chunk_ids": source_ids,
        "suggest_quick_quiz": bool(payload.get("suggest_quick_quiz", False)),
    }


def tutor_reply(conversation, student_text):
    student_text = (student_text or "").strip()
    if not student_text:
        raise ValueError("اكتبي رسالة أولًا.")
    if len(student_text) > 1200:
        raise ValueError("الرسالة طويلة جدًا. اختصريها قليلًا.")

    # Keep greetings, jokes, encouragement requests, and score complaints
    # conversational without sending them through the learning evaluator.
    if is_non_learning_message(student_text):
        normalized = student_text.lower()
        if re.search(r"على اي اساس|على أي أساس|إتقان المفهوم صار|اتقان المفهوم صار|نسبة الإتقان|نسبة الاتقان|ليش.*(?:اتقان|إتقان|نقاط|النسبة)|كيف.*(?:اتقان|إتقان|النسبة)", normalized):
            reply = (
                "معك حق تسألي عن النسبة. إتقان المفهوم لازم يتغيّر بناءً على إجابة تعليمية واضحة "
                "وقابلة للتقييم، مش على المزاح أو الكلام عن النقاط. رح أتعامل مع رسالتك كتوضيح، "
                "من دون تعديل الإتقان أو إضافة نقاط."
            )
        elif re.search(r"راح تحفزني|تحكي كلام منيح|شجعيني|شجعني", normalized):
            reply = (
                "أكيد، لما تقدّمي إجابة صحيحة رح أشجّعك على الشيء اللي أتقنتيه فعلًا، "
                "وإذا احتجنا نراجع نقطة بنعملها بهدوء ومن غير مبالغة."
            )
        else:
            reply = (
                "هههه وصلت الفكرة 😄 خلّينا نخفف الرسمية شوي. لما تكوني جاهزة نرجع للدرس، "
                "بمشي معك خطوة خطوة وبشجّعك على إجاباتك الفعلية."
            )
        return {
            "reply": reply,
            "action": "review",
            "evaluation": "not_evaluated",
            "concept": conversation.current_concept or "المفهوم العام",
            "mastery_delta": 0,
            "source_chunk_ids": [],
            "sources": [],
            "suggest_quick_quiz": False,
            "model": None,
            "prompt_version": PROMPT_VERSION,
        }

    query_parts = [student_text]
    if conversation.current_concept:
        query_parts.append(conversation.current_concept)
    if conversation.lesson:
        query_parts.append(conversation.lesson.title)

    search_results = semantic_search(
        " ".join(query_parts),
        top_k=6,
        min_similarity=0.16,
        lesson_id=conversation.lesson_id,
    )

    if not search_results:
        return {
            "reply": (
                "لا أجد في المصادر المتاحة مقطعًا كافيًا لبناء شرح موثوق. "
                "جرّبي اختيار درس محدد أو إعادة صياغة السؤال."
            ),
            "action": "review",
            "evaluation": "not_evaluated",
            "concept": conversation.current_concept or "المفهوم العام",
            "mastery_delta": 0,
            "source_chunk_ids": [],
            "sources": [],
            "suggest_quick_quiz": False,
            "model": None,
            "prompt_version": PROMPT_VERSION,
        }

    context = build_context(search_results)
    history_messages = list(conversation.messages)
    if (
        history_messages
        and history_messages[-1].role == "student"
        and history_messages[-1].content == student_text
    ):
        history_messages = history_messages[:-1]
    history = _history_text(history_messages)
    previous_tutor_message = next(
        (
            message
            for message in reversed(history_messages)
            if message.role == "tutor"
        ),
        None,
    )
    topic_invitation = bool(
        previous_tutor_message
        and previous_tutor_message.action == "ask_diagnostic"
        and any(
            phrase in previous_tutor_message.content
            for phrase in (
                "شو حابة نفهم",
                "من وين بدك نبدأ",
                "احكيلي شو حابة",
                "بدك ندرس",
                "بدك نراجع",
            )
        )
    )
    evaluation_required = bool(
        previous_tutor_message
        and previous_tutor_message.action in {
            "ask_diagnostic",
            "ask_follow_up",
            "give_hint",
        }
        and not topic_invitation
        and (
            "؟" in previous_tutor_message.content
            or "?" in previous_tutor_message.content
        )
    )
    api_key = current_app.config.get("OPENROUTER_API_KEY")
    model = current_app.config.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    if not api_key:
        raise RuntimeError("خدمة المعلم الذكي غير مضبوطة حاليًا.")

    request_body = {
        "model": model,
        "temperature": 0.55,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"الدرس الحالي: {conversation.lesson.title if conversation.lesson else 'غير محدد'}\n"
                    f"اسم الطالب: {conversation.student.first_name}\n"
                    f"المفهوم الحالي: {conversation.current_concept or 'غير محدد'}\n"
                    f"حالة المعلم: {conversation.tutor_state}\n"
                    f"مستوى الصعوبة: {conversation.difficulty}\n\n"
                    f"هل يجب تقييم الرسالة الحالية؟ {'نعم' if evaluation_required else 'لا'}\n"
                    "إذا كانت الإجابة نعم، اختر correct أو partially_correct أو incorrect "
                    "أو needs_explanation، ولا تستخدم not_evaluated.\n\n"
                    f"المحادثة السابقة:\n{history}\n\n"
                    f"رسالة الطالب الجديدة:\n{student_text}\n\n"

                    f"سياق المنهج:\n{context}"
                ),
            },
        ],
    }

    allowed_ids = {item["chunk_id"] for item in search_results}
    payload = None
    last_format_error = None

    for generation_attempt in range(2):
        response = None

        for connection_attempt in range(2):
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                    timeout=60,
                )
                break
            except requests.RequestException as error:
                current_app.logger.warning(
                    "Tutor provider connection failed on attempt %s: %s",
                    connection_attempt + 1,
                    error,
                )
                if connection_attempt == 1:
                    raise RuntimeError(
                        "تعذر الاتصال بالمعلم الذكي الآن. حاولي مرة أخرى بعد قليل."
                    ) from error

        try:
            response_data = response.json()
        except ValueError as error:
            raise RuntimeError("وصل رد غير صالح من خدمة المعلم الذكي.") from error

        if not response.ok:
            current_app.logger.error(
                "Tutor request failed (%s): %s", response.status_code, response_data
            )
            raise RuntimeError("تعذر تجهيز الرد التعليمي الآن.")

        try:
            raw_content = response_data["choices"][0]["message"]["content"]
            raw_payload = _extract_json(raw_content)
            candidate_payload = _validate_payload(
                raw_payload,
                allowed_ids,
            )

            # Social chat and meta-feedback are not assessed answers.
            # Only score messages responding to an explicit learning question.
            if is_non_learning_message(student_text) or not evaluation_required:
                candidate_payload["evaluation"] = "not_evaluated"
                candidate_payload["mastery_delta"] = 0

            if (
                evaluation_required
                and not is_non_learning_message(student_text)
                and candidate_payload["evaluation"] == "not_evaluated"
                and generation_attempt == 0
            ):
                request_body["temperature"] = 0.1
                request_body["messages"].append({
                    "role": "user",
                    "content": (
                        "رسالة الطالب إجابة عن سؤال المعلم السابق. "
                        "أعد التقييم واختر تقييمًا تربويًا صريحًا غير not_evaluated."
                    ),
                })
                continue
            payload = candidate_payload
            break
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            last_format_error = error
            current_app.logger.warning(
                "Tutor returned malformed structured output on generation %s: %r",
                generation_attempt + 1,
                str(raw_content if "raw_content" in locals() else "")[:1000],
            )
            request_body["temperature"] = 0.1
            request_body["messages"].append({
                "role": "user",
                "content": (
                    "أعد الرد الآن ككائن JSON صالح فقط. "
                    "لا تضف Markdown أو أي نص قبل القوس { أو بعد القوس }."
                ),
            })

    if payload is None:
        raise RuntimeError(
            "لم يرجع المعلم ردًا تعليميًا منظمًا."
        ) from last_format_error
    payload["sources"] = prepare_sources(
        [
            item
            for item in search_results
            if item["chunk_id"] in payload["source_chunk_ids"]
        ]
    )
    payload["model"] = model
    payload["prompt_version"] = PROMPT_VERSION
    return payload
