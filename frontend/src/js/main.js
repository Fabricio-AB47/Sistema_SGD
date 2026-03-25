// Helper simple para delegar eventos
function on(event, selector, handler) {
  document.addEventListener(event, (e) => {
    if (e.target.closest(selector)) handler(e);
  });
}

// Ejemplo: toggle de sidebar en mobile
on("click", "[data-toggle-sidebar]", () => {
  document.body.classList.toggle("sidebar-open");
});

function initSidebarGroups() {
  const groups = Array.from(document.querySelectorAll("[data-sidebar-group]"));

  groups.forEach((group) => {
    const toggle = group.querySelector("[data-sidebar-toggle]");
    if (!toggle) return;

    toggle.addEventListener("click", () => {
      const isOpen = group.classList.contains("sidebar__group--open");

      groups.forEach((item) => {
        item.classList.remove("sidebar__group--open");
        const itemToggle = item.querySelector("[data-sidebar-toggle]");
        if (itemToggle) itemToggle.setAttribute("aria-expanded", "false");
      });

      if (!isOpen) {
        group.classList.add("sidebar__group--open");
        toggle.setAttribute("aria-expanded", "true");
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initSidebarGroups();
  console.info("Frontend SIG listo (SCSS + JS compilados con Gulp).");
});
