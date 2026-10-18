(() => {
  "use strict";

  for (const form of document.querySelectorAll("form")) {
    const status = form.querySelector(".preview-form-status");
    const showPreviewResult = () => {
      if (!form.reportValidity()) return;
      status.textContent = "Preview — not submitted. No information was sent.";
      status.focus();
    };

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      showPreviewResult();
    });
    form.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && event.target.tagName === "INPUT") {
        event.preventDefault();
        showPreviewResult();
      }
    });
    form.querySelector(".preview-form-button").addEventListener("click", showPreviewResult);
  }
})();
