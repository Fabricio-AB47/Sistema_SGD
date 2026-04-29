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
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbIm1haW4uanMiLCJwYWdlcy9hY3JlZGl0YWNpb24tZWxlbWVudHMuanMiLCJwYWdlcy9tYXRyaXgtcmVnaXN0cnkuanMiLCJwYWdlcy9yZWFzc2lnbm1lbnQuanMiLCJwYWdlcy91c3Vhcmlvcy5qcyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQ3JFQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FDckNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQ3RDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQ3hCQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQSIsImZpbGUiOiJhcHAuanMiLCJzb3VyY2VzQ29udGVudCI6WyIvLyBIZWxwZXIgc2ltcGxlIHBhcmEgZGVsZWdhciBldmVudG9zXG5mdW5jdGlvbiBvbihldmVudCwgc2VsZWN0b3IsIGhhbmRsZXIpIHtcbiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihldmVudCwgKGUpID0+IHtcbiAgICBpZiAoZS50YXJnZXQuY2xvc2VzdChzZWxlY3RvcikpIGhhbmRsZXIoZSk7XG4gIH0pO1xufVxuXG4vLyBFamVtcGxvOiB0b2dnbGUgZGUgc2lkZWJhciBlbiBtb2JpbGVcbm9uKFwiY2xpY2tcIiwgXCJbZGF0YS10b2dnbGUtc2lkZWJhcl1cIiwgKCkgPT4ge1xuICBkb2N1bWVudC5ib2R5LmNsYXNzTGlzdC50b2dnbGUoXCJzaWRlYmFyLW9wZW5cIik7XG59KTtcblxuZnVuY3Rpb24gaW5pdFNpZGViYXJHcm91cHMoKSB7XG4gIGNvbnN0IGdyb3VwcyA9IEFycmF5LmZyb20oZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbChcIltkYXRhLXNpZGViYXItZ3JvdXBdXCIpKTtcblxuICBncm91cHMuZm9yRWFjaCgoZ3JvdXApID0+IHtcbiAgICBjb25zdCB0b2dnbGUgPSBncm91cC5xdWVyeVNlbGVjdG9yKFwiW2RhdGEtc2lkZWJhci10b2dnbGVdXCIpO1xuICAgIGlmICghdG9nZ2xlKSByZXR1cm47XG5cbiAgICB0b2dnbGUuYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsICgpID0+IHtcbiAgICAgIGNvbnN0IGlzT3BlbiA9IGdyb3VwLmNsYXNzTGlzdC5jb250YWlucyhcInNpZGViYXJfX2dyb3VwLS1vcGVuXCIpO1xuXG4gICAgICBncm91cHMuZm9yRWFjaCgoaXRlbSkgPT4ge1xuICAgICAgICBpdGVtLmNsYXNzTGlzdC5yZW1vdmUoXCJzaWRlYmFyX19ncm91cC0tb3BlblwiKTtcbiAgICAgICAgY29uc3QgaXRlbVRvZ2dsZSA9IGl0ZW0ucXVlcnlTZWxlY3RvcihcIltkYXRhLXNpZGViYXItdG9nZ2xlXVwiKTtcbiAgICAgICAgaWYgKGl0ZW1Ub2dnbGUpIGl0ZW1Ub2dnbGUuc2V0QXR0cmlidXRlKFwiYXJpYS1leHBhbmRlZFwiLCBcImZhbHNlXCIpO1xuICAgICAgfSk7XG5cbiAgICAgIGlmICghaXNPcGVuKSB7XG4gICAgICAgIGdyb3VwLmNsYXNzTGlzdC5hZGQoXCJzaWRlYmFyX19ncm91cC0tb3BlblwiKTtcbiAgICAgICAgdG9nZ2xlLnNldEF0dHJpYnV0ZShcImFyaWEtZXhwYW5kZWRcIiwgXCJ0cnVlXCIpO1xuICAgICAgfVxuICAgIH0pO1xuICB9KTtcbn1cblxuZnVuY3Rpb24gaW5pdE5vdGlmaWNhdGlvbnNNZW51KCkge1xuICBjb25zdCBtZW51ID0gZG9jdW1lbnQucXVlcnlTZWxlY3RvcihcIltkYXRhLW5vdGlmaWNhdGlvbnMtbWVudV1cIik7XG4gIGlmICghbWVudSkgcmV0dXJuO1xuXG4gIGNvbnN0IHRvZ2dsZSA9IG1lbnUucXVlcnlTZWxlY3RvcihcIltkYXRhLW5vdGlmaWNhdGlvbnMtdG9nZ2xlXVwiKTtcbiAgY29uc3QgcGFuZWwgPSBtZW51LnF1ZXJ5U2VsZWN0b3IoXCJbZGF0YS1ub3RpZmljYXRpb25zLXBhbmVsXVwiKTtcbiAgaWYgKCF0b2dnbGUgfHwgIXBhbmVsKSByZXR1cm47XG5cbiAgY29uc3QgY2xvc2UgPSAoKSA9PiB7XG4gICAgcGFuZWwuaGlkZGVuID0gdHJ1ZTtcbiAgICB0b2dnbGUuc2V0QXR0cmlidXRlKFwiYXJpYS1leHBhbmRlZFwiLCBcImZhbHNlXCIpO1xuICB9O1xuXG4gIHRvZ2dsZS5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgKCkgPT4ge1xuICAgIGNvbnN0IGlzT3BlbiA9ICFwYW5lbC5oaWRkZW47XG4gICAgcGFuZWwuaGlkZGVuID0gaXNPcGVuO1xuICAgIHRvZ2dsZS5zZXRBdHRyaWJ1dGUoXCJhcmlhLWV4cGFuZGVkXCIsIFN0cmluZyghaXNPcGVuKSk7XG4gIH0pO1xuXG4gIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCAoZXZlbnQpID0+IHtcbiAgICBpZiAoIW1lbnUuY29udGFpbnMoZXZlbnQudGFyZ2V0KSkgY2xvc2UoKTtcbiAgfSk7XG5cbiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihcImtleWRvd25cIiwgKGV2ZW50KSA9PiB7XG4gICAgaWYgKGV2ZW50LmtleSA9PT0gXCJFc2NhcGVcIikgY2xvc2UoKTtcbiAgfSk7XG59XG5cbmRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoXCJET01Db250ZW50TG9hZGVkXCIsICgpID0+IHtcbiAgaW5pdFNpZGViYXJHcm91cHMoKTtcbiAgaW5pdE5vdGlmaWNhdGlvbnNNZW51KCk7XG4gIGNvbnNvbGUuaW5mbyhcIkZyb250ZW5kIFNJRyBsaXN0byAoU0NTUyArIEpTIGNvbXBpbGFkb3MgY29uIEd1bHApLlwiKTtcbn0pO1xuIiwiZnVuY3Rpb24gaW5pdEVsZW1lbnRvT3JkZXJEZWZhdWx0cygpIHtcbiAgY29uc3QgbWFwTm9kZSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiZWxlbWVudC1vcmRlci1tYXBcIik7XG4gIGNvbnN0IGluZGljYXRvclNlbGVjdCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiaWRfaW5kaWNhZG9yXCIpO1xuICBjb25zdCBvcmRlcklucHV0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJpZF9vcmRlbl92aXN1YWxcIik7XG4gIGlmICghbWFwTm9kZSB8fCAhaW5kaWNhdG9yU2VsZWN0IHx8ICFvcmRlcklucHV0KSByZXR1cm47XG5cbiAgbGV0IG9yZGVyTWFwID0ge307XG4gIHRyeSB7XG4gICAgb3JkZXJNYXAgPSBKU09OLnBhcnNlKG1hcE5vZGUudGV4dENvbnRlbnQgfHwgXCJ7fVwiKTtcbiAgfSBjYXRjaCAoX2Vycm9yKSB7XG4gICAgb3JkZXJNYXAgPSB7fTtcbiAgfVxuXG4gIGxldCBvcmRlclRvdWNoZWQgPSBmYWxzZTtcbiAgb3JkZXJJbnB1dC5hZGRFdmVudExpc3RlbmVyKFwiaW5wdXRcIiwgKCkgPT4ge1xuICAgIG9yZGVyVG91Y2hlZCA9IHRydWU7XG4gIH0pO1xuXG4gIGNvbnN0IGFwcGx5RGVmYXVsdE9yZGVyID0gKGZvcmNlID0gZmFsc2UpID0+IHtcbiAgICBjb25zdCBuZXh0T3JkZXIgPSBvcmRlck1hcFtTdHJpbmcoaW5kaWNhdG9yU2VsZWN0LnZhbHVlKV07XG4gICAgaWYgKCFuZXh0T3JkZXIpIHJldHVybjtcbiAgICBpZiAoZm9yY2UgfHwgIW9yZGVySW5wdXQudmFsdWUgfHwgIW9yZGVyVG91Y2hlZCkge1xuICAgICAgb3JkZXJJbnB1dC52YWx1ZSA9IG5leHRPcmRlcjtcbiAgICAgIG9yZGVyVG91Y2hlZCA9IGZhbHNlO1xuICAgIH1cbiAgfTtcblxuICBpbmRpY2F0b3JTZWxlY3QuYWRkRXZlbnRMaXN0ZW5lcihcImNoYW5nZVwiLCAoKSA9PiB7XG4gICAgYXBwbHlEZWZhdWx0T3JkZXIodHJ1ZSk7XG4gIH0pO1xuXG4gIGFwcGx5RGVmYXVsdE9yZGVyKGZhbHNlKTtcbn1cblxuZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihcIkRPTUNvbnRlbnRMb2FkZWRcIiwgKCkgPT4ge1xuICBpbml0RWxlbWVudG9PcmRlckRlZmF1bHRzKCk7XG59KTtcbiIsImZ1bmN0aW9uIGluaXRNYXRyaXhSZWdpc3RyeVVwbG9hZE1vZGFsKCkge1xuICBjb25zdCBtb2RhbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwicmVnaXN0cm8tZXZpZGVuY2lhLW1vZGFsXCIpO1xuICBpZiAoIW1vZGFsKSByZXR1cm47XG5cbiAgY29uc3QgY2xvc2VVcmwgPSBtb2RhbC5kYXRhc2V0LmNsb3NlVXJsIHx8IHdpbmRvdy5sb2NhdGlvbi5wYXRobmFtZTtcbiAgY29uc3QgY2xvc2VNb2RhbCA9IChldmVudCkgPT4ge1xuICAgIGlmIChldmVudCkgZXZlbnQucHJldmVudERlZmF1bHQoKTtcbiAgICB3aW5kb3cubG9jYXRpb24uYXNzaWduKGNsb3NlVXJsKTtcbiAgfTtcblxuICBtb2RhbC5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgKGV2ZW50KSA9PiB7XG4gICAgaWYgKGV2ZW50LnRhcmdldC5jbG9zZXN0KFwiLmFjcmVkaXRhY2lvbi1pbmZvLWRpYWxvZ1wiKSkgcmV0dXJuO1xuICAgIGNsb3NlTW9kYWwoZXZlbnQpO1xuICB9KTtcblxuICBtb2RhbC5xdWVyeVNlbGVjdG9yQWxsKFwiW2RhdGEtcmVnaXN0cm8tdXBsb2FkLWNsb3NlXVwiKS5mb3JFYWNoKCh0cmlnZ2VyKSA9PiB7XG4gICAgdHJpZ2dlci5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgY2xvc2VNb2RhbCk7XG4gIH0pO1xuXG4gIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoXCJrZXlkb3duXCIsIChldmVudCkgPT4ge1xuICAgIGlmIChldmVudC5rZXkgPT09IFwiRXNjYXBlXCIpIHtcbiAgICAgIGNsb3NlTW9kYWwoZXZlbnQpO1xuICAgIH1cbiAgfSk7XG59XG5cbmZ1bmN0aW9uIGluaXRBY3JlZGl0YWNpb25Qcm9ncmVzc0JhcnMoKSB7XG4gIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoXCJbZGF0YS1hY3JlZGl0YWNpb24tcHJvZ3Jlc3MtdmFsdWVdXCIpLmZvckVhY2goKGJhcikgPT4ge1xuICAgIGNvbnN0IHJhd1ZhbHVlID0gTnVtYmVyLnBhcnNlRmxvYXQoYmFyLmRhdGFzZXQuYWNyZWRpdGFjaW9uUHJvZ3Jlc3NWYWx1ZSB8fCBcIjBcIik7XG4gICAgY29uc3Qgc2FmZVZhbHVlID0gTnVtYmVyLmlzRmluaXRlKHJhd1ZhbHVlKSA/IE1hdGgubWF4KDAsIE1hdGgubWluKHJhd1ZhbHVlLCAxMDApKSA6IDA7XG4gICAgYmFyLnN0eWxlLndpZHRoID0gYCR7c2FmZVZhbHVlfSVgO1xuICB9KTtcbn1cblxuZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihcIkRPTUNvbnRlbnRMb2FkZWRcIiwgKCkgPT4ge1xuICBpbml0TWF0cml4UmVnaXN0cnlVcGxvYWRNb2RhbCgpO1xuICBpbml0QWNyZWRpdGFjaW9uUHJvZ3Jlc3NCYXJzKCk7XG59KTtcbiIsImZ1bmN0aW9uIGluaXRSZWFzc2lnbm1lbnRIaWVyYXJjaHkoKSB7XG4gIGNvbnN0IGhpZXJhcmNoeSA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoXCJbZGF0YS1yZWFzc2lnbm1lbnQtaGllcmFyY2h5XVwiKTtcbiAgaWYgKCFoaWVyYXJjaHkpIHJldHVybjtcblxuICBoaWVyYXJjaHkuYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIChldmVudCkgPT4ge1xuICAgIGNvbnN0IHRvZ2dsZSA9IGV2ZW50LnRhcmdldC5jbG9zZXN0KFwiW2RhdGEtcmVhc3NpZ25tZW50LXRvZ2dsZV1cIik7XG4gICAgaWYgKCF0b2dnbGUgfHwgIWhpZXJhcmNoeS5jb250YWlucyh0b2dnbGUpKSByZXR1cm47XG5cbiAgICBjb25zdCBncm91cCA9IHRvZ2dsZS5jbG9zZXN0KFwiW2RhdGEtcmVhc3NpZ25tZW50LWdyb3VwXVwiKTtcbiAgICBpZiAoIWdyb3VwKSByZXR1cm47XG5cbiAgICBjb25zdCBpc0NvbGxhcHNlZCA9IGdyb3VwLmNsYXNzTGlzdC50b2dnbGUoXCJpcy1jb2xsYXBzZWRcIik7XG4gICAgdG9nZ2xlLnNldEF0dHJpYnV0ZShcImFyaWEtZXhwYW5kZWRcIiwgU3RyaW5nKCFpc0NvbGxhcHNlZCkpO1xuXG4gICAgY29uc3QgaWNvbiA9IHRvZ2dsZS5xdWVyeVNlbGVjdG9yKFwiLnJlYXNzaWdubWVudC10b2dnbGUtaWNvblwiKTtcbiAgICBpZiAoaWNvbikge1xuICAgICAgaWNvbi50ZXh0Q29udGVudCA9IGlzQ29sbGFwc2VkID8gXCIrXCIgOiBcIi1cIjtcbiAgICB9XG4gIH0pO1xufVxuXG5kb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKFwiRE9NQ29udGVudExvYWRlZFwiLCAoKSA9PiB7XG4gIGluaXRSZWFzc2lnbm1lbnRIaWVyYXJjaHkoKTtcbn0pO1xuIiwiLy8gQ29tcG9ydGFtaWVudG9zIGRlIGxhIHZpc3RhIGRlIHVzdWFyaW9zLlxuLy8gU2luIGRlcGVuZGVuY2lhcyBleHRlcm5hcywgc29sbyBoZWxwZXJzIGxpdmlhbm9zLlxuXG4vLyBIZWxwZXIgcGFyYSBkZWxlZ2FyIGV2ZW50b3NcbmZ1bmN0aW9uIG9uKGV2ZW50LCBzZWxlY3RvciwgaGFuZGxlcikge1xuICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKGV2ZW50LCAoZSkgPT4ge1xuICAgIGlmIChlLnRhcmdldC5jbG9zZXN0KHNlbGVjdG9yKSkgaGFuZGxlcihlKTtcbiAgfSk7XG59XG5cbi8vIENvbmZpcm1hY2nDs24gcGFyYSBhY3RpdmFyL2Rlc2FjdGl2YXIgdXN1YXJpb3Ncbm9uKFwiY2xpY2tcIiwgXCJbZGF0YS10b2dnbGUtZXN0YWRvXVwiLCAoZSkgPT4ge1xuICBjb25zdCBidG4gPSBlLnRhcmdldC5jbG9zZXN0KFwiW2RhdGEtdG9nZ2xlLWVzdGFkb11cIik7XG4gIGNvbnN0IG5vbWJyZSA9IGJ0bi5kYXRhc2V0Lm5vbWJyZSB8fCBcImVsIHVzdWFyaW9cIjtcbiAgY29uc3QgYWNjaW9uID0gYnRuLmRhdGFzZXQuYWN0aXZvID09PSBcInRydWVcIiA/IFwiZGVzYWN0aXZhclwiIDogXCJhY3RpdmFyXCI7XG4gIGNvbnN0IG9rID0gY29uZmlybShgwr9TZWd1cm8gcXVlIGRlc2VhcyAke2FjY2lvbn0gYSAke25vbWJyZX0/YCk7XG4gIGlmICghb2spIGUucHJldmVudERlZmF1bHQoKTtcbn0pO1xuXG4vLyBFbnbDrW8gZGUgZmlsdHJvcyAob3BjaW9uYWxtZW50ZSBhbCBwcmVzaW9uYXIgRW50ZXIpXG5vbihcImtleXByZXNzXCIsIFwiLmZpbHRlcnMgaW5wdXRcIiwgKGUpID0+IHtcbiAgaWYgKGUua2V5ID09PSBcIkVudGVyXCIpIHtcbiAgICBlLnRhcmdldC5mb3JtPy5zdWJtaXQoKTtcbiAgfVxufSk7XG5cbi8vIEluaWNpYWxpemFjacOzbiBiw6FzaWNhIGRlIG1vZGFsZXMgKHNpIGV4aXN0ZW4gZWxlbWVudG9zIGNvbiBkYXRhLW1vZGFsKVxub24oXCJjbGlja1wiLCBcIltkYXRhLW1vZGFsLW9wZW5dXCIsIChlKSA9PiB7XG4gIGNvbnN0IHRhcmdldElkID0gZS50YXJnZXQuY2xvc2VzdChcIltkYXRhLW1vZGFsLW9wZW5dXCIpLmRhdGFzZXQubW9kYWxPcGVuO1xuICBjb25zdCBtb2RhbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHRhcmdldElkKTtcbiAgaWYgKG1vZGFsKSB7XG4gICAgbW9kYWwucmVtb3ZlQXR0cmlidXRlKFwiaGlkZGVuXCIpO1xuICAgIG1vZGFsLmNsYXNzTGlzdC5hZGQoXCJpcy1vcGVuXCIpO1xuICB9XG59KTtcblxub24oXCJjbGlja1wiLCBcIltkYXRhLW1vZGFsLWNsb3NlXVwiLCAoZSkgPT4ge1xuICBjb25zdCBtb2RhbCA9IGUudGFyZ2V0LmNsb3Nlc3QoXCJbZGF0YS1tb2RhbF1cIik7XG4gIGlmIChtb2RhbCkge1xuICAgIG1vZGFsLmNsYXNzTGlzdC5yZW1vdmUoXCJpcy1vcGVuXCIpO1xuICAgIG1vZGFsLnNldEF0dHJpYnV0ZShcImhpZGRlblwiLCBcImhpZGRlblwiKTtcbiAgfVxufSk7XG5cbi8vIENlcnJhciBtb2RhbCBhbCBoYWNlciBjbGljayBlbiBiYWNrZHJvcFxub24oXCJjbGlja1wiLCBcIltkYXRhLW1vZGFsXVwiLCAoZSkgPT4ge1xuICBpZiAoZS50YXJnZXQgPT09IGUuY3VycmVudFRhcmdldCkge1xuICAgIGUudGFyZ2V0LmNsYXNzTGlzdC5yZW1vdmUoXCJpcy1vcGVuXCIpO1xuICAgIGUudGFyZ2V0LnNldEF0dHJpYnV0ZShcImhpZGRlblwiLCBcImhpZGRlblwiKTtcbiAgfVxufSk7XG4iXX0=
