const testBank = document.getElementById("test-bank-app");

if (testBank) {
    const csrfToken = testBank.dataset.csrfToken;

    document.querySelectorAll(".quick-bank-quiz").forEach((button) => {
        button.addEventListener("click", async () => {
            button.disabled = true;
            const oldText = button.textContent;
            button.textContent = "جاري تجهيز الاختبار...";

            try {
                const response = await fetch(testBank.dataset.quizUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        lesson_id: button.dataset.lessonId
                    })
                });
                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.error || "تعذر بدء الاختبار.");
                }
                window.location.href = data.url;
            } catch (error) {
                window.alert(error.message);
                button.disabled = false;
                button.textContent = oldText;
            }
        });
    });
}
