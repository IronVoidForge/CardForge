(function () {
  function cookieValue(name) {
    const prefix = name + "=";
    return document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(prefix))?.slice(prefix.length) || "";
  }
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = cookieValue("cardforge_csrf") || (meta ? meta.content : "");
  if (token) {
    document.querySelectorAll('form[method="post"], form[method="POST"]').forEach((form) => {
      if (!form.querySelector('input[name="csrf_token"]')) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "csrf_token";
        input.value = token;
        form.appendChild(input);
      }
    });
  }
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch(() => undefined);
    });
  }

  document.querySelectorAll("[data-review-tag]").forEach((button) => {
    button.addEventListener("click", () => {
      const tag = button.getAttribute("data-review-tag") || "";
      const tagsInput = document.querySelector("#review-tags-input");
      const notesInput = document.querySelector("#mobile-decision-notes textarea[name='notes']");
      if (tagsInput) {
        const existing = tagsInput.value.split(",").map((item) => item.trim()).filter(Boolean);
        if (!existing.includes(tag)) {
          existing.push(tag);
          tagsInput.value = existing.join(", ");
        }
      }
      if (notesInput && !notesInput.value.includes(tag.replaceAll("_", " "))) {
        const note = tag.replaceAll("_", " ");
        notesInput.value = notesInput.value ? notesInput.value + "\n- " + note : "- " + note;
      }
      button.setAttribute("aria-pressed", "true");
      button.classList.add("selected");
    });
  });
})();
