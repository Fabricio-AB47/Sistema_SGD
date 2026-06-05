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

function initElementoOrderDefaults() {
  const mapNode = document.getElementById("element-order-map");
  const indicatorSelect = document.getElementById("id_indicador");
  const orderInput = document.getElementById("id_orden_visual");
  if (!mapNode || !indicatorSelect || !orderInput) return;

  let orderMap = {};
  try {
    orderMap = JSON.parse(mapNode.textContent || "{}");
  } catch (_error) {
    orderMap = {};
  }

  let orderTouched = false;
  orderInput.addEventListener("input", () => {
    orderTouched = true;
  });

  const applyDefaultOrder = (force = false) => {
    const nextOrder = orderMap[String(indicatorSelect.value)];
    if (!nextOrder) return;
    if (force || !orderInput.value || !orderTouched) {
      orderInput.value = nextOrder;
      orderTouched = false;
    }
  };

  indicatorSelect.addEventListener("change", () => {
    applyDefaultOrder(true);
  });

  applyDefaultOrder(false);
}

document.addEventListener("DOMContentLoaded", () => {
  initElementoOrderDefaults();
});

function initMatrixRegistryUploadModal() {
  const modal = document.getElementById("registro-evidencia-modal");
  if (!modal) return;

  const closeUrl = modal.dataset.closeUrl || window.location.pathname;
  const closeModal = (event) => {
    if (event) event.preventDefault();
    window.location.assign(closeUrl);
  };

  modal.addEventListener("click", (event) => {
    if (event.target.closest(".acreditacion-info-dialog")) return;
    closeModal(event);
  });

  modal.querySelectorAll("[data-registro-upload-close]").forEach((trigger) => {
    trigger.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal(event);
    }
  });
}

