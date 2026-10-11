(() => {
  document.querySelectorAll('input[type="password"]').forEach((input) => {
    if (input.dataset.passwordToggleReady === "true") return;
    input.dataset.passwordToggleReady = "true";

    const wrapper = document.createElement("span");
    wrapper.className = "password-field-wrap";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "password-visibility-toggle";
    toggle.textContent = "إظهار";
    toggle.setAttribute("aria-label", "إظهار كلمة المرور");
    toggle.setAttribute("aria-pressed", "false");
    wrapper.appendChild(toggle);

    toggle.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.textContent = show ? "إخفاء" : "إظهار";
      toggle.setAttribute("aria-label", show ? "إخفاء كلمة المرور" : "إظهار كلمة المرور");
      toggle.setAttribute("aria-pressed", show ? "true" : "false");
      input.focus();
    });
  });
})();
