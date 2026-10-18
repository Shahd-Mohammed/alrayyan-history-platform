const tutorApp = document.getElementById("tutor-app");

if (tutorApp) {
    const form = document.getElementById("teacher-form");
    const input = document.getElementById("question-input");
    const sendButton = document.getElementById("send-button");
    const messages = document.getElementById("chat-messages");
    const typingIndicator = document.getElementById("typing-indicator");
    const lessonSelect = document.getElementById("lesson-select");
    const newButton = document.getElementById("new-conversation");
    const quizButton = document.getElementById("quick-quiz");
    const conversationList = document.getElementById("conversation-list");
    const conversationTitle = document.getElementById("conversation-title");
    const insight = document.getElementById("tutor-insight");
    const evaluationBadge = document.getElementById("evaluation-badge");
    const masteryBadge = document.getElementById("mastery-badge");
    const xpBadge = document.getElementById("xp-badge");
    const progressLink = document.getElementById("progress-link");
    const csrfToken = tutorApp.dataset.csrfToken;
    const initialConcept = tutorApp.dataset.initialConcept || "";
    const deleteUrlTemplate = tutorApp.dataset.deleteUrlTemplate;
    let conversationId = null;

    const evaluationLabels = {
        correct: "إجابة صحيحة",
        partially_correct: "إجابة صحيحة جزئيًا",
        incorrect: "تحتاج مراجعة",
        needs_explanation: "تحتاج شرحًا إضافيًا",
        off_topic: "خارج الموضوع",
        not_evaluated: "حوار تعليمي"
    };

    function endpoint(template, id) {
        return template.replace(/\/0(?=\/|$)/, `/${id}`);
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
                ...(options.headers || {})
            }
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || "تعذر تنفيذ الطلب.");
        }
        return data;
    }

    function scrollToLatest() {
        messages.scrollTop = messages.scrollHeight;
    }

    function createSourcesBox(sources) {
        const box = document.createElement("div");
        box.className = "sources-box";
        const heading = document.createElement("strong");
        heading.textContent = "المصادر المستخدمة";
        box.appendChild(heading);
        sources.forEach((source, index) => {
            const item = document.createElement("div");
            item.className = "source-item";
            let text = `${index + 1}. ${source.title}`;
            if (source.lesson_title) text += ` — ${source.lesson_title}`;
            if (source.page_number !== null) text += ` — صفحة ${source.page_number}`;
            if (source.is_primary) text += " — المصدر الأساسي";
            item.textContent = text;
            box.appendChild(item);
        });
        return box;
    }

    function createMessage(message) {
        const article = document.createElement("article");
        article.className = message.role === "student"
            ? "message user-message" : "message assistant-message";
        const avatar = document.createElement("div");
        avatar.className = "message-avatar";
        avatar.textContent = message.role === "student" ? "أنت" : "ر";
        const content = document.createElement("div");
        content.className = "message-content";
        const name = document.createElement("span");
        name.className = "message-name";
        name.textContent = message.role === "student" ? "أنت" : "معلّم الريان";
        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.textContent = message.content;
        content.append(name, bubble);
        if (message.sources && message.sources.length) {
            content.appendChild(createSourcesBox(message.sources));
        }
        article.append(avatar, content);
        messages.appendChild(article);
        scrollToLatest();
    }

    function renderMessages(items) {
        messages.innerHTML = "";
        items.forEach(createMessage);
        scrollToLatest();
    }

    function setLoading(loading) {
        sendButton.disabled = loading;
        input.disabled = loading;
        newButton.disabled = loading;
        typingIndicator.hidden = !loading;
        if (loading) scrollToLatest();
    }

    function showInsight(message, masteryScore, xpAwarded = 0, progressUpdated = false) {
        if (!message.evaluation || message.evaluation === "not_evaluated") {
            insight.hidden = true;
            return;
        }
        evaluationBadge.textContent = evaluationLabels[message.evaluation] || "تقييم جديد";
        const conceptName = (message.concept || "").trim();
        masteryBadge.textContent = masteryScore === null || masteryScore === undefined
            ? ""
            : conceptName
                ? `إتقان «${conceptName}»: ${masteryScore}%`
                : `إتقان المفهوم الحالي: ${masteryScore}%`;
        xpBadge.textContent = xpAwarded > 0
            ? `+${xpAwarded} XP`
            : progressUpdated
                ? "تحدّثت نسبة الإتقان؛ النقاط تُحسب بشكل منفصل"
                : "لم تتغير نسبة الإتقان";
        progressLink.hidden = !progressUpdated && xpAwarded <= 0;
        insight.hidden = false;
    }

    function addConversationButton(id, title) {
        // Resuming a saved review must not add a duplicate row to the history.
        if (conversationList.querySelector('[data-conversation-id="' + id + '"]')) {
            return;
        }
        const empty = document.getElementById("empty-history");
        if (empty) empty.remove();

        const item = document.createElement("div");
        item.className = "conversation-item";
        item.dataset.conversationItem = "";

        const openButton = document.createElement("button");
        openButton.type = "button";
        openButton.className = "conversation-open";
        openButton.dataset.conversationId = id;

        const bold = document.createElement("b");
        bold.textContent = title;
        const small = document.createElement("small");
        small.textContent = lessonSelect.options[lessonSelect.selectedIndex].text;
        openButton.append(bold, small);

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "conversation-delete";
        deleteButton.dataset.deleteConversationId = id;
        deleteButton.textContent = "حذف";
        deleteButton.title = "حذف المحادثة";
        deleteButton.setAttribute("aria-label", "حذف المحادثة " + title);

        item.append(openButton, deleteButton);
        conversationList.prepend(item);
    }

    async function deleteConversation(id, deleteButton) {
        if (!window.confirm("بدك تحذفي هاي المحادثة ورسائلها؟ ما رح يأثر الحذف على نقاطك أو محادثاتك الثانية.")) {
            return;
        }

        deleteButton.disabled = true;
        try {
            await requestJson(endpoint(deleteUrlTemplate, id), { method: "POST", body: "{}" });
            const item = deleteButton.closest("[data-conversation-item]");
            if (item) item.remove();

            if (Number(conversationId) === Number(id)) {
                conversationId = null;
                conversationTitle.textContent = "معلّم الريان";
                renderMessages([{
                    role: "tutor",
                    content: "انحذفت المحادثة 🌷 إذا حابة، نقدر نبدأ محادثة جديدة بأي درس تختاريه.",
                    sources: []
                }]);
                insight.hidden = true;
            }

            if (!conversationList.querySelector("[data-conversation-item]")) {
                const empty = document.createElement("p");
                empty.id = "empty-history";
                empty.textContent = "ما في محادثات سابقة لسه.";
                conversationList.appendChild(empty);
            }
        } catch (error) {
            window.alert(error.message);
            deleteButton.disabled = false;
        }
    }

    async function createConversation() {
        setLoading(true);
        try {
            const data = await requestJson(tutorApp.dataset.createUrl, {
                method: "POST",
                body: JSON.stringify({
                    lesson_id: lessonSelect.value,
                    concept: initialConcept,
                    difficulty: "adaptive"
                })
            });
            conversationId = data.conversation_id;
            conversationTitle.textContent = data.title;
            if (data.lesson_id) lessonSelect.value = String(data.lesson_id);
            renderMessages(data.messages);
            addConversationButton(data.conversation_id, data.title);
            insight.hidden = true;
            input.focus();
        } catch (error) {
            window.alert(error.message);
        } finally {
            setLoading(false);
        }
    }

    async function loadConversation(id) {
        setLoading(true);
        try {
            const data = await requestJson(
                endpoint(tutorApp.dataset.historyUrlTemplate, id)
            );
            conversationId = id;
            conversationTitle.textContent = data.title;
            if (data.lesson_id) lessonSelect.value = String(data.lesson_id);
            renderMessages(data.messages);
            insight.hidden = true;
        } catch (error) {
            window.alert(error.message);
        } finally {
            setLoading(false);
        }
    }

    async function sendMessage(text) {
        if (!conversationId) await createConversation();
        if (!conversationId) return;
        createMessage({ role: "student", content: text, sources: [] });
        setLoading(true);
        try {
            const data = await requestJson(
                endpoint(tutorApp.dataset.messageUrlTemplate, conversationId),
                { method: "POST", body: JSON.stringify({ message: text }) }
            );
            createMessage(data.message);
            showInsight(data.message, data.mastery_score, data.xp_awarded, data.progress_updated);
            if (data.suggest_quick_quiz) {
                quizButton.classList.add("recommended");
                quizButton.textContent = "اختبار سريع مقترح — 5 أسئلة";
            }
        } catch (error) {
            createMessage({
                role: "tutor",
                content: `عذرًا، ${error.message}`,
                sources: []
            });
        } finally {
            setLoading(false);
            input.focus();
        }
    }

    newButton.addEventListener("click", createConversation);
    conversationList.addEventListener("click", (event) => {
        const deleteButton = event.target.closest("[data-delete-conversation-id]");
        if (deleteButton) {
            event.preventDefault();
            event.stopPropagation();
            deleteConversation(Number(deleteButton.dataset.deleteConversationId), deleteButton);
            return;
        }

        const button = event.target.closest("[data-conversation-id]");
        if (button) loadConversation(Number(button.dataset.conversationId));
    });
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        input.value = "";
        await sendMessage(text);
    });
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    quizButton.addEventListener("click", async () => {
        quizButton.disabled = true;
        try {
            const data = await requestJson(tutorApp.dataset.quizUrl, {
                method: "POST",
                body: JSON.stringify({ lesson_id: lessonSelect.value })
            });
            window.location.href = data.url;
        } catch (error) {
            window.alert(error.message);
            quizButton.disabled = false;
        }
    });

    // A review link must open a lesson-bound conversation immediately.
    // Never create a generic conversation when the requested lesson is unavailable.
    if (tutorApp.dataset.reviewMode === "true" && lessonSelect.value) {
        createConversation();
    }
}
