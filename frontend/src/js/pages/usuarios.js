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
