
(() => {
    "use strict";

    /*
     * D14E — visual transplant helper only.
     *
     * This file:
     *   - moves existing DOM nodes for the Stitch layout,
     *   - injects decorative SVG,
     *   - injects idle reticles.
     *
     * It performs NO network calls and installs NO
     * robot-control listeners.
     */

    const NS = "http://www.w3.org/2000/svg";

    const flourish = (flip=false) => `
        <svg class="rv-flourish${flip ? " flip" : ""}"
             fill="none" stroke="currentColor" viewBox="0 0 60 20"
             aria-hidden="true">
            <path d="M2 10 C 15 3, 30 18, 45 10 C 52 6, 58 10, 58 10"
                  stroke="#f59e0b" stroke-linecap="round"
                  stroke-width="1.2"/>
            <path d="M18 7 C 22 2, 28 4, 25 9"
                  fill="rgba(245,158,11,0.18)"
                  stroke="#f59e0b" stroke-width="1"/>
            <path d="M33 13 C 37 18, 43 16, 40 11"
                  fill="rgba(16,185,129,0.25)"
                  stroke="#10b981" stroke-width="1"/>
            <circle cx="5" cy="10" r="1.5" fill="#f59e0b"
                    stroke="none"/>
            <circle cx="58" cy="10" r="1.5" fill="#10b981"
                    stroke="none"/>
        </svg>
    `;

    const emblem = `
        <div class="rv-brand-emblem" aria-hidden="true">
            <svg fill="none" stroke="currentColor"
                 viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="44" opacity=".6"
                        stroke-dasharray="3 3" stroke-width="2"/>
                <circle cx="50" cy="50" r="36" opacity=".4"
                        stroke-width="1.5"/>
                <path d="M50 14 C44 28,35 40,50 65 C65 40,56 28,50 14 Z"
                      fill="rgba(245,158,11,.18)" stroke-width="2"/>
                <path d="M14 50 C28 44,40 35,65 50 C40 65,28 56,14 50 Z"
                      fill="rgba(245,158,11,.15)" stroke-width="2"/>
                <path d="M50 86 C44 72,35 60,50 35 C65 60,56 72,50 86 Z"
                      fill="rgba(245,158,11,.18)" stroke-width="2"/>
                <path d="M86 50 C72 44,60 35,35 50 C60 65,72 56,86 50 Z"
                      fill="rgba(245,158,11,.15)" stroke-width="2"/>
                <circle cx="50" cy="50" r="6"
                        fill="#10b981" stroke-width="1.5"/>
            </svg>
            <span class="rv-brand-online-dot"></span>
        </div>
    `;

    const ornaments = {
        raw: `
            <svg class="rv-header-ornament" fill="none"
                 stroke="currentColor" viewBox="0 0 24 24"
                 aria-hidden="true">
                <path d="M12 2C12 2 13.8 6.2 16.5 7.5C19.2 8.8 22 8 22 8C22 8 20.8 11.2 18.5 13C16.2 14.8 15 18 15 18C15 18 13.5 15.5 12 15C10.5 15.5 9 18 9 18C9 18 7.8 14.8 5.5 13C3.2 11.2 2 8 2 8C2 8 4.8 8.8 7.5 7.5C10.2 6.2 12 2 12 2Z"
                      fill="rgba(245,158,11,.18)"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="1.2"/>
                <circle cx="12" cy="10" r="1.5"
                        fill="#34d399" stroke="none"/>
            </svg>`,
        sim: `
            <svg class="rv-header-ornament" fill="none"
                 stroke="currentColor" viewBox="0 0 24 24"
                 aria-hidden="true">
                <circle cx="12" cy="12" r="8"
                        stroke="rgba(245,158,11,.6)"
                        stroke-dasharray="2 2"
                        stroke-width="1.2"/>
                <path d="M12 4 L14 10 L20 12 L14 14 L12 20 L10 14 L4 12 L10 10 Z"
                      fill="rgba(245,158,11,.22)"
                      stroke="#f59e0b" stroke-width="1"/>
                <circle cx="12" cy="12" r="1.5"
                        fill="#10b981" stroke="none"/>
            </svg>`,
        keypoint: `
            <svg class="rv-header-ornament" fill="none"
                 stroke="currentColor" viewBox="0 0 24 24"
                 aria-hidden="true">
                <path d="M12 2C13 6 18 7 18 12C18 17 13 18 12 22C11 18 6 17 6 12C6 7 11 6 12 2Z"
                      fill="rgba(245,158,11,.18)"
                      stroke="#f59e0b" stroke-width="1.2"/>
                <circle cx="12" cy="12" r="1.8"
                        fill="#10b981" stroke="none"/>
                <circle cx="12" cy="5" r=".8"
                        fill="#f59e0b" stroke="none"/>
                <circle cx="12" cy="19" r=".8"
                        fill="#f59e0b" stroke="none"/>
            </svg>`,
        robot: `
            <svg class="rv-header-ornament" fill="none"
                 stroke="currentColor" viewBox="0 0 24 24"
                 aria-hidden="true">
                <path d="M7 17C7 17 8 13 12 11C16 9 17 5 17 5C17 5 15 9 11 11C7 13 7 17 7 17Z"
                      fill="rgba(245,158,11,.2)"
                      stroke="#f59e0b"
                      stroke-linecap="round"
                      stroke-width="1.4"/>
                <circle cx="12" cy="11" r="1.3"
                        fill="#34d399" stroke="none"/>
                <path d="M11 17C11 17 12 15 14 14"
                      stroke="#34d399" stroke-width="1"/>
            </svg>`
    };

    const reticles = {
        raw: `
            <div class="rv-reticle raw" aria-hidden="true">
                <svg class="rv-outer reticle-spin" fill="none"
                     stroke="#10b981" stroke-opacity=".35"
                     viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="47"
                            stroke-dasharray="3 4" stroke-width="1"/>
                    <circle cx="50" cy="50" r="41"
                            opacity=".6" stroke-width=".75"/>
                    <circle cx="50" cy="3" r="2"
                            fill="#f59e0b" stroke="none"/>
                    <circle cx="97" cy="50" r="2"
                            fill="#10b981" stroke="none"/>
                    <circle cx="50" cy="97" r="2"
                            fill="#f59e0b" stroke="none"/>
                    <circle cx="3" cy="50" r="2"
                            fill="#10b981" stroke="none"/>
                </svg>
                <svg class="rv-inner reticle-spin-rev" fill="none"
                     stroke="#f59e0b" stroke-opacity=".40"
                     viewBox="0 0 100 100">
                    <path d="M50 16 C42 32,32 42,50 68 C68 42,58 32,50 16 Z"
                          fill="rgba(245,158,11,.08)" stroke-width="1.2"/>
                    <path d="M16 50 C32 42,42 32,68 50 C42 68,32 58,16 50 Z"
                          fill="rgba(245,158,11,.08)" stroke-width="1.2"/>
                    <path d="M50 84 C42 68,32 58,50 32 C68 58,58 68,50 84 Z"
                          fill="rgba(245,158,11,.08)" stroke-width="1.2"/>
                    <path d="M84 50 C68 42,58 32,32 50 C58 68,68 58,84 50 Z"
                          fill="rgba(245,158,11,.08)" stroke-width="1.2"/>
                    <circle cx="50" cy="50" r="30" opacity=".7"
                            stroke-dasharray="1 3" stroke-width=".8"/>
                </svg>
                <div class="rv-reticle-core reticle-pulse">
                    <svg fill="none" stroke="currentColor"
                         viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="9"
                                stroke-dasharray="2 2"
                                stroke-width="1.2"/>
                        <path d="M12 7c-2 2.5-3 5-3 7 0 1.66 1.34 3 3 3s3-1.34 3-3c0-2-1-4.5-3-7z"
                              fill="rgba(52,211,153,.25)"
                              stroke-width="1.3"/>
                        <circle cx="12" cy="14" r="1.5"
                                fill="#34d399" stroke="none"/>
                    </svg>
                </div>
            </div>`,
        sim: `
            <div class="rv-reticle sim" aria-hidden="true">
                <svg class="rv-outer reticle-spin" fill="none"
                     stroke="#10b981" stroke-opacity=".35"
                     viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="46"
                            stroke-dasharray="4 3" stroke-width="1"/>
                    <rect x="23" y="23" width="54" height="54"
                          transform="rotate(45 50 50)"
                          stroke="rgba(16,185,129,.3)"
                          stroke-dasharray="3 3"
                          stroke-width="1.2"/>
                    <circle cx="50" cy="50" r="35"
                            opacity=".4" stroke-width=".8"/>
                </svg>
                <svg class="rv-inner reticle-spin-rev" fill="none"
                     stroke="#f59e0b" stroke-opacity=".40"
                     viewBox="0 0 100 100">
                    <rect x="27" y="27" width="46" height="46"
                          fill="rgba(245,158,11,.07)"
                          stroke-width="1.2"/>
                    <circle cx="50" cy="27" r="2.5" fill="#f59e0b"/>
                    <circle cx="73" cy="50" r="2.5" fill="#f59e0b"/>
                    <circle cx="50" cy="73" r="2.5" fill="#f59e0b"/>
                    <circle cx="27" cy="50" r="2.5" fill="#f59e0b"/>
                </svg>
                <div class="rv-reticle-core reticle-pulse">
                    <svg fill="none" stroke="currentColor"
                         stroke-width="1.5" viewBox="0 0 24 24">
                        <rect x="6" y="6" width="12" height="12"
                              transform="rotate(45 12 12)"
                              fill="rgba(16,185,129,.18)"
                              stroke-width="1.4"/>
                        <circle cx="12" cy="12" r="2.5"
                                fill="#34d399" stroke="none"/>
                    </svg>
                </div>
            </div>`,
        keypoint: `
            <div class="rv-reticle keypoint" aria-hidden="true">
                <svg class="rv-outer reticle-spin" fill="none"
                     stroke="#34d399" stroke-opacity=".40"
                     viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="46"
                            stroke-dasharray="2 4" stroke-width="1"/>
                    <circle cx="50" cy="14" r="3"
                            fill="#10b981" stroke="#34d399" stroke-width="1"/>
                    <circle cx="86" cy="50" r="3"
                            fill="#10b981" stroke="#34d399" stroke-width="1"/>
                    <circle cx="50" cy="86" r="3"
                            fill="#10b981" stroke="#34d399" stroke-width="1"/>
                    <circle cx="14" cy="50" r="3"
                            fill="#10b981" stroke="#34d399" stroke-width="1"/>
                    <line x1="50" y1="14" x2="86" y2="50"
                          opacity=".5" stroke-dasharray="2 3" stroke-width=".75"/>
                    <line x1="86" y1="50" x2="50" y2="86"
                          opacity=".5" stroke-dasharray="2 3" stroke-width=".75"/>
                    <line x1="50" y1="86" x2="14" y2="50"
                          opacity=".5" stroke-dasharray="2 3" stroke-width=".75"/>
                    <line x1="14" y1="50" x2="50" y2="14"
                          opacity=".5" stroke-dasharray="2 3" stroke-width=".75"/>
                </svg>
                <svg class="rv-inner reticle-spin-rev" fill="none"
                     stroke="#f59e0b" stroke-opacity=".45"
                     viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="32"
                            stroke-dasharray="3 3" stroke-width="1"/>
                    <circle cx="50" cy="24" r="2.2" fill="#f59e0b"/>
                    <circle cx="68" cy="32" r="2" fill="#fbbf24"/>
                    <circle cx="76" cy="50" r="2.2" fill="#f59e0b"/>
                    <circle cx="68" cy="68" r="2" fill="#fbbf24"/>
                    <circle cx="50" cy="76" r="2.2" fill="#f59e0b"/>
                    <circle cx="32" cy="68" r="2" fill="#fbbf24"/>
                    <circle cx="24" cy="50" r="2.2" fill="#f59e0b"/>
                    <circle cx="32" cy="32" r="2" fill="#fbbf24"/>
                </svg>
                <div class="rv-reticle-core reticle-pulse">
                    <svg fill="none" stroke="currentColor"
                         viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="22"
                                stroke-dasharray="2 2"
                                stroke-width="1.5"/>
                        <circle cx="50" cy="50" r="6"
                                fill="#34d399" stroke="none"/>
                        <circle cx="50" cy="50" r="11"
                                fill="none" stroke="#10b981"
                                stroke-width="2"/>
                    </svg>
                </div>
            </div>`,
        robot: `
            <div class="rv-reticle robot" aria-hidden="true">
                <svg class="rv-outer reticle-spin" fill="none"
                     stroke="#10b981" stroke-opacity=".35"
                     viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="47"
                            stroke-dasharray="5 3" stroke-width="1"/>
                    <circle cx="50" cy="50" r="42"
                            opacity=".5" stroke-width=".8"/>
                    <path d="M50 8 L50 20 M92 50 L80 50 M50 92 L50 80 M8 50 L20 50"
                          stroke="#f59e0b" stroke-width="1.5"/>
                    <path d="M20 20 L28 28 M80 20 L72 28 M80 80 L72 72 M20 80 L28 72"
                          stroke="#10b981" stroke-width="1.2"/>
                </svg>
                <svg class="rv-inner reticle-spin-rev" fill="none"
                     stroke="#f59e0b" stroke-opacity=".40"
                     viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="34"
                            stroke-dasharray="2 3"
                            stroke-width="1.2"/>
                    <circle cx="50" cy="18" r="2.2" fill="#10b981"/>
                    <circle cx="78" cy="36" r="2" fill="#f59e0b"/>
                    <circle cx="78" cy="64" r="2" fill="#f59e0b"/>
                    <circle cx="50" cy="82" r="2.2" fill="#10b981"/>
                    <circle cx="22" cy="64" r="2" fill="#f59e0b"/>
                    <circle cx="22" cy="36" r="2" fill="#f59e0b"/>
                </svg>
                <div class="rv-reticle-core reticle-pulse">
                    <svg fill="none" stroke="currentColor"
                         stroke-width="1.5" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="8"
                                stroke-dasharray="2 2"
                                stroke-width="1.2"/>
                        <circle cx="12" cy="12" r="4.5"
                                fill="rgba(16,185,129,.2)"
                                stroke="none"/>
                        <circle cx="12" cy="12" r="2.2"
                                fill="#34d399" stroke="none"/>
                    </svg>
                </div>
            </div>`
    };

    function kindFromText(value) {
        const text = String(value || "").trim().toUpperCase();
        if (text.includes("RAW CAMERA")) return "raw";
        if (text.includes("KEYPOINT")) return "keypoint";
        if (text.includes("SIMULATION") || text.includes("MUJOCO")) return "sim";
        if (text.includes("ROBOT CAMERA")) return "robot";
        return null;
    }

    function makeBrand(topbar) {
        if (!topbar || topbar.querySelector(".rv-brand-cluster")) return;

        const sidebar = document.querySelector(".sidebar");
        const brand = sidebar?.querySelector(".brand") || document.querySelector(".brand");
        const footer = sidebar?.querySelector(".sidebar-footer") || document.querySelector(".sidebar-footer");

        const cluster = document.createElement("div");
        cluster.className = "rv-brand-cluster";
        cluster.innerHTML = emblem;

        const text = document.createElement("div");
        text.className = "rv-brand-copy";

        if (brand) text.appendChild(brand);
        if (footer) text.appendChild(footer);

        cluster.appendChild(text);
        topbar.prepend(cluster);
    }

    function makeCenterTitle(topbar) {
        if (!topbar || topbar.querySelector(".rv-center-title")) return;

        const title = document.getElementById("pageTitle");
        if (!title) return;

        const oldParent = title.parentElement;

        const center = document.createElement("div");
        center.className = "rv-center-title";
        center.innerHTML = flourish(false) + '<span class="rv-title-dot"></span>';
        center.appendChild(title);
        center.insertAdjacentHTML("beforeend", flourish(true));

        topbar.appendChild(center);

        if (
            oldParent &&
            oldParent !== topbar &&
            oldParent !== center &&
            oldParent.children.length === 0 &&
            !oldParent.textContent.trim()
        ) {
            oldParent.remove();
        }
    }

    function addNavIcons() {
        for (const button of document.querySelectorAll(".nav-item")) {
            if (button.querySelector(".rv-nav-icon")) continue;
            const text = button.textContent.trim().toLowerCase();
            const wrap = document.createElement("span");
            wrap.className = "rv-nav-icon";
            wrap.innerHTML = text.includes("log")
                ? '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-2 10H7v-2h10v2zm0-4H7V7h10v2zm-4 8H7v-2h6v2z"/></svg>'
                : '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M13 2L3 14h8l-2 8 10-12h-8l2-8z"/></svg>';
            button.prepend(wrap);
        }
    }

    function headerTarget(tile) {
        return tile.querySelector(
            ".workspace-tile-header, .panel-header, .camera-feed-label"
        );
    }

    function addHeaderOrnament(tile, kind) {
        const header = headerTarget(tile);
        if (!header || header.querySelector(".rv-header-ornament")) return;

        const label = header.querySelector("strong, h2, span");
        if (!label) return;

        label.insertAdjacentHTML("afterend", ornaments[kind]);
    }

    function addReticle(tile, kind) {
        const placeholder = tile.querySelector(
            ".camera-placeholder, .unified-preview-placeholder, .robot-camera-placeholder"
        );

        if (!placeholder || placeholder.querySelector(".rv-reticle")) return;
        placeholder.insertAdjacentHTML("afterbegin", reticles[kind]);
    }

    function decorateTiles() {
        const tiles = document.querySelectorAll(
            "#mediaWorkspace > *, .workspace-tile, .camera-feed, .mujoco-panel, .robot-camera-panel"
        );

        for (const tile of tiles) {
            const header = headerTarget(tile);
            const kind = kindFromText(header?.textContent || tile.textContent);
            if (!kind) continue;
            addHeaderOrnament(tile, kind);
            addReticle(tile, kind);
        }

        const direct = [
            ["#rawCameraPlaceholder", "raw"],
            ["#cameraPlaceholder", "keypoint"],
        ];

        for (const [selector, kind] of direct) {
            const placeholder = document.querySelector(selector);
            if (placeholder && !placeholder.querySelector(".rv-reticle")) {
                placeholder.insertAdjacentHTML("afterbegin", reticles[kind]);
            }
        }
    }

    function moveTopbar() {
        const shell = document.querySelector(".app-shell");
        const topbar = document.querySelector(".topbar");
        if (!shell || !topbar) return null;

        if (topbar.parentElement !== shell) {
            shell.prepend(topbar);
        }

        return topbar;
    }

    function apply() {
        document.body.classList.add("reference-stitch");

        const topbar = moveTopbar();
        makeBrand(topbar);
        makeCenterTitle(topbar);
        /* D14G: Live / Logs intentionally have no icons. */
        decorateTiles();
    }

    let queued = false;

    function queueApply() {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => {
            queued = false;
            apply();
        });
    }

    function init() {
        apply();

        const observer = new MutationObserver(queueApply);
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        window.addEventListener("load", queueApply, { once: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();

// D14G_OFF_STATUS_VISUAL_NORMALIZER
(() => {
    "use strict";

    /*
     * Presentation only:
     * marks sidebar text whose displayed value is literally OFF.
     * No API/network calls.
     * No click/drag/control listeners.
     */

    function syncOffStatusVisuals() {
        const nodes =
            document.querySelectorAll(
                ".sidebar strong, .sidebar span"
            );

        for (const node of nodes) {
            const value =
                String(
                    node.textContent || ""
                )
                .trim()
                .toUpperCase();

            node.classList.toggle(
                "rv-status-off",
                value === "OFF"
            );
        }
    }

    let queued =
        false;

    function queueSync() {
        if (queued) {
            return;
        }

        queued =
            true;

        requestAnimationFrame(
            () => {
                queued =
                    false;

                syncOffStatusVisuals();
            }
        );
    }

    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            queueSync,
            {
                once: true,
            }
        );
    }

    else {
        queueSync();
    }

    const observer =
        new MutationObserver(
            queueSync
        );

    observer.observe(
        document.body,
        {
            childList: true,
            subtree: true,
            characterData: true,
        }
    );
})();

// ============================================================
// D14O_VIEWPORT_AND_WINDOW_STATE
// ============================================================

(() => {
    "use strict";


    const BOTTOM_GAP =
        10;


    function d14oSyncWorkspaceHeight() {
        const workspace =
            document.getElementById(
                "mediaWorkspace"
            );


        if (!workspace) {
            return;
        }


        const rect =
            workspace
                .getBoundingClientRect();


        const available =
            Math.max(
                300,
                window.innerHeight
                    - rect.top
                    - BOTTOM_GAP
            );


        workspace.style.setProperty(
            "--d14o-workspace-height",
            `${available}px`
        );
    }


    function d14oIsVisible(
        element
    ) {
        if (
            !element
            ||
            element.hidden
        ) {
            return false;
        }


        const style =
            getComputedStyle(
                element
            );


        return (
            style.display !== "none"
            &&
            style.visibility !== "hidden"
            &&
            element.getClientRects()
                .length > 0
        );
    }


    function d14oTileIsOpen(
        tile
    ) {
        /*
         * A visible idle placeholder means the window is closed.
         */
        const placeholder =
            tile.querySelector(
                ".camera-placeholder, "
                + ".unified-preview-placeholder, "
                + ".robot-camera-placeholder"
            );


        if (
            placeholder
            &&
            d14oIsVisible(
                placeholder
            )
        ) {
            return false;
        }


        for (
            const image
            of tile.querySelectorAll(
                "img"
            )
        ) {
            const src =
                image.currentSrc
                ||
                image.getAttribute(
                    "src"
                )
                ||
                "";


            if (
                src
                &&
                d14oIsVisible(
                    image
                )
                &&
                image.naturalWidth > 0
                &&
                image.naturalHeight > 0
            ) {
                return true;
            }
        }


        const video =
            tile.querySelector(
                "video"
            );


        if (
            video
            &&
            d14oIsVisible(
                video
            )
            &&
            video.readyState >= 2
        ) {
            return true;
        }


        return false;
    }


    function d14oSyncWindowStates() {
        const workspace =
            document.getElementById(
                "mediaWorkspace"
            );


        if (!workspace) {
            return;
        }


        for (
            const tile
            of workspace.querySelectorAll(
                ".workspace-tile"
            )
        ) {
            tile.classList.toggle(
                "rv-window-open",
                d14oTileIsOpen(
                    tile
                )
            );
        }
    }


    let queued =
        false;


    function d14oQueue() {
        if (queued) {
            return;
        }


        queued =
            true;


        requestAnimationFrame(
            () => {
                queued =
                    false;

                d14oSyncWorkspaceHeight();
                d14oSyncWindowStates();
            }
        );
    }


    function d14oInstall() {
        d14oQueue();


        window.addEventListener(
            "resize",
            d14oQueue
        );


        const workspace =
            document.getElementById(
                "mediaWorkspace"
            );


        if (!workspace) {
            return;
        }


        workspace.addEventListener(
            "load",
            d14oQueue,
            true
        );


        workspace.addEventListener(
            "error",
            d14oQueue,
            true
        );


        new MutationObserver(
            d14oQueue
        ).observe(
            workspace,
            {
                subtree: true,
                childList: true,
                attributes: true,
                attributeFilter: [
                    "hidden",
                    "src",
                    "class",
                ],
            }
        );


        /*
         * Small periodic visual-state refresh only.
         * No networking and no robot interaction.
         */
        window.setInterval(
            d14oSyncWindowStates,
            1000
        );
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            d14oInstall,
            {
                once: true,
            }
        );
    }

    else {
        d14oInstall();
    }
})();

// ============================================================
// D14T_START_STOP_VISUAL_SWITCH
//
// Presentation only.
//
// Existing dashboard Start/Stop handlers remain completely
// authoritative. This code only mirrors the resulting state
// into the segmented-switch appearance.
// ============================================================

(() => {
    "use strict";


    function d14tFind() {
        return {
            track:
                document.querySelector(
                    ".bacalbasa-system-switch"
                ),

            start:
                document.querySelector(
                    ".bacalbasa-system-segment-primary"
                ),

            stop:
                document.querySelector(
                    ".bacalbasa-system-segment-stop"
                ),

            badge:
                document.getElementById(
                    "systemLaunchState"
                ),

            target:
                document.getElementById(
                    "systemTargetSelect"
                ),
        };
    }


    function d14tRuntimeActive() {
        /*
         * Prefer the real status object already maintained by
         * app.js. No network/API calls are made here.
         */
        try {
            if (
                typeof latestDemoStatus
                    !== "undefined"
                &&
                latestDemoStatus
            ) {
                const target =
                    document
                        .getElementById(
                            "systemTargetSelect"
                        )
                        ?.value
                    || "sim";


                if (target === "robot") {
                    return Boolean(
                        latestDemoStatus
                            ?.physical
                            ?.active
                    );
                }


                return Boolean(
                    latestDemoStatus
                        ?.stack
                        ?.active
                );
            }
        }

        catch (_) {
            // Fall through to DOM-state detection.
        }


        /*
         * Fallback for early page startup before the first
         * status payload has arrived.
         */
        const badge =
            document.getElementById(
                "systemLaunchState"
            );


        if (!badge) {
            return false;
        }


        if (
            badge.classList.contains(
                "live"
            )
        ) {
            return true;
        }


        const value =
            String(
                badge.textContent
                || ""
            )
            .trim()
            .toUpperCase();


        if (
            !value
            ||
            value === "OFF"
            ||
            value.includes(
                "ERROR"
            )
        ) {
            return false;
        }


        return true;
    }


    function d14tSync() {
        const {
            track,
        } = d14tFind();


        if (!track) {
            return;
        }


        track.classList.toggle(
            "rv-system-active",
            d14tRuntimeActive()
        );
    }


    function d14tInstall() {
        const {
            track,
            start,
            stop,
            badge,
            target,
        } = d14tFind();


        if (
            !track
            ||
            !start
            ||
            !stop
        ) {
            return false;
        }


        /*
         * D14U — ACTUAL STATE OWNS SWITCH
         *
         * Do not move the visual switch optimistically on click.
         * The existing dashboard control logic performs the real
         * action, and d14tSync() moves the switch only after the
         * resulting dashboard state confirms it.
         */


        /*
         * Reconcile the visual position with actual dashboard
         * status whenever app.js updates the hidden state badge.
         */
        if (badge) {
            new MutationObserver(
                d14tSync
            ).observe(
                badge,
                {
                    childList: true,
                    characterData: true,
                    subtree: true,
                    attributes: true,
                    attributeFilter: [
                        "class",
                    ],
                }
            );
        }


        target?.addEventListener(
            "change",
            () => {
                requestAnimationFrame(
                    d14tSync
                );
            }
        );


        d14tSync();

        return true;
    }


    function d14tBoot() {
        if (
            d14tInstall()
        ) {
            return;
        }


        /*
         * Controls can be visually relocated during startup.
         * Watch only until they exist, then disconnect.
         */
        const observer =
            new MutationObserver(
                () => {
                    if (
                        d14tInstall()
                    ) {
                        observer.disconnect();
                    }
                }
            );


        observer.observe(
            document.body,
            {
                childList: true,
                subtree: true,
            }
        );
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            d14tBoot,
            {
                once: true,
            }
        );
    }

    else {
        d14tBoot();
    }
})();

