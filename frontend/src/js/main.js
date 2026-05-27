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
  let firstOpenGroup = null;

  groups.forEach((group) => {
    const toggle = group.querySelector("[data-sidebar-toggle]");
    if (!toggle) return;

    if (group.classList.contains("sidebar__group--open")) {
      if (firstOpenGroup) {
        group.classList.remove("sidebar__group--open");
        toggle.setAttribute("aria-expanded", "false");
      } else {
        firstOpenGroup = group;
        toggle.setAttribute("aria-expanded", "true");
      }
    } else {
      toggle.setAttribute("aria-expanded", "false");
    }

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

function initNotificationsMenu() {
  const menu = document.querySelector("[data-notifications-menu]");
  if (!menu) return;

  const toggle = menu.querySelector("[data-notifications-toggle]");
  const panel = menu.querySelector("[data-notifications-panel]");
  if (!toggle || !panel) return;

  const close = () => {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  };

  toggle.addEventListener("click", () => {
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    toggle.setAttribute("aria-expanded", String(!isOpen));
  });

  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) close();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initSidebarGroups();
  initNotificationsMenu();
  console.info("Frontend SIG listo (SCSS + JS compilados con Gulp).");
});
