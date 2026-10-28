document.addEventListener("DOMContentLoaded", () => {
    const text = document.getElementById("id_text");
    const counter = document.getElementById("counter");
    const meter = document.getElementById("meter");
    const form = document.getElementById("source-form");
    const button = document.getElementById("submit-btn");
    const results = document.getElementById("results");

    if (text && counter) {
        const update = () => {
            const len = Array.from(text.value).length;
            counter.textContent = len + " таңба";
            if (meter) {
                meter.firstElementChild.style.width = Math.min(100, len / 120) + "%";
                meter.classList.toggle("ok", len >= 80 && len <= 12000);
            }
        };
        text.addEventListener("input", update);
        update();
    }

    if (form && button) {
        form.addEventListener("submit", () => {
            if (form.checkValidity()) {
                button.disabled = true;
                button.textContent = "Өңделуде...";
            }
        });
    }

    document.querySelectorAll(".card details").forEach(d => {
        const summary = d.querySelector("summary");
        d.addEventListener("toggle", () => {
            summary.textContent = d.open ? "Жауапты жасыру" : "Жауапты көрсету";
        });
    });

    if (results) {
        results.scrollIntoView({ behavior: "smooth", block: "start" });
    }
});