// ============================================================
// D14X_CONNECTION_BUTTON_STATE
//
// Presentation only.
// Adds an amber-style class when the existing button says
// "Disconnect". No API calls and no click behavior changes.
// ============================================================

(() => {
    "use strict";


    function d14xSync(
        button
    ) {
        if (!button) {
            return;
        }


        const label =
            String(
                button.textContent
                || ""
            )
            .trim()
            .toUpperCase();


        button.classList.toggle(
            "rv-disconnect-control",
            label === "DISCONNECT"
        );
    }


    function d14xInstall() {
        const button =
            document.querySelector(
                ".robot-connection-toggle"
            );


        if (!button) {
            return false;
        }


        d14xSync(
            button
        );


        new MutationObserver(
            () => {
                d14xSync(
                    button
                );
            }
        ).observe(
            button,
            {
                childList: true,
                characterData: true,
                subtree: true,
            }
        );


        return true;
    }


    function d14xBoot() {
        if (
            d14xInstall()
        ) {
            return;
        }


        /*
         * Startup-only observer. Disconnects as soon as the
         * existing connection button appears.
         */
        const observer =
            new MutationObserver(
                () => {
                    if (
                        d14xInstall()
                    ) {
                        observer.disconnect();
                    }
                }
            );


        observer.observe(
            document.body,
            {
                childList: true,
                subtree: true,
            }
        );
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            d14xBoot,
            {
                once: true,
            }
        );
    }

    else {
        d14xBoot();
    }
})();

// ============================================================
// D14Y_TARGET_PRESENTATION_STATE
//
// Presentation only.
// No API calls and no system-control changes.
// ============================================================

(() => {
    "use strict";


    function d14ySync() {
        const select =
            document.getElementById(
                "systemTargetSelect"
            );

        if (!select) {
            return;
        }


        const value =
            String(
                select.value || ""
            )
            .trim()
            .toLowerCase();


        const simulation =
            (
                value === "sim"
                ||
                value === "simulation"
            );


        document.body.classList.toggle(
            "rv-target-simulation",
            simulation
        );

        document.body.classList.toggle(
            "rv-target-robot",
            !simulation
        );
    }


    function d14yInstall() {
        const select =
            document.getElementById(
                "systemTargetSelect"
            );

        if (!select) {
            return false;
        }


        select.addEventListener(
            "change",
            d14ySync
        );

        d14ySync();

        return true;
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            d14yInstall,
            {
                once: true,
            }
        );
    }
    else {
        d14yInstall();
    }
})();

// ============================================================
// D15B_DRAGGABLE_WINDOW_DOCK
//
// Separate UI layer.
// Does NOT rewrite D7H drag/swap logic.
//
// Workspace -> dock:
//     drag a real workspace card into the right rail.
//
// Dock -> workspace:
//     drag a parked icon into an empty 2x2 position.
//
// Display Settings is retired.
// ============================================================

