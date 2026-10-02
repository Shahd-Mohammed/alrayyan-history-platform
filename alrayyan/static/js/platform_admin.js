document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-value], [data-copy-all]");
    if (!button) return;
    const value = button.hasAttribute("data-copy-all") ? document.getElementById("all-invite-links")?.value : button.dataset.copyValue;
    if (!value) return;
    try { await navigator.clipboard.writeText(value); const previous = button.textContent; button.textContent = "تم النسخ ✓"; window.setTimeout(() => { button.textContent = previous; }, 1600); }
    catch (_) { window.prompt("انسخي النص:", value); }
});
