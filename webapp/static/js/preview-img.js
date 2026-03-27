class PreviewImg extends HTMLElement {
    connectedCallback() {
        if (this.dataset.initialized === "true") return;
        this.dataset.initialized = "true";
        this.style.display = "inline-block";

        this.render();
    }

    static get observedAttributes() {
        return ["src", "alt", "class"];
    }

    attributeChangedCallback() {
        if (this.dataset.initialized === "true") {
            this.render();
        }
    }

    render() {
        const src = this.getAttribute("src") || "";
        const alt = this.getAttribute("alt") || "";
        const cls = this.getAttribute("class") || "";

        this.innerHTML = "";

        const img = document.createElement("img");
        img.src = src;
        img.alt = alt;
        img.className = `${cls} cursor-pointer`;
        img.loading = "lazy";

        img.addEventListener("click", () => {
            PreviewImg.openPreview(src, alt);
        });

        this.appendChild(img);
    }

    static ensureModal() {
        let modal = document.getElementById("preview-img-modal");
        if (modal) return modal;

        modal = document.createElement("div");
        modal.id = "preview-img-modal";
        modal.className = "fixed inset-0 z-[9999] hidden items-center justify-center bg-black/80 p-4";

        modal.innerHTML = `
            <button
                type="button"
                aria-label="Close preview"
                class="absolute right-4 top-4 rounded-full bg-white/10 px-3 py-2 text-white hover:bg-white/20"
            >
                ✕
            </button>
            <img
                class="max-h-[90vh] max-w-[90vw] rounded-lg shadow-2xl object-contain"
                alt=""
            >
        `;

        const close = () => {
            modal.classList.add("hidden");
            modal.classList.remove("flex");
        };

        modal.addEventListener("click", close);

        const button = modal.querySelector("button");
        button.addEventListener("click", (e) => {
            e.stopPropagation();
            close();
        });

        const previewImg = modal.querySelector("img");
        previewImg.addEventListener("click", (e) => {
            e.stopPropagation();
        });

        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && !modal.classList.contains("hidden")) {
                close();
            }
        });

        document.body.appendChild(modal);
        return modal;
    }

    static openPreview(src, alt = "") {
        const modal = PreviewImg.ensureModal();
        const previewImg = modal.querySelector("img");

        previewImg.src = src;
        previewImg.alt = alt;

        modal.classList.remove("hidden");
        modal.classList.add("flex");
    }
}


customElements.define("preview-img", PreviewImg);
console.log("Defined <preview-img> custom element");