(() => {
    "use strict";


    const INFO = {
        raw: {
            label: "Raw Camera",
            number: "01",
            icon: `
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.6">
                    <rect x="4" y="7"
                          width="16" height="11"
                          rx="2"/>
                    <circle cx="12" cy="12.5"
                            r="3.2"/>
                    <path d="M8 7l1.3-2h5.4L16 7"/>
                </svg>
            `,
        },

        simulation: {
            label: "Simulation",
            number: "02",
            icon: `
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.5">
                    <path d="M12 3 20 7.5 12 12 4 7.5 12 3Z"/>
                    <path d="M4 7.5v9L12 21v-9"/>
                    <path d="M20 7.5v9L12 21"/>
                </svg>
            `,
        },

        robot: {
            label: "Robot Camera",
            number: "03",
            icon: `
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.5">
                    <rect x="5" y="7"
                          width="14" height="11"
                          rx="3"/>
                    <circle cx="12" cy="12.5"
                            r="2.7"/>
                    <path d="M12 7V4"/>
                    <circle cx="12" cy="3"
                            r="1"/>
                    <path d="M8 18v2M16 18v2"/>
                </svg>
            `,
        },

        keypoint: {
            label: "Keypoint Camera",
            number: "04",
            icon: `
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.5">
                    <circle cx="12" cy="5" r="1.7"/>
                    <circle cx="8" cy="10" r="1.5"/>
                    <circle cx="16" cy="10" r="1.5"/>
                    <circle cx="7" cy="17" r="1.5"/>
                    <circle cx="17" cy="17" r="1.5"/>
                    <path d="M12 6.7 8 8.5
                             M12 6.7 16 8.5
                             M8 11.5 7 15.5
                             M16 11.5 17 15.5
                             M8 10h8"/>
                </svg>
            `,
        },
    };


    let dock = null;
    let parking = null;
    let iconDrag = null;


    function workspace() {
        return document.getElementById(
            "mediaWorkspace"
        );
    }


    function slots() {
        const ws = workspace();

        if (!ws) {
            return [];
        }

        return [
            ...ws.querySelectorAll(
                ":scope > .workspace-slot"
            ),
        ].slice(0, 4);
    }


    function tileFor(
        key
    ) {
        if (key === "raw") {
            return document.getElementById(
                "rawCameraView"
            );
        }

        if (key === "keypoint") {
            return document.getElementById(
                "keypointCameraView"
            );
        }

        if (key === "robot") {
            return document.getElementById(
                "robotCameraView"
            );
        }

        if (key === "simulation") {
            return (
                document.querySelector(
                    "#mediaWorkspace .workspace-tile.mujoco-panel"
                )
                ||
                document.querySelector(
                    ".workspace-tile.mujoco-panel"
                )
            );
        }

        return null;
    }


    function keyForTile(
        tile
    ) {
        if (!tile) {
            return null;
        }

        if (tile.id === "rawCameraView") {
            return "raw";
        }

        if (tile.id === "keypointCameraView") {
            return "keypoint";
        }

        if (tile.id === "robotCameraView") {
            return "robot";
        }

        if (
            tile.classList.contains(
                "mujoco-panel"
            )
        ) {
            return "simulation";
        }

        return (
            tile.dataset.workspaceTile
            || null
        );
    }


    function ensureParking() {
        parking =
            document.getElementById(
                "d15WindowParking"
            )
            || parking;

        if (!parking) {
            parking =
                document.createElement(
                    "div"
                );

            parking.id =
                "d15WindowParking";

            parking.setAttribute(
                "aria-hidden",
                "true"
            );

            document.body.appendChild(
                parking
            );
        }

        return parking;
    }


    function isParked(
        tile
    ) {
        return Boolean(
            tile
            &&
            (
                tile.classList.contains(
                    "d15-parked"
                )
                ||
                ensureParking().contains(
                    tile
                )
            )
        );
    }


    function syncSlotClasses() {
        for (
            const slot
            of slots()
        ) {
            const occupied =
                Boolean(
                    slot.querySelector(
                        ":scope > .workspace-tile"
                    )
                );

            slot.classList.toggle(
                "workspace-slot-empty",
                !occupied
            );

            slot.classList.toggle(
                "d10b-empty-slot",
                !occupied
            );
        }


        try {
            if (
                typeof d7hUpdateSlotVisuals
                === "function"
            ) {
                d7hUpdateSlotVisuals();
            }
        }
        catch (_) {
            // Optional compatibility helper.
        }
    }


    function keepVisibleWhenDockedOut(
        tile
    ) {
        if (!tile) {
            return;
        }


        /*
         * The retired Keypoints / Show Both controls must no
         * longer hide an on-workspace window.
         */
        const repair = () => {
            if (
                !isParked(tile)
                &&
                tile.classList.contains(
                    "hidden"
                )
            ) {
                tile.classList.remove(
                    "hidden"
                );
            }
        };


        repair();


        new MutationObserver(
            repair
        ).observe(
            tile,
            {
                attributes: true,
                attributeFilter: [
                    "class",
                ],
            }
        );
    }


    function hideDisplaySettings() {
        const sidebar =
            document.querySelector(
                ".sidebar"
            );

        if (!sidebar) {
            return;
        }


        const heading =
            [
                ...sidebar.querySelectorAll(
                    "*"
                ),
            ].find(
                (node) =>
                    node.children.length === 0
                    &&
                    String(
                        node.textContent || ""
                    )
                    .trim()
                    .toUpperCase()
                    === "DISPLAY SETTINGS"
            );


        if (!heading) {
            return;
        }


        let node =
            heading.parentElement;


        while (
            node
            &&
            node !== sidebar
        ) {
            const value =
                String(
                    node.textContent || ""
                )
                .toUpperCase();


            if (
                value.includes("KEYPOINT")
                &&
                value.includes("SHOW BOTH")
                &&
                !value.includes("ROBOT MODES")
            ) {
                node.classList.add(
                    "d15-display-settings-hidden"
                );

                return;
            }


            node =
                node.parentElement;
        }


        heading.parentElement
            ?.classList.add(
                "d15-display-settings-hidden"
            );
    }


    function createDock() {
        if (
            dock
            &&
            dock.isConnected
        ) {
            return dock;
        }


        const shell =
            document.querySelector(
                ".app-shell"
            );

        if (!shell) {
            return null;
        }


        dock =
            document.createElement(
                "aside"
            );

        dock.id =
            "d15WindowDock";

        dock.className =
            "d15-window-dock";

        dock.setAttribute(
            "aria-label",
            "Window dock"
        );


        const grip =
            document.createElement(
                "div"
            );

        grip.className =
            "d15-dock-grip";


        const items =
            document.createElement(
                "div"
            );

        items.className =
            "d15-dock-items";


        for (
            const key
            of [
                "raw",
                "simulation",
                "robot",
                "keypoint",
            ]
        ) {
            const info =
                INFO[key];


            const button =
                document.createElement(
                    "button"
                );

            button.type =
                "button";

            button.className =
                "d15-dock-item";

            button.dataset.d15Tile =
                key;

            button.title =
                info.label;

            button.innerHTML =
                `
                <span class="d15-dock-icon">
                    ${info.icon}
                </span>
                <span class="d15-dock-number">
                    ${info.number}
                </span>
                `;


            items.appendChild(
                button
            );
        }


        dock.append(
            grip,
            items
        );


        shell.appendChild(
            dock
        );


        return dock;
    }


    function pointInsideDock(
        x,
        y
    ) {
        if (
            !dock
            ||
            dock.hidden
        ) {
            return false;
        }


        const rect =
            dock.getBoundingClientRect();


        return (
            x >= rect.left
            &&
            x <= rect.right
            &&
            y >= rect.top
            &&
            y <= rect.bottom
        );
    }


    function parkTile(
        tile
    ) {
        if (
            !tile
            ||
            isParked(tile)
        ) {
            return;
        }


        tile.classList.add(
            "d15-parked",
            "hidden"
        );


        ensureParking()
            .appendChild(
                tile
            );


        syncSlotClasses();
        syncDockState();
    }


    function restoreTile(
        tile,
        slot
    ) {
        if (
            !tile
            ||
            !slot
            ||
            slot.querySelector(
                ":scope > .workspace-tile"
            )
        ) {
            return false;
        }


        slot.appendChild(
            tile
        );


        tile.classList.remove(
            "d15-parked",
            "hidden"
        );


        try {
            if (
                typeof d7hWorkspaceManualLayout
                    !== "undefined"
            ) {
                d7hWorkspaceManualLayout =
                    true;
            }
        }
        catch (_) {
            // Optional compatibility.
        }


        syncSlotClasses();
        syncDockState();

        return true;
    }


    function slotAtPoint(
        x,
        y,
        emptyOnly = true
    ) {
        const ws =
            workspace();

        const list =
            slots();


        if (
            !ws
            ||
            list.length < 4
        ) {
            return null;
        }


        const rect =
            ws.getBoundingClientRect();


        if (
            x < rect.left
            ||
            x > rect.right
            ||
            y < rect.top
            ||
            y > rect.bottom
        ) {
            return null;
        }


        const column =
            x < rect.left + rect.width / 2
                ? 0
                : 1;


        const row =
            y < rect.top + rect.height / 2
                ? 0
                : 1;


        const slot =
            list[
                row * 2 + column
            ]
            || null;


        if (
            emptyOnly
            &&
            slot
            &&
            slot.querySelector(
                ":scope > .workspace-tile"
            )
        ) {
            return null;
        }


        return slot;
    }


    function clearRestoreTargets() {
        for (
            const slot
            of slots()
        ) {
            slot.classList.remove(
                "d15-restore-target"
            );
        }
    }


    function createGhost(
        key
    ) {
        const ghost =
            document.createElement(
                "div"
            );

        ghost.className =
            "d15-window-ghost";

        ghost.innerHTML =
            `
            <span class="d15-window-ghost-icon">
                ${INFO[key].icon}
            </span>
            <strong>
                ${INFO[key].label}
            </strong>
            `;


        document.body.appendChild(
            ghost
        );

        return ghost;
    }


    function moveGhost(
        ghost,
        x,
        y
    ) {
        ghost.style.left =
            `${x}px`;

        ghost.style.top =
            `${y}px`;
    }


    function syncDockState() {
        if (!dock) {
            return;
        }


        for (
            const button
            of dock.querySelectorAll(
                ".d15-dock-item"
            )
        ) {
            const key =
                button.dataset.d15Tile;


            const tile =
                tileFor(
                    key
                );


            button.classList.toggle(
                "d15-is-parked",
                isParked(tile)
            );


            button.classList.toggle(
                "d15-on-workspace",
                Boolean(
                    tile
                    &&
                    workspace()
                        ?.contains(tile)
                )
            );


            button.classList.toggle(
                "d15-unavailable",
                !tile
            );


            button.disabled =
                !tile;
        }
    }


    function installDockIconDrag(
        button
    ) {
        button.addEventListener(
            "pointerdown",
            (event) => {
                if (
                    event.button !== 0
                ) {
                    return;
                }


                const key =
                    button.dataset.d15Tile;


                const tile =
                    tileFor(key);


                if (
                    !tile
                    ||
                    !isParked(tile)
                ) {
                    return;
                }


                event.preventDefault();


                const ghost =
                    createGhost(
                        key
                    );


                iconDrag = {
                    pointerId:
                        event.pointerId,

                    button,

                    tile,

                    ghost,

                    targetSlot:
                        null,
                };


                try {
                    button.setPointerCapture(
                        event.pointerId
                    );
                }
                catch (_) {}


                moveGhost(
                    ghost,
                    event.clientX,
                    event.clientY
                );
            }
        );


        button.addEventListener(
            "pointermove",
            (event) => {
                if (
                    !iconDrag
                    ||
                    iconDrag.pointerId
                    !== event.pointerId
                ) {
                    return;
                }


                event.preventDefault();


                moveGhost(
                    iconDrag.ghost,
                    event.clientX,
                    event.clientY
                );


                clearRestoreTargets();


                const slot =
                    slotAtPoint(
                        event.clientX,
                        event.clientY,
                        true
                    );


                if (slot) {
                    slot.classList.add(
                        "d15-restore-target"
                    );
                }


                iconDrag.targetSlot =
                    slot;
            }
        );


        const finish = (
            event
        ) => {
            if (
                !iconDrag
                ||
                iconDrag.pointerId
                !== event.pointerId
            ) {
                return;
            }


            if (
                iconDrag.targetSlot
            ) {
                restoreTile(
                    iconDrag.tile,
                    iconDrag.targetSlot
                );
            }


            clearRestoreTargets();


            iconDrag.ghost
                ?.remove();


            try {
                iconDrag.button
                    .releasePointerCapture(
                        event.pointerId
                    );
            }
            catch (_) {}


            iconDrag =
                null;


            syncDockState();
        };


        button.addEventListener(
            "pointerup",
            finish
        );

        button.addEventListener(
            "pointercancel",
            finish
        );
    }


    /*
     * WORKSPACE -> DOCK
     *
     * D7H already owns the actual card drag.
     * We only observe it.
     */
    function installWorkspaceToDock() {
        document.addEventListener(
            "pointermove",
            (event) => {
                const tile =
                    workspace()
                        ?.querySelector(
                            ".workspace-tile.workspace-dragging"
                        );


                if (!tile) {
                    dock?.classList.remove(
                        "d15-drop-target"
                    );

                    return;
                }


                dock?.classList.toggle(
                    "d15-drop-target",
                    pointInsideDock(
                        event.clientX,
                        event.clientY
                    )
                );
            },
            true
        );


        document.addEventListener(
            "pointerup",
            (event) => {
                const tile =
                    workspace()
                        ?.querySelector(
                            ".workspace-tile.workspace-dragging"
                        );


                const shouldPark =
                    Boolean(
                        tile
                        &&
                        pointInsideDock(
                            event.clientX,
                            event.clientY
                        )
                    );


                dock?.classList.remove(
                    "d15-drop-target"
                );


                /*
                 * Capture-phase listener runs before D7H's
                 * normal pointerup handler.
                 *
                 * Outside the workspace D7H has no targetSlot,
                 * so it safely finishes the drag after the tile
                 * has been moved into parking.
                 */
                if (
                    shouldPark
                    &&
                    tile
                ) {
                    parkTile(
                        tile
                    );
                }
            },
            true
        );


        document.addEventListener(
            "pointercancel",
            () => {
                dock?.classList.remove(
                    "d15-drop-target"
                );
            },
            true
        );
    }


    function syncLiveVisibility() {
        const live =
            document.getElementById(
                "view-live"
            );


        if (
            !dock
            ||
            !live
        ) {
            return;
        }


        dock.hidden =
            !live.classList.contains(
                "active"
            );
    }


    function prepareTiles() {
        /*
         * Dock now owns presence. Keep on-workspace tiles from
         * being hidden by the retired camera-mode controls.
         */
        for (
            const key
            of [
                "raw",
                "simulation",
                "robot",
                "keypoint",
            ]
        ) {
            const tile =
                tileFor(key);


            if (!tile) {
                continue;
            }


            const actualKey =
                keyForTile(
                    tile
                );


            if (actualKey) {
                tile.dataset.workspaceTile =
                    actualKey;
            }


            keepVisibleWhenDockedOut(
                tile
            );
        }
    }


    function initialize() {
        if (
            document.body.classList.contains(
                "d15-window-dock-ready"
            )
        ) {
            return true;
        }


        if (
            !workspace()
            ||
            slots().length < 4
        ) {
            return false;
        }


        ensureParking();


        if (
            !createDock()
        ) {
            return false;
        }


        /*
         * D15 now owns manual window placement.
         */
        try {
            if (
                typeof d7hWorkspaceManualLayout
                    !== "undefined"
            ) {
                d7hWorkspaceManualLayout =
                    true;
            }
        }
        catch (_) {}


        /*
         * Retire old camera-display ownership.
         */
        try {
            if (
                typeof state
                    !== "undefined"
            ) {
                state.keypointsEnabled =
                    true;

                state.showBothCameras =
                    true;
            }
        }
        catch (_) {}


        hideDisplaySettings();

        prepareTiles();


        for (
            const button
            of dock.querySelectorAll(
                ".d15-dock-item"
            )
        ) {
            installDockIconDrag(
                button
            );
        }


        installWorkspaceToDock();


        const live =
            document.getElementById(
                "view-live"
            );


        if (live) {
            new MutationObserver(
                syncLiveVisibility
            ).observe(
                live,
                {
                    attributes: true,
                    attributeFilter: [
                        "class",
                    ],
                }
            );
        }


        /*
         * Robot camera can be created slightly later.
         * This observer only acts when that specific tile appears.
         */
        const robotObserver =
            new MutationObserver(
                () => {
                    const robot =
                        tileFor(
                            "robot"
                        );


                    if (!robot) {
                        return;
                    }


                    robotObserver.disconnect();

                    keepVisibleWhenDockedOut(
                        robot
                    );

                    syncDockState();
                }
            );


        if (
            !tileFor(
                "robot"
            )
        ) {
            robotObserver.observe(
                document.body,
                {
                    childList: true,
                    subtree: true,
                }
            );
        }


        document.body.classList.add(
            "d15-window-dock-ready"
        );


        syncSlotClasses();
        syncLiveVisibility();
        syncDockState();

        return true;
    }


    function boot(
        attempt = 0
    ) {
        if (
            initialize()
        ) {
            return;
        }


        if (
            attempt < 40
        ) {
            window.setTimeout(
                () => {
                    boot(
                        attempt + 1
                    );
                },
                100
            );
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                boot();
            },
            {
                once: true,
            }
        );
    }
    else {
        boot();
    }
})();

// ============================================================
// D15C_WINDOW_TITLE_ICONS
//
// Adds the same window identity icons used by the right dock
// immediately to the left of each workspace title.
// ============================================================

(() => {
    "use strict";


    const ICONS = {
        raw: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.6">
                <rect x="4" y="7"
                      width="16" height="11"
                      rx="2"/>
                <circle cx="12" cy="12.5"
                        r="3.2"/>
                <path d="M8 7l1.3-2h5.4L16 7"/>
            </svg>
        `,

        simulation: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.5">
                <path d="M12 3 20 7.5 12 12 4 7.5 12 3Z"/>
                <path d="M4 7.5v9L12 21v-9"/>
                <path d="M20 7.5v9L12 21"/>
            </svg>
        `,

        robot: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.5">
                <rect x="5" y="7"
                      width="14" height="11"
                      rx="3"/>
                <circle cx="12" cy="12.5"
                        r="2.7"/>
                <path d="M12 7V4"/>
                <circle cx="12" cy="3"
                        r="1"/>
                <path d="M8 18v2M16 18v2"/>
            </svg>
        `,

        keypoint: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.5">
                <circle cx="12" cy="5" r="1.7"/>
                <circle cx="8" cy="10" r="1.5"/>
                <circle cx="16" cy="10" r="1.5"/>
                <circle cx="7" cy="17" r="1.5"/>
                <circle cx="17" cy="17" r="1.5"/>
                <path d="M12 6.7 8 8.5
                         M12 6.7 16 8.5
                         M8 11.5 7 15.5
                         M16 11.5 17 15.5
                         M8 10h8"/>
            </svg>
        `,
    };


    function keyForTile(
        tile
    ) {
        if (!tile) {
            return null;
        }

        if (tile.id === "rawCameraView") {
            return "raw";
        }

        if (tile.id === "keypointCameraView") {
            return "keypoint";
        }

        if (tile.id === "robotCameraView") {
            return "robot";
        }

        if (
            tile.classList.contains(
                "mujoco-panel"
            )
        ) {
            return "simulation";
        }

        return (
            tile.dataset.workspaceTile
            || null
        );
    }


    function decorate(
        tile
    ) {
        if (
            !tile
            ||
            tile.dataset.d15cTitleIcon
            === "1"
        ) {
            return;
        }


        const key =
            keyForTile(
                tile
            );


        if (
            !key
            ||
            !ICONS[key]
        ) {
            return;
        }


        const header =
            tile.querySelector(
                ".workspace-tile-header"
            );


        if (!header) {
            return;
        }


        const title =
            header.querySelector(
                "strong, h2"
            );


        if (!title) {
            return;
        }


        /*
         * Set marker before mutating DOM so observers cannot
         * decorate the same header twice.
         */
        tile.dataset.d15cTitleIcon =
            "1";


        const group =
            document.createElement(
                "span"
            );

        group.className =
            "d15-window-title-group";


        const icon =
            document.createElement(
                "span"
            );

        icon.className =
            "d15-window-title-icon";

        icon.innerHTML =
            ICONS[key];


        title.parentElement.insertBefore(
            group,
            title
        );


        group.append(
            icon,
            title
        );
    }


    function scan() {
        document
            .querySelectorAll(
                "#mediaWorkspace .workspace-tile"
            )
            .forEach(
                decorate
            );
    }


    function install() {
        scan();


        const workspace =
            document.getElementById(
                "mediaWorkspace"
            );


        if (!workspace) {
            return;
        }


        new MutationObserver(
            scan
        ).observe(
            workspace,
            {
                childList: true,
                subtree: true,
            }
        );
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            install,
            {
                once: true,
            }
        );
    }
    else {
        install();
    }
})();

// ============================================================
// D15D_TITLE_REPAIR_AND_FULL_DROP_OVERLAY
//
// 1. Rebuilds all four window titles from known presentation
//    labels so Simulation is handled identically to cameras.
//
// 2. Draws a full-quadrant restore target independently of the
//    old slot geometry.
// ============================================================

