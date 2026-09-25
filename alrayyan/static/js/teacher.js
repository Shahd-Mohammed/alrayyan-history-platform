const form = document.getElementById("teacher-form");
const csrfToken = document.getElementById(
    "teacher-csrf-token"
).value;
const input = document.getElementById("question-input");
const sendButton = document.getElementById("send-button");
const messages = document.getElementById("chat-messages");
const typingIndicator = document.getElementById("typing-indicator");
const clearButton = document.getElementById("clear-chat");
const suggestionButtons = document.querySelectorAll(
    ".suggestion-button"
);

function scrollToLatestMessage() {
    messages.scrollTop = messages.scrollHeight;
}

function createMessage(role, text, sources = []) {
    const article = document.createElement("article");

    article.className =
        role === "user"
            ? "message user-message"
            : "message assistant-message";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "أنت" : "ر";

    const content = document.createElement("div");
    content.className = "message-content";

    const name = document.createElement("span");
    name.className = "message-name";
    name.textContent =
        role === "user"
            ? "أنت"
            : "معلّم الريان";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = text;

    content.appendChild(name);
    content.appendChild(bubble);

    if (sources.length > 0) {
        content.appendChild(createSourcesBox(sources));
    }

    article.appendChild(avatar);
    article.appendChild(content);

    messages.appendChild(article);
    scrollToLatestMessage();
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

        let sourceText =
            `${index + 1}. ${source.title}`;

        if (source.lesson_title) {
            sourceText +=
                ` — درس: ${source.lesson_title}`;
        }

        if (source.page_number !== null) {
            sourceText +=
                ` — صفحة ${source.page_number}`;
        }

        if (source.is_primary) {
            sourceText += " — المصدر الأساسي";
        }

        item.textContent = sourceText;
        box.appendChild(item);
    });

    return box;
}

function setLoading(isLoading) {
    sendButton.disabled = isLoading;
    input.disabled = isLoading;
    typingIndicator.hidden = !isLoading;

    if (isLoading) {
        scrollToLatestMessage();
    }
}

async function askTeacher(question) {
    createMessage("user", question);
    setLoading(true);

    try {
        const response = await fetch("/teacher/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            },
            body: JSON.stringify({
                question: question
            })
        });

        const contentType =
            response.headers.get("content-type") || "";

        if (!contentType.includes("application/json")) {
            throw new Error(
                `تعذّر الاتصال بالخادم (${response.status}).`
            );
        }

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(
                data.error ||
                "تعذّر الحصول على الإجابة."
            );
        }

        createMessage(
            "assistant",
            data.answer,
            data.sources || []
        );
    } catch (error) {
        createMessage(
            "assistant",
            `عذرًا، حدث خطأ: ${error.message}`
        );
    } finally {
        setLoading(false);
        input.focus();
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const question = input.value.trim();

    if (!question) {
        return;
    }

    input.value = "";
    await askTeacher(question);
});

input.addEventListener("keydown", (event) => {
    if (
        event.key === "Enter" &&
        !event.shiftKey
    ) {
        event.preventDefault();
        form.requestSubmit();
    }
});

suggestionButtons.forEach((button) => {
    button.addEventListener("click", () => {
        input.value = button.dataset.question;
        input.focus();
    });
});

clearButton.addEventListener("click", () => {
    messages.innerHTML = "";

    createMessage(
        "assistant",
        "بدأنا محادثة جديدة. ما الموضوع التاريخي الذي تريد فهمه؟"
    );

    input.value = "";
    input.focus();
});