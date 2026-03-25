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
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbIm1haW4uanMiLCJwYWdlcy91c3Vhcmlvcy5qcyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FDeENBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBIiwiZmlsZSI6ImFwcC5qcyIsInNvdXJjZXNDb250ZW50IjpbIi8vIEhlbHBlciBzaW1wbGUgcGFyYSBkZWxlZ2FyIGV2ZW50b3NcbmZ1bmN0aW9uIG9uKGV2ZW50LCBzZWxlY3RvciwgaGFuZGxlcikge1xuICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKGV2ZW50LCAoZSkgPT4ge1xuICAgIGlmIChlLnRhcmdldC5jbG9zZXN0KHNlbGVjdG9yKSkgaGFuZGxlcihlKTtcbiAgfSk7XG59XG5cbi8vIEVqZW1wbG86IHRvZ2dsZSBkZSBzaWRlYmFyIGVuIG1vYmlsZVxub24oXCJjbGlja1wiLCBcIltkYXRhLXRvZ2dsZS1zaWRlYmFyXVwiLCAoKSA9PiB7XG4gIGRvY3VtZW50LmJvZHkuY2xhc3NMaXN0LnRvZ2dsZShcInNpZGViYXItb3BlblwiKTtcbn0pO1xuXG5mdW5jdGlvbiBpbml0U2lkZWJhckdyb3VwcygpIHtcbiAgY29uc3QgZ3JvdXBzID0gQXJyYXkuZnJvbShkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKFwiW2RhdGEtc2lkZWJhci1ncm91cF1cIikpO1xuXG4gIGdyb3Vwcy5mb3JFYWNoKChncm91cCkgPT4ge1xuICAgIGNvbnN0IHRvZ2dsZSA9IGdyb3VwLnF1ZXJ5U2VsZWN0b3IoXCJbZGF0YS1zaWRlYmFyLXRvZ2dsZV1cIik7XG4gICAgaWYgKCF0b2dnbGUpIHJldHVybjtcblxuICAgIHRvZ2dsZS5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgKCkgPT4ge1xuICAgICAgY29uc3QgaXNPcGVuID0gZ3JvdXAuY2xhc3NMaXN0LmNvbnRhaW5zKFwic2lkZWJhcl9fZ3JvdXAtLW9wZW5cIik7XG5cbiAgICAgIGdyb3Vwcy5mb3JFYWNoKChpdGVtKSA9PiB7XG4gICAgICAgIGl0ZW0uY2xhc3NMaXN0LnJlbW92ZShcInNpZGViYXJfX2dyb3VwLS1vcGVuXCIpO1xuICAgICAgICBjb25zdCBpdGVtVG9nZ2xlID0gaXRlbS5xdWVyeVNlbGVjdG9yKFwiW2RhdGEtc2lkZWJhci10b2dnbGVdXCIpO1xuICAgICAgICBpZiAoaXRlbVRvZ2dsZSkgaXRlbVRvZ2dsZS5zZXRBdHRyaWJ1dGUoXCJhcmlhLWV4cGFuZGVkXCIsIFwiZmFsc2VcIik7XG4gICAgICB9KTtcblxuICAgICAgaWYgKCFpc09wZW4pIHtcbiAgICAgICAgZ3JvdXAuY2xhc3NMaXN0LmFkZChcInNpZGViYXJfX2dyb3VwLS1vcGVuXCIpO1xuICAgICAgICB0b2dnbGUuc2V0QXR0cmlidXRlKFwiYXJpYS1leHBhbmRlZFwiLCBcInRydWVcIik7XG4gICAgICB9XG4gICAgfSk7XG4gIH0pO1xufVxuXG5kb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKFwiRE9NQ29udGVudExvYWRlZFwiLCAoKSA9PiB7XG4gIGluaXRTaWRlYmFyR3JvdXBzKCk7XG4gIGNvbnNvbGUuaW5mbyhcIkZyb250ZW5kIFNJRyBsaXN0byAoU0NTUyArIEpTIGNvbXBpbGFkb3MgY29uIEd1bHApLlwiKTtcbn0pO1xuIiwiLy8gQ29tcG9ydGFtaWVudG9zIGRlIGxhIHZpc3RhIGRlIHVzdWFyaW9zLlxuLy8gU2luIGRlcGVuZGVuY2lhcyBleHRlcm5hcywgc29sbyBoZWxwZXJzIGxpdmlhbm9zLlxuXG4vLyBIZWxwZXIgcGFyYSBkZWxlZ2FyIGV2ZW50b3NcbmZ1bmN0aW9uIG9uKGV2ZW50LCBzZWxlY3RvciwgaGFuZGxlcikge1xuICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKGV2ZW50LCAoZSkgPT4ge1xuICAgIGlmIChlLnRhcmdldC5jbG9zZXN0KHNlbGVjdG9yKSkgaGFuZGxlcihlKTtcbiAgfSk7XG59XG5cbi8vIENvbmZpcm1hY2nDs24gcGFyYSBhY3RpdmFyL2Rlc2FjdGl2YXIgdXN1YXJpb3Ncbm9uKFwiY2xpY2tcIiwgXCJbZGF0YS10b2dnbGUtZXN0YWRvXVwiLCAoZSkgPT4ge1xuICBjb25zdCBidG4gPSBlLnRhcmdldC5jbG9zZXN0KFwiW2RhdGEtdG9nZ2xlLWVzdGFkb11cIik7XG4gIGNvbnN0IG5vbWJyZSA9IGJ0bi5kYXRhc2V0Lm5vbWJyZSB8fCBcImVsIHVzdWFyaW9cIjtcbiAgY29uc3QgYWNjaW9uID0gYnRuLmRhdGFzZXQuYWN0aXZvID09PSBcInRydWVcIiA/IFwiZGVzYWN0aXZhclwiIDogXCJhY3RpdmFyXCI7XG4gIGNvbnN0IG9rID0gY29uZmlybShgwr9TZWd1cm8gcXVlIGRlc2VhcyAke2FjY2lvbn0gYSAke25vbWJyZX0/YCk7XG4gIGlmICghb2spIGUucHJldmVudERlZmF1bHQoKTtcbn0pO1xuXG4vLyBFbnbDrW8gZGUgZmlsdHJvcyAob3BjaW9uYWxtZW50ZSBhbCBwcmVzaW9uYXIgRW50ZXIpXG5vbihcImtleXByZXNzXCIsIFwiLmZpbHRlcnMgaW5wdXRcIiwgKGUpID0+IHtcbiAgaWYgKGUua2V5ID09PSBcIkVudGVyXCIpIHtcbiAgICBlLnRhcmdldC5mb3JtPy5zdWJtaXQoKTtcbiAgfVxufSk7XG5cbi8vIEluaWNpYWxpemFjacOzbiBiw6FzaWNhIGRlIG1vZGFsZXMgKHNpIGV4aXN0ZW4gZWxlbWVudG9zIGNvbiBkYXRhLW1vZGFsKVxub24oXCJjbGlja1wiLCBcIltkYXRhLW1vZGFsLW9wZW5dXCIsIChlKSA9PiB7XG4gIGNvbnN0IHRhcmdldElkID0gZS50YXJnZXQuY2xvc2VzdChcIltkYXRhLW1vZGFsLW9wZW5dXCIpLmRhdGFzZXQubW9kYWxPcGVuO1xuICBjb25zdCBtb2RhbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKHRhcmdldElkKTtcbiAgaWYgKG1vZGFsKSB7XG4gICAgbW9kYWwucmVtb3ZlQXR0cmlidXRlKFwiaGlkZGVuXCIpO1xuICAgIG1vZGFsLmNsYXNzTGlzdC5hZGQoXCJpcy1vcGVuXCIpO1xuICB9XG59KTtcblxub24oXCJjbGlja1wiLCBcIltkYXRhLW1vZGFsLWNsb3NlXVwiLCAoZSkgPT4ge1xuICBjb25zdCBtb2RhbCA9IGUudGFyZ2V0LmNsb3Nlc3QoXCJbZGF0YS1tb2RhbF1cIik7XG4gIGlmIChtb2RhbCkge1xuICAgIG1vZGFsLmNsYXNzTGlzdC5yZW1vdmUoXCJpcy1vcGVuXCIpO1xuICAgIG1vZGFsLnNldEF0dHJpYnV0ZShcImhpZGRlblwiLCBcImhpZGRlblwiKTtcbiAgfVxufSk7XG5cbi8vIENlcnJhciBtb2RhbCBhbCBoYWNlciBjbGljayBlbiBiYWNrZHJvcFxub24oXCJjbGlja1wiLCBcIltkYXRhLW1vZGFsXVwiLCAoZSkgPT4ge1xuICBpZiAoZS50YXJnZXQgPT09IGUuY3VycmVudFRhcmdldCkge1xuICAgIGUudGFyZ2V0LmNsYXNzTGlzdC5yZW1vdmUoXCJpcy1vcGVuXCIpO1xuICAgIGUudGFyZ2V0LnNldEF0dHJpYnV0ZShcImhpZGRlblwiLCBcImhpZGRlblwiKTtcbiAgfVxufSk7XG4iXX0=