(() => {
    "use strict";


    const WINDOWS = {
        raw: {
            label:
                "RAW CAMERA",

            icon: `
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.6">
                    <rect x="4" y="7"
                          width="16" height="11"
                          rx="2"/>
                    <circle cx="12" cy="12.5"
                            r="3.2"/>
                    <path d="M8 7l1.3-2h5.4L16 7"/>
                </svg>
            `,
        },

        simulation: {
            label:
                "SIMULATION",

            icon: `
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.5">
                    <path d="M12 3
                             20 7.5
                             12 12
                             4 7.5
                             12 3Z"/>
                    <path d="M4 7.5v9L12 21v-9"/>
                    <path d="M20 7.5v9L12 21"/>
                </svg>
            `,
        },

        robot: {
            label:
                "ROBOT CAMERA",

            icon: `
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.5">
                    <rect x="5" y="7"
                          width="14" height="11"
                          rx="3"/>
                    <circle cx="12" cy="12.5"
                            r="2.7"/>
                    <path d="M12 7V4"/>
                    <circle cx="12" cy="3"
                            r="1"/>
                    <path d="M8 18v2M16 18v2"/>
                </svg>
            `,
        },

        keypoint: {
            label:
                "KEYPOINT CAMERA",

            icon: `
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.5">
                    <circle cx="12" cy="5" r="1.7"/>
                    <circle cx="8" cy="10" r="1.5"/>
                    <circle cx="16" cy="10" r="1.5"/>
                    <circle cx="7" cy="17" r="1.5"/>
                    <circle cx="17" cy="17" r="1.5"/>
                    <path d="M12 6.7 8 8.5
                             M12 6.7 16 8.5
                             M8 11.5 7 15.5
                             M16 11.5 17 15.5
                             M8 10h8"/>
                </svg>
            `,
        },
    };


    // --------------------------------------------------------
    // WINDOW TITLE REPAIR
    // --------------------------------------------------------

    function d15dKeyForTile(
        tile
    ) {
        if (!tile) {
            return null;
        }


        if (
            tile.id
            === "rawCameraView"
        ) {
            return "raw";
        }


        if (
            tile.id
            === "keypointCameraView"
        ) {
            return "keypoint";
        }


        if (
            tile.id
            === "robotCameraView"
        ) {
            return "robot";
        }


        if (
            tile.classList.contains(
                "mujoco-panel"
            )
        ) {
            return "simulation";
        }


        return (
            tile.dataset.workspaceTile
            || null
        );
    }


    function d15dRepairTitle(
        tile
    ) {
        const key =
            d15dKeyForTile(
                tile
            );


        if (
            !key
            ||
            !WINDOWS[key]
        ) {
            return;
        }


        const header =
            tile.querySelector(
                ".workspace-tile-header"
            );


        if (!header) {
            return;
        }


        /*
         * D15C moved the legacy h2/strong inside its title
         * wrapper. Remove that presentation layer entirely.
         */
        const oldGroup =
            header.querySelector(
                ".d15-window-title-group"
            );


        if (oldGroup) {
            /*
             * Preserve the original semantic title node for
             * older dashboard code that may still query it.
             */
            const original =
                oldGroup.querySelector(
                    "strong, h2"
                );


            if (original) {
                original.classList.add(
                    "d15d-original-title-source"
                );

                header.appendChild(
                    original
                );
            }


            oldGroup.remove();
        }


        /*
         * Hide any remaining legacy title node visually.
         * It stays in the DOM for old logic.
         */
        header
            .querySelectorAll(
                "strong, h2"
            )
            .forEach(
                (node) => {
                    node.classList.add(
                        "d15d-original-title-source"
                    );
                }
            );


        let group =
            header.querySelector(
                ".d15d-window-title-group"
            );


        if (!group) {
            group =
                document.createElement(
                    "span"
                );

            group.className =
                "d15d-window-title-group";


            group.innerHTML =
                `
                <span class="d15d-window-title-icon">
                    ${WINDOWS[key].icon}
                </span>

                <span class="d15d-window-title-text">
                    ${WINDOWS[key].label}
                </span>
                `;


            header.appendChild(
                group
            );
        }
    }


    function d15dRepairTitles() {
        document
            .querySelectorAll(
                "#mediaWorkspace .workspace-tile"
            )
            .forEach(
                d15dRepairTitle
            );
    }


    // --------------------------------------------------------
    // FULL QUADRANT DROP OVERLAY
    // --------------------------------------------------------

    let restoreOverlay =
        null;


    function d15dEnsureOverlay() {
        if (
            restoreOverlay
            &&
            restoreOverlay.isConnected
        ) {
            return restoreOverlay;
        }


        restoreOverlay =
            document.getElementById(
                "d15RestoreQuadrantOverlay"
            );


        if (!restoreOverlay) {
            restoreOverlay =
                document.createElement(
                    "div"
                );

            restoreOverlay.id =
                "d15RestoreQuadrantOverlay";

            document.body.appendChild(
                restoreOverlay
            );
        }


        return restoreOverlay;
    }


    function d15dHideOverlay() {
        const overlay =
            d15dEnsureOverlay();


        overlay.classList.remove(
            "active"
        );
    }


    function d15dUpdateOverlay(
        event
    ) {
        /*
         * The D15B dock creates this ghost only while an icon
         * is actively being dragged out of the right rail.
         */
        const ghost =
            document.querySelector(
                ".d15-window-ghost"
            );


        if (!ghost) {
            d15dHideOverlay();
            return;
        }


        const workspace =
            document.getElementById(
                "mediaWorkspace"
            );


        if (!workspace) {
            d15dHideOverlay();
            return;
        }


        const slots = [
            ...workspace.querySelectorAll(
                ":scope > .workspace-slot"
            ),
        ].slice(
            0,
            4
        );


        if (
            slots.length < 4
        ) {
            d15dHideOverlay();
            return;
        }


        const rect =
            workspace.getBoundingClientRect();


        if (
            event.clientX < rect.left
            ||
            event.clientX > rect.right
            ||
            event.clientY < rect.top
            ||
            event.clientY > rect.bottom
        ) {
            d15dHideOverlay();
            return;
        }


        const column =
            event.clientX
                <
            (
                rect.left
                +
                rect.width / 2
            )
                ? 0
                : 1;


        const row =
            event.clientY
                <
            (
                rect.top
                +
                rect.height / 2
            )
                ? 0
                : 1;


        const index =
            row * 2 + column;


        const targetSlot =
            slots[index];


        /*
         * Dock -> workspace only restores into an EMPTY slot.
         */
        if (
            targetSlot.querySelector(
                ":scope > .workspace-tile"
            )
        ) {
            d15dHideOverlay();
            return;
        }


        const style =
            window.getComputedStyle(
                workspace
            );


        const columnGap =
            parseFloat(
                style.columnGap
            )
            || 0;


        const rowGap =
            parseFloat(
                style.rowGap
            )
            || 0;


        const cellWidth =
            (
                rect.width
                -
                columnGap
            )
            / 2;


        const cellHeight =
            (
                rect.height
                -
                rowGap
            )
            / 2;


        const left =
            rect.left
            +
            column
            *
            (
                cellWidth
                +
                columnGap
            );


        const top =
            rect.top
            +
            row
            *
            (
                cellHeight
                +
                rowGap
            );


        const overlay =
            d15dEnsureOverlay();


        overlay.style.left =
            `${left}px`;

        overlay.style.top =
            `${top}px`;

        overlay.style.width =
            `${cellWidth}px`;

        overlay.style.height =
            `${cellHeight}px`;


        overlay.classList.add(
            "active"
        );
    }


    function d15dInstall() {
        d15dRepairTitles();


        const workspace =
            document.getElementById(
                "mediaWorkspace"
            );


        if (workspace) {
            new MutationObserver(
                d15dRepairTitles
            ).observe(
                workspace,
                {
                    childList: true,
                    subtree: true,
                }
            );
        }


        /*
         * Capture phase lets this presentation overlay follow
         * the same pointer used by D15B without changing D15B.
         */
        document.addEventListener(
            "pointermove",
            d15dUpdateOverlay,
            true
        );


        document.addEventListener(
            "pointerup",
            d15dHideOverlay,
            true
        );


        document.addEventListener(
            "pointercancel",
            d15dHideOverlay,
            true
        );


        window.addEventListener(
            "blur",
            d15dHideOverlay
        );
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            d15dInstall,
            {
                once: true,
            }
        );
    }
    else {
        d15dInstall();
    }
})();

// ============================================================
// D15F_WORKSPACE_MAXIMIZE
//
// Maximizes one real workspace tile over the complete 2x2
// media area.
//
// Only windows that were on the workspace before maximizing
// are restored afterward. Previously parked windows remain
// parked.
//
// No backend/API behavior is changed.
// ============================================================

(() => {
    "use strict";


    let maximizeState =
        null;


    function d15fWorkspace() {
        return document.getElementById(
            "mediaWorkspace"
        );
    }


    function d15fSlots() {
        const workspace =
            d15fWorkspace();


        if (!workspace) {
            return [];
        }


        return [
            ...workspace.querySelectorAll(
                ":scope > .workspace-slot"
            ),
        ].slice(
            0,
            4
        );
    }


    function d15fTileInSlot(
        slot
    ) {
        return (
            slot
                ?.querySelector(
                    ":scope > .workspace-tile"
                )
            ||
            null
        );
    }


    function d15fTileKey(
        tile
    ) {
        if (!tile) {
            return null;
        }


        if (
            tile.id
            === "rawCameraView"
        ) {
            return "raw";
        }


        if (
            tile.id
            === "keypointCameraView"
        ) {
            return "keypoint";
        }


        if (
            tile.id
            === "robotCameraView"
        ) {
            return "robot";
        }


        if (
            tile.classList.contains(
                "mujoco-panel"
            )
        ) {
            return "simulation";
        }


        return (
            tile.dataset.workspaceTile
            ||
            null
        );
    }


    function d15fEnsureParking() {
        let parking =
            document.getElementById(
                "d15WindowParking"
            );


        if (!parking) {
            parking =
                document.createElement(
                    "div"
                );

            parking.id =
                "d15WindowParking";

            parking.setAttribute(
                "aria-hidden",
                "true"
            );


            document.body.appendChild(
                parking
            );
        }


        return parking;
    }


    function d15fIsParked(
        tile
    ) {
        const parking =
            d15fEnsureParking();


        return Boolean(
            tile
            &&
            (
                tile.classList.contains(
                    "d15-parked"
                )
                ||
                parking.contains(
                    tile
                )
            )
        );
    }


    function d15fParkTile(
        tile
    ) {
        if (
            !tile
            ||
            d15fIsParked(
                tile
            )
        ) {
            return;
        }


        tile.classList.add(
            "d15-parked",
            "hidden"
        );


        d15fEnsureParking()
            .appendChild(
                tile
            );
    }


    function d15fRestoreTile(
        tile,
        slot
    ) {
        if (
            !tile
            ||
            !slot
        ) {
            return;
        }


        slot.appendChild(
            tile
        );


        tile.classList.remove(
            "d15-parked",
            "hidden"
        );
    }


    function d15fSyncSlots() {
        for (
            const slot
            of d15fSlots()
        ) {
            const empty =
                !d15fTileInSlot(
                    slot
                );


            slot.classList.toggle(
                "workspace-slot-empty",
                empty
            );


            slot.classList.toggle(
                "d10b-empty-slot",
                empty
            );
        }


        try {
            if (
                typeof d7hUpdateSlotVisuals
                    === "function"
            ) {
                d7hUpdateSlotVisuals();
            }
        }

        catch (_) {
            // Compatibility only.
        }
    }


    function d15fSyncDock() {
        const dock =
            document.getElementById(
                "d15WindowDock"
            );


        if (!dock) {
            return;
        }


        for (
            const button
            of dock.querySelectorAll(
                ".d15-dock-item"
            )
        ) {
            const key =
                button.dataset.d15Tile;


            let tile =
                null;


            if (
                key === "raw"
            ) {
                tile =
                    document.getElementById(
                        "rawCameraView"
                    );
            }

            else if (
                key === "keypoint"
            ) {
                tile =
                    document.getElementById(
                        "keypointCameraView"
                    );
            }

            else if (
                key === "robot"
            ) {
                tile =
                    document.getElementById(
                        "robotCameraView"
                    );
            }

            else if (
                key === "simulation"
            ) {
                tile =
                    document.querySelector(
                        ".workspace-tile.mujoco-panel"
                    );
            }


            const parked =
                d15fIsParked(
                    tile
                );


            const onWorkspace =
                Boolean(
                    tile
                    &&
                    d15fWorkspace()
                        ?.contains(
                            tile
                        )
                );


            button.classList.toggle(
                "d15-is-parked",
                parked
            );


            button.classList.toggle(
                "d15-on-workspace",
                onWorkspace
            );
        }
    }


    function d15fButtonMarkup() {
        return `
            <span
                class="d15f-expand-icon"
                aria-hidden="true"
            >
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <path d="M9 4H4v5"/>
                    <path d="M4 4l6 6"/>
                    <path d="M15 20h5v-5"/>
                    <path d="M20 20l-6-6"/>
                </svg>
            </span>

            <span
                class="d15f-restore-icon"
                aria-hidden="true"
            >
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.7"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <!-- Standard inward-corner / fullscreen-exit icon -->
                    <path d="M4 14h6v6"/>
                    <path d="M3 21l7-7"/>

                    <path d="M20 10h-6V4"/>
                    <path d="M21 3l-7 7"/>
                </svg>
            </span>
        `;
    }


    function d15fUpdateButton(
        button,
        maximized
    ) {
        button.classList.toggle(
            "d15f-is-restore",
            maximized
        );


        button.title =
            maximized
                ?
                "Restore workspace"
                :
                "Maximize window";


        button.setAttribute(
            "aria-label",
            button.title
        );
    }


    // ========================================================
    // D15G_FLUID_MAXIMIZE_RESTORE
    //
    // FLIP animation:
    //
    //     capture old rectangle
    //     perform real layout change
    //     capture new rectangle
    //     visually animate old -> new
    //
    // The DOM reaches its final state immediately, so dashboard
    // state remains deterministic while the presentation glides.
    // ========================================================

    function d15gAnimateSlot(
        slot,
        before,
        after
    ) {
        if (
            !slot
            ||
            !before
            ||
            !after
            ||
            before.width <= 0
            ||
            before.height <= 0
            ||
            after.width <= 0
            ||
            after.height <= 0
        ) {
            return;
        }


        const dx =
            before.left
            -
            after.left;


        const dy =
            before.top
            -
            after.top;


        const sx =
            before.width
            /
            after.width;


        const sy =
            before.height
            /
            after.height;


        if (
            Math.abs(dx) < .5
            &&
            Math.abs(dy) < .5
            &&
            Math.abs(sx - 1) < .002
            &&
            Math.abs(sy - 1) < .002
        ) {
            return;
        }


        const animation =
            slot.animate(
                [
                    {
                        transformOrigin:
                            "top left",

                        transform:
                            `translate3d(${dx}px, ${dy}px, 0) `
                            +
                            `scale(${sx}, ${sy})`,
                    },

                    {
                        offset:
                            .68,

                        transformOrigin:
                            "top left",

                        transform:
                            "translate3d(0, 0, 0) "
                            +
                            "scale(1.008, 1.008)",
                    },

                    {
                        transformOrigin:
                            "top left",

                        transform:
                            "translate3d(0, 0, 0) "
                            +
                            "scale(1, 1)",
                    },
                ],
                {
                    duration:
                        430,

                    easing:
                        "cubic-bezier(.22, 1, .36, 1)",

                    fill:
                        "both",
                }
            );


        /*
         * Remove the animation-owned transform once finished so
         * normal workspace drag logic remains completely clean.
         */
        animation.addEventListener(
            "finish",
            () => {
                animation.cancel();
            },
            {
                once: true,
            }
        );
    }


    function d15gAnimateRestoredWindows(
        snapshot,
        activeTile
    ) {
        let order =
            0;


        for (
            const entry
            of snapshot
        ) {
            if (
                !entry.tile
                ||
                entry.tile
                === activeTile
            ) {
                continue;
            }


            const tile =
                entry.tile;


            tile.animate(
                [
                    {
                        opacity:
                            0,

                        transform:
                            "scale(.975)",
                    },

                    {
                        opacity:
                            1,

                        transform:
                            "scale(1)",
                    },
                ],
                {
                    duration:
                        280,

                    delay:
                        85
                        +
                        order * 22,

                    easing:
                        "cubic-bezier(.22, 1, .36, 1)",

                    fill:
                        "backwards",
                }
            );


            order +=
                1;
        }
    }


    function d15fEnterMaximize(
        tile
    ) {
        if (
            maximizeState
            ||
            !tile
        ) {
            return;
        }


        const workspace =
            d15fWorkspace();


        const slots =
            d15fSlots();


        const activeSlot =
            tile.closest(
                ".workspace-slot"
            );


        if (
            !workspace
            ||
            slots.length < 4
            ||
            !activeSlot
        ) {
            return;
        }


        /*
         * D15G:
         * Geometry before changing from 2x2 -> 1x1.
         */
        const d15gBeforeMaximize =
            activeSlot
                .getBoundingClientRect();


        /*
         * Save ONLY the windows currently visible in the 2x2
         * workspace and their exact slot positions.
         */
        const snapshot =
            slots
                .map(
                    (slot, index) => ({
                        index,
                        tile:
                            d15fTileInSlot(
                                slot
                            ),
                    })
                )
                .filter(
                    (entry) =>
                        Boolean(
                            entry.tile
                        )
                );


        maximizeState = {
            tile,
            activeSlot,
            snapshot,
        };


        /*
         * Protect the user's manual layout from older layout
         * normalizers.
         */
        try {
            if (
                typeof d7hWorkspaceManualLayout
                    !== "undefined"
            ) {
                d7hWorkspaceManualLayout =
                    true;
            }
        }

        catch (_) {}


        /*
         * Park only the OTHER windows that were open.
         *
         * Windows already in the dock are not part of snapshot
         * and are therefore untouched.
         */
        for (
            const entry
            of snapshot
        ) {
            if (
                entry.tile
                !== tile
            ) {
                d15fParkTile(
                    entry.tile
                );
            }
        }


        workspace.classList.add(
            "d15f-maximized-workspace"
        );


        activeSlot.classList.add(
            "d15f-maximized-slot"
        );


        tile.classList.add(
            "d15f-maximized-tile"
        );


        document.body.classList.add(
            "d15f-workspace-maximized"
        );


        /*
         * Force layout after the real maximize state has been
         * applied, then animate from the old quadrant geometry.
         */
        const d15gAfterMaximize =
            activeSlot
                .getBoundingClientRect();


        d15gAnimateSlot(
            activeSlot,
            d15gBeforeMaximize,
            d15gAfterMaximize
        );


        const button =
            tile.querySelector(
                ".d15f-maximize-button"
            );


        if (button) {
            d15fUpdateButton(
                button,
                true
            );
        }


        d15fSyncSlots();
        d15fSyncDock();
    }


    function d15fExitMaximize() {
        if (!maximizeState) {
            return;
        }


        const {
            tile,
            activeSlot,
            snapshot,
        } = maximizeState;


        const workspace =
            d15fWorkspace();


        /*
         * D15G:
         * Geometry while the active slot still fills the entire
         * workspace.
         */
        const d15gBeforeRestore =
            activeSlot
                ?.getBoundingClientRect();


        /*
         * Remove fullscreen layout first, then put only the
         * original workspace windows back.
         */
        workspace
            ?.classList.remove(
                "d15f-maximized-workspace"
            );


        activeSlot
            ?.classList.remove(
                "d15f-maximized-slot"
            );


        tile
            ?.classList.remove(
                "d15f-maximized-tile"
            );


        document.body.classList.remove(
            "d15f-workspace-maximized"
        );


        const slots =
            d15fSlots();


        for (
            const entry
            of snapshot
        ) {
            const slot =
                slots[
                    entry.index
                ];


            if (
                slot
                &&
                entry.tile
            ) {
                d15fRestoreTile(
                    entry.tile,
                    slot
                );
            }
        }


        /*
         * Layout is now back to 2x2. Animate the active window
         * smoothly from the fullscreen rectangle into its saved
         * quadrant.
         */
        const d15gAfterRestore =
            activeSlot
                ?.getBoundingClientRect();


        d15gAnimateSlot(
            activeSlot,
            d15gBeforeRestore,
            d15gAfterRestore
        );


        /*
         * The other windows return with a restrained fade/scale
         * rather than abruptly popping into existence.
         */
        d15gAnimateRestoredWindows(
            snapshot,
            tile
        );


        const button =
            tile
                ?.querySelector(
                    ".d15f-maximize-button"
                );


        if (button) {
            d15fUpdateButton(
                button,
                false
            );
        }


        maximizeState =
            null;


        d15fSyncSlots();
        d15fSyncDock();
    }


    function d15fToggle(
        tile
    ) {
        if (
            maximizeState
            &&
            maximizeState.tile
            === tile
        ) {
            d15fExitMaximize();
            return;
        }


        if (!maximizeState) {
            d15fEnterMaximize(
                tile
            );
        }
    }


    function d15fInstallButton(
        tile
    ) {
        if (!tile) {
            return;
        }


        const header =
            tile.querySelector(
                ".workspace-tile-header"
            );


        if (
            !header
            ||
            header.querySelector(
                ".d15f-maximize-button"
            )
        ) {
            return;
        }


        const button =
            document.createElement(
                "button"
            );


        button.type =
            "button";


        button.className =
            "d15f-maximize-button";


        button.innerHTML =
            d15fButtonMarkup();


        d15fUpdateButton(
            button,
            false
        );


        /*
         * The entire header is normally D7H's drag handle.
         * Stop this button from initiating a window drag.
         */
        button.addEventListener(
            "pointerdown",
            (event) => {
                event.stopPropagation();
            }
        );


        button.addEventListener(
            "click",
            (event) => {
                event.preventDefault();
                event.stopPropagation();


                d15fToggle(
                    tile
                );
            }
        );


        header.appendChild(
            button
        );
    }


    function d15fScanButtons() {
        document
            .querySelectorAll(
                "#mediaWorkspace .workspace-tile"
            )
            .forEach(
                d15fInstallButton
            );
    }


    function d15fInstall() {
        d15fScanButtons();


        const workspace =
            d15fWorkspace();


        if (workspace) {
            new MutationObserver(
                d15fScanButtons
            ).observe(
                workspace,
                {
                    childList: true,
                    subtree: true,
                }
            );
        }


        /*
         * While one tile fills the workspace, do not allow the
         * fullscreen tile header to accidentally enter D7H
         * rearrange mode.
         */
        document.addEventListener(
            "pointerdown",
            (event) => {
                if (!maximizeState) {
                    return;
                }


                if (
                    event.target.closest(
                        ".d15f-maximize-button"
                    )
                ) {
                    return;
                }


                if (
                    event.target.closest(
                        ".workspace-tile-header"
                    )
                ) {
                    event.stopPropagation();
                }
            },
            true
        );
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            d15fInstall,
            {
                once: true,
            }
        );
    }

    else {
        d15fInstall();
    }
})();