function initAcreditacionProgressBars() {
  document.querySelectorAll("[data-acreditacion-progress-value]").forEach((bar) => {
    const rawValue = Number.parseFloat(bar.dataset.acreditacionProgressValue || "0");
    const safeValue = Number.isFinite(rawValue) ? Math.max(0, Math.min(rawValue, 100)) : 0;
    bar.style.width = `${safeValue}%`;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initMatrixRegistryUploadModal();
  initAcreditacionProgressBars();
});

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

// Comportamientos de la vista de usuarios.
// Sin dependencias externas, solo helpers livianos.

// Helper para delegar eventos
function on(event, selector, handler) {
  document.addEventListener(event, (e) => {
    if (e.target.closest(selector)) handler(e);
  });
}

// Confirmación para activar/desactivar usuarios
on("click", "[data-toggle-estado]", (e) => {
  const btn = e.target.closest("[data-toggle-estado]");
  const nombre = btn.dataset.nombre || "el usuario";
  const accion = btn.dataset.activo === "true" ? "desactivar" : "activar";
  const ok = confirm(`¿Seguro que deseas ${accion} a ${nombre}?`);
  if (!ok) e.preventDefault();
});

// Envío de filtros (opcionalmente al presionar Enter)
on("keypress", ".filters input", (e) => {
  if (e.key === "Enter") {
    e.target.form?.submit();
  }
});

// Inicialización básica de modales (si existen elementos con data-modal)
on("click", "[data-modal-open]", (e) => {
  const targetId = e.target.closest("[data-modal-open]").dataset.modalOpen;
  const modal = document.getElementById(targetId);
  if (modal) {
    modal.removeAttribute("hidden");
    modal.classList.add("is-open");
  }
});

on("click", "[data-modal-close]", (e) => {
  const modal = e.target.closest("[data-modal]");
  if (modal) {
    modal.classList.remove("is-open");
    modal.setAttribute("hidden", "hidden");
  }
});

// Cerrar modal al hacer click en backdrop
on("click", "[data-modal]", (e) => {
  if (e.target === e.currentTarget) {
    e.target.classList.remove("is-open");
    e.target.setAttribute("hidden", "hidden");
  }
});
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbIm1haW4uanMiLCJwYWdlcy9hY3JlZGl0YWNpb24tZWxlbWVudHMuanMiLCJwYWdlcy9tYXRyaXgtcmVnaXN0cnkuanMiLCJwYWdlcy9yZWFzc2lnbm1lbnQuanMiLCJwYWdlcy91c3Vhcmlvcy5qcyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FDbEZBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUNyQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FDdENBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FDeEJBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBIiwiZmlsZSI6ImFwcC5qcyIsInNvdXJjZXNDb250ZW50IjpbIi8vIEhlbHBlciBzaW1wbGUgcGFyYSBkZWxlZ2FyIGV2ZW50b3NcclxuZnVuY3Rpb24gb24oZXZlbnQsIHNlbGVjdG9yLCBoYW5kbGVyKSB7XHJcbiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihldmVudCwgKGUpID0+IHtcclxuICAgIGlmIChlLnRhcmdldC5jbG9zZXN0KHNlbGVjdG9yKSkgaGFuZGxlcihlKTtcclxuICB9KTtcclxufVxyXG5cclxuLy8gRWplbXBsbzogdG9nZ2xlIGRlIHNpZGViYXIgZW4gbW9iaWxlXHJcbm9uKFwiY2xpY2tcIiwgXCJbZGF0YS10b2dnbGUtc2lkZWJhcl1cIiwgKCkgPT4ge1xyXG4gIGRvY3VtZW50LmJvZHkuY2xhc3NMaXN0LnRvZ2dsZShcInNpZGViYXItb3BlblwiKTtcclxufSk7XHJcblxyXG5mdW5jdGlvbiBpbml0U2lkZWJhckdyb3VwcygpIHtcclxuICBjb25zdCBncm91cHMgPSBBcnJheS5mcm9tKGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoXCJbZGF0YS1zaWRlYmFyLWdyb3VwXVwiKSk7XHJcbiAgbGV0IGZpcnN0T3Blbkdyb3VwID0gbnVsbDtcclxuXHJcbiAgZ3JvdXBzLmZvckVhY2goKGdyb3VwKSA9PiB7XHJcbiAgICBjb25zdCB0b2dnbGUgPSBncm91cC5xdWVyeVNlbGVjdG9yKFwiW2RhdGEtc2lkZWJhci10b2dnbGVdXCIpO1xyXG4gICAgaWYgKCF0b2dnbGUpIHJldHVybjtcclxuXHJcbiAgICBpZiAoZ3JvdXAuY2xhc3NMaXN0LmNvbnRhaW5zKFwic2lkZWJhcl9fZ3JvdXAtLW9wZW5cIikpIHtcclxuICAgICAgaWYgKGZpcnN0T3Blbkdyb3VwKSB7XHJcbiAgICAgICAgZ3JvdXAuY2xhc3NMaXN0LnJlbW92ZShcInNpZGViYXJfX2dyb3VwLS1vcGVuXCIpO1xyXG4gICAgICAgIHRvZ2dsZS5zZXRBdHRyaWJ1dGUoXCJhcmlhLWV4cGFuZGVkXCIsIFwiZmFsc2VcIik7XHJcbiAgICAgIH0gZWxzZSB7XHJcbiAgICAgICAgZmlyc3RPcGVuR3JvdXAgPSBncm91cDtcclxuICAgICAgICB0b2dnbGUuc2V0QXR0cmlidXRlKFwiYXJpYS1leHBhbmRlZFwiLCBcInRydWVcIik7XHJcbiAgICAgIH1cclxuICAgIH0gZWxzZSB7XHJcbiAgICAgIHRvZ2dsZS5zZXRBdHRyaWJ1dGUoXCJhcmlhLWV4cGFuZGVkXCIsIFwiZmFsc2VcIik7XHJcbiAgICB9XHJcblxyXG4gICAgdG9nZ2xlLmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCAoKSA9PiB7XHJcbiAgICAgIGNvbnN0IGlzT3BlbiA9IGdyb3VwLmNsYXNzTGlzdC5jb250YWlucyhcInNpZGViYXJfX2dyb3VwLS1vcGVuXCIpO1xyXG5cclxuICAgICAgZ3JvdXBzLmZvckVhY2goKGl0ZW0pID0+IHtcclxuICAgICAgICBpdGVtLmNsYXNzTGlzdC5yZW1vdmUoXCJzaWRlYmFyX19ncm91cC0tb3BlblwiKTtcclxuICAgICAgICBjb25zdCBpdGVtVG9nZ2xlID0gaXRlbS5xdWVyeVNlbGVjdG9yKFwiW2RhdGEtc2lkZWJhci10b2dnbGVdXCIpO1xyXG4gICAgICAgIGlmIChpdGVtVG9nZ2xlKSBpdGVtVG9nZ2xlLnNldEF0dHJpYnV0ZShcImFyaWEtZXhwYW5kZWRcIiwgXCJmYWxzZVwiKTtcclxuICAgICAgfSk7XHJcblxyXG4gICAgICBpZiAoIWlzT3Blbikge1xyXG4gICAgICAgIGdyb3VwLmNsYXNzTGlzdC5hZGQoXCJzaWRlYmFyX19ncm91cC0tb3BlblwiKTtcclxuICAgICAgICB0b2dnbGUuc2V0QXR0cmlidXRlKFwiYXJpYS1leHBhbmRlZFwiLCBcInRydWVcIik7XHJcbiAgICAgIH1cclxuICAgIH0pO1xyXG4gIH0pO1xyXG59XHJcblxyXG5mdW5jdGlvbiBpbml0Tm90aWZpY2F0aW9uc01lbnUoKSB7XHJcbiAgY29uc3QgbWVudSA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoXCJbZGF0YS1ub3RpZmljYXRpb25zLW1lbnVdXCIpO1xyXG4gIGlmICghbWVudSkgcmV0dXJuO1xyXG5cclxuICBjb25zdCB0b2dnbGUgPSBtZW51LnF1ZXJ5U2VsZWN0b3IoXCJbZGF0YS1ub3RpZmljYXRpb25zLXRvZ2dsZV1cIik7XHJcbiAgY29uc3QgcGFuZWwgPSBtZW51LnF1ZXJ5U2VsZWN0b3IoXCJbZGF0YS1ub3RpZmljYXRpb25zLXBhbmVsXVwiKTtcclxuICBpZiAoIXRvZ2dsZSB8fCAhcGFuZWwpIHJldHVybjtcclxuXHJcbiAgY29uc3QgY2xvc2UgPSAoKSA9PiB7XHJcbiAgICBwYW5lbC5oaWRkZW4gPSB0cnVlO1xyXG4gICAgdG9nZ2xlLnNldEF0dHJpYnV0ZShcImFyaWEtZXhwYW5kZWRcIiwgXCJmYWxzZVwiKTtcclxuICB9O1xyXG5cclxuICB0b2dnbGUuYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsICgpID0+IHtcclxuICAgIGNvbnN0IGlzT3BlbiA9ICFwYW5lbC5oaWRkZW47XHJcbiAgICBwYW5lbC5oaWRkZW4gPSBpc09wZW47XHJcbiAgICB0b2dnbGUuc2V0QXR0cmlidXRlKFwiYXJpYS1leHBhbmRlZFwiLCBTdHJpbmcoIWlzT3BlbikpO1xyXG4gIH0pO1xyXG5cclxuICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgKGV2ZW50KSA9PiB7XHJcbiAgICBpZiAoIW1lbnUuY29udGFpbnMoZXZlbnQudGFyZ2V0KSkgY2xvc2UoKTtcclxuICB9KTtcclxuXHJcbiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihcImtleWRvd25cIiwgKGV2ZW50KSA9PiB7XHJcbiAgICBpZiAoZXZlbnQua2V5ID09PSBcIkVzY2FwZVwiKSBjbG9zZSgpO1xyXG4gIH0pO1xyXG59XHJcblxyXG5kb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKFwiRE9NQ29udGVudExvYWRlZFwiLCAoKSA9PiB7XHJcbiAgaW5pdFNpZGViYXJHcm91cHMoKTtcclxuICBpbml0Tm90aWZpY2F0aW9uc01lbnUoKTtcclxuICBjb25zb2xlLmluZm8oXCJGcm9udGVuZCBTSUcgbGlzdG8gKFNDU1MgKyBKUyBjb21waWxhZG9zIGNvbiBHdWxwKS5cIik7XHJcbn0pO1xyXG4iLCJmdW5jdGlvbiBpbml0RWxlbWVudG9PcmRlckRlZmF1bHRzKCkge1xyXG4gIGNvbnN0IG1hcE5vZGUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChcImVsZW1lbnQtb3JkZXItbWFwXCIpO1xyXG4gIGNvbnN0IGluZGljYXRvclNlbGVjdCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiaWRfaW5kaWNhZG9yXCIpO1xyXG4gIGNvbnN0IG9yZGVySW5wdXQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChcImlkX29yZGVuX3Zpc3VhbFwiKTtcclxuICBpZiAoIW1hcE5vZGUgfHwgIWluZGljYXRvclNlbGVjdCB8fCAhb3JkZXJJbnB1dCkgcmV0dXJuO1xyXG5cclxuICBsZXQgb3JkZXJNYXAgPSB7fTtcclxuICB0cnkge1xyXG4gICAgb3JkZXJNYXAgPSBKU09OLnBhcnNlKG1hcE5vZGUudGV4dENvbnRlbnQgfHwgXCJ7fVwiKTtcclxuICB9IGNhdGNoIChfZXJyb3IpIHtcclxuICAgIG9yZGVyTWFwID0ge307XHJcbiAgfVxyXG5cclxuICBsZXQgb3JkZXJUb3VjaGVkID0gZmFsc2U7XHJcbiAgb3JkZXJJbnB1dC5hZGRFdmVudExpc3RlbmVyKFwiaW5wdXRcIiwgKCkgPT4ge1xyXG4gICAgb3JkZXJUb3VjaGVkID0gdHJ1ZTtcclxuICB9KTtcclxuXHJcbiAgY29uc3QgYXBwbHlEZWZhdWx0T3JkZXIgPSAoZm9yY2UgPSBmYWxzZSkgPT4ge1xyXG4gICAgY29uc3QgbmV4dE9yZGVyID0gb3JkZXJNYXBbU3RyaW5nKGluZGljYXRvclNlbGVjdC52YWx1ZSldO1xyXG4gICAgaWYgKCFuZXh0T3JkZXIpIHJldHVybjtcclxuICAgIGlmIChmb3JjZSB8fCAhb3JkZXJJbnB1dC52YWx1ZSB8fCAhb3JkZXJUb3VjaGVkKSB7XHJcbiAgICAgIG9yZGVySW5wdXQudmFsdWUgPSBuZXh0T3JkZXI7XHJcbiAgICAgIG9yZGVyVG91Y2hlZCA9IGZhbHNlO1xyXG4gICAgfVxyXG4gIH07XHJcblxyXG4gIGluZGljYXRvclNlbGVjdC5hZGRFdmVudExpc3RlbmVyKFwiY2hhbmdlXCIsICgpID0+IHtcclxuICAgIGFwcGx5RGVmYXVsdE9yZGVyKHRydWUpO1xyXG4gIH0pO1xyXG5cclxuICBhcHBseURlZmF1bHRPcmRlcihmYWxzZSk7XHJcbn1cclxuXHJcbmRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoXCJET01Db250ZW50TG9hZGVkXCIsICgpID0+IHtcclxuICBpbml0RWxlbWVudG9PcmRlckRlZmF1bHRzKCk7XHJcbn0pO1xyXG4iLCJmdW5jdGlvbiBpbml0TWF0cml4UmVnaXN0cnlVcGxvYWRNb2RhbCgpIHtcclxuICBjb25zdCBtb2RhbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwicmVnaXN0cm8tZXZpZGVuY2lhLW1vZGFsXCIpO1xyXG4gIGlmICghbW9kYWwpIHJldHVybjtcclxuXHJcbiAgY29uc3QgY2xvc2VVcmwgPSBtb2RhbC5kYXRhc2V0LmNsb3NlVXJsIHx8IHdpbmRvdy5sb2NhdGlvbi5wYXRobmFtZTtcclxuICBjb25zdCBjbG9zZU1vZGFsID0gKGV2ZW50KSA9PiB7XHJcbiAgICBpZiAoZXZlbnQpIGV2ZW50LnByZXZlbnREZWZhdWx0KCk7XHJcbiAgICB3aW5kb3cubG9jYXRpb24uYXNzaWduKGNsb3NlVXJsKTtcclxuICB9O1xyXG5cclxuICBtb2RhbC5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgKGV2ZW50KSA9PiB7XHJcbiAgICBpZiAoZXZlbnQudGFyZ2V0LmNsb3Nlc3QoXCIuYWNyZWRpdGFjaW9uLWluZm8tZGlhbG9nXCIpKSByZXR1cm47XHJcbiAgICBjbG9zZU1vZGFsKGV2ZW50KTtcclxuICB9KTtcclxuXHJcbiAgbW9kYWwucXVlcnlTZWxlY3RvckFsbChcIltkYXRhLXJlZ2lzdHJvLXVwbG9hZC1jbG9zZV1cIikuZm9yRWFjaCgodHJpZ2dlcikgPT4ge1xyXG4gICAgdHJpZ2dlci5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgY2xvc2VNb2RhbCk7XHJcbiAgfSk7XHJcblxyXG4gIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoXCJrZXlkb3duXCIsIChldmVudCkgPT4ge1xyXG4gICAgaWYgKGV2ZW50LmtleSA9PT0gXCJFc2NhcGVcIikge1xyXG4gICAgICBjbG9zZU1vZGFsKGV2ZW50KTtcclxuICAgIH1cclxuICB9KTtcclxufVxyXG5cclxuZnVuY3Rpb24gaW5pdEFjcmVkaXRhY2lvblByb2dyZXNzQmFycygpIHtcclxuICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKFwiW2RhdGEtYWNyZWRpdGFjaW9uLXByb2dyZXNzLXZhbHVlXVwiKS5mb3JFYWNoKChiYXIpID0+IHtcclxuICAgIGNvbnN0IHJhd1ZhbHVlID0gTnVtYmVyLnBhcnNlRmxvYXQoYmFyLmRhdGFzZXQuYWNyZWRpdGFjaW9uUHJvZ3Jlc3NWYWx1ZSB8fCBcIjBcIik7XHJcbiAgICBjb25zdCBzYWZlVmFsdWUgPSBOdW1iZXIuaXNGaW5pdGUocmF3VmFsdWUpID8gTWF0aC5tYXgoMCwgTWF0aC5taW4ocmF3VmFsdWUsIDEwMCkpIDogMDtcclxuICAgIGJhci5zdHlsZS53aWR0aCA9IGAke3NhZmVWYWx1ZX0lYDtcclxuICB9KTtcclxufVxyXG5cclxuZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihcIkRPTUNvbnRlbnRMb2FkZWRcIiwgKCkgPT4ge1xyXG4gIGluaXRNYXRyaXhSZWdpc3RyeVVwbG9hZE1vZGFsKCk7XHJcbiAgaW5pdEFjcmVkaXRhY2lvblByb2dyZXNzQmFycygpO1xyXG59KTtcclxuIiwiZnVuY3Rpb24gaW5pdFJlYXNzaWdubWVudEhpZXJhcmNoeSgpIHtcclxuICBjb25zdCBoaWVyYXJjaHkgPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKFwiW2RhdGEtcmVhc3NpZ25tZW50LWhpZXJhcmNoeV1cIik7XHJcbiAgaWYgKCFoaWVyYXJjaHkpIHJldHVybjtcclxuXHJcbiAgaGllcmFyY2h5LmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCAoZXZlbnQpID0+IHtcclxuICAgIGNvbnN0IHRvZ2dsZSA9IGV2ZW50LnRhcmdldC5jbG9zZXN0KFwiW2RhdGEtcmVhc3NpZ25tZW50LXRvZ2dsZV1cIik7XHJcbiAgICBpZiAoIXRvZ2dsZSB8fCAhaGllcmFyY2h5LmNvbnRhaW5zKHRvZ2dsZSkpIHJldHVybjtcclxuXHJcbiAgICBjb25zdCBncm91cCA9IHRvZ2dsZS5jbG9zZXN0KFwiW2RhdGEtcmVhc3NpZ25tZW50LWdyb3VwXVwiKTtcclxuICAgIGlmICghZ3JvdXApIHJldHVybjtcclxuXHJcbiAgICBjb25zdCBpc0NvbGxhcHNlZCA9IGdyb3VwLmNsYXNzTGlzdC50b2dnbGUoXCJpcy1jb2xsYXBzZWRcIik7XHJcbiAgICB0b2dnbGUuc2V0QXR0cmlidXRlKFwiYXJpYS1leHBhbmRlZFwiLCBTdHJpbmcoIWlzQ29sbGFwc2VkKSk7XHJcblxyXG4gICAgY29uc3QgaWNvbiA9IHRvZ2dsZS5xdWVyeVNlbGVjdG9yKFwiLnJlYXNzaWdubWVudC10b2dnbGUtaWNvblwiKTtcclxuICAgIGlmIChpY29uKSB7XHJcbiAgICAgIGljb24udGV4dENvbnRlbnQgPSBpc0NvbGxhcHNlZCA/IFwiK1wiIDogXCItXCI7XHJcbiAgICB9XHJcbiAgfSk7XHJcbn1cclxuXHJcbmRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoXCJET01Db250ZW50TG9hZGVkXCIsICgpID0+IHtcclxuICBpbml0UmVhc3NpZ25tZW50SGllcmFyY2h5KCk7XHJcbn0pO1xyXG4iLCIvLyBDb21wb3J0YW1pZW50b3MgZGUgbGEgdmlzdGEgZGUgdXN1YXJpb3MuXHJcbi8vIFNpbiBkZXBlbmRlbmNpYXMgZXh0ZXJuYXMsIHNvbG8gaGVscGVycyBsaXZpYW5vcy5cclxuXHJcbi8vIEhlbHBlciBwYXJhIGRlbGVnYXIgZXZlbnRvc1xyXG5mdW5jdGlvbiBvbihldmVudCwgc2VsZWN0b3IsIGhhbmRsZXIpIHtcclxuICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKGV2ZW50LCAoZSkgPT4ge1xyXG4gICAgaWYgKGUudGFyZ2V0LmNsb3Nlc3Qoc2VsZWN0b3IpKSBoYW5kbGVyKGUpO1xyXG4gIH0pO1xyXG59XHJcblxyXG4vLyBDb25maXJtYWNpw7NuIHBhcmEgYWN0aXZhci9kZXNhY3RpdmFyIHVzdWFyaW9zXHJcbm9uKFwiY2xpY2tcIiwgXCJbZGF0YS10b2dnbGUtZXN0YWRvXVwiLCAoZSkgPT4ge1xyXG4gIGNvbnN0IGJ0biA9IGUudGFyZ2V0LmNsb3Nlc3QoXCJbZGF0YS10b2dnbGUtZXN0YWRvXVwiKTtcclxuICBjb25zdCBub21icmUgPSBidG4uZGF0YXNldC5ub21icmUgfHwgXCJlbCB1c3VhcmlvXCI7XHJcbiAgY29uc3QgYWNjaW9uID0gYnRuLmRhdGFzZXQuYWN0aXZvID09PSBcInRydWVcIiA/IFwiZGVzYWN0aXZhclwiIDogXCJhY3RpdmFyXCI7XHJcbiAgY29uc3Qgb2sgPSBjb25maXJtKGDCv1NlZ3VybyBxdWUgZGVzZWFzICR7YWNjaW9ufSBhICR7bm9tYnJlfT9gKTtcclxuICBpZiAoIW9rKSBlLnByZXZlbnREZWZhdWx0KCk7XHJcbn0pO1xyXG5cclxuLy8gRW52w61vIGRlIGZpbHRyb3MgKG9wY2lvbmFsbWVudGUgYWwgcHJlc2lvbmFyIEVudGVyKVxyXG5vbihcImtleXByZXNzXCIsIFwiLmZpbHRlcnMgaW5wdXRcIiwgKGUpID0+IHtcclxuICBpZiAoZS5rZXkgPT09IFwiRW50ZXJcIikge1xyXG4gICAgZS50YXJnZXQuZm9ybT8uc3VibWl0KCk7XHJcbiAgfVxyXG59KTtcclxuXHJcbi8vIEluaWNpYWxpemFjacOzbiBiw6FzaWNhIGRlIG1vZGFsZXMgKHNpIGV4aXN0ZW4gZWxlbWVudG9zIGNvbiBkYXRhLW1vZGFsKVxyXG5vbihcImNsaWNrXCIsIFwiW2RhdGEtbW9kYWwtb3Blbl1cIiwgKGUpID0+IHtcclxuICBjb25zdCB0YXJnZXRJZCA9IGUudGFyZ2V0LmNsb3Nlc3QoXCJbZGF0YS1tb2RhbC1vcGVuXVwiKS5kYXRhc2V0Lm1vZGFsT3BlbjtcclxuICBjb25zdCBtb2RhbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHRhcmdldElkKTtcclxuICBpZiAobW9kYWwpIHtcclxuICAgIG1vZGFsLnJlbW92ZUF0dHJpYnV0ZShcImhpZGRlblwiKTtcclxuICAgIG1vZGFsLmNsYXNzTGlzdC5hZGQoXCJpcy1vcGVuXCIpO1xyXG4gIH1cclxufSk7XHJcblxyXG5vbihcImNsaWNrXCIsIFwiW2RhdGEtbW9kYWwtY2xvc2VdXCIsIChlKSA9PiB7XHJcbiAgY29uc3QgbW9kYWwgPSBlLnRhcmdldC5jbG9zZXN0KFwiW2RhdGEtbW9kYWxdXCIpO1xyXG4gIGlmIChtb2RhbCkge1xyXG4gICAgbW9kYWwuY2xhc3NMaXN0LnJlbW92ZShcImlzLW9wZW5cIik7XHJcbiAgICBtb2RhbC5zZXRBdHRyaWJ1dGUoXCJoaWRkZW5cIiwgXCJoaWRkZW5cIik7XHJcbiAgfVxyXG59KTtcclxuXHJcbi8vIENlcnJhciBtb2RhbCBhbCBoYWNlciBjbGljayBlbiBiYWNrZHJvcFxyXG5vbihcImNsaWNrXCIsIFwiW2RhdGEtbW9kYWxdXCIsIChlKSA9PiB7XHJcbiAgaWYgKGUudGFyZ2V0ID09PSBlLmN1cnJlbnRUYXJnZXQpIHtcclxuICAgIGUudGFyZ2V0LmNsYXNzTGlzdC5yZW1vdmUoXCJpcy1vcGVuXCIpO1xyXG4gICAgZS50YXJnZXQuc2V0QXR0cmlidXRlKFwiaGlkZGVuXCIsIFwiaGlkZGVuXCIpO1xyXG4gIH1cclxufSk7XHJcbiJdfQ==
