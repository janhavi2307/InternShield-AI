document.addEventListener("DOMContentLoaded", () => {
    const main =
        document.querySelector("main") ||
        document.querySelector("[role='main']");

    if (main && !main.id) {
        main.id = "main-content";
    }

    if (main && !document.querySelector(".skip-link")) {
        const skipLink = document.createElement("a");
        skipLink.className = "skip-link";
        skipLink.href = `#${main.id}`;
        skipLink.textContent = "Skip to main content";
        document.body.prepend(skipLink);
    }

    const flashCandidates = document.querySelectorAll(
        ".flash-message, .flash, .alert, [class*='message-']"
    );

    flashCandidates.forEach((message) => {
        if (
            message.querySelector(".global-flash-close") ||
            message.closest("form")
        ) {
            return;
        }

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "global-flash-close";
        closeButton.setAttribute("aria-label", "Dismiss message");
        closeButton.textContent = "×";
        closeButton.addEventListener("click", () => dismiss(message));
        message.append(closeButton);
    });

    document.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", () => {
            if (!form.checkValidity()) {
                return;
            }

            const submitButton = form.querySelector(
                "button[type='submit'], input[type='submit']"
            );

            if (!submitButton || submitButton.dataset.noLoading === "true") {
                return;
            }

            submitButton.classList.add("is-submitting");
            submitButton.setAttribute("aria-busy", "true");
        });
    });

    setupHistoryControls();
});

function dismiss(element) {
    element.classList.add("is-dismissing");
    window.setTimeout(() => element.remove(), 220);
}

function setupHistoryControls() {
    const table = document.querySelector("[data-history-table]");
    const search = document.querySelector("#historySearch");
    const status = document.querySelector("#historyStatus");
    const sort = document.querySelector("#historySort");
    const summary = document.querySelector("#historyResultsSummary");
    const empty = document.querySelector("#historyEmptyFilter");

    if (!table || !search || !status || !sort) {
        return;
    }

    const body = table.querySelector("tbody");
    const rows = Array.from(body.querySelectorAll("[data-history-row]"));

    const update = () => {
        const query = search.value.trim().toLowerCase();
        const selectedStatus = status.value;
        const selectedSort = sort.value;

        const visible = rows.filter((row) => {
            const matchesText =
                !query ||
                row.dataset.search.includes(query);
            const matchesStatus =
                selectedStatus === "all" ||
                row.dataset.status === selectedStatus;
            return matchesText && matchesStatus;
        });

        rows.forEach((row) => {
            row.hidden = !visible.includes(row);
        });

        visible.sort((a, b) => {
            if (selectedSort === "verification") {
                return Number(b.dataset.verification) -
                    Number(a.dataset.verification);
            }
            if (selectedSort === "value") {
                return Number(b.dataset.value) -
                    Number(a.dataset.value);
            }
            if (selectedSort === "oldest") {
                return a.dataset.date.localeCompare(b.dataset.date);
            }
            return b.dataset.date.localeCompare(a.dataset.date);
        });

        visible.forEach((row) => body.append(row));

        if (summary) {
            summary.textContent =
                `${visible.length} of ${rows.length} assessments shown`;
        }
        if (empty) {
            empty.hidden = visible.length > 0;
        }
    };

    [search, status, sort].forEach((control) => {
        control.addEventListener("input", update);
        control.addEventListener("change", update);
    });

    update();
}