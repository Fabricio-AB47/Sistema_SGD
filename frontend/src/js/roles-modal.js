document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("rolesModal");
  const openBtn = document.getElementById("openRolesModal");
  const cancelBtn = document.getElementById("rolesCancel");
  const acceptBtn = document.getElementById("rolesAccept");
  const summary = document.getElementById("rolesSummary");
  const hiddenContainer = document.getElementById("rolesHiddenContainer");
  const form = document.querySelector(".user-create-form");

  if (!modal || !openBtn || !cancelBtn || !acceptBtn || !summary || !hiddenContainer || !form) return;

  const closeModal = () => modal.setAttribute("hidden", "hidden");
  const openModal = () => modal.removeAttribute("hidden");

  const updateSummary = (names) => {
    if (!names.length) {
      summary.textContent = "Ningun rol seleccionado";
    } else {
      summary.textContent = names.join(", ");
    }
  };

  const getCurrentSelectedIds = () => {
    return Array.from(hiddenContainer.querySelectorAll('input[name="roles"]')).map(
      (inp) => inp.value
    );
  };

  const setModalChecks = (ids) => {
    const allChecks = modal.querySelectorAll('input[name="role_modal"]');
    allChecks.forEach((chk) => {
      chk.checked = ids.includes(chk.value);
    });
  };

  const syncHiddenInputs = () => {
    hiddenContainer.innerHTML = "";
    const checked = modal.querySelectorAll('input[name="role_modal"]:checked');
    const names = [];
    checked.forEach((chk) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "roles";
      input.value = chk.value;
      hiddenContainer.appendChild(input);
      names.push(chk.dataset.name || chk.value);
    });
    updateSummary(names);
    return checked.length;
  };

  openBtn.addEventListener("click", () => {
    const current = getCurrentSelectedIds();
    setModalChecks(current);
    openModal();
  });

  cancelBtn.addEventListener("click", () => {
    const current = getCurrentSelectedIds();
    setModalChecks(current);
    closeModal();
  });
  acceptBtn.addEventListener("click", () => {
    const count = syncHiddenInputs();
    if (!count) {
      alert("Selecciona al menos un rol.");
      return;
    }
    closeModal();
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.classList.contains("roles-modal__backdrop")) {
      closeModal();
    }
  });

  form.addEventListener("submit", (e) => {
    const count = syncHiddenInputs();
    if (!count) {
      e.preventDefault();
      openModal();
      alert("Selecciona al menos un rol para continuar.");
    }
  });
});
