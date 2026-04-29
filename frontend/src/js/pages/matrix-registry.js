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