// ============================================================
// D15K_DRAGGABLE_SIDE_RAIL_LAYOUT
//
// The horizontal accent bars become drag handles for:
//
//     left  = main control sidebar
//     right = window dock
//
// The central workspace is not directly draggable. It moves
// automatically as either sidebar is reordered.
//
// Valid layouts are all permutations of:
//
//     left / main / right
//
// Layout order is browser-local and persists across refreshes.
// ============================================================

(() => {
    "use strict";


    const STORAGE_KEY =
        "cameraPoseTeleop.d15kRailOrder";


    const DEFAULT_ORDER = [
        "left",
        "main",
        "right",
    ];


    let refs =
        null;


    let order = [
        ...DEFAULT_ORDER,
    ];


    let drag =
        null;


    const flipAnimations =
        new WeakMap();


    // --------------------------------------------------------
    // DOM
    // --------------------------------------------------------

    function d15kRefs() {
        const shell =
            document.querySelector(
                ".app-shell"
            );


        const left =
            document.querySelector(
                ".sidebar"
            );


        const main =
            document.querySelector(
                ".main"
            );


        const right =
            document.getElementById(
                "d15WindowDock"
            );


        if (
            !shell
            ||
            !left
            ||
            !main
            ||
            !right
        ) {
            return null;
        }


        return {
            shell,
            left,
            main,
            right,
        };
    }


    function d15kElement(
        key
    ) {
        return refs?.[key]
            || null;
    }


    // --------------------------------------------------------
    // ORDER
    // --------------------------------------------------------

    function d15kValidOrder(
        value
    ) {
        if (
            !Array.isArray(
                value
            )
            ||
            value.length !== 3
        ) {
            return false;
        }


        return (
            value.includes("left")
            &&
            value.includes("main")
            &&
            value.includes("right")
            &&
            new Set(value).size === 3
        );
    }


    function d15kLoadOrder() {
        try {
            const saved =
                JSON.parse(
                    localStorage.getItem(
                        STORAGE_KEY
                    )
                    || "null"
                );


            if (
                d15kValidOrder(
                    saved
                )
            ) {
                return saved;
            }
        }

        catch (_) {
            // Invalid local state simply falls back to default.
        }


        return [
            ...DEFAULT_ORDER,
        ];
    }


    function d15kSaveOrder() {
        try {
            localStorage.setItem(
                STORAGE_KEY,
                JSON.stringify(
                    order
                )
            );
        }

        catch (_) {
            // Layout still works if browser storage is blocked.
        }
    }


    // --------------------------------------------------------
    // FLIP ANIMATION
    // --------------------------------------------------------

    function d15kCaptureRects() {
        const result =
            new Map();


        for (
            const key
            of [
                "left",
                "main",
                "right",
            ]
        ) {
            const element =
                d15kElement(
                    key
                );


            if (!element) {
                continue;
            }


            result.set(
                element,
                element
                    .getBoundingClientRect()
            );
        }


        return result;
    }


    function d15kAnimateFrom(
        before
    ) {
        for (
            const [
                element,
                oldRect,
            ]
            of before
        ) {
            const newRect =
                element
                    .getBoundingClientRect();


            const dx =
                oldRect.left
                -
                newRect.left;


            const dy =
                oldRect.top
                -
                newRect.top;


            if (
                Math.abs(dx) < .5
                &&
                Math.abs(dy) < .5
            ) {
                continue;
            }


            const previous =
                flipAnimations.get(
                    element
                );


            previous?.cancel();


            const animation =
                element.animate(
                    [
                        {
                            transform:
                                `translate3d(${dx}px, ${dy}px, 0)`,
                        },

                        {
                            offset:
                                .72,

                            transform:
                                "translate3d(0, 0, 0)",
                        },

                        {
                            transform:
                                "translate3d(0, 0, 0)",
                        },
                    ],
                    {
                        duration:
                            420,

                        easing:
                            "cubic-bezier(.22, 1, .36, 1)",

                        fill:
                            "both",
                    }
                );


            flipAnimations.set(
                element,
                animation
            );


            animation.addEventListener(
                "finish",
                () => {
                    if (
                        flipAnimations.get(
                            element
                        )
                        === animation
                    ) {
                        flipAnimations.delete(
                            element
                        );
                    }


                    animation.cancel();
                },
                {
                    once: true,
                }
            );
        }
    }


    // --------------------------------------------------------
    // APPLY GRID ORDER
    // --------------------------------------------------------

    function d15kColumnTrack(
        key
    ) {
        if (
            key === "left"
        ) {
            return "var(--st-sidebar)";
        }


        if (
            key === "right"
        ) {
            return "var(--d15-dock-width)";
        }


        return "minmax(0, 1fr)";
    }


    function d15kApplyOrder(
        next,
        animate = true
    ) {
        if (
            !refs
            ||
            !d15kValidOrder(
                next
            )
        ) {
            return;
        }


        const before =
            animate
                ?
                d15kCaptureRects()
                :
                null;


        order = [
            ...next,
        ];


        refs.shell.style.setProperty(
            "grid-template-columns",
            order
                .map(
                    d15kColumnTrack
                )
                .join(" "),
            "important"
        );


        order.forEach(
            (
                key,
                index
            ) => {
                const element =
                    d15kElement(
                        key
                    );


                element?.style.setProperty(
                    "grid-column",
                    String(
                        index + 1
                    ),
                    "important"
                );


                element?.style.setProperty(
                    "grid-row",
                    "2",
                    "important"
                );
            }
        );


        /*
         * Force the new grid geometry before FLIP measurement.
         */
        refs.shell
            .getBoundingClientRect();


        if (
            animate
            &&
            before
        ) {
            d15kAnimateFrom(
                before
            );
        }
    }


    // --------------------------------------------------------
    // LEFT HANDLE
    // --------------------------------------------------------

    function d15kEnsureLeftHandle() {
        let handle =
            refs.left.querySelector(
                ".d15k-left-rail-handle"
            );


        if (handle) {
            return handle;
        }


        handle =
            document.createElement(
                "button"
            );


        handle.type =
            "button";


        handle.className =
            "d15k-left-rail-handle";


        handle.title =
            "Drag sidebar";


        handle.setAttribute(
            "aria-label",
            "Move left sidebar"
        );


        handle.innerHTML =
            `
            <span
                class="d15k-left-rail-grip"
                aria-hidden="true"
            ></span>
            `;


        refs.left.appendChild(
            handle
        );


        return handle;
    }


    // --------------------------------------------------------
    // DRAG GHOST
    // --------------------------------------------------------

    function d15kCreateGhost(
        key
    ) {
        const ghost =
            document.createElement(
                "div"
            );


        ghost.className =
            "d15k-rail-drag-ghost";


        ghost.innerHTML =
            `
            <span class="d15k-rail-drag-ghost-grip"></span>
            <span>
                ${
                    key === "left"
                        ?
                        "CONTROL SIDEBAR"
                        :
                        "WINDOW DOCK"
                }
            </span>
            `;


        document.body.appendChild(
            ghost
        );


        return ghost;
    }


    function d15kMoveGhost(
        ghost,
        event
    ) {
        ghost.style.left =
            `${event.clientX}px`;


        ghost.style.top =
            `${event.clientY}px`;
    }


    // --------------------------------------------------------
    // DETERMINE WHICH OF THE THREE HORIZONTAL POSITIONS
    // THE USER IS CURRENTLY TARGETING.
    // --------------------------------------------------------

    function d15kTargetIndex(
        clientX
    ) {
        const rect =
            refs.shell
                .getBoundingClientRect();


        const ratio =
            Math.max(
                0,
                Math.min(
                    .999999,
                    (
                        clientX
                        -
                        rect.left
                    )
                    /
                    Math.max(
                        1,
                        rect.width
                    )
                )
            );


        if (
            ratio < 1 / 3
        ) {
            return 0;
        }


        if (
            ratio < 2 / 3
        ) {
            return 1;
        }


        return 2;
    }


    function d15kCandidateOrder(
        key,
        index,
        startOrder
    ) {
        const result =
            startOrder.filter(
                (item) =>
                    item !== key
            );


        result.splice(
            index,
            0,
            key
        );


        return result;
    }


    function d15kSameOrder(
        a,
        b
    ) {
        return (
            a.length === b.length
            &&
            a.every(
                (
                    value,
                    index
                ) =>
                    value === b[index]
            )
        );
    }


    // --------------------------------------------------------
    // DRAG LIFECYCLE
    // --------------------------------------------------------

    function d15kBeginDrag(
        key,
        handle,
        event
    ) {
        if (
            event.button !== 0
        ) {
            return;
        }


        event.preventDefault();
        event.stopPropagation();


        drag = {
            key,

            pointerId:
                event.pointerId,

            handle,

            startOrder: [
                ...order,
            ],

            candidateOrder: [
                ...order,
            ],

            ghost:
                d15kCreateGhost(
                    key
                ),
        };


        document.body.classList.add(
            "d15k-rail-dragging"
        );


        handle.classList.add(
            "d15k-rail-handle-active"
        );


        try {
            handle.setPointerCapture(
                event.pointerId
            );
        }

        catch (_) {
            // Enhancement only.
        }


        d15kMoveGhost(
            drag.ghost,
            event
        );
    }


    function d15kMoveDrag(
        event
    ) {
        if (
            !drag
            ||
            drag.pointerId
            !== event.pointerId
        ) {
            return;
        }


        event.preventDefault();


        d15kMoveGhost(
            drag.ghost,
            event
        );


        const index =
            d15kTargetIndex(
                event.clientX
            );


        const candidate =
            d15kCandidateOrder(
                drag.key,
                index,
                drag.startOrder
            );


        if (
            d15kSameOrder(
                candidate,
                drag.candidateOrder
            )
        ) {
            return;
        }


        drag.candidateOrder = [
            ...candidate,
        ];


        /*
         * Live preview:
         * the real UI smoothly rearranges while the grip is
         * being dragged.
         */
        d15kApplyOrder(
            candidate,
            true
        );
    }


    function d15kCleanupDrag() {
        if (!drag) {
            return;
        }


        drag.handle.classList.remove(
            "d15k-rail-handle-active"
        );


        drag.ghost?.remove();


        document.body.classList.remove(
            "d15k-rail-dragging"
        );


        drag =
            null;
    }


    function d15kFinishDrag(
        event
    ) {
        if (
            !drag
            ||
            drag.pointerId
            !== event.pointerId
        ) {
            return;
        }


        try {
            drag.handle
                .releasePointerCapture(
                    event.pointerId
                );
        }

        catch (_) {}


        /*
         * The currently previewed order becomes permanent.
         */
        d15kSaveOrder();


        d15kCleanupDrag();
    }


    function d15kCancelDrag(
        event
    ) {
        if (
            !drag
            ||
            drag.pointerId
            !== event.pointerId
        ) {
            return;
        }


        const original = [
            ...drag.startOrder,
        ];


        try {
            drag.handle
                .releasePointerCapture(
                    event.pointerId
                );
        }

        catch (_) {}


        d15kApplyOrder(
            original,
            true
        );


        d15kCleanupDrag();
    }


    function d15kBindHandle(
        handle,
        key
    ) {
        if (
            !handle
            ||
            handle.dataset.d15kBound
            === "1"
        ) {
            return;
        }


        handle.dataset.d15kBound =
            "1";


        handle.style.touchAction =
            "none";


        handle.addEventListener(
            "pointerdown",
            (event) => {
                d15kBeginDrag(
                    key,
                    handle,
                    event
                );
            }
        );


        handle.addEventListener(
            "pointermove",
            d15kMoveDrag
        );


        handle.addEventListener(
            "pointerup",
            d15kFinishDrag
        );


        handle.addEventListener(
            "pointercancel",
            d15kCancelDrag
        );


        handle.addEventListener(
            "lostpointercapture",
            (event) => {
                /*
                 * Normal pointerup already cleaned the state.
                 */
                if (
                    drag
                    &&
                    drag.pointerId
                    === event.pointerId
                ) {
                    d15kFinishDrag(
                        event
                    );
                }
            }
        );
    }


    // --------------------------------------------------------
    // INSTALL
    // --------------------------------------------------------

    function d15kInstall() {
        refs =
            d15kRefs();


        if (!refs) {
            return false;
        }


        const leftHandle =
            d15kEnsureLeftHandle();


        const rightHandle =
            refs.right.querySelector(
                ".d15-dock-grip"
            );


        if (!rightHandle) {
            return false;
        }


        rightHandle.setAttribute(
            "role",
            "button"
        );


        rightHandle.setAttribute(
            "aria-label",
            "Move window dock"
        );


        rightHandle.title =
            "Drag window dock";


        d15kBindHandle(
            leftHandle,
            "left"
        );


        d15kBindHandle(
            rightHandle,
            "right"
        );


        order =
            d15kLoadOrder();


        d15kApplyOrder(
            order,
            false
        );


        document.body.classList.add(
            "d15k-rail-reorder-ready"
        );


        return true;
    }


    function d15kBoot(
        attempt = 0
    ) {
        if (
            d15kInstall()
        ) {
            return;
        }


        /*
         * D15 dock is created dynamically.
         * Retry only during startup.
         */
        if (
            attempt < 60
        ) {
            window.setTimeout(
                () => {
                    d15kBoot(
                        attempt + 1
                    );
                },
                100
            );
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                d15kBoot();
            },
            {
                once: true,
            }
        );
    }

    else {
        d15kBoot();
    }
})();

