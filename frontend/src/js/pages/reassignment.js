function initReassignmentHierarchy() {
  const hierarchy = document.querySelector("[data-reassignment-hierarchy]");
  if (!hierarchy) return;

  hierarchy.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-reassignment-toggle]");
    if (!toggle || !hierarchy.contains(toggle)) return;

    const group = toggle.closest("[data-reassignment-group]");
    if (!group) return;

    const isCollapsed = group.classList.toggle("is-collapsed");
    toggle.setAttribute("aria-expanded", String(!isCollapsed));

    const icon = toggle.querySelector(".reassignment-toggle-icon");
    if (icon) {
      icon.textContent = isCollapsed ? "+" : "-";
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initReassignmentHierarchy();
});
