const app = document.getElementById("challenge-app");

if (app) {
    const options = [...document.querySelectorAll(".challenge-option")];
    const hintButton = document.getElementById("hint-button");
    const hintBox = document.getElementById("hint-box");
    const feedbackPanel = document.getElementById("feedback-panel");
    const csrfToken = app.dataset.csrfToken;
    let submitting = false;

    async function postJson(url, body = {}) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || "تعذر تنفيذ الطلب.");
        }
        return data;
    }

    function lockOptions() {
        options.forEach((option) => {
            option.disabled = true;
        });
        hintButton.disabled = true;
    }

    function renderSources(sources) {
        const container = document.getElementById("source-list");
        container.innerHTML = "";
        if (!sources.length) return;

        const title = document.createElement("strong");
        title.textContent = "المصادر المستخدمة";
        container.appendChild(title);

        sources.forEach((source) => {
            const item = document.createElement("p");
            let text = source.title;
            if (source.lesson_title) text += ` — ${source.lesson_title}`;
            if (source.page_number !== null) text += ` — صفحة ${source.page_number}`;
            if (source.is_primary) text += " — المصدر الأساسي";
            item.textContent = text;
            container.appendChild(item);
        });
    }

    async function submitAnswer(option) {
        if (submitting) return;
        submitting = true;
        lockOptions();
        option.classList.add("selected");

        try {
            const selectedIndex = Number(option.dataset.optionIndex);
            const data = await postJson(app.dataset.answerUrl, {
                selected_option_index: selectedIndex
            });

            options.forEach((item) => {
                const index = Number(item.dataset.optionIndex);
                if (index === data.correct_option_index) {
                    item.classList.add("correct");
                } else if (index === selectedIndex) {
                    item.classList.add("incorrect");
                }
            });

            document.getElementById("feedback-title").textContent =
                data.correct ? "إجابة صحيحة ✦" : "لنحوّل الخطأ إلى معرفة";
            document.getElementById("feedback-text").textContent = data.feedback;
            document.getElementById("score-reward").textContent = `+${data.score_awarded} نقطة`;
            document.getElementById("xp-reward").textContent = `+${data.xp_awarded + data.completion_xp} XP`;
            document.getElementById("combo-reward").textContent = `Combo ×${data.combo}`;
            document.getElementById("hud-score").textContent = data.score;
            document.getElementById("hud-xp").textContent = data.xp_total;
            document.getElementById("hud-combo").textContent = `×${data.combo}`;
            document.getElementById("next-round-link").href = data.next_url;
            document.getElementById("next-round-link").textContent =
                data.completed ? "شاهد النتيجة ←" : "الجولة التالية ←";
            renderSources(data.sources || []);
            feedbackPanel.hidden = false;
            feedbackPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } catch (error) {
            submitting = false;
            options.forEach((item) => { item.disabled = false; });
            hintButton.disabled = false;
            window.alert(error.message);
        }
    }

    options.forEach((option) => {
        option.addEventListener("click", () => submitAnswer(option));
    });

    hintButton.addEventListener("click", async () => {
        if (submitting) return;
        hintButton.disabled = true;
        try {
            const data = await postJson(app.dataset.hintUrl);
            hintBox.textContent = data.hint;
            hintBox.hidden = false;
            hintButton.textContent =
                data.hints_used >= 2 ? "تم استخدام التلميحين" : "💡 تلميح أقوى";
            hintButton.disabled = data.hints_used >= 2;
        } catch (error) {
            hintButton.disabled = false;
            window.alert(error.message);
        }
    });
}
