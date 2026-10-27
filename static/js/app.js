
console.log("TessOS loaded.");

function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("overlay");

    if (!sidebar || !overlay) return;

    const isOpen = sidebar.classList.contains("open");

    sidebar.classList.toggle("open", !isOpen);
    overlay.classList.toggle("active", !isOpen);
}

function closeSidebar() {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("overlay");

    if (sidebar) sidebar.classList.remove("open");
    if (overlay) overlay.classList.remove("active");
}

document.addEventListener("DOMContentLoaded", function () {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("overlay");

    if (overlay) {
        overlay.addEventListener("click", closeSidebar);
    }

    if (sidebar) {
        sidebar.querySelectorAll("nav a").forEach(function (link) {
            link.addEventListener("click", closeSidebar);
        });
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeSidebar();
    });
});