// ============================================================
// D15L_PHYSICAL_RAIL_DRAG
//
// Replaces D15K's small drag ghost with the ACTUAL sidebar.
//
// During drag:
//     actual sidebar follows pointer horizontally
//
// On release:
//     sidebar snaps smoothly into one of the three valid
//     horizontal positions.
//
// Existing D15K persisted order key is preserved.
// ============================================================

(() => {
    "use strict";


    const STORAGE_KEY =
        "cameraPoseTeleop.d15kRailOrder";


    let drag =
        null;


    const animations =
        new WeakMap();


    function refs() {
        return {
            shell:
                document.querySelector(
                    ".app-shell"
                ),

            left:
                document.querySelector(
                    ".sidebar"
                ),

            main:
                document.querySelector(
                    ".main"
                ),

            right:
                document.getElementById(
                    "d15WindowDock"
                ),
        };
    }


    function validRefs(
        r
    ) {
        return Boolean(
            r.shell
            &&
            r.left
            &&
            r.main
            &&
            r.right
        );
    }


    function elementFor(
        r,
        key
    ) {
        return r[key]
            || null;
    }


    function keyFor(
        r,
        element
    ) {
        if (
            element === r.left
        ) {
            return "left";
        }


        if (
            element === r.main
        ) {
            return "main";
        }


        if (
            element === r.right
        ) {
            return "right";
        }


        return null;
    }


    function currentOrder(
        r
    ) {
        return [
            r.left,
            r.main,
            r.right,
        ]
        .map(
            (element) => ({
                element,
                rect:
                    element
                        .getBoundingClientRect(),
            })
        )
        .sort(
            (a, b) =>
                a.rect.left
                -
                b.rect.left
        )
        .map(
            (entry) =>
                keyFor(
                    r,
                    entry.element
                )
        );
    }


    function columnTrack(
        key
    ) {
        if (
            key === "left"
        ) {
            return "var(--st-sidebar)";
        }


        if (
            key === "right"
        ) {
            return "var(--d15-dock-width)";
        }


        return "minmax(0, 1fr)";
    }


    function saveOrder(
        order
    ) {
        try {
            localStorage.setItem(
                STORAGE_KEY,
                JSON.stringify(
                    order
                )
            );
        }

        catch (_) {
            // Persistence is optional.
        }
    }


    function applyOrder(
        r,
        order
    ) {
        r.shell.style.setProperty(
            "grid-template-columns",
            order
                .map(
                    columnTrack
                )
                .join(" "),
            "important"
        );


        order.forEach(
            (
                key,
                index
            ) => {
                const element =
                    elementFor(
                        r,
                        key
                    );


                element.style.setProperty(
                    "grid-column",
                    String(
                        index + 1
                    ),
                    "important"
                );


                element.style.setProperty(
                    "grid-row",
                    "2",
                    "important"
                );
            }
        );
    }


    function captureRects(
        r
    ) {
        const result =
            new Map();


        for (
            const element
            of [
                r.left,
                r.main,
                r.right,
            ]
        ) {
            result.set(
                element,
                element
                    .getBoundingClientRect()
            );
        }


        return result;
    }


    function animateFrom(
        before
    ) {
        for (
            const [
                element,
                oldRect,
            ]
            of before
        ) {
            const newRect =
                element
                    .getBoundingClientRect();


            const dx =
                oldRect.left
                -
                newRect.left;


            const dy =
                oldRect.top
                -
                newRect.top;


            if (
                Math.abs(dx) < .5
                &&
                Math.abs(dy) < .5
            ) {
                continue;
            }


            animations
                .get(
                    element
                )
                ?.cancel();


            const animation =
                element.animate(
                    [
                        {
                            transform:
                                `translate3d(${dx}px, ${dy}px, 0)`,
                        },

                        {
                            offset:
                                .76,

                            transform:
                                "translate3d(0, 0, 0)",
                        },

                        {
                            transform:
                                "translate3d(0, 0, 0)",
                        },
                    ],
                    {
                        duration:
                            390,

                        easing:
                            "cubic-bezier(.22, 1, .36, 1)",

                        fill:
                            "both",
                    }
                );


            animations.set(
                element,
                animation
            );


            animation.addEventListener(
                "finish",
                () => {
                    if (
                        animations.get(
                            element
                        )
                        === animation
                    ) {
                        animations.delete(
                            element
                        );
                    }


                    animation.cancel();
                },
                {
                    once: true,
                }
            );
        }
    }


    /*
     * Determine insertion position relative to the CENTERS of
     * the two elements that are not currently being dragged.
     *
     * This is more natural than dividing the screen into thirds,
     * especially because the two sidebars have different widths.
     */
    function targetIndex(
        event,
        r,
        draggedKey,
        startOrder
    ) {
        const otherKeys =
            startOrder.filter(
                (key) =>
                    key !== draggedKey
            );


        const centers =
            otherKeys.map(
                (key) => {
                    const rect =
                        elementFor(
                            r,
                            key
                        )
                        .getBoundingClientRect();


                    return (
                        rect.left
                        +
                        rect.width / 2
                    );
                }
            );


        if (
            event.clientX
            <
            centers[0]
        ) {
            return 0;
        }


        if (
            event.clientX
            <
            centers[1]
        ) {
            return 1;
        }


        return 2;
    }


    function orderWith(
        key,
        target,
        startOrder
    ) {
        const result =
            startOrder.filter(
                (item) =>
                    item !== key
            );


        result.splice(
            target,
            0,
            key
        );


        return result;
    }


    function cleanup() {
        if (!drag) {
            return;
        }


        drag.rail.classList.remove(
            "d15l-rail-following"
        );


        drag.handle.classList.remove(
            "d15l-active-rail-handle"
        );


        drag.rail.style.removeProperty(
            "--d15l-drag-x"
        );


        document.body.classList.remove(
            "d15l-physical-rail-drag"
        );


        drag =
            null;
    }


    // ========================================================
    // D15M_LIVE_RAIL_REFLOW
    //
    // The dragged rail stays attached to the cursor while the
    // OTHER two real dashboard surfaces FLIP into their new
    // columns immediately when the pointer crosses a valid
    // insertion position.
    // ========================================================

    function d15mSameOrder(
        a,
        b
    ) {
        return (
            a.length === b.length
            &&
            a.every(
                (
                    value,
                    index
                ) =>
                    value === b[index]
            )
        );
    }


    function d15mAnimateOthers(
        before,
        draggedRail
    ) {
        for (
            const [
                element,
                oldRect,
            ]
            of before
        ) {
            /*
             * Never animate the rail currently in the hand.
             * Its transform is owned directly by the pointer.
             */
            if (
                element === draggedRail
            ) {
                continue;
            }


            const newRect =
                element
                    .getBoundingClientRect();


            const dx =
                oldRect.left
                -
                newRect.left;


            const dy =
                oldRect.top
                -
                newRect.top;


            if (
                Math.abs(dx) < .5
                &&
                Math.abs(dy) < .5
            ) {
                continue;
            }


            animations
                .get(
                    element
                )
                ?.cancel();


            const animation =
                element.animate(
                    [
                        {
                            transform:
                                `translate3d(${dx}px, ${dy}px, 0)`,
                        },

                        {
                            offset:
                                .74,

                            transform:
                                "translate3d(0, 0, 0)",
                        },

                        {
                            transform:
                                "translate3d(0, 0, 0)",
                        },
                    ],
                    {
                        duration:
                            360,

                        easing:
                            "cubic-bezier(.22, 1, .36, 1)",

                        fill:
                            "both",
                    }
                );


            animations.set(
                element,
                animation
            );


            animation.addEventListener(
                "finish",
                () => {
                    if (
                        animations.get(
                            element
                        )
                        === animation
                    ) {
                        animations.delete(
                            element
                        );
                    }


                    animation.cancel();
                },
                {
                    once: true,
                }
            );
        }
    }


    function onMove(
        event
    ) {
        if (
            !drag
            ||
            event.pointerId
            !== drag.pointerId
        ) {
            return;
        }


        event.preventDefault();
        event.stopImmediatePropagation();


        /*
         * Where the LEFT EDGE of the real rail should currently
         * be so the original grab point remains under the mouse.
         */
        const desiredLeft =
            event.clientX
            -
            drag.grabOffset;


        const target =
            targetIndex(
                event,
                drag.refs,
                drag.key,
                drag.startOrder
            );


        const candidate =
            orderWith(
                drag.key,
                target,
                drag.startOrder
            );


        /*
         * D15M — LIVE REFLOW
         *
         * As soon as the cursor crosses into a different valid
         * insertion position, change the REAL grid immediately.
         */
        if (
            !d15mSameOrder(
                candidate,
                drag.currentOrder
            )
        ) {
            /*
             * Capture where everything is visually located now.
             * The dragged rail is excluded from the following
             * FLIP animation.
             */
            const before =
                captureRects(
                    drag.refs
                );


            /*
             * Temporarily remove its manual translation so its
             * new underlying grid position can be measured.
             *
             * This all happens in one pointer event before the
             * browser paints, so there is no visible jump.
             */
            drag.rail.style.setProperty(
                "--d15l-drag-x",
                "0px"
            );


            applyOrder(
                drag.refs,
                candidate
            );


            /*
             * Force the new CSS-grid geometry to resolve.
             */
            drag.refs.shell
                .getBoundingClientRect();


            drag.baseLeft =
                drag.rail
                    .getBoundingClientRect()
                    .left;


            /*
             * Put the REAL rail straight back under the mouse,
             * now relative to its NEW grid column.
             */
            const newDx =
                desiredLeft
                -
                drag.baseLeft;


            drag.rail.style.setProperty(
                "--d15l-drag-x",
                `${newDx}px`
            );


            /*
             * Main workspace + non-dragged rail smoothly glide
             * to make room in real time.
             */
            d15mAnimateOthers(
                before,
                drag.rail
            );


            drag.currentOrder = [
                ...candidate,
            ];


            drag.targetOrder = [
                ...candidate,
            ];
        }

        else {
            /*
             * Same accepted position: simply keep the actual rail
             * attached to the pointer.
             */
            const dx =
                desiredLeft
                -
                drag.baseLeft;


            drag.rail.style.setProperty(
                "--d15l-drag-x",
                `${dx}px`
            );


            drag.targetOrder = [
                ...candidate,
            ];
        }
    }


    function finish(
        event,
        cancelled = false
    ) {
        if (
            !drag
            ||
            event.pointerId
            !== drag.pointerId
        ) {
            return;
        }


        event.preventDefault();
        event.stopImmediatePropagation();


        /*
         * IMPORTANT:
         *
         * Capture the current VISUAL location while the actual
         * sidebar is still following the cursor.
         */
        const before =
            captureRects(
                drag.refs
            );


        const finalOrder =
            cancelled
                ?
                drag.startOrder
                :
                drag.targetOrder;


        /*
         * Remove the manual cursor transform, apply the final
         * grid order, then FLIP all three real surfaces from
         * their current visual positions into the accepted slots.
         */
        drag.rail.classList.remove(
            "d15l-rail-following"
        );


        drag.rail.style.removeProperty(
            "--d15l-drag-x"
        );


        applyOrder(
            drag.refs,
            finalOrder
        );


        drag.refs.shell
            .getBoundingClientRect();


        animateFrom(
            before
        );


        if (!cancelled) {
            saveOrder(
                finalOrder
            );
        }


        try {
            drag.handle
                .releasePointerCapture(
                    event.pointerId
                );
        }

        catch (_) {
            // Safe to ignore.
        }


        cleanup();


        document.removeEventListener(
            "pointermove",
            onMove,
            true
        );


        document.removeEventListener(
            "pointerup",
            onUp,
            true
        );


        document.removeEventListener(
            "pointercancel",
            onCancel,
            true
        );
    }


    function onUp(
        event
    ) {
        finish(
            event,
            false
        );
    }


    function onCancel(
        event
    ) {
        finish(
            event,
            true
        );
    }


    function begin(
        event,
        key,
        handle,
        rail
    ) {
        if (
            event.button !== 0
            ||
            drag
        ) {
            return;
        }


        /*
         * Capture-phase interception prevents D15K's older
         * ghost-drag implementation from starting.
         */
        event.preventDefault();
        event.stopImmediatePropagation();


        const r =
            refs();


        if (
            !validRefs(
                r
            )
        ) {
            return;
        }


        const startOrder =
            currentOrder(
                r
            );


        drag = {
            pointerId:
                event.pointerId,

            key,

            handle,

            rail,

            refs:
                r,

            startX:
                event.clientX,

            /*
             * D15M — preserve the exact point where the user
             * grabbed the real rail.
             */
            grabOffset:
                event.clientX
                -
                rail.getBoundingClientRect().left,

            /*
             * Untransformed grid position of the rail.
             * Updated each time the live grid order changes.
             */
            baseLeft:
                rail.getBoundingClientRect().left,

            startOrder,

            currentOrder: [
                ...startOrder,
            ],

            targetOrder: [
                ...startOrder,
            ],
        };


        rail.classList.add(
            "d15l-rail-following"
        );


        handle.classList.add(
            "d15l-active-rail-handle"
        );


        document.body.classList.add(
            "d15l-physical-rail-drag"
        );


        try {
            handle.setPointerCapture(
                event.pointerId
            );
        }

        catch (_) {
            // Enhancement only.
        }


        document.addEventListener(
            "pointermove",
            onMove,
            true
        );


        document.addEventListener(
            "pointerup",
            onUp,
            true
        );


        document.addEventListener(
            "pointercancel",
            onCancel,
            true
        );
    }


    function bind(
        handle,
        key,
        rail
    ) {
        if (
            !handle
            ||
            handle.dataset.d15lBound
            === "1"
        ) {
            return;
        }


        handle.dataset.d15lBound =
            "1";


        handle.addEventListener(
            "pointerdown",
            (event) => {
                begin(
                    event,
                    key,
                    handle,
                    rail
                );
            },
            true
        );
    }


    function install() {
        const r =
            refs();


        if (
            !validRefs(
                r
            )
        ) {
            return false;
        }


        const leftHandle =
            r.left.querySelector(
                ".d15k-left-rail-handle"
            );


        const rightHandle =
            r.right.querySelector(
                ".d15-dock-grip"
            );


        if (
            !leftHandle
            ||
            !rightHandle
        ) {
            return false;
        }


        bind(
            leftHandle,
            "left",
            r.left
        );


        bind(
            rightHandle,
            "right",
            r.right
        );


        document.body.classList.add(
            "d15l-physical-rail-ready"
        );


        return true;
    }


    function boot(
        attempt = 0
    ) {
        if (
            install()
        ) {
            return;
        }


        if (
            attempt < 60
        ) {
            window.setTimeout(
                () => {
                    boot(
                        attempt + 1
                    );
                },
                100
            );
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                boot();
            },
            {
                once: true,
            }
        );
    }

    else {
        boot();
    }
})();

// ============================================================
// D15N_COMPACT_LEFT_SIDEBAR
//
// 1. Repairs the fullscreen restore icon so it uses the same
//    top-left / bottom-right diagonal as maximize.
//
// 2. Adds a compact left-sidebar mode equal in width to the
//    D15 window dock.
//
// Compact UI proxies the EXISTING dashboard controls.
// It does not create new backend/system behavior.
// ============================================================

