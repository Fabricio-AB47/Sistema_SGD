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
