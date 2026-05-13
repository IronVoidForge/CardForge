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

  const lightboxTriggers = document.querySelectorAll("[data-lightbox-src]");
  if (lightboxTriggers.length) {
    const lightbox = document.createElement("div");
    lightbox.className = "image-lightbox";
    lightbox.setAttribute("role", "dialog");
    lightbox.setAttribute("aria-modal", "true");
    lightbox.setAttribute("aria-label", "Full screen card preview");
    lightbox.hidden = true;
    lightbox.innerHTML = [
      '<button class="image-lightbox-close" type="button" aria-label="Close full screen preview">Close</button>',
      '<img class="image-lightbox-image" alt="">',
    ].join("");
    document.body.appendChild(lightbox);

    const image = lightbox.querySelector(".image-lightbox-image");
    const closeButton = lightbox.querySelector(".image-lightbox-close");
    let previousFocus = null;

    function closeLightbox() {
      lightbox.hidden = true;
      document.body.classList.remove("lightbox-open");
      if (image) {
        image.removeAttribute("src");
      }
      if (previousFocus) {
        previousFocus.focus();
      }
    }

    lightboxTriggers.forEach((trigger) => {
      trigger.addEventListener("click", () => {
        previousFocus = document.activeElement;
        if (image) {
          image.src = trigger.getAttribute("data-lightbox-src") || "";
          image.alt = trigger.getAttribute("data-lightbox-alt") || "Full screen preview";
        }
        lightbox.hidden = false;
        document.body.classList.add("lightbox-open");
        if (closeButton) {
          closeButton.focus();
        }
      });
    });

    if (closeButton) {
      closeButton.addEventListener("click", closeLightbox);
    }
    lightbox.addEventListener("click", (event) => {
      if (event.target === lightbox) {
        closeLightbox();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (!lightbox.hidden && event.key === "Escape") {
        closeLightbox();
      }
    });
  }
})();