(() => {
    "use strict";


    const STORAGE_KEY =
        "cameraPoseTeleop.d15nLeftCompact";


    let sidebar =
        null;


    let panel =
        null;


    let toggleButton =
        null;


    let syncQueued =
        false;


    const layoutAnimations =
        new WeakMap();


    const STATUS_NAMES = [
        "System",
        "Simulation",
        "SONIC",
        "Camera",
        "Alignment",
        "Tracking",
    ];


    const ICON = {
        live: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.7"
                 stroke-linecap="round"
                 stroke-linejoin="round">
                <rect x="4" y="5"
                      width="16" height="13"
                      rx="2"/>
                <path d="M9 21h6"/>
                <path d="M12 18v3"/>
                <circle cx="12" cy="11.5"
                        r="2.3"/>
            </svg>
        `,

        logs: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.7"
                 stroke-linecap="round">
                <path d="M8 6h11"/>
                <path d="M8 12h11"/>
                <path d="M8 18h11"/>
                <circle cx="4.5" cy="6"
                        r=".8"
                        fill="currentColor"
                        stroke="none"/>
                <circle cx="4.5" cy="12"
                        r=".8"
                        fill="currentColor"
                        stroke="none"/>
                <circle cx="4.5" cy="18"
                        r=".8"
                        fill="currentColor"
                        stroke="none"/>
            </svg>
        `,

        connected: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.8"
                 stroke-linecap="round"
                 stroke-linejoin="round">
                <path d="M9.5 14.5l5-5"/>
                <path d="M7 17H5.5a4 4 0 0 1 0-8H9"/>
                <path d="M15 7h3.5a4 4 0 0 1 0 8H15"/>
            </svg>
        `,

        disconnected: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.8"
                 stroke-linecap="round"
                 stroke-linejoin="round">
                <path d="M8.5 15.5
                         5.5 18.5"/>
                <path d="M15.5 8.5
                         18.5 5.5"/>
                <path d="M7 17H5.5a4 4 0 0 1 0-8H9"/>
                <path d="M15 7h3.5a4 4 0 0 1 0 8H15"/>
                <path d="M4 4l16 16"/>
            </svg>
        `,

        connect: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.7"
                 stroke-linecap="round"
                 stroke-linejoin="round">
                <path d="M8 12h8"/>
                <path d="M12 8l4 4-4 4"/>
                <rect x="3" y="5"
                      width="18" height="14"
                      rx="3"/>
            </svg>
        `,

        disconnect: `
            <svg viewBox="0 0 24 24"
                 fill="none"
                 stroke="currentColor"
                 stroke-width="1.7"
                 stroke-linecap="round"
                 stroke-linejoin="round">
                <path d="M16 12H8"/>
                <path d="M12 8l-4 4 4 4"/>
                <rect x="3" y="5"
                      width="18" height="14"
                      rx="3"/>
            </svg>
        `,
    };


    // --------------------------------------------------------
    // FULLSCREEN RESTORE ICON REPAIR
    // --------------------------------------------------------

    function d15nRepairFullscreenIcons() {
        document
            .querySelectorAll(
                ".d15f-restore-icon svg"
            )
            .forEach(
                (svg) => {
                    if (
                        svg.dataset.d15nFixed
                        === "1"
                    ) {
                        return;
                    }


                    svg.dataset.d15nFixed =
                        "1";


                    /*
                     * Same diagonal as maximize:
                     *
                     *     top-left
                     *          ↘
                     *          ↖
                     *     bottom-right
                     *
                     * but arrows point inward.
                     */
                    svg.innerHTML =
                        `
                        <path d="M4 10h6V4"/>
                        <path d="M3 3l7 7"/>

                        <path d="M20 14h-6v6"/>
                        <path d="M21 21l-7-7"/>
                        `;
                }
            );
    }


    // --------------------------------------------------------
    // ORIGINAL CONTROL DISCOVERY
    // --------------------------------------------------------

    function d15nOriginalTarget() {
        return document.getElementById(
            "systemTargetSelect"
        );
    }


    function d15nOriginalConnectionButton() {
        return sidebar
            ?.querySelector(
                ".robot-connection-toggle"
            )
            || null;
    }


    function d15nOriginalNav(
        label
    ) {
        if (!sidebar) {
            return null;
        }


        return [
            ...sidebar.querySelectorAll(
                ".nav-item"
            ),
        ].find(
            (item) =>
                String(
                    item.textContent
                    || ""
                )
                .trim()
                .toUpperCase()
                === label.toUpperCase()
        )
        || null;
    }


    function d15nLeafByText(
        text
    ) {
        if (!sidebar) {
            return null;
        }


        const expected =
            text
                .trim()
                .toUpperCase();


        return [
            ...sidebar.querySelectorAll(
                "*"
            ),
        ].find(
            (node) => {
                if (
                    panel
                    &&
                    panel.contains(
                        node
                    )
                ) {
                    return false;
                }


                return (
                    node.children.length
                    === 0
                    &&
                    String(
                        node.textContent
                        || ""
                    )
                    .trim()
                    .toUpperCase()
                    === expected
                );
            }
        )
        || null;
    }


    function d15nConnectionText() {
        const explicit =
            sidebar
                ?.querySelector(
                    ".d12n-connection-row"
                );


        if (explicit) {
            const text =
                String(
                    explicit.textContent
                    || ""
                )
                .trim()
                .toUpperCase();


            if (
                text.includes(
                    "CONNECTED"
                )
                &&
                !text.includes(
                    "DISCONNECTED"
                )
            ) {
                return "CONNECTED";
            }


            if (
                text.includes(
                    "DISCONNECTED"
                )
            ) {
                return "DISCONNECTED";
            }
        }


        if (
            d15nLeafByText(
                "CONNECTED"
            )
        ) {
            return "CONNECTED";
        }


        if (
            d15nLeafByText(
                "DISCONNECTED"
            )
        ) {
            return "DISCONNECTED";
        }


        return "UNKNOWN";
    }


    function d15nStatusValue(
        name
    ) {
        const label =
            d15nLeafByText(
                name
            );


        if (!label) {
            return "--";
        }


        let node =
            label.parentElement;


        for (
            let depth = 0;
            depth < 4
            &&
            node
            &&
            node !== sidebar;
            depth += 1
        ) {
            const value =
                String(
                    node.textContent
                    || ""
                )
                .trim()
                .toUpperCase();


            const matches =
                value.match(
                    /\b(OFF|ON|READY|LIVE|RUNNING|IDLE|STARTING|STOPPING|ERROR|FAULT|WAITING)\b/g
                );


            if (
                matches
                &&
                matches.length
            ) {
                return matches[
                    matches.length - 1
                ];
            }


            node =
                node.parentElement;
        }


        return "--";
    }


    // --------------------------------------------------------
    // BUILD COMPACT PANEL
    // --------------------------------------------------------

    function d15nCreateCompactPanel() {
        if (
            panel
            &&
            panel.isConnected
        ) {
            return panel;
        }


        panel =
            document.createElement(
                "div"
            );


        panel.className =
            "d15n-compact-panel";


        panel.innerHTML =
            `
            <div class="d15n-mini-nav">
                <button
                    type="button"
                    class="d15n-mini-button d15n-mini-live"
                    title="Live"
                    aria-label="Live"
                >
                    ${ICON.live}
                </button>

                <button
                    type="button"
                    class="d15n-mini-button d15n-mini-logs"
                    title="Logs"
                    aria-label="Logs"
                >
                    ${ICON.logs}
                </button>
            </div>


            <select
                class="d15n-mini-target"
                title="System target"
                aria-label="System target"
            ></select>


            <div class="d15n-mini-connection">
                <div
                    class="d15n-mini-connection-state"
                    title="Connection status"
                ></div>

                <button
                    type="button"
                    class="d15n-mini-button d15n-mini-connect-action"
                    aria-label="Connect"
                ></button>
            </div>


            <div
                class="d15n-mini-status-grid"
                aria-label="System component status"
            >
                ${
                    STATUS_NAMES
                        .map(
                            (name) =>
                                `
                                <span
                                    class="d15n-mini-status"
                                    data-d15n-status="${name}"
                                    title="${name}"
                                >
                                    --
                                </span>
                                `
                        )
                        .join("")
                }
            </div>
            `;


        sidebar.appendChild(
            panel
        );


        // ----------------------------------------------------
        // Live
        // ----------------------------------------------------

        panel
            .querySelector(
                ".d15n-mini-live"
            )
            .addEventListener(
                "click",
                () => {
                    d15nOriginalNav(
                        "Live"
                    )
                    ?.click();
                }
            );


        // ----------------------------------------------------
        // Logs
        // ----------------------------------------------------

        panel
            .querySelector(
                ".d15n-mini-logs"
            )
            .addEventListener(
                "click",
                () => {
                    d15nOriginalNav(
                        "Logs"
                    )
                    ?.click();
                }
            );


        // ----------------------------------------------------
        // Target
        // ----------------------------------------------------

        panel
            .querySelector(
                ".d15n-mini-target"
            )
            .addEventListener(
                "change",
                (event) => {
                    const original =
                        d15nOriginalTarget();


                    if (!original) {
                        return;
                    }


                    original.value =
                        event.target.value;


                    original.dispatchEvent(
                        new Event(
                            "input",
                            {
                                bubbles: true,
                            }
                        )
                    );


                    original.dispatchEvent(
                        new Event(
                            "change",
                            {
                                bubbles: true,
                            }
                        )
                    );


                    d15nScheduleSync();
                }
            );


        // ----------------------------------------------------
        // Connect / Disconnect
        // ----------------------------------------------------

        panel
            .querySelector(
                ".d15n-mini-connect-action"
            )
            .addEventListener(
                "click",
                () => {
                    const original =
                        d15nOriginalConnectionButton();


                    if (
                        original
                        &&
                        !original.disabled
                    ) {
                        original.click();
                    }
                }
            );


        return panel;
    }


    function d15nCreateToggle() {
        if (
            toggleButton
            &&
            toggleButton.isConnected
        ) {
            return toggleButton;
        }


        toggleButton =
            document.createElement(
                "button"
            );


        toggleButton.type =
            "button";


        toggleButton.className =
            "d15n-sidebar-toggle";


        toggleButton.title =
            "Minimize sidebar";


        toggleButton.setAttribute(
            "aria-label",
            "Minimize sidebar"
        );


        toggleButton.innerHTML =
            `
            <span class="d15n-collapse-icon">
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.8"
                     stroke-linecap="round"
                     stroke-linejoin="round">
                    <path d="M15 5l-7 7 7 7"/>
                </svg>
            </span>

            <span class="d15n-expand-icon">
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     stroke-width="1.8"
                     stroke-linecap="round"
                     stroke-linejoin="round">
                    <path d="M9 5l7 7-7 7"/>
                </svg>
            </span>
            `;


        /*
         * Must never start D15K/D15L sidebar dragging.
         */
        toggleButton.addEventListener(
            "pointerdown",
            (event) => {
                event.stopPropagation();
            }
        );


        toggleButton.addEventListener(
            "click",
            (event) => {
                event.preventDefault();
                event.stopPropagation();


                d15nSetCompact(
                    !document.body
                        .classList
                        .contains(
                            "d15n-left-compact"
                        ),
                    true
                );
            }
        );


        sidebar.appendChild(
            toggleButton
        );


        return toggleButton;
    }


    // --------------------------------------------------------
    // COMPACT SELECT OPTIONS
    // --------------------------------------------------------

    function d15nSyncTargetOptions() {
        const original =
            d15nOriginalTarget();


        const compact =
            panel
                ?.querySelector(
                    ".d15n-mini-target"
                );


        if (
            !original
            ||
            !compact
        ) {
            return;
        }


        const signature =
            [
                ...original.options,
            ]
            .map(
                (option) =>
                    `${option.value}:${option.text}`
            )
            .join("|");


        if (
            compact.dataset.signature
            !== signature
        ) {
            compact.innerHTML =
                "";


            for (
                const option
                of original.options
            ) {
                const mini =
                    document.createElement(
                        "option"
                    );


                mini.value =
                    option.value;


                const source =
                    String(
                        option.text
                        || ""
                    );


                if (
                    /sim/i.test(
                        source
                    )
                ) {
                    mini.textContent =
                        "SIM";
                }

                else if (
                    /robot|physical|g1/i.test(
                        source
                    )
                ) {
                    mini.textContent =
                        "G1";
                }

                else {
                    mini.textContent =
                        source
                            .trim()
                            .slice(
                                0,
                                3
                            )
                            .toUpperCase();
                }


                compact.appendChild(
                    mini
                );
            }


            compact.dataset.signature =
                signature;
        }


        compact.value =
            original.value;


        const activeText =
            String(
                original
                    .selectedOptions?.[0]
                    ?.text
                || ""
            )
            .toLowerCase();


        const simulation =
            (
                /sim/.test(
                    activeText
                )
                ||
                /sim/.test(
                    String(
                        original.value
                        || ""
                    )
                    .toLowerCase()
                )
            );


        panel.classList.toggle(
            "d15n-simulation-target",
            simulation
        );
    }


    // --------------------------------------------------------
    // SYNC
    // --------------------------------------------------------

    function d15nIsActiveNav(
        item
    ) {
        return Boolean(
            item
            &&
            (
                item.classList.contains(
                    "active"
                )
                ||
                item.classList.contains(
                    "selected"
                )
                ||
                item.getAttribute(
                    "aria-selected"
                )
                === "true"
                ||
                item.getAttribute(
                    "aria-current"
                )
                === "page"
            )
        );
    }


    function d15nSync() {
        syncQueued =
            false;


        if (
            !sidebar
            ||
            !panel
        ) {
            return;
        }


        d15nRepairFullscreenIcons();


        // Nav state
        panel
            .querySelector(
                ".d15n-mini-live"
            )
            .classList.toggle(
                "d15n-active",
                d15nIsActiveNav(
                    d15nOriginalNav(
                        "Live"
                    )
                )
            );


        panel
            .querySelector(
                ".d15n-mini-logs"
            )
            .classList.toggle(
                "d15n-active",
                d15nIsActiveNav(
                    d15nOriginalNav(
                        "Logs"
                    )
                )
            );


        // Target
        d15nSyncTargetOptions();


        // Connection status
        const connection =
            d15nConnectionText();


        const connectionNode =
            panel.querySelector(
                ".d15n-mini-connection-state"
            );


        connectionNode.classList.toggle(
            "d15n-connected",
            connection === "CONNECTED"
        );


        connectionNode.classList.toggle(
            "d15n-disconnected",
            connection === "DISCONNECTED"
        );


        connectionNode.title =
            connection;


        connectionNode.innerHTML =
            connection === "CONNECTED"
                ?
                ICON.connected
                :
                ICON.disconnected;


        // Connect / Disconnect action
        const originalAction =
            d15nOriginalConnectionButton();


        const action =
            panel.querySelector(
                ".d15n-mini-connect-action"
            );


        const actionText =
            String(
                originalAction
                    ?.textContent
                || "Connect"
            )
            .trim()
            .toUpperCase();


        const disconnecting =
            actionText
                .includes(
                    "DISCONNECT"
                );


        action.innerHTML =
            disconnecting
                ?
                ICON.disconnect
                :
                ICON.connect;


        action.classList.toggle(
            "d15n-disconnect-action",
            disconnecting
        );


        action.title =
            disconnecting
                ?
                "Disconnect"
                :
                "Connect";


        action.setAttribute(
            "aria-label",
            action.title
        );


        action.disabled =
            Boolean(
                originalAction
                ?.disabled
            );


        // Component statuses
        for (
            const name
            of STATUS_NAMES
        ) {
            const node =
                panel.querySelector(
                    `[data-d15n-status="${name}"]`
                );


            const value =
                d15nStatusValue(
                    name
                );


            if (!node) {
                continue;
            }


            if (
                node.textContent
                !== value
            ) {
                node.textContent =
                    value;
            }


            node.title =
                `${name}: ${value}`;


            node.dataset.state =
                value;
        }
    }


    function d15nScheduleSync() {
        if (syncQueued) {
            return;
        }


        syncQueued =
            true;


        requestAnimationFrame(
            d15nSync
        );
    }


    // --------------------------------------------------------
    // COLLAPSE / EXPAND FLIP
    // --------------------------------------------------------

    function d15nCaptureLayout() {
        const elements = [
            sidebar,
            document.querySelector(
                ".main"
            ),
            document.getElementById(
                "d15WindowDock"
            ),
        ]
        .filter(
            Boolean
        );


        return new Map(
            elements.map(
                (element) => [
                    element,
                    element
                        .getBoundingClientRect(),
                ]
            )
        );
    }


    function d15nAnimateLayout(
        before
    ) {
        for (
            const [
                element,
                oldRect,
            ]
            of before
        ) {
            const newRect =
                element
                    .getBoundingClientRect();


            if (
                oldRect.width <= 0
                ||
                oldRect.height <= 0
                ||
                newRect.width <= 0
                ||
                newRect.height <= 0
            ) {
                continue;
            }


            const dx =
                oldRect.left
                -
                newRect.left;


            const dy =
                oldRect.top
                -
                newRect.top;


            const sx =
                oldRect.width
                /
                newRect.width;


            if (
                Math.abs(dx) < .5
                &&
                Math.abs(dy) < .5
                &&
                Math.abs(sx - 1) < .002
            ) {
                continue;
            }


            layoutAnimations
                .get(
                    element
                )
                ?.cancel();


            const animation =
                element.animate(
                    [
                        {
                            transformOrigin:
                                "top left",

                            transform:
                                `translate3d(${dx}px, ${dy}px, 0) `
                                +
                                `scaleX(${sx})`,
                        },

                        {
                            transformOrigin:
                                "top left",

                            transform:
                                "translate3d(0, 0, 0) "
                                +
                                "scaleX(1)",
                        },
                    ],
                    {
                        duration:
                            390,

                        easing:
                            "cubic-bezier(.22, 1, .36, 1)",

                        fill:
                            "both",
                    }
                );


            layoutAnimations.set(
                element,
                animation
            );


            animation.addEventListener(
                "finish",
                () => {
                    if (
                        layoutAnimations.get(
                            element
                        )
                        === animation
                    ) {
                        layoutAnimations.delete(
                            element
                        );
                    }


                    animation.cancel();
                },
                {
                    once: true,
                }
            );
        }
    }


    function d15nSetCompact(
        compact,
        animate
    ) {
        const before =
            animate
                ?
                d15nCaptureLayout()
                :
                null;


        document.body.classList.toggle(
            "d15n-left-compact",
            Boolean(
                compact
            )
        );


        if (toggleButton) {
            toggleButton.title =
                compact
                    ?
                    "Expand sidebar"
                    :
                    "Minimize sidebar";


            toggleButton.setAttribute(
                "aria-label",
                toggleButton.title
            );


            toggleButton.setAttribute(
                "aria-expanded",
                compact
                    ?
                    "false"
                    :
                    "true"
            );
        }


        try {
            localStorage.setItem(
                STORAGE_KEY,
                compact
                    ?
                    "1"
                    :
                    "0"
            );
        }

        catch (_) {
            // Persistence is optional.
        }


        /*
         * Resolve the new CSS grid geometry before FLIP.
         */
        document
            .querySelector(
                ".app-shell"
            )
            ?.getBoundingClientRect();


        if (
            animate
            &&
            before
        ) {
            d15nAnimateLayout(
                before
            );
        }


        d15nScheduleSync();
    }


    // --------------------------------------------------------
    // INSTALL
    // --------------------------------------------------------

    function d15nInstall() {
        sidebar =
            document.querySelector(
                ".sidebar"
            );


        if (!sidebar) {
            return false;
        }


        d15nCreateToggle();
        d15nCreateCompactPanel();


        d15nRepairFullscreenIcons();


        /*
         * React to real dashboard state changes.
         *
         * Ignore mutations generated exclusively inside our own
         * compact mirror so we never create a self-observer loop.
         */
        new MutationObserver(
            (records) => {
                const relevant =
                    records.some(
                        (record) =>
                            !panel.contains(
                                record.target
                            )
                    );


                if (relevant) {
                    d15nScheduleSync();
                }
            }
        ).observe(
            sidebar,
            {
                childList: true,
                characterData: true,
                subtree: true,
                attributes: true,
                attributeFilter: [
                    "class",
                    "aria-selected",
                    "aria-current",
                    "disabled",
                ],
            }
        );


        /*
         * Target/nav changes may use element properties rather
         * than DOM mutations.
         */
        document.addEventListener(
            "change",
            d15nScheduleSync,
            true
        );


        document.addEventListener(
            "click",
            () => {
                queueMicrotask(
                    d15nScheduleSync
                );
            },
            true
        );


        /*
         * Newly-created workspace windows receive the corrected
         * restore icon too.
         */
        const workspace =
            document.getElementById(
                "mediaWorkspace"
            );


        if (workspace) {
            new MutationObserver(
                d15nRepairFullscreenIcons
            ).observe(
                workspace,
                {
                    childList: true,
                    subtree: true,
                }
            );
        }


        let saved =
            false;


        try {
            saved =
                localStorage.getItem(
                    STORAGE_KEY
                )
                === "1";
        }

        catch (_) {}


        d15nSetCompact(
            saved,
            false
        );


        d15nSync();


        document.body.classList.add(
            "d15n-compact-sidebar-ready"
        );


        return true;
    }


    function d15nBoot(
        attempt = 0
    ) {
        if (
            d15nInstall()
        ) {
            return;
        }


        if (
            attempt < 50
        ) {
            window.setTimeout(
                () => {
                    d15nBoot(
                        attempt + 1
                    );
                },
                100
            );
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                d15nBoot();
            },
            {
                once: true,
            }
        );
    }

    else {
        d15nBoot();
    }
})();

// ============================================================
// D15O_REAL_COMPACT_STATUS_MIRROR
//
// D15N originally inferred compact status values by searching
// progressively larger parent containers. That can accidentally
// encounter unrelated ON/OFF controls elsewhere in the sidebar.
//
// D15O instead finds the smallest real expanded status row for:
//
//     System
//     Simulation
//     SONIC
//     Camera
//     Alignment
//     Tracking
//
// and mirrors that exact displayed value.
//
// It also copies the expanded value's computed typography/color,
// so compact OFF/READY/LIVE/etc. visually match reality.
// ============================================================

(() => {
    "use strict";


    const NAMES = [
        "System",
        "Simulation",
        "SONIC",
        "Camera",
        "Alignment",
        "Tracking",
    ];


    const STATES =
        new Set([
            "OFF",
            "ON",
            "READY",
            "LIVE",
            "RUNNING",
            "IDLE",
            "STARTING",
            "STOPPING",
            "WAITING",
            "ERROR",
            "FAULT",
            "UNKNOWN",
            "N/A",
        ]);


    let sidebar =
        null;


    let panel =
        null;


    let queued =
        false;


    function normalized(
        node
    ) {
        return String(
            node?.textContent
            || ""
        )
        .trim()
        .toUpperCase();
    }


    function isInsideCompact(
        node
    ) {
        return Boolean(
            panel
            &&
            node
            &&
            panel.contains(
                node
            )
        );
    }


    function realLeafNodes() {
        if (!sidebar) {
            return [];
        }


        return [
            ...sidebar.querySelectorAll(
                "*"
            ),
        ].filter(
            (node) =>
                node.children.length === 0
                &&
                !isInsideCompact(
                    node
                )
        );
    }


    /*
     * Find a real state leaf inside a candidate row.
     *
     * Exact-token matching is deliberate:
     * "ON" must not be inferred from unrelated words or controls.
     */
    function findStateLeaf(
        root
    ) {
        if (!root) {
            return null;
        }


        const candidates = [
            root,
            ...root.querySelectorAll(
                "*"
            ),
        ];


        for (
            const node
            of candidates
        ) {
            if (
                isInsideCompact(
                    node
                )
                ||
                node.children.length !== 0
            ) {
                continue;
            }


            const value =
                normalized(
                    node
                );


            if (
                STATES.has(
                    value
                )
            ) {
                return {
                    node,
                    value,
                };
            }
        }


        return null;
    }


    /*
     * Starting at the exact component-name label, walk outward.
     * The FIRST ancestor containing a real state value is the
     * component's smallest status row.
     */
    function findSourceStatus(
        name
    ) {
        const wanted =
            name.toUpperCase();


        const labels =
            realLeafNodes()
                .filter(
                    (node) =>
                        normalized(
                            node
                        )
                        === wanted
                );


        for (
            const label
            of labels
        ) {
            let row =
                label.parentElement;


            while (
                row
                &&
                row !== sidebar
            ) {
                const source =
                    findStateLeaf(
                        row
                    );


                if (source) {
                    return source;
                }


                row =
                    row.parentElement;
            }
        }


        return null;
    }


    function mirrorStyle(
        target,
        source
    ) {
        if (
            !target
            ||
            !source
        ) {
            return;
        }


        const style =
            getComputedStyle(
                source
            );


        /*
         * Mirror the actual expanded status typography.
         * Compact geometry remains controlled by D15O CSS.
         */
        target.style.setProperty(
            "--d15o-status-color",
            style.color
        );


        target.style.setProperty(
            "--d15o-status-font-family",
            style.fontFamily
        );


        target.style.setProperty(
            "--d15o-status-font-weight",
            style.fontWeight
        );


        target.style.setProperty(
            "--d15o-status-letter-spacing",
            style.letterSpacing
        );
    }


    function syncOne(
        name
    ) {
        const target =
            panel
                ?.querySelector(
                    `[data-d15n-status="${name}"]`
                );


        if (!target) {
            return;
        }


        const source =
            findSourceStatus(
                name
            );


        if (!source) {
            target.textContent =
                "--";

            target.dataset.state =
                "UNKNOWN";

            target.title =
                `${name}: unknown`;

            return;
        }


        if (
            target.textContent
            !== source.value
        ) {
            target.textContent =
                source.value;
        }


        target.dataset.state =
            source.value;


        target.title =
            `${name}: ${source.value}`;


        mirrorStyle(
            target,
            source.node
        );
    }


    function sync() {
        queued =
            false;


        for (
            const name
            of NAMES
        ) {
            syncOne(
                name
            );
        }
    }


    function schedule() {
        if (queued) {
            return;
        }


        queued =
            true;


        /*
         * D15N's original mirror may also update in this frame.
         * Our later RAF runs after those mutation callbacks and
         * leaves the compact values equal to the real rows.
         */
        requestAnimationFrame(
            sync
        );
    }


    function install() {
        sidebar =
            document.querySelector(
                ".sidebar"
            );


        panel =
            sidebar
                ?.querySelector(
                    ".d15n-compact-panel"
                );


        if (
            !sidebar
            ||
            !panel
        ) {
            return false;
        }


        /*
         * Expanded dashboard state changes are DOM-driven.
         *
         * Ignore our own compact mirror mutations to avoid a
         * feedback loop.
         */
        new MutationObserver(
            (records) => {
                const relevant =
                    records.some(
                        (record) =>
                            !panel.contains(
                                record.target
                            )
                    );


                if (relevant) {
                    schedule();
                }
            }
        ).observe(
            sidebar,
            {
                childList: true,
                subtree: true,
                characterData: true,
                attributes: true,
                attributeFilter: [
                    "class",
                    "data-state",
                ],
            }
        );


        document.addEventListener(
            "change",
            schedule,
            true
        );


        document.addEventListener(
            "click",
            () => {
                queueMicrotask(
                    schedule
                );
            },
            true
        );


        /*
         * Initial correction after D15N startup rendering.
         */
        schedule();


        document.body.classList.add(
            "d15o-compact-polish-ready"
        );


        return true;
    }


    function boot(
        attempt = 0
    ) {
        if (
            install()
        ) {
            return;
        }


        if (
            attempt < 50
        ) {
            setTimeout(
                () => {
                    boot(
                        attempt + 1
                    );
                },
                100
            );
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                boot();
            },
            {
                once: true,
            }
        );
    }

    else {
        boot();
    }
})();

// ============================================================
// D15U_INTERFACE_TEXT_CLEANUP
//
// Presentation only:
//
// - removes explanatory text below the four idle preview labels
// - normalizes STATUS / ROBOT MODES typography to SYSTEM TARGET
// - removes the standalone MODES heading
// ============================================================

(() => {
    "use strict";


    const DESCRIPTION_PREFIXES = [
        "START V2 TO BEGIN",
        "START THE SIMULATION STACK",
        "DEPLOY TO ROBOT",
    ];


    function leafNodes(
        root
    ) {
        return [
            ...root.querySelectorAll(
                "*"
            ),
        ].filter(
            (node) =>
                node.children.length === 0
        );
    }


    function normalized(
        node
    ) {
        return String(
            node?.textContent
            || ""
        )
        .trim()
        .toUpperCase();
    }


    function d15uHideWindowDescriptions() {
        const workspace =
            document.getElementById(
                "mediaWorkspace"
            );


        if (!workspace) {
            return;
        }


        for (
            const node
            of leafNodes(
                workspace
            )
        ) {
            const value =
                normalized(
                    node
                );


            if (
                DESCRIPTION_PREFIXES.some(
                    (prefix) =>
                        value.startsWith(
                            prefix
                        )
                )
            ) {
                node.classList.add(
                    "d15u-hidden-preview-description"
                );
            }
        }
    }


    function d15uSidebarTypography() {
        const sidebar =
            document.querySelector(
                ".sidebar"
            );


        if (!sidebar) {
            return;
        }


        const leaves =
            leafNodes(
                sidebar
            )
            .filter(
                (node) =>
                    !node.closest(
                        ".d15n-compact-panel"
                    )
            );


        const systemTarget =
            leaves.find(
                (node) =>
                    normalized(
                        node
                    )
                    === "SYSTEM TARGET"
            );


        if (!systemTarget) {
            return;
        }


        const reference =
            getComputedStyle(
                systemTarget
            );


        const wanted = [
            "SYSTEM TARGET",
            "STATUS",
            "ROBOT MODES",
        ];


        for (
            const label
            of wanted
        ) {
            const node =
                leaves.find(
                    (candidate) =>
                        normalized(
                            candidate
                        )
                        === label
                );


            if (!node) {
                continue;
            }


            node.classList.add(
                "d15u-section-heading"
            );


            /*
             * Copy the CURRENT rendered typography of
             * SYSTEM TARGET instead of guessing values.
             */
            node.style.setProperty(
                "font-family",
                reference.fontFamily,
                "important"
            );

            node.style.setProperty(
                "font-size",
                reference.fontSize,
                "important"
            );

            node.style.setProperty(
                "font-weight",
                reference.fontWeight,
                "important"
            );

            node.style.setProperty(
                "line-height",
                reference.lineHeight,
                "important"
            );

            node.style.setProperty(
                "letter-spacing",
                reference.letterSpacing,
                "important"
            );

            node.style.setProperty(
                "color",
                reference.color,
                "important"
            );

            node.style.setProperty(
                "text-transform",
                reference.textTransform,
                "important"
            );
        }


        /*
         * Remove ONLY the standalone heading "MODES".
         * Do not touch actual Dev / Damping / Walk / etc buttons.
         */
        const modesHeading =
            leaves.find(
                (node) =>
                    normalized(
                        node
                    )
                    === "MODES"
            );


        if (modesHeading) {
            modesHeading.classList.add(
                "d15u-hidden-modes-heading"
            );
        }
    }


    function d15uApply() {
        d15uHideWindowDescriptions();
        d15uSidebarTypography();
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            d15uApply,
            {
                once: true,
            }
        );
    }

    else {
        d15uApply();
    }
})();

// ============================================================
// D15V_EXPANDED_STATUS_ALIGNMENT
//
// Marks only the six real expanded sidebar status values so
// their visual alignment can be adjusted independently.
// ============================================================

(() => {
    "use strict";

    const LABELS = [
        "SYSTEM",
        "SIMULATION",
        "SONIC",
        "CAMERA",
        "ALIGNMENT",
        "TRACKING",
    ];

    const STATES = new Set([
        "OFF",
        "ON",
        "READY",
        "LIVE",
        "RUNNING",
        "IDLE",
        "STARTING",
        "STOPPING",
        "WAITING",
        "ERROR",
        "FAULT",
    ]);


    function textOf(node) {
        return String(
            node?.textContent || ""
        )
        .trim()
        .toUpperCase();
    }


    function install() {
        const sidebar =
            document.querySelector(
                ".sidebar"
            );

        if (!sidebar) {
            return;
        }


        const leaves = [
            ...sidebar.querySelectorAll("*"),
        ].filter(
            (node) =>
                node.children.length === 0
                &&
                !node.closest(
                    ".d15n-compact-panel"
                )
        );


        for (const name of LABELS) {
            const label =
                leaves.find(
                    (node) =>
                        textOf(node)
                        === name
                );

            if (!label) {
                continue;
            }


            let row =
                label.parentElement;

            while (
                row
                &&
                row !== sidebar
            ) {
                const state =
                    [
                        row,
                        ...row.querySelectorAll("*"),
                    ].find(
                        (node) =>
                            node.children.length === 0
                            &&
                            node !== label
                            &&
                            STATES.has(
                                textOf(node)
                            )
                    );

                if (state) {
                    state.classList.add(
                        "d15v-expanded-status-value"
                    );
                    break;
                }

                row =
                    row.parentElement;
            }
        }
    }


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            install,
            {
                once: true,
            }
        );
    }

    else {
        install();
    }
})();

// ============================================================
// D15W_SIMULATION_STATUS_ALIGNMENT
//
// D15V could encounter another "Simulation" label before the
// actual component-status row.
//
// Find the real Simulation row by requiring a nearby exact
// state token, then apply the same alignment class as the other
// five component statuses.
// ============================================================

(() => {
    "use strict";

    const STATES = new Set([
        "OFF",
        "ON",
        "READY",
        "LIVE",
        "RUNNING",
        "IDLE",
        "STARTING",
        "STOPPING",
        "WAITING",
        "ERROR",
        "FAULT",
    ]);


    function value(node) {
        return String(
            node?.textContent || ""
        )
        .trim()
        .toUpperCase();
    }


    function install() {
        const sidebar =
            document.querySelector(
                ".sidebar"
            );

        if (!sidebar) {
            return;
        }


        const labels = [
            ...sidebar.querySelectorAll("*"),
        ].filter(
            (node) =>
                node.children.length === 0
                &&
                !node.closest(
                    ".d15n-compact-panel"
                )
                &&
                value(node) === "SIMULATION"
        );


        let best = null;


        for (const label of labels) {
            let row =
                label.parentElement;

            let depth = 0;


            while (
                row
                &&
                row !== sidebar
                &&
                depth < 5
            ) {
                const state = [
                    ...row.querySelectorAll("*"),
                ].find(
                    (node) =>
                        node.children.length === 0
                        &&
                        node !== label
                        &&
                        STATES.has(
                            value(node)
                        )
                );


                if (state) {
                    const score =
                        row.querySelectorAll("*")
                            .length;


                    if (
                        !best
                        ||
                        score < best.score
                    ) {
                        best = {
                            state,
                            score,
                        };
                    }

                    break;
                }


                row =
                    row.parentElement;

                depth += 1;
            }
        }


        if (best) {
            best.state.classList.add(
                "d15v-expanded-status-value"
            );

            console.log(
                "D15W: Simulation status aligned:",
                value(best.state)
            );
        }
    }


    if (
        document.readyState === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            install,
            {
                once: true,
            }
        );
    }

    else {
        install();
    }
})();
