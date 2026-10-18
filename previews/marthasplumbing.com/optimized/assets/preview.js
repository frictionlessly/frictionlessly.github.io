document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", (event) => event.preventDefault());
});

document.querySelectorAll('a[aria-disabled="true"]').forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const notice = document.getElementById("preview-unavailable");
    notice.closest("details").open = true;
    notice.focus();
  });
});

document.querySelectorAll(".preview-submenu-toggle").forEach((button) => {
  const group = document.getElementById(button.getAttribute("aria-controls"));
  const setExpanded = (expanded) => {
    button.setAttribute("aria-expanded", String(expanded));
    group.hidden = !expanded;
  };
  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") === "true";
    setExpanded(!expanded);
  });
  button.closest("li").addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setExpanded(false);
      button.focus();
    }
  });
  button.closest("li").addEventListener("focusout", (event) => {
    if (!button.closest("li").contains(event.relatedTarget)) setExpanded(false);
  });
});
