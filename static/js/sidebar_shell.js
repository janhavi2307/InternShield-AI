document.addEventListener(
    "DOMContentLoaded",
    function () {
        const sidebar =
            document.getElementById(
                "sidebar"
            );

        const mobileMenu =
            document.getElementById(
                "mobileMenu"
            );

        const mobileOverlay =
            document.getElementById(
                "mobileOverlay"
            );

        /* -----------------------------------------------------
           Shared mobile sidebar
        ----------------------------------------------------- */

        if (
            sidebar
            && mobileMenu
            && mobileOverlay
        ) {
            function openSidebar() {
                sidebar.classList.add(
                    "open"
                );

                mobileOverlay.classList.add(
                    "visible"
                );
            }

            function closeSidebar() {
                sidebar.classList.remove(
                    "open"
                );

                mobileOverlay.classList.remove(
                    "visible"
                );
            }

            mobileMenu.addEventListener(
                "click",
                openSidebar
            );

            mobileOverlay.addEventListener(
                "click",
                closeSidebar
            );

            document.addEventListener(
                "keydown",
                function (event) {
                    if (
                        event.key
                        === "Escape"
                    ) {
                        closeSidebar();
                    }
                }
            );

            window.addEventListener(
                "resize",
                function () {
                    if (
                        window.innerWidth
                        > 850
                    ) {
                        closeSidebar();
                    }
                }
            );
        }


        /* -----------------------------------------------------
           Application Tracker:
           make Add Application immediately understandable.

           applications.html already opens/closes #addPanel.
           This shared enhancement handles:
           - button state
           - automatic scroll to the opened form
           - brief visual reveal
           - sensible first-field focus
        ----------------------------------------------------- */

        const addToggle =
            document.getElementById(
                "addToggle"
            );

        const addPanel =
            document.getElementById(
                "addPanel"
            );

        const cancelAdd =
            document.getElementById(
                "cancelAdd"
            );

        if (
            addToggle
            && addPanel
        ) {
            function prefersReducedMotion() {
                return window.matchMedia(
                    "(prefers-reduced-motion: reduce)"
                ).matches;
            }

            function updateAddButtonState() {
                const isOpen =
                    addPanel.classList.contains(
                        "open"
                    );

                addToggle.setAttribute(
                    "aria-expanded",
                    isOpen
                        ? "true"
                        : "false"
                );

                addToggle.textContent =
                    isOpen
                        ? "Close application form"
                        : "+ Add application";
            }

            function revealAddPanel() {
                if (
                    !addPanel.classList.contains(
                        "open"
                    )
                ) {
                    updateAddButtonState();
                    return;
                }

                updateAddButtonState();

                addPanel.classList.remove(
                    "is-revealed"
                );

                void addPanel.offsetWidth;

                addPanel.classList.add(
                    "is-revealed"
                );

                window.setTimeout(
                    function () {
                        addPanel.scrollIntoView({
                            behavior:
                                prefersReducedMotion()
                                    ? "auto"
                                    : "smooth",
                            block: "start"
                        });
                    },
                    80
                );

                window.setTimeout(
                    function () {
                        const firstField =
                            addPanel.querySelector(
                                "#analysis_id, input, select, textarea"
                            );

                        if (firstField) {
                            try {
                                firstField.focus({
                                    preventScroll: true
                                });
                            } catch (error) {
                                firstField.focus();
                            }
                        }
                    },
                    prefersReducedMotion()
                        ? 120
                        : 650
                );

                window.setTimeout(
                    function () {
                        addPanel.classList.remove(
                            "is-revealed"
                        );
                    },
                    900
                );
            }

            addToggle.setAttribute(
                "aria-controls",
                "addPanel"
            );

            updateAddButtonState();

            /*
             * The inline applications.html click handler runs first
             * and toggles .open. This listener then reacts to the
             * resulting state.
             */
            addToggle.addEventListener(
                "click",
                function () {
                    window.setTimeout(
                        revealAddPanel,
                        0
                    );
                }
            );

            if (cancelAdd) {
                cancelAdd.addEventListener(
                    "click",
                    function () {
                        window.setTimeout(
                            updateAddButtonState,
                            0
                        );

                        addToggle.focus({
                            preventScroll: true
                        });
                    }
                );
            }
        }
    }
);
