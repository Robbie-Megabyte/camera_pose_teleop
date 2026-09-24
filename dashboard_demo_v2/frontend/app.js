"use strict";


const state = {
    currentView: "live",
    backendOnline: false,

    keypointsEnabled: true,
    showBothCameras: false,

    keypointLive: false,
    rawLive: false,
    mujocoLive: false,

    keypointFramePending: false,
    rawFramePending: false,
    mujocoFramePending: false,
};


function text(
    id,
    value
) {
    const node = document.getElementById(id);

    if (node) {
        node.textContent = value;
    }
}


function upper(
    value
) {
    if (
        value === null
        ||
        value === undefined
    ) {
        return "--";
    }

    return String(value)
        .replaceAll("_", " ")
        .toUpperCase();
}


function setActionMessage(
    message,
    isError = false
) {
    const node = document.getElementById(
        "actionMessage"
    );

    if (!node) {
        return;
    }

    node.textContent = (
        message || ""
    );

    node.classList.toggle(
        "error",
        Boolean(isError)
    );
}


function setFeedPresentation(
    kind,
    live,
    cameraReady
) {
    const config = {
        keypoint: {
            pill: "keypointCameraPill",
            image: "keypointCameraImage",
            placeholder: "cameraPlaceholder",
            title: "cameraPlaceholderTitle",
            message: "cameraPlaceholderText",
            idleTitle: "Keypoint preview idle",
            waitingTitle: "Waiting for keypoint preview",
            idleMessage: "Start V2 to begin the keypoint stream.",
            waitingMessage: "V2 is running; waiting for the ViTPose fanout.",
        },

        raw: {
            pill: "rawCameraPill",
            image: "rawCameraImage",
            placeholder: "rawCameraPlaceholder",
            title: "rawCameraPlaceholderTitle",
            message: "rawCameraPlaceholderText",
            idleTitle: "Raw preview idle",
            waitingTitle: "Waiting for raw preview",
            idleMessage: "Start V2 to begin the raw stream.",
            waitingMessage: "V2 is running; waiting for the raw MJPEG fanout.",
        },
    }[kind];

    if (!config) {
        return;
    }

    const image = document.getElementById(
        config.image
    );

    const placeholder = document.getElementById(
        config.placeholder
    );

    if (live) {
        text(
            config.pill,
            "LIVE"
        );

        placeholder?.classList.add(
            "hidden"
        );

        return;
    }

    image?.classList.remove(
        "visible"
    );

    placeholder?.classList.remove(
        "hidden"
    );

    text(
        config.pill,
        cameraReady
            ? "WAITING"
            : "OFF"
    );

    text(
        config.title,
        cameraReady
            ? config.waitingTitle
            : config.idleTitle
    );

    text(
        config.message,
        cameraReady
            ? config.waitingMessage
            : config.idleMessage
    );
}


function updateCameraModeUI() {
    const rawView = document.getElementById(
        "rawCameraView"
    );

    const keypointView = document.getElementById(
        "keypointCameraView"
    );

    const views = document.getElementById(
        "cameraViews"
    );

    const keypointButton = document.getElementById(
        "keypointToggleButton"
    );

    const bothButton = document.getElementById(
        "bothToggleButton"
    );

    if (state.showBothCameras) {
        rawView?.classList.remove(
            "hidden"
        );

        keypointView?.classList.remove(
            "hidden"
        );

        views?.classList.add(
            "show-both"
        );
    }
    else {
        views?.classList.remove(
            "show-both"
        );

        if (state.keypointsEnabled) {
            rawView?.classList.add(
                "hidden"
            );

            keypointView?.classList.remove(
                "hidden"
            );
        }
        else {
            rawView?.classList.remove(
                "hidden"
            );

            keypointView?.classList.add(
                "hidden"
            );
        }
    }

    if (keypointButton) {
        keypointButton.textContent = (
            state.keypointsEnabled
                ? "Keypoints: ON"
                : "Keypoints: OFF"
        );

        keypointButton.classList.toggle(
            "active",
            state.keypointsEnabled
        );

        keypointButton.disabled = (
            state.showBothCameras
        );
    }

    if (bothButton) {
        bothButton.textContent = (
            state.showBothCameras
                ? "Show Both: ON"
                : "Show Both: OFF"
        );

        bothButton.classList.toggle(
            "active",
            state.showBothCameras
        );
    }
}


function applyCameraPreviewStatus(
    data
) {
    const keypoint = (
        data.keypoint_preview
        || {}
    );

    const raw = (
        data.raw_preview
        || {}
    );

    state.keypointLive = Boolean(
        keypoint.live
    );

    state.rawLive = Boolean(
        raw.live
    );

    // D15X_WINDOW_LIVE_LEDS
    // Bind the existing workspace header LEDs to the actual
    // preview states rather than leaving them decorative.
    document
        .getElementById(
            "keypointCameraView"
        )
        ?.classList.toggle(
            "feed-live",
            state.keypointLive
        );

    document
        .getElementById(
            "rawCameraView"
        )
        ?.classList.toggle(
            "feed-live",
            state.rawLive
        );

    const cameraReady = (
        data.camera?.state === "ready"
    );

    setFeedPresentation(
        "keypoint",
        state.keypointLive,
        cameraReady
    );

    setFeedPresentation(
        "raw",
        state.rawLive,
        cameraReady
    );

    if (state.showBothCameras) {
        if (
            state.rawLive
            &&
            state.keypointLive
        ) {
            text(
                "cameraPill",
                "BOTH LIVE"
            );
        }
        else if (
            state.rawLive
            ||
            state.keypointLive
        ) {
            text(
                "cameraPill",
                "1/2 LIVE"
            );
        }
        else {
            text(
                "cameraPill",
                cameraReady
                    ? "WAITING"
                    : "OFF"
            );
        }
    }
    else {
        const selectedLive = (
            state.keypointsEnabled
                ? state.keypointLive
                : state.rawLive
        );

        text(
            "cameraPill",
            selectedLive
                ? "LIVE"
                : (
                    cameraReady
                        ? "WAITING"
                        : "OFF"
                )
        );
    }

    updateCameraModeUI();
}


function refreshCameraFeed(
    kind
) {
    const config = {
        keypoint: {
            live: state.keypointLive,
            pending: "keypointFramePending",
            image: "keypointCameraImage",
            path: "/api/camera/keypoints.jpg",
        },

        raw: {
            live: state.rawLive,
            pending: "rawFramePending",
            image: "rawCameraImage",
            path: "/api/camera/raw.jpg",
        },
    }[kind];

    if (!config) {
        return;
    }

    const visible = (
        state.showBothCameras
        ||
        (
            kind === "keypoint"
            &&
            state.keypointsEnabled
        )
        ||
        (
            kind === "raw"
            &&
            !state.keypointsEnabled
        )
    );

    if (
        !state.backendOnline
        ||
        !config.live
        ||
        !visible
        ||
        state.currentView !== "live"
        ||
        state[config.pending]
    ) {
        return;
    }

    const image = document.getElementById(
        config.image
    );

    if (!image) {
        return;
    }

    state[
        config.pending
    ] = true;

    image.onload = () => {
        state[
            config.pending
        ] = false;

        const stillLive = (
            kind === "keypoint"
                ? state.keypointLive
                : state.rawLive
        );

        if (stillLive) {
            image.classList.add(
                "visible"
            );
        }
    };

    image.onerror = () => {
        state[
            config.pending
        ] = false;
    };

    image.src = (
        config.path
        + "?t="
        + Date.now()
    );
}


function refreshCameraFrames() {
    refreshCameraFeed(
        "keypoint"
    );

    refreshCameraFeed(
        "raw"
    );
}


function applyMujocoPreviewStatus(
    data
) {
    const preview = (
        data.mujoco_preview
        || {}
    );

    state.mujocoLive = Boolean(
        preview.live
    );

    document
        .querySelector(
            "#view-live .workspace-tile.mujoco-panel"
        )
        ?.classList.toggle(
            "feed-live",
            state.mujocoLive
        );

    const image = document.getElementById(
        "mujocoImage"
    );

    const placeholder = document.getElementById(
        "mujocoPlaceholder"
    );

    const simState = (
        data.simulation?.mujoco
        || "off"
    );

    if (state.mujocoLive) {
        text(
            "mujocoPill",
            "LIVE"
        );

        placeholder?.classList.add(
            "hidden"
        );

        return;
    }

    image?.classList.remove(
        "visible"
    );

    placeholder?.classList.remove(
        "hidden"
    );

    if (
        simState !== "off"
        &&
        simState !== "stopped"
    ) {
        text(
            "mujocoPill",
            "WAITING"
        );

        text(
            "mujocoPlaceholderTitle",
            "Waiting for MuJoCo render"
        );

        text(
            "mujocoPlaceholderText",
            "Simulation is starting; waiting for the offscreen image publisher."
        );
    }
    else {
        text(
            "mujocoPill",
            "OFF"
        );

        text(
            "mujocoPlaceholderTitle",
            "MuJoCo preview idle"
        );

        text(
            "mujocoPlaceholderText",
            "Start the simulation stack to begin rendering."
        );
    }
}


function refreshMujocoFrame() {
    const image =
        document.getElementById(
            "mujocoImage"
        );

    if (!image) {
        return;
    }


    const shouldStream = (
        state.backendOnline
        &&
        state.mujocoLive
        &&
        state.currentView === "live"
    );


    if (!shouldStream) {
        if (
            image.dataset
            .mjpegActive
            === "1"
        ) {
            /*
             * Removing src closes the browser's persistent
             * multipart MJPEG response.
             */
            image.removeAttribute(
                "src"
            );

            image.dataset
                .mjpegActive = "0";
        }

        return;
    }


    if (
        image.dataset
        .mjpegActive
        === "1"
    ) {
        return;
    }


    /*
     * One persistent connection.
     *
     * The HTTP response stays open and the browser displays
     * each JPEG as soon as the backend receives a new MuJoCo
     * frame.
     *
     * No repeated 100 ms GET cycle.
     * No image decoding here.
     * No re-encoding here.
     */
    image.dataset
        .mjpegActive = "1";


    image.onload = () => {
        if (
            state.mujocoLive
        ) {
            image.classList.add(
                "visible"
            );
        }
    };


    image.onerror = () => {
        image.dataset
            .mjpegActive = "0";

        image.classList.remove(
            "visible"
        );
    };


    image.src = (
        "/api/mujoco/stream.mjpg?t="
        + Date.now()
    );
}


function applyStatus(
    data
) {
    state.backendOnline = true;

    const online = (
        data.dashboard
        &&
        data.dashboard.status === "online"
    );

    const dot = document.getElementById(
        "backendDot"
    );

    const badge = document.getElementById(
        "systemBadge"
    );

    if (online) {
        dot.classList.remove("off");
        dot.classList.add("on");

        badge.classList.add("online");

        text(
            "backendText",
            "Backend online"
        );

        text(
            "systemBadge",
            "DASHBOARD ONLINE"
        );
    }

    text(
        "dashboardStatus",
        upper(
            data.dashboard?.status
        )
    );

    text(
        "modeState",
        upper(
            data.mode
        )
    );

    text(
        "cameraState",
        upper(
            data.camera?.state
        )
    );

    text(
        "gvhmrState",
        upper(
            data.gvhmr?.state
        )
    );

    text(
        "framingState",
        upper(
            data.framing?.state
        )
    );

    text(
        "alignmentState",
        upper(
            data.alignment?.state
        )
    );

    text(
        "bridgeState",
        upper(
            data.sonic_bridge?.state
        )
    );

    text(
        "publisherState",
        upper(
            data.publisher?.state
        )
    );

    const hz = (
        data.publisher?.pose_hz
    );

    text(
        "poseRate",
        hz == null
            ? "--"
            : `${Number(hz).toFixed(1)} Hz`
    );

    text(
        "mujocoState",
        upper(
            data.simulation?.mujoco
        )
    );

    text(
        "sonicSimState",
        upper(
            data.simulation?.sonic
        )
    );

    applyCameraPreviewStatus(
        data
    );

    applyMujocoPreviewStatus(
        data
    );

    updateDemoControlStrip(
        data
    );

    const teleop = (
        data.teleop || {}
    );

    const teleopState = (
        teleop.state || "off"
    );

    const processAlive = Boolean(
        teleop.process_alive
    );

    const running = Boolean(
        teleop.running
    );

    if (
        teleopState === "off"
    ) {
        text(
            "teleopDescription",
            "Pipeline is stopped."
        );
    }
    else if (
        teleopState === "error"
    ) {
        text(
            "teleopDescription",
            teleop.last_error
                || "V2 stopped with an error."
        );
    }
    else {
        text(
            "teleopDescription",
            `Pipeline state: ${upper(teleopState)}`
        );
    }

    const startButton = (
        document.getElementById(
            "startV2Button"
        )
    );

    const stopButton = (
        document.getElementById(
            "stopV2Button"
        )
    );

    if (startButton) {
        startButton.disabled = (
            processAlive
            ||
            teleopState === "starting"
            ||
            teleopState === "stopping"
        );
    }

    if (stopButton) {
        stopButton.disabled = (
            !processAlive
        );
    }

    text(
        "stepCamera",
        data.camera?.state === "ready"
            ? "READY"
            : upper(
                data.camera?.state
                || "waiting"
            )
    );

    const framing = (
        data.framing || {}
    );

    if (
        framing.state === "waiting"
        &&
        framing.required_streak
    ) {
        text(
            "stepFraming",
            `${framing.good_streak}/${framing.required_streak}`
        );
    }
    else {
        text(
            "stepFraming",
            upper(
                framing.state
                || "waiting"
            )
        );
    }

    const gvhmr = (
        data.gvhmr || {}
    );

    if (
        gvhmr.state
        === "building_history"
    ) {
        text(
            "stepHistory",
            `${gvhmr.history_frames}/${gvhmr.history_required}`
        );
    }
    else {
        text(
            "stepHistory",
            upper(
                gvhmr.state
                || "waiting"
            )
        );
    }

    const alignment = (
        data.alignment || {}
    );

    if (
        alignment.state
        === "collecting"
    ) {
        text(
            "stepAlignment",
            alignment.valid_frames > 0
                ? `COLLECTING ${alignment.valid_frames}`
                : "COLLECTING"
        );
    }
    else {
        text(
            "stepAlignment",
            upper(
                alignment.state
                || "waiting"
            )
        );
    }

    text(
        "stepBridge",
        upper(
            data.sonic_bridge?.state
            || "waiting"
        )
    );

    text(
        "stepTeleop",
        teleopState === "running"
            ? "RUNNING"
            : (
                teleopState === "error"
                    ? "ERROR"
                    : (
                        teleopState === "ready"
                            ? "READY"
                            : "LOCKED"
                    )
            )
    );
}


function applyEvents(
    payload
) {
    const events = (
        payload.events || []
    );

    const lines = events.map(
        event => (
            `[${event.time}] `
            +
            `${event.level.toUpperCase()}  `
            +
            event.message
        )
    );

    text(
        "eventLog",
        lines.length
            ? lines.join("\n")
            : "No events."
    );
}


function applyLogs(
    payload
) {
    const logs = (
        payload.logs || []
    );

    const lines = logs.map(
        item => (
            `[${item.time}] `
            +
            item.line
        )
    );

    text(
        "runtimeLog",
        lines.length
            ? lines.join("\n")
            : "V2 has not been started."
    );

    const node = (
        document.getElementById(
            "runtimeLog"
        )
    );

    if (node) {
        node.scrollTop = (
            node.scrollHeight
        );
    }
}


async function fetchJson(
    path,
    options = {}
) {
    const response = await fetch(
        path,
        {
            cache: "no-store",
            ...options,
        }
    );

    const data = await response.json();

    if (!response.ok) {
        throw new Error(
            data.error
            || `HTTP ${response.status}`
        );
    }

    return data;
}


async function refreshStatus() {
    try {
        const data = await fetchJson(
            "/api/status"
        );

        applyStatus(
            data
        );
    }
    catch (error) {
        state.backendOnline = false;

        state.keypointLive = false;
        state.rawLive = false;
        state.mujocoLive = false;

        const mujocoOfflineImage =
            document.getElementById(
                "mujocoImage"
            );

        if (mujocoOfflineImage) {
            mujocoOfflineImage.removeAttribute(
                "src"
            );

            mujocoOfflineImage.dataset
                .mjpegActive = "0";
        }

        state.keypointFramePending = false;
        state.rawFramePending = false;
        state.mujocoFramePending = false;

        for (const id of [
            "keypointCameraImage",
            "rawCameraImage",
            "mujocoImage",
        ]) {
            document
                .getElementById(id)
                ?.classList.remove(
                    "visible"
                );
        }

        for (const id of [
            "cameraPlaceholder",
            "rawCameraPlaceholder",
            "mujocoPlaceholder",
        ]) {
            document
                .getElementById(id)
                ?.classList.remove(
                    "hidden"
                );
        }

        text(
            "cameraPill",
            "OFFLINE"
        );

        text(
            "keypointCameraPill",
            "OFFLINE"
        );

        text(
            "rawCameraPill",
            "OFFLINE"
        );

        text(
            "mujocoPill",
            "OFFLINE"
        );

        text(
            "cameraPlaceholderTitle",
            "Dashboard offline"
        );

        text(
            "cameraPlaceholderText",
            "Waiting for the dashboard backend."
        );

        text(
            "rawCameraPlaceholderTitle",
            "Dashboard offline"
        );

        text(
            "rawCameraPlaceholderText",
            "Waiting for the dashboard backend."
        );

        text(
            "backendText",
            "Backend offline"
        );

        const badge = (
            document.getElementById(
                "systemBadge"
            )
        );

        badge.classList.remove(
            "online"
        );

        text(
            "systemBadge",
            "OFFLINE"
        );

        const startButton = (
            document.getElementById(
                "startV2Button"
            )
        );

        const stopButton = (
            document.getElementById(
                "stopV2Button"
            )
        );

        if (startButton) {
            startButton.disabled = true;
        }

        if (stopButton) {
            stopButton.disabled = true;
        }
    }
}


async function refreshEvents() {
    try {
        applyEvents(
            await fetchJson(
                "/api/events"
            )
        );
    }
    catch {
        // Status polling handles backend failure.
    }
}


async function refreshLogs() {
    try {
        applyLogs(
            await fetchJson(
                "/api/logs"
            )
        );
    }
    catch {
        // Status polling handles backend failure.
    }
}


async function startV2() {
    const confirmed = window.confirm(
        "Start Camera Pose Teleop V2?\n\n"
        +
        "The human-facing camera will be opened. "
        +
        "Stand neutral with your full body and feet visible "
        +
        "for V2 framing and session alignment."
    );

    if (!confirmed) {
        return;
    }

    setActionMessage(
        "Starting V2..."
    );

    try {
        const result = await fetchJson(
            "/api/teleop/start",
            {
                method: "POST",
            }
        );

        setActionMessage(
            `V2 process started (PID ${result.pid}).`
        );

        await refreshStatus();
        await refreshEvents();
        await refreshLogs();
    }
    catch (error) {
        setActionMessage(
            error.message,
            true
        );
    }
}


async function stopV2() {
    setActionMessage(
        "Stopping V2 process group..."
    );

    try {
        const result = await fetchJson(
            "/api/teleop/stop",
            {
                method: "POST",
            }
        );

        const signals = (
            result.signals || []
        );

        setActionMessage(
            result.already_stopped
                ? "V2 was already stopped."
                : (
                    "V2 stopped"
                    +
                    (
                        signals.length
                            ? ` via ${signals.join(" → ")}.`
                            : "."
                    )
                )
        );

        await refreshStatus();
        await refreshEvents();
        await refreshLogs();
    }
    catch (error) {
        setActionMessage(
            error.message,
            true
        );
    }
}


function showView(
    name
) {
    state.currentView = name;

    document
        .querySelectorAll(".view")
        .forEach(
            view => {
                view.classList.remove(
                    "active"
                );
            }
        );

    document
        .querySelectorAll(".nav-item")
        .forEach(
            button => {
                button.classList.remove(
                    "active"
                );
            }
        );

    document
        .getElementById(
            `view-${name}`
        )
        ?.classList.add(
            "active"
        );

    document
        .querySelector(
            `[data-view="${name}"]`
        )
        ?.classList.add(
            "active"
        );

    const titles = {
        live: "Live",
        teleop: "Teleop",
        system: "System",
        logs: "Logs",
    };

    text(
        "pageTitle",
        titles[name] || "Dashboard"
    );
}


document
    .querySelectorAll(
        ".nav-item"
    )
    .forEach(
        button => {
            button.addEventListener(
                "click",
                () => {
                    showView(
                        button.dataset.view
                    );
                }
            );
        }
    );


document
    .getElementById(
        "startV2Button"
    )
    ?.addEventListener(
        "click",
        startV2
    );


document
    .getElementById(
        "stopV2Button"
    )
    ?.addEventListener(
        "click",
        stopV2
    );


refreshStatus();
refreshEvents();
refreshLogs();

setInterval(
    refreshStatus,
    750
);

setInterval(
    refreshEvents,
    1250
);

setInterval(
    refreshLogs,
    1000
);



// ---------------------------------------------------------
// CAMERA VIEW CONTROLS
// ---------------------------------------------------------

document
    .getElementById(
        "keypointToggleButton"
    )
    ?.addEventListener(
        "click",
        () => {
            state.keypointsEnabled = (
                !state.keypointsEnabled
            );

            updateCameraModeUI();
            refreshCameraFrames();
        }
    );


document
    .getElementById(
        "bothToggleButton"
    )
    ?.addEventListener(
        "click",
        () => {
            state.showBothCameras = (
                !state.showBothCameras
            );

            updateCameraModeUI();
            refreshCameraFrames();
        }
    );


updateCameraModeUI();


// ---------------------------------------------------------
// CAMERA FRAME REFRESH
// ---------------------------------------------------------
//
// raw:
//     existing V2 UDP MJPEG :5600
//
// keypoints:
//     existing V2 ZMQ JPEG :5601
//
// Both are passive dashboard consumers.
// Neither opens the physical camera.
//
setInterval(
    () => {
        refreshCameraFrames();
        refreshMujocoFrame();
    },
    100
);


// =========================================================
// D5I — MUJOCO PRESENTATION CAMERA
// =========================================================

async function sendMujocoCameraCommand(
    command
) {
    try {
        await fetch(
            "/api/mujoco/camera",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json",
                },

                body:
                    JSON.stringify(
                        command
                    ),
            }
        );
    }
    catch (_error) {
        /*
         * Presentation-camera commands are deliberately
         * isolated from the control pipeline.
         */
    }
}


function setupMujocoCameraInteraction() {
    const surface =
        document.getElementById(
            "mujocoInteractionSurface"
        );

    if (!surface) {
        return;
    }


    let dragging = false;

    let lastX = 0;
    let lastY = 0;

    let accumulatedX = 0;
    let accumulatedY = 0;

    let sendTimer = null;


    function scheduleOrbitSend() {
        if (
            sendTimer !== null
        ) {
            return;
        }

        /*
         * Limit browser viewpoint commands to about 28 Hz.
         */
        sendTimer =
            window.setTimeout(
                () => {
                    sendTimer = null;

                    const dx =
                        accumulatedX;

                    const dy =
                        accumulatedY;

                    accumulatedX = 0;
                    accumulatedY = 0;

                    if (
                        dx === 0
                        &&
                        dy === 0
                    ) {
                        return;
                    }

                    sendMujocoCameraCommand(
                        {
                            op: "orbit",
                            dx,
                            dy,
                        }
                    );
                },
                35
            );
    }


    surface.addEventListener(
        "pointerdown",
        (event) => {
            if (
                event.target.closest(
                    ".mujoco-camera-toolbar"
                )
            ) {
                return;
            }

            dragging = true;

            lastX =
                event.clientX;

            lastY =
                event.clientY;

            surface.classList.add(
                "dragging"
            );

            try {
                surface.setPointerCapture(
                    event.pointerId
                );
            }
            catch (_error) {
            }
        }
    );


    surface.addEventListener(
        "pointermove",
        (event) => {
            if (!dragging) {
                return;
            }

            const dx =
                event.clientX
                - lastX;

            const dy =
                event.clientY
                - lastY;

            lastX =
                event.clientX;

            lastY =
                event.clientY;

            accumulatedX += dx;
            accumulatedY += dy;

            scheduleOrbitSend();
        }
    );


    function endDrag() {
        dragging = false;

        surface.classList.remove(
            "dragging"
        );
    }


    surface.addEventListener(
        "pointerup",
        endDrag
    );

    surface.addEventListener(
        "pointercancel",
        endDrag
    );


    surface.addEventListener(
        "wheel",
        (event) => {
            event.preventDefault();

            const direction =
                Math.sign(
                    event.deltaY
                );

            if (
                direction === 0
            ) {
                return;
            }

            sendMujocoCameraCommand(
                {
                    op: "zoom",
                    delta: direction,
                }
            );
        },
        {
            passive: false,
        }
    );


    surface.addEventListener(
        "dblclick",
        (event) => {
            if (
                event.target.closest(
                    ".mujoco-camera-toolbar"
                )
            ) {
                return;
            }

            sendMujocoCameraCommand(
                {
                    op: "reset",
                }
            );
        }
    );


    for (
        const button
        of document.querySelectorAll(
            "[data-mujoco-camera]"
        )
    ) {
        button.addEventListener(
            "click",
            () => {
                const preset =
                    button.dataset
                    .mujocoCamera;

                sendMujocoCameraCommand(
                    {
                        op: "preset",
                        name: preset,
                    }
                );
            }
        );
    }
}


// =========================================================
// D5I — DEMO STATE STRIP
//
// Informational only for now.
//
// We deliberately do NOT enable lifecycle buttons until
// SONIC supervision proves the real controller state.
// =========================================================

function normalizeDemoState(
    value
) {
    if (
        typeof value
        === "string"
    ) {
        return value;
    }

    if (
        value
        &&
        typeof value
        === "object"
    ) {
        return (
            value.state
            ||
            value.status
            ||
            "OFF"
        );
    }

    return "OFF";
}


function setDemoState(
    id,
    value
) {
    const element =
        document.getElementById(
            id
        );

    if (!element) {
        return;
    }


    const normalized =
        String(
            normalizeDemoState(
                value
            )
        ).toUpperCase();


    element.textContent =
        normalized;


    element.classList.remove(
        "ready",
        "live",
        "waiting"
    );


    if (
        normalized.includes(
            "LIVE"
        )
    ) {
        element.classList.add(
            "live"
        );
    }

    else if (
        normalized.includes(
            "READY"
        )
        ||
        normalized.includes(
            "RUNNING"
        )
    ) {
        element.classList.add(
            "ready"
        );
    }

    else if (
        normalized.includes(
            "WAIT"
        )
        ||
        normalized.includes(
            "START"
        )
        ||
        normalized.includes(
            "WARM"
        )
    ) {
        element.classList.add(
            "waiting"
        );
    }
}


let selectedSystemTarget = "sim";
let latestDemoStatus = null;
let systemRequestPending = false;


function prettyStackState(
    value
) {
    const labels = {
        off:
            "OFF",

        starting_mujoco:
            "STARTING MUJOCO",

        starting_relay:
            "STARTING RELAY",

        waiting_mujoco:
            "WAITING FOR MUJOCO",

        starting_v2:
            "STARTING V2",

        waiting_v2:
            "WAITING FOR V2",

        starting_sonic:
            "STARTING SONIC",

        waiting_sonic_reference:
            "WAITING FOR SONIC",

        releasing_mujoco:
            "RELEASING ROBOT",

        going_live:
            "GOING LIVE",

        running:
            "LIVE",

        stopping:
            "STOPPING",

        error:
            "ERROR",
    };

    return (
        labels[value]
        ||
        upper(
            value
            || "off"
        )
    );
}


function updateDemoControlStrip(
    data
) {
    latestDemoStatus = data;


    const stack = (
        data.stack
        || {}
    );

    const stackState = (
        stack.state
        || "off"
    );

    const stackActive = Boolean(
        stack.active
    );


    const sonic = (
        data.sonic
        || {}
    );


    setDemoState(
        "demoSimState",
        data.mujoco_preview
        ?.live
            ? "LIVE"
            : "OFF"
    );


    setDemoState(
        "demoSonicState",
        sonic.process_alive
            ? (
                "SIM · "
                +
                upper(
                    sonic.state
                    || "starting"
                )
            )
            : "OFF"
    );


    setDemoState(
        "demoCameraState",
        data.camera
        || "OFF"
    );


    setDemoState(
        "demoAlignState",
        stackActive
            ? (
                data.alignment
                || "OFF"
            )
            : "OFF"
    );


    setDemoState(
        "demoTrackingState",
        sonic.zmq_live
            ? "LIVE"
            : "OFF"
    );


    const target =
        document.getElementById(
            "systemTargetSelect"
        );

    const button =
        document.getElementById(
            "systemPrimaryButton"
        );

    const stateBadge =
        document.getElementById(
            "systemLaunchState"
        );

    const hint =
        document.getElementById(
            "systemLaunchHint"
        );


    if (target) {
        if (!stackActive) {
            selectedSystemTarget = (
                target.value
                || "sim"
            );
        }

        target.disabled = (
            stackActive
            ||
            systemRequestPending
        );
    }


    if (stateBadge) {
        stateBadge.textContent =
            prettyStackState(
                stackState
            );

        stateBadge.classList.toggle(
            "live",
            stackState === "running"
        );
    }


    if (hint) {
        const hints = {
            off:
                "MuJoCo · V2 · SONIC · live tracking",

            starting_mujoco:
                "Starting simulation physics...",

            starting_relay:
                "Starting simulation video...",

            waiting_mujoco:
                "Waiting for MuJoCo render...",

            starting_v2:
                "Starting camera pose pipeline...",

            waiting_v2:
                "Waiting for camera framing and alignment...",

            starting_sonic:
                "Starting SONIC controller...",

            waiting_sonic_reference:
                "Waiting for SONIC reference mode...",

            releasing_mujoco:
                "Releasing MuJoCo robot to the floor...",

            going_live:
                "Enabling live V2 tracking...",

            running:
                "Complete simulation stack is live.",

            stopping:
                "Stopping complete simulation stack...",

            error:
                (
                    stack.last_error
                    ||
                    "Simulation startup failed."
                ),
        };

        hint.textContent = (
            hints[stackState]
            ||
            hints.off
        );
    }


    if (!button) {
        return;
    }


    if (stackActive) {
        button.textContent =
            "Stop System";

        button.title =
            "Stops SONIC, V2, relay and MuJoCo.";

        button.disabled =
            systemRequestPending;

        return;
    }


    if (
        selectedSystemTarget
        === "robot"
    ) {
        button.textContent =
            "Deploy System";

        button.title =
            "Physical G1 deployment is not enabled yet.";

        button.disabled = true;

        return;
    }


    button.textContent =
        "Launch Simulation";

    button.title =
        "Starts MuJoCo, V2, SONIC and live tracking.";

    button.disabled = (
        systemRequestPending
        ||
        !state.backendOnline
    );
}


async function handleSystemPrimaryAction() {
    if (systemRequestPending) {
        return;
    }


    const stack = (
        latestDemoStatus
        ?.stack
        || {}
    );

    const active = Boolean(
        stack.active
    );


    if (
        !active
        &&
        selectedSystemTarget
        === "robot"
    ) {
        setActionMessage(
            "Physical Robot deployment is not enabled yet.",
            true
        );

        return;
    }


    const endpoint = (
        active
            ? "/api/system/sim/stop"
            : "/api/system/sim/start"
    );


    systemRequestPending = true;


    if (
        latestDemoStatus
    ) {
        updateDemoControlStrip(
            latestDemoStatus
        );
    }


    setActionMessage(
        active
            ? "Stopping complete simulation system..."
            : "Launching complete simulation system..."
    );


    try {
        await fetchJson(
            endpoint,
            {
                method: "POST",
            }
        );


        setActionMessage(
            active
                ? ""
                : (
                    "Simulation startup started. "
                    +
                    "The dashboard will complete all stages automatically."
                )
        );
    }

    catch (error) {
        setActionMessage(
            error.message,
            true
        );
    }

    finally {
        systemRequestPending = false;

        await refreshStatus();
    }
}


const systemTargetSelect =
    document.getElementById(
        "systemTargetSelect"
    );


systemTargetSelect
    ?.addEventListener(
        "change",
        () => {
            selectedSystemTarget = (
                systemTargetSelect.value
                || "sim"
            );


            if (
                latestDemoStatus
            ) {
                updateDemoControlStrip(
                    latestDemoStatus
                );
            }


            /*
             * Target selection is already represented by the
             * selector and Robot Connection bar. Do not consume
             * live-page space with an additional sentence.
             */
            setActionMessage(
                ""
            );
        }
    );


document
    .getElementById(
        "systemPrimaryButton"
    )
    ?.addEventListener(
        "click",
        handleSystemPrimaryAction
    );


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        setupMujocoCameraInteraction,
        {
            once: true,
        }
    );
}

else {
    setupMujocoCameraInteraction();
}



// ============================================================
// D7F_LIVE_TITLE_LOCK
// ============================================================

(() => {
    const pageTitle =
        document.getElementById(
            "pageTitle"
        );

    const liveView =
        document.getElementById(
            "view-live"
        );


    if (
        !pageTitle
        ||
        !liveView
    ) {
        return;
    }


    const syncLiveTitle = () => {
        if (
            liveView.classList.contains(
                "active"
            )
            &&
            pageTitle.textContent.trim()
            !== "Camera Teleoperation"
        ) {
            pageTitle.textContent =
                "Camera Teleoperation";
        }
    };


    const observer =
        new MutationObserver(
            syncLiveTitle
        );


    observer.observe(
        liveView,
        {
            attributes: true,
            attributeFilter: [
                "class",
            ],
        }
    );


    observer.observe(
        pageTitle,
        {
            childList: true,
            characterData: true,
            subtree: true,
        }
    );


    document.addEventListener(
        "click",
        () => {
            queueMicrotask(
                syncLiveTitle
            );
        },
        true
    );


    syncLiveTitle();
})();



// ============================================================
// D7H_MOVABLE_WORKSPACE
// ============================================================

let d7hWorkspace = null;
let d7hWorkspaceSlots = [];
let d7hWorkspaceManualLayout = false;
let d7hCameraActions = null;

let d7hDragPending = null;
let d7hDragState = null;


// ------------------------------------------------------------
// Slot helpers
// ------------------------------------------------------------

function d7hTileInSlot(
    slot
) {
    if (!slot) {
        return null;
    }

    return Array.from(
        slot.children
    ).find(
        (node) =>
            node.classList
                ?.contains(
                    "workspace-tile"
                )
    ) || null;
}


function d7hUpdateSlotVisuals() {
    for (
        const slot
        of d7hWorkspaceSlots
    ) {
        const tile =
            d7hTileInSlot(
                slot
            );

        const visiblyOccupied = Boolean(
            tile
            &&
            !tile.classList
                .contains(
                    "hidden"
                )
        );

        slot.classList.toggle(
            "workspace-slot-empty",
            !visiblyOccupied
        );
    }
}


// ------------------------------------------------------------
// Default layout
//
// Normal keypoint-only:
//     [ Keypoints ] [ Simulation ]
//     [ Raw hidden] [ empty      ]
//
// Show Both:
//     [ Raw       ] [ Simulation ]
//     [ Keypoints ] [ empty      ]
//
// Raw-only:
//     [ Raw       ] [ Simulation ]
//     [ Keypoints hidden ] [empty]
//
// Once the user manually drags a tile, we stop forcing the
// default arrangement.
// ------------------------------------------------------------

function d7hApplyDefaultWorkspaceLayout() {
    if (
        !d7hWorkspace
        ||
        d7hWorkspaceManualLayout
    ) {
        d7hUpdateSlotVisuals();
        return;
    }


    const raw =
        document.getElementById(
            "rawCameraView"
        );

    const keypoint =
        document.getElementById(
            "keypointCameraView"
        );

    const simulation =
        document.querySelector(
            ".workspace-tile.mujoco-panel"
        );


    if (
        !raw
        ||
        !keypoint
        ||
        !simulation
    ) {
        return;
    }


    let order;


    if (state.showBothCameras) {
        order = [
            raw,
            simulation,
            keypoint,
        ];
    }

    else if (
        state.keypointsEnabled
    ) {
        order = [
            keypoint,
            simulation,
            raw,
        ];
    }

    else {
        order = [
            raw,
            simulation,
            keypoint,
        ];
    }


    order.forEach(
        (
            tile,
            index
        ) => {
            d7hWorkspaceSlots[
                index
            ]?.appendChild(
                tile
            );
        }
    );


    d7hUpdateSlotVisuals();
}


// ------------------------------------------------------------
// Move Keypoints / Show Both controls into the active Camera
// tile header.
//
// When both views are visible, controls sit in Raw Camera's
// header as requested.
// ------------------------------------------------------------

function d7hSyncCameraControlsHost() {
    if (!d7hCameraActions) {
        return;
    }


    const launcherControls =
        document.querySelector(
            ".system-launch-controls"
        );

    const stateBadge =
        document.getElementById(
            "systemLaunchState"
        );


    if (
        !launcherControls
        ||
        !stateBadge
    ) {
        return;
    }


    /*
     * Keep the exact existing Camera controls and event
     * handlers, but move them into the System Launcher.
     *
     * Order:
     *
     * Simulation
     * Launch Simulation
     * Keypoints
     * Show Both
     * OFF / LIVE
     */
    if (
        d7hCameraActions.parentElement
        !== launcherControls
    ) {
        launcherControls.insertBefore(
            d7hCameraActions,
            stateBadge
        );
    }
}


// Called after existing Camera mode changes.
function syncWorkspaceCameraMode() {
    if (!d7hWorkspace) {
        return;
    }


    d7hSyncCameraControlsHost();

    d7hApplyDefaultWorkspaceLayout();

    d7hUpdateSlotVisuals();
}


// ------------------------------------------------------------
// FLIP animation after a tile swap
// ------------------------------------------------------------

function d7hCaptureTileRects() {
    const result =
        new Map();


    document
        .querySelectorAll(
            ".workspace-tile"
        )
        .forEach(
            (tile) => {
                if (
                    tile.classList
                        .contains(
                            "hidden"
                        )
                ) {
                    return;
                }


                result.set(
                    tile,
                    tile
                        .getBoundingClientRect()
                );
            }
        );


    return result;
}


function d7hAnimateTileSwap(
    before
) {
    for (
        const [
            tile,
            oldRect,
        ]
        of before
    ) {
        if (
            !tile.isConnected
            ||
            tile.classList
                .contains(
                    "hidden"
                )
        ) {
            continue;
        }


        const newRect =
            tile.getBoundingClientRect();


        const dx =
            oldRect.left
            -
            newRect.left;

        const dy =
            oldRect.top
            -
            newRect.top;


        if (
            Math.abs(dx) < 1
            &&
            Math.abs(dy) < 1
        ) {
            continue;
        }


        /*
         * D15T — RELEASE FINISHED FLIP TRANSFORM
         *
         * The original FLIP animation used fill:"both" and was
         * never cancelled. After a swap, that completed Web
         * Animation could continue owning the tile's transform,
         * preventing later CSS rearrange wiggles from becoming
         * visible.
         *
         * Keep the exact same FLIP animation, but release it as
         * soon as the transition finishes.
         */
        const flipAnimation =
            tile.animate(
                [
                    {
                        transform:
                            `translate3d(${dx}px, ${dy}px, 0) scale(0.985)`,
                    },

                    {
                        transform:
                            "translate3d(0, 0, 0) scale(1)",
                    },
                ],
                {
                    duration: 290,

                    easing:
                        "cubic-bezier(0.2, 0.85, 0.25, 1)",

                    fill: "both",
                }
            );


        flipAnimation.addEventListener(
            "finish",
            () => {
                flipAnimation.cancel();
            },
            {
                once: true,
            }
        );
    }
}


// ------------------------------------------------------------
// Drag lifecycle
// ------------------------------------------------------------

function d7hClearTargetSlot() {
    for (
        const slot
        of d7hWorkspaceSlots
    ) {
        slot.classList.remove(
            "workspace-slot-target"
        );
    }
}


function d7hBeginDrag(
    event,
    pending
) {
    if (
        !pending
        ||
        d7hDragState
    ) {
        return;
    }


    clearTimeout(
        pending.timer
    );


    d7hWorkspaceManualLayout =
        true;


    d7hDragState = {
        pointerId:
            event.pointerId,

        tile:
            pending.tile,

        header:
            pending.header,

        originSlot:
            pending.tile
                .parentElement,

        startX:
            pending.startX,

        startY:
            pending.startY,

        targetSlot: null,
    };


    d7hDragPending =
        null;


    pending.tile
        .classList
        .add(
            "workspace-dragging"
        );


    d7hWorkspace
        ?.classList
        .add(
            "workspace-arranging"
        );


    try {
        pending.header
            .setPointerCapture(
                event.pointerId
            );
    }

    catch (_) {
        // Pointer capture is an enhancement only.
    }
}


function d7hMoveDrag(
    event
) {
    if (
        !d7hDragState
        ||
        event.pointerId
        !== d7hDragState.pointerId
    ) {
        return;
    }


    event.preventDefault();


    const dx =
        event.clientX
        -
        d7hDragState.startX;

    const dy =
        event.clientY
        -
        d7hDragState.startY;


    d7hDragState.tile
        .style
        .setProperty(
            "--workspace-drag-x",
            `${dx}px`
        );


    d7hDragState.tile
        .style
        .setProperty(
            "--workspace-drag-y",
            `${dy}px`
        );


    /*
     * D14V — 2X2 QUADRANT DROP TARGETING
     *
     * The workspace always represents four logical positions:
     *
     *     slot 1 | slot 2
     *     -------+-------
     *     slot 3 | slot 4
     *
     * Older compaction CSS can collapse an empty slot's own
     * bounding rectangle. Therefore destination selection must
     * not depend on whether that slot currently contains a
     * visible tile.
     *
     * Instead, map the pointer directly into one of the four
     * workspace quadrants.
     */
    let target =
        null;


    const workspaceRect =
        d7hWorkspace
            ?.getBoundingClientRect();


    if (
        workspaceRect
        &&
        event.clientX >= workspaceRect.left
        &&
        event.clientX <= workspaceRect.right
        &&
        event.clientY >= workspaceRect.top
        &&
        event.clientY <= workspaceRect.bottom
    ) {
        const midX =
            workspaceRect.left
            +
            workspaceRect.width / 2;


        const midY =
            workspaceRect.top
            +
            workspaceRect.height / 2;


        const column =
            event.clientX < midX
                ? 0
                : 1;


        const row =
            event.clientY < midY
                ? 0
                : 1;


        const index =
            row * 2 + column;


        target =
            d7hWorkspaceSlots[
                index
            ]
            || null;
    }


    d7hClearTargetSlot();


    if (
        target
        &&
        d7hWorkspace
            ?.contains(
                target
            )
    ) {
        target.classList.add(
            "workspace-slot-target"
        );

        d7hDragState.targetSlot =
            target;
    }

    else {
        d7hDragState.targetSlot =
            null;
    }
}


function d7hFinishDrag(
    event
) {
    if (
        d7hDragPending
        &&
        (
            event.pointerId
            ===
            d7hDragPending.pointerId
        )
    ) {
        clearTimeout(
            d7hDragPending.timer
        );

        d7hDragPending =
            null;
    }


    if (
        !d7hDragState
        ||
        event.pointerId
        !== d7hDragState.pointerId
    ) {
        return;
    }


    const {
        tile,
        header,
        originSlot,
        targetSlot,
    } = d7hDragState;


    const before =
        d7hCaptureTileRects();


    d7hClearTargetSlot();


    if (
        targetSlot
        &&
        targetSlot
        !== originSlot
    ) {
        const targetTile =
            d7hTileInSlot(
                targetSlot
            );


        if (
            targetTile
            &&
            targetTile
            !== tile
        ) {
            originSlot.appendChild(
                targetTile
            );
        }


        targetSlot.appendChild(
            tile
        );
    }


    tile.classList.remove(
        "workspace-dragging"
    );


    tile.style.removeProperty(
        "--workspace-drag-x"
    );

    tile.style.removeProperty(
        "--workspace-drag-y"
    );


    d7hWorkspace
        ?.classList
        .remove(
            "workspace-arranging"
        );


    try {
        header.releasePointerCapture(
            event.pointerId
        );
    }

    catch (_) {
        // Safe to ignore.
    }


    d7hDragState =
        null;


    d7hUpdateSlotVisuals();



    d7hAnimateTileSwap(
        before
    );
}


function d7hPrepareTileDrag(
    tile
) {
    const header =
        tile.querySelector(
            ".workspace-tile-header"
        );


    if (!header) {
        return;
    }


    header.addEventListener(
        "pointerdown",
        (event) => {
            if (
                event.button !== 0
                ||
                event.target.closest(
                    "button, input, select, a"
                )
            ) {
                return;
            }


            const pending = {
                pointerId:
                    event.pointerId,

                tile,

                header,

                startX:
                    event.clientX,

                startY:
                    event.clientY,

                timer: null,
            };


            pending.timer =
                setTimeout(
                    () => {
                        d7hBeginDrag(
                            event,
                            pending
                        );
                    },
                    115
                );


            d7hDragPending =
                pending;
        }
    );


    header.addEventListener(
        "pointermove",
        (event) => {
            if (
                d7hDragState
                &&
                event.pointerId
                ===
                d7hDragState.pointerId
            ) {
                d7hMoveDrag(
                    event
                );

                return;
            }


            if (
                !d7hDragPending
                ||
                event.pointerId
                !==
                d7hDragPending.pointerId
            ) {
                return;
            }


            const dx =
                event.clientX
                -
                d7hDragPending.startX;

            const dy =
                event.clientY
                -
                d7hDragPending.startY;


            if (
                Math.hypot(
                    dx,
                    dy
                )
                >
                6
            ) {
                d7hBeginDrag(
                    event,
                    d7hDragPending
                );

                d7hMoveDrag(
                    event
                );
            }
        }
    );


    header.addEventListener(
        "pointerup",
        d7hFinishDrag
    );


    header.addEventListener(
        "pointercancel",
        d7hFinishDrag
    );
}


// ------------------------------------------------------------
// Build the actual four-slot workspace from the existing DOM.
//
// We move nodes only. We do not duplicate Camera or MuJoCo
// render elements.
// ------------------------------------------------------------

function setupD7HMovableWorkspace() {
    if (
        document.getElementById(
            "mediaWorkspace"
        )
    ) {
        return;
    }


    const mediaGrid =
        document.querySelector(
            ".live-media-grid"
        );

    const oldCameraPanel =
        mediaGrid
            ?.querySelector(
                ".panel.camera-panel"
            );

    const raw =
        document.getElementById(
            "rawCameraView"
        );

    const keypoint =
        document.getElementById(
            "keypointCameraView"
        );

    const simulation =
        mediaGrid
            ?.querySelector(
                ".panel.mujoco-panel"
            );


    if (
        !mediaGrid
        ||
        !oldCameraPanel
        ||
        !raw
        ||
        !keypoint
        ||
        !simulation
    ) {
        return;
    }


    d7hCameraActions =
        oldCameraPanel
            .querySelector(
                ".camera-header-actions"
            );


    /*
     * Convert existing Camera feed sections into standalone
     * cards.
     */
    for (
        const [
            tile,
            name,
        ]
        of [
            [
                raw,
                "raw",
            ],
            [
                keypoint,
                "keypoint",
            ],
        ]
    ) {
        tile.classList.add(
            "workspace-tile",
            "camera-panel"
        );

        tile.dataset.workspaceTile =
            name;


        const header =
            tile.querySelector(
                ".camera-feed-label"
            );


        header?.classList.add(
            "workspace-tile-header"
        );
    }


    simulation.classList.add(
        "workspace-tile"
    );

    simulation.dataset.workspaceTile =
        "simulation";


    simulation
        .querySelector(
            ".panel-header"
        )
        ?.classList
        .add(
            "workspace-tile-header"
        );


    /*
     * Reuse the exact existing media-grid DOM node.
     */
    mediaGrid.id =
        "mediaWorkspace";

    mediaGrid.className =
        "media-workspace";


    const slots = [];


    for (
        let index = 0;
        index < 4;
        index += 1
    ) {
        const slot =
            document.createElement(
                "div"
            );

        slot.className =
            "workspace-slot workspace-slot-empty";

        slot.dataset.workspaceSlot =
            String(
                index + 1
            );


        slots.push(
            slot
        );
    }


    /*
     * Removing the old Camera parent here is safe because we
     * already hold references to the exact Raw / Keypoint
     * nodes and Camera controls.
     */
    mediaGrid.replaceChildren(
        ...slots
    );


    d7hWorkspace =
        mediaGrid;

    d7hWorkspaceSlots =
        slots;


    /*
     * Initial placement is mode-aware.
     */
    if (state.showBothCameras) {
        slots[0].appendChild(
            raw
        );

        slots[1].appendChild(
            simulation
        );

        slots[2].appendChild(
            keypoint
        );
    }

    else if (
        state.keypointsEnabled
    ) {
        slots[0].appendChild(
            keypoint
        );

        slots[1].appendChild(
            simulation
        );

        slots[2].appendChild(
            raw
        );
    }

    else {
        slots[0].appendChild(
            raw
        );

        slots[1].appendChild(
            simulation
        );

        slots[2].appendChild(
            keypoint
        );
    }


    d7hSyncCameraControlsHost();

    d7hUpdateSlotVisuals();


    for (
        const tile
        of [
            raw,
            keypoint,
            simulation,
        ]
    ) {
        d7hPrepareTileDrag(
            tile
        );
    }


    /*
     * Existing Camera mode handlers were registered earlier
     * in app.js.
     *
     * These listeners run afterward and only synchronize the
     * workspace layout/controls.
     */
    document
        .getElementById(
            "keypointToggleButton"
        )
        ?.addEventListener(
            "click",
            () => {
                queueMicrotask(
                    syncWorkspaceCameraMode
                );
            }
        );


    document
        .getElementById(
            "bothToggleButton"
        )
        ?.addEventListener(
            "click",
            () => {
                queueMicrotask(
                    syncWorkspaceCameraMode
                );
            }
        );
}


// ============================================================
// D7H CUSTOM SYSTEM TARGET PICKER
// ============================================================

function setupD7HTargetPicker() {
    const select =
        document.getElementById(
            "systemTargetSelect"
        );


    if (
        !select
        ||
        document.getElementById(
            "systemTargetPicker"
        )
    ) {
        return;
    }


    select.classList.add(
        "native-target-select-hidden"
    );


    select.tabIndex =
        -1;


    const picker =
        document.createElement(
            "div"
        );

    picker.id =
        "systemTargetPicker";

    picker.className =
        "system-target-picker";


    const button =
        document.createElement(
            "button"
        );

    button.type =
        "button";

    button.id =
        "systemTargetPickerButton";

    button.className =
        "system-target-button";

    button.setAttribute(
        "aria-haspopup",
        "listbox"
    );

    button.setAttribute(
        "aria-expanded",
        "false"
    );


    const label =
        document.createElement(
            "span"
        );

    label.className =
        "system-target-picker-label";


    const chevron =
        document.createElement(
            "span"
        );

    chevron.className =
        "system-target-chevron";

    chevron.setAttribute(
        "aria-hidden",
        "true"
    );

    chevron.textContent =
        "⌄";


    button.append(
        label,
        chevron
    );


    const menu =
        document.createElement(
            "div"
        );

    menu.id =
        "systemTargetMenu";

    menu.className =
        "system-target-menu";

    menu.setAttribute(
        "role",
        "listbox"
    );

    menu.hidden =
        true;


    const choices = [
        [
            "sim",
            "Simulation",
        ],

        [
            "robot",
            "Physical Robot",
        ],
    ];


    function sync() {
        const current =
            choices.find(
                (
                    [
                        value,
                    ]
                ) =>
                    value
                    ===
                    select.value
            )
            ||
            choices[0];


        label.textContent =
            current[1];


        button.disabled =
            select.disabled;


        menu
            .querySelectorAll(
                ".system-target-option"
            )
            .forEach(
                (option) => {
                    const selected =
                        option.dataset
                            .value
                        ===
                        select.value;


                    option.classList.toggle(
                        "selected",
                        selected
                    );

                    option.setAttribute(
                        "aria-selected",
                        selected
                            ? "true"
                            : "false"
                    );
                }
            );


        if (select.disabled) {
            closeMenu();
        }
    }


    function closeMenu() {
        menu.hidden =
            true;

        picker.classList.remove(
            "open"
        );

        button.setAttribute(
            "aria-expanded",
            "false"
        );
    }


    function openMenu() {
        if (select.disabled) {
            return;
        }


        menu.hidden =
            false;

        picker.classList.add(
            "open"
        );

        button.setAttribute(
            "aria-expanded",
            "true"
        );
    }


    for (
        const [
            value,
            title,
        ]
        of choices
    ) {
        const option =
            document.createElement(
                "button"
            );

        option.type =
            "button";

        option.className =
            "system-target-option";

        option.dataset.value =
            value;

        option.setAttribute(
            "role",
            "option"
        );

        option.textContent =
            title;


        option.addEventListener(
            "click",
            () => {
                select.value =
                    value;


                select.dispatchEvent(
                    new Event(
                        "change",
                        {
                            bubbles: true,
                        }
                    )
                );


                sync();

                closeMenu();

                button.focus();
            }
        );


        menu.appendChild(
            option
        );
    }


    button.addEventListener(
        "click",
        () => {
            if (menu.hidden) {
                openMenu();
            }

            else {
                closeMenu();
            }
        }
    );


    picker.addEventListener(
        "keydown",
        (event) => {
            if (
                event.key
                === "Escape"
            ) {
                closeMenu();

                button.focus();
            }
        }
    );


    document.addEventListener(
        "pointerdown",
        (event) => {
            if (
                !picker.contains(
                    event.target
                )
            ) {
                closeMenu();
            }
        }
    );


    select.addEventListener(
        "change",
        sync
    );


    const observer =
        new MutationObserver(
            sync
        );


    observer.observe(
        select,
        {
            attributes: true,

            attributeFilter: [
                "disabled",
            ],
        }
    );


    picker.append(
        button,
        menu
    );


    select.insertAdjacentElement(
        "afterend",
        picker
    );


    sync();
}


// ============================================================
// D7H INIT
// ============================================================

function setupD7HInterface() {
    setupD7HMovableWorkspace();

    setupD7HTargetPicker();
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        setupD7HInterface,
        {
            once: true,
        }
    );
}

else {
    setupD7HInterface();
}



// ============================================================
// D8A_REFERENCE_UI
// ============================================================

let d8LaunchButton = null;
let d8StopButton = null;


// ------------------------------------------------------------
// Helper
// ------------------------------------------------------------

function d8MakeStatusRow(
    labelText,
    valueNode
) {
    const row =
        document.createElement(
            "div"
        );

    row.className =
        "node-status-row";


    const label =
        document.createElement(
            "span"
        );

    label.className =
        "node-status-label";

    label.textContent =
        labelText;


    row.appendChild(
        label
    );


    if (valueNode) {
        row.appendChild(
            valueNode
        );
    }


    return row;
}


// ------------------------------------------------------------
// Sidebar
// ------------------------------------------------------------

function d8BuildSidebar() {
    const sidebar =
        document.querySelector(
            ".sidebar"
        );

    const brand =
        sidebar
            ?.querySelector(
                ".brand"
            );

    const nav =
        sidebar
            ?.querySelector(
                "nav"
            );


    if (
        !sidebar
        ||
        !brand
        ||
        !nav
    ) {
        return;
    }


    /*
     * Final brand.
     */
    const brandTitle =
        brand.querySelector(
            ".brand-title"
        );


    if (brandTitle) {
        brandTitle.textContent =
            "Bacalbasa";
    }


    /*
     * Move the already-working Dashboard badge beneath brand.
     */
    const systemBadge =
        document.getElementById(
            "systemBadge"
        );


    if (
        systemBadge
        &&
        systemBadge.parentElement
        !== brand
    ) {
        brand.appendChild(
            systemBadge
        );
    }


    /*
     * Remove unwanted navigation options visually and from
     * tab order.
     */
    sidebar
        .querySelectorAll(
            '.nav-item[data-view="teleop"], '
            +
            '.nav-item[data-view="system"]'
        )
        .forEach(
            (button) => {
                button.remove();
            }
        );


    let sections =
        document.getElementById(
            "designSidebarSections"
        );


    if (sections) {
        return;
    }


    sections =
        document.createElement(
            "div"
        );

    sections.id =
        "designSidebarSections";

    sections.className =
        "design-sidebar-sections";


    // --------------------------------------------------------
    // NODE STATUS
    // --------------------------------------------------------

    const nodeCard =
        document.createElement(
            "section"
        );

    nodeCard.className =
        "design-side-card";


    const nodeTitle =
        document.createElement(
            "div"
        );

    nodeTitle.className =
        "design-side-title";

    nodeTitle.textContent =
        "Node Status";


    nodeCard.appendChild(
        nodeTitle
    );


    /*
     * System target / launcher selection.
     */
    const targetField =
        document.querySelector(
            ".system-target-field"
        );


    if (targetField) {
        const targetLabel =
            document.createElement(
                "span"
            );

        targetLabel.className =
            "design-target-label";

        targetLabel.textContent =
            "System Target";


        nodeCard.appendChild(
            targetLabel
        );

        nodeCard.appendChild(
            targetField
        );
    }


    const statusList =
        document.createElement(
            "div"
        );

    statusList.className =
        "design-status-list";


    /*
     * Preserve all existing status IDs.
     *
     * updateDemoControlStrip() therefore continues updating
     * these exact nodes.
     */
    const statusDefinitions = [
        [
            "System",
            "systemLaunchState",
        ],

        [
            "Simulation",
            "demoSimState",
        ],

        [
            "SONIC",
            "demoSonicState",
        ],

        [
            "Camera",
            "demoCameraState",
        ],

        [
            "Alignment",
            "demoAlignState",
        ],

        [
            "Tracking",
            "demoTrackingState",
        ],
    ];


    for (
        const [
            label,
            id,
        ]
        of statusDefinitions
    ) {
        const value =
            document.getElementById(
                id
            );


        if (value) {
            statusList.appendChild(
                d8MakeStatusRow(
                    label,
                    value
                )
            );
        }
    }


    nodeCard.appendChild(
        statusList
    );


    // --------------------------------------------------------
    // DISPLAY SETTINGS
    // --------------------------------------------------------

    const displayCard =
        document.createElement(
            "section"
        );

    displayCard.className =
        "design-side-card";


    const displayTitle =
        document.createElement(
            "div"
        );

    displayTitle.className =
        "design-side-title";

    displayTitle.textContent =
        "Display Settings";


    displayCard.appendChild(
        displayTitle
    );


    const settings = [
        [
            "Keypoints",
            document.getElementById(
                "keypointToggleButton"
            ),
        ],

        [
            "Show Both",
            document.getElementById(
                "bothToggleButton"
            ),
        ],
    ];


    for (
        const [
            labelText,
            button,
        ]
        of settings
    ) {
        if (!button) {
            continue;
        }


        const row =
            document.createElement(
                "div"
            );

        row.className =
            "design-setting-row";


        const label =
            document.createElement(
                "span"
            );

        label.className =
            "design-setting-label";

        label.textContent =
            labelText;


        row.append(
            label,
            button
        );


        displayCard.appendChild(
            row
        );
    }


    sections.append(
        nodeCard,
        displayCard
    );


    nav.insertAdjacentElement(
        "afterend",
        sections
    );
}


// ------------------------------------------------------------
// Top actions
// ------------------------------------------------------------

function d8BuildTopActions() {
    const topbar =
        document.querySelector(
            ".topbar"
        );


    if (
        !topbar
        ||
        document.getElementById(
            "designTopActions"
        )
    ) {
        return;
    }


    const title =
        document.getElementById(
            "pageTitle"
        );


    if (title) {
        title.textContent =
            "Camera Teleoperation";
    }


    const actions =
        document.createElement(
            "div"
        );

    actions.id =
        "designTopActions";

    actions.className =
        "design-top-actions";


    d8LaunchButton =
        document.createElement(
            "button"
        );

    d8LaunchButton.type =
        "button";

    d8LaunchButton.className =
        "design-launch-button";

    d8LaunchButton.textContent =
        "Launch Simulation";


    d8StopButton =
        document.createElement(
            "button"
        );

    d8StopButton.type =
        "button";

    d8StopButton.className =
        "design-stop-button";

    d8StopButton.textContent =
        "Stop System";


    d8LaunchButton.addEventListener(
        "click",
        () => {
            const stack =
                latestDemoStatus
                    ?.stack
                || {};


            if (
                stack.active
                ||
                systemRequestPending
            ) {
                return;
            }


            /*
             * Reuse the existing one-button implementation.
             */
            handleSystemPrimaryAction();
        }
    );


    d8StopButton.addEventListener(
        "click",
        () => {
            const stack =
                latestDemoStatus
                    ?.stack
                || {};


            if (
                !stack.active
                ||
                systemRequestPending
            ) {
                return;
            }


            /*
             * Existing handler selects /stop when stack.active.
             */
            handleSystemPrimaryAction();
        }
    );


    actions.append(
        d8LaunchButton,
        d8StopButton
    );


    topbar.appendChild(
        actions
    );
}


// ------------------------------------------------------------
// Synchronize top actions with existing backend state.
// ------------------------------------------------------------

function d8SyncActions(
    data
) {
    if (
        !d8LaunchButton
        ||
        !d8StopButton
    ) {
        return;
    }


    const stack =
        data?.stack
        || {};


    const active =
        Boolean(
            stack.active
        );


    const select =
        document.getElementById(
            "systemTargetSelect"
        );


    const target =
        select?.value
        || "sim";


    const robot =
        target
        === "robot";


    d8LaunchButton.textContent =
        robot
            ? "Deploy to Robot"
            : "Launch Simulation";


    /*
     * Physical execution remains deliberately locked.
     */
    d8LaunchButton.disabled =
        Boolean(
            systemRequestPending
            ||
            active
            ||
            !state.backendOnline
            ||
            robot
        );


    d8StopButton.disabled =
        Boolean(
            systemRequestPending
            ||
            !active
        );
}


// ------------------------------------------------------------
// Center workspace labels.
// ------------------------------------------------------------

function d8StyleWorkspace() {
    const workspace =
        document.getElementById(
            "mediaWorkspace"
        );


    if (workspace) {
        workspace.classList.add(
            "reference-workspace"
        );
    }


    const rawTitle =
        document
            .getElementById(
                "rawCameraView"
            )
            ?.querySelector(
                ".camera-feed-label strong"
            );


    const keypointTitle =
        document
            .getElementById(
                "keypointCameraView"
            )
            ?.querySelector(
                ".camera-feed-label strong"
            );


    const simulationTitle =
        document
            .querySelector(
                ".workspace-tile.mujoco-panel "
                +
                ".panel-header h2"
            );


    if (rawTitle) {
        rawTitle.textContent =
            "RAW / OPTICAL";
    }


    if (keypointTitle) {
        keypointTitle.textContent =
            "SPATIAL KEYPOINTS";
    }


    if (simulationTitle) {
        simulationTitle.textContent =
            "SIM / VIRTUAL";
    }
}


// ------------------------------------------------------------
// Hook the existing status update rather than creating a new
// polling path.
// ------------------------------------------------------------

const d8OriginalUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d8OriginalUpdateDemoControlStrip(
            data
        );

        d8SyncActions(
            data
        );
    };


// ------------------------------------------------------------
// Final setup
// ------------------------------------------------------------

function setupD8ReferenceUI() {
    d8BuildSidebar();

    d8BuildTopActions();

    d8StyleWorkspace();


    /*
     * Existing custom target picker dispatches change through
     * the hidden native select. Keep using that.
     */
    document
        .getElementById(
            "systemTargetSelect"
        )
        ?.addEventListener(
            "change",
            () => {
                d8SyncActions(
                    latestDemoStatus
                );
            }
        );


    d8SyncActions(
        latestDemoStatus
    );
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        setupD8ReferenceUI,
        {
            once: true,
        }
    );
}

else {
    setupD8ReferenceUI();
}



// ============================================================
// D9C_ROBOT_CONNECTIVITY
// ============================================================

let d9cRobotPollTimer = null;


function d9cRobotSelected() {
    const select =
        document.getElementById(
            "systemTargetSelect"
        );

    return (
        select?.value
        === "robot"
    );
}


function d9cGetRobotBar() {
    let bar =
        document.getElementById(
            "robotConnectionBar"
        );

    if (bar) {
        return bar;
    }


    const targetField =
        document.querySelector(
            ".design-side-card "
            +
            ".system-target-field"
        );


    if (!targetField) {
        return null;
    }


    bar =
        document.createElement(
            "div"
        );

    bar.id =
        "robotConnectionBar";

    bar.className =
        "robot-connection-bar";

    bar.hidden =
        true;


    const dot =
        document.createElement(
            "span"
        );

    dot.className =
        "robot-connection-dot";


    const state =
        document.createElement(
            "strong"
        );

    state.id =
        "robotConnectionState";

    state.textContent =
        "CHECKING";


    const endpoint =
        document.createElement(
            "span"
        );

    endpoint.className =
        "robot-connection-endpoint";

    endpoint.textContent =
        "G1 · 192.168.0.116";


    bar.append(
        dot,
        state,
        endpoint
    );


    targetField.insertAdjacentElement(
        "afterend",
        bar
    );


    return bar;
}


function d9cSetRobotBar(
    status,
    mode
) {
    const bar =
        d9cGetRobotBar();

    if (!bar) {
        return;
    }


    const state =
        document.getElementById(
            "robotConnectionState"
        );


    bar.classList.remove(
        "connected",
        "disconnected",
        "checking"
    );


    bar.classList.add(
        mode
    );


    if (state) {
        state.textContent =
            status;
    }
}


async function d9cRefreshRobotConnection() {
    const bar =
        d9cGetRobotBar();


    if (!bar) {
        return;
    }


    if (!d9cRobotSelected()) {
        bar.hidden =
            true;

        return;
    }


    bar.hidden =
        false;


    d9cSetRobotBar(
        "CHECKING",
        "checking"
    );


    try {
        const response =
            await fetch(
                "/api/robot/connectivity",
                {
                    cache:
                        "no-store",
                }
            );


        if (!response.ok) {
            throw new Error(
                "Connectivity API failed"
            );
        }


        const data =
            await response.json();


        if (data.connected) {
            d9cSetRobotBar(
                "CONNECTED",
                "connected"
            );
        }

        else {
            d9cSetRobotBar(
                "DISCONNECTED",
                "disconnected"
            );
        }
    }

    catch (error) {
        d9cSetRobotBar(
            "DISCONNECTED",
            "disconnected"
        );
    }
}


function d9cSyncRobotConnectivity() {
    const bar =
        d9cGetRobotBar();


    if (!bar) {
        return;
    }


    if (d9cRobotSelected()) {
        bar.hidden =
            false;

        d9cRefreshRobotConnection();


        if (!d9cRobotPollTimer) {
            d9cRobotPollTimer =
                window.setInterval(
                    d9cRefreshRobotConnection,
                    2000
                );
        }
    }

    else {
        bar.hidden =
            true;


        if (d9cRobotPollTimer) {
            window.clearInterval(
                d9cRobotPollTimer
            );

            d9cRobotPollTimer =
                null;
        }
    }
}


function d9cSetupRobotConnectivity() {
    d9cGetRobotBar();


    document
        .getElementById(
            "systemTargetSelect"
        )
        ?.addEventListener(
            "change",
            d9cSyncRobotConnectivity
        );


    window.addEventListener(
        "focus",
        () => {
            if (
                d9cRobotSelected()
            ) {
                d9cRefreshRobotConnection();
            }
        }
    );


    d9cSyncRobotConnectivity();
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            /*
             * D8 builds/moves the sidebar first.
             */
            queueMicrotask(
                d9cSetupRobotConnectivity
            );
        },
        {
            once: true,
        }
    );
}

else {
    queueMicrotask(
        d9cSetupRobotConnectivity
    );
}



// ============================================================
// D10B_TWO_STAGE_PHYSICAL
// ============================================================

function d10bPhysicalState() {
    return (
        latestDemoStatus
            ?.physical
        || {
            state: "off",
            active: false,
            ready_to_start: false,
            live: false,
        }
    );
}


function d10bSyncPhysicalActions(
    data
) {
    const select =
        document.getElementById(
            "systemTargetSelect"
        );

    const robot =
        (
            select?.value
            === "robot"
        );


    if (!robot) {
        return;
    }


    const physical =
        data?.physical
        || {};


    const physicalState =
        physical.state
        || "off";


    if (
        typeof d8LaunchButton
        !== "undefined"
        &&
        d8LaunchButton
    ) {
        let text =
            "Deploy to Robot";

        let disabled =
            Boolean(
                systemRequestPending
                ||
                !state.backendOnline
            );


        if (
            physicalState
            === "ready_to_start"
        ) {
            text =
                "Start";
        }

        else if (
            physicalState
            === "live"
        ) {
            text =
                "Robot Live";

            disabled =
                true;
        }

        else if (
            physicalState
            === "validation_failed"
        ) {
            text =
                "Validation Failed";

            disabled =
                true;
        }

        else if (
            physicalState
            === "physical_init_failed"
        ) {
            text =
                "Physical Init Failed";

            disabled =
                true;
        }

        else if (
            physical.active
        ) {
            text =
                (
                    physicalState
                        .replaceAll(
                            "_",
                            " "
                        )
                        .replace(
                            /\b\w/g,
                            (c) =>
                                c.toUpperCase()
                        )
                )
                + "...";

            disabled =
                true;
        }

        else if (
            physicalState
            === "error"
        ) {
            text =
                "Deploy to Robot";
        }


        d8LaunchButton.textContent =
            text;

        d8LaunchButton.disabled =
            disabled;
    }


    if (
        typeof d8StopButton
        !== "undefined"
        &&
        d8StopButton
    ) {
        d8StopButton.disabled =
            Boolean(
                systemRequestPending
                ||
                !physical.active
            );
    }


    if (select) {
        select.disabled =
            Boolean(
                physical.active
                ||
                systemRequestPending
            );
    }
}


// Wrap the already-working UI status updater.
// D8 runs first; D10B then applies physical semantics.
const d10bPreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d10bPreviousUpdateDemoControlStrip(
            data
        );

        d10bSyncPhysicalActions(
            data
        );
    };


// Existing D8 button callbacks resolve this global function
// at click time, so Simulation remains unchanged and Physical
// gets the new two-stage endpoints.
const d10bSimulationSystemAction =
    handleSystemPrimaryAction;


handleSystemPrimaryAction =
    async function () {
        if (
            selectedSystemTarget
            !== "robot"
        ) {
            return (
                d10bSimulationSystemAction()
            );
        }


        if (systemRequestPending) {
            return;
        }


        const physical =
            d10bPhysicalState();


        let endpoint = null;

        let startMessage = "";


        if (
            physical.state
            === "ready_to_start"
        ) {
            endpoint =
                "/api/system/robot/start";

            startMessage =
                (
                    "Requesting physical CONTROL. "
                    +
                    "The dashboard will wait for confirmed "
                    +
                    "reference before enabling live V2."
                );
        }

        else if (
            !physical.active
        ) {
            endpoint =
                "/api/system/robot/deploy";

            startMessage =
                (
                    "Preparing V2 cameras, validation simulation "
                    +
                    "and physical SONIC. Physical CONTROL will "
                    +
                    "NOT be entered during this stage."
                );
        }

        else {
            return;
        }


        systemRequestPending =
            true;


        if (latestDemoStatus) {
            updateDemoControlStrip(
                latestDemoStatus
            );
        }


        setActionMessage(
            startMessage
        );


        try {
            await fetchJson(
                endpoint,
                {
                    method: "POST",
                }
            );
        }

        catch (error) {
            setActionMessage(
                error.message,
                true
            );
        }

        finally {
            systemRequestPending =
                false;

            await refreshStatus();
        }
    };


// Physical Stop System must not be blocked by the old
// simulation-only `stack.active` test.
document.addEventListener(
    "click",
    async (
        event
    ) => {
        if (
            typeof d8StopButton
            === "undefined"
            ||
            !d8StopButton
            ||
            event.target
            !== d8StopButton
            ||
            selectedSystemTarget
            !== "robot"
        ) {
            return;
        }


        event.preventDefault();
        event.stopImmediatePropagation();


        if (systemRequestPending) {
            return;
        }


        const physical =
            d10bPhysicalState();


        if (!physical.active) {
            return;
        }


        systemRequestPending =
            true;


        if (latestDemoStatus) {
            updateDemoControlStrip(
                latestDemoStatus
            );
        }


        setActionMessage(
            "Stopping physical stack..."
        );


        try {
            await fetchJson(
                "/api/system/robot/stop",
                {
                    method: "POST",
                }
            );

            setActionMessage(
                ""
            );
        }

        catch (error) {
            setActionMessage(
                error.message,
                true
            );
        }

        finally {
            systemRequestPending =
                false;

            await refreshStatus();
        }
    },
    true
);


// ============================================================
// D10B COMPACT WORKSPACE ROWS
// ============================================================

function d10bCompactWorkspace() {
    const workspace =
        document.getElementById(
            "mediaWorkspace"
        );


    if (!workspace) {
        return;
    }


    const slots = [
        ...workspace.querySelectorAll(
            ":scope > .workspace-slot"
        ),
    ];


    for (
        const slot
        of slots
    ) {
        const visible =
            slot.querySelector(
                ".workspace-tile:not(.hidden)"
            );


        const empty =
            !visible;


        if (
            slot.classList.contains(
                "d10b-empty-slot"
            )
            !== empty
        ) {
            slot.classList.toggle(
                "d10b-empty-slot",
                empty
            );
        }
    }


    const visibleCount =
        slots.filter(
            (
                slot
            ) =>
                !slot.classList.contains(
                    "d10b-empty-slot"
                )
        ).length;


    workspace.dataset.visibleTiles =
        String(
            visibleCount
        );
}


function d10bSetupWorkspaceCompaction() {
    const workspace =
        document.getElementById(
            "mediaWorkspace"
        );


    if (!workspace) {
        return;
    }


    d10bCompactWorkspace();


    const observer =
        new MutationObserver(
            () => {
                queueMicrotask(
                    d10bCompactWorkspace
                );
            }
        );


    observer.observe(
        workspace,
        {
            subtree: true,
            childList: true,
            attributes: true,
            attributeFilter: [
                "class",
            ],
        }
    );
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            queueMicrotask(
                d10bSetupWorkspaceCompaction
            );
        },
        {
            once: true,
        }
    );
}

else {
    queueMicrotask(
        d10bSetupWorkspaceCompaction
    );
}



// ============================================================
// D10E_TERMINAL_LOGS
// ============================================================

let d10eTerminalSource =
    "all";

let d10eTerminalAutoScroll =
    true;

let d10eTerminalTimer =
    null;

let d10eTerminalRefreshing =
    false;


const D10E_TERMINAL_ORDER = [
    "v2",
    "mujoco",
    "relay",
    "sim_sonic",
    "physical_sonic",
    "robot_camera",
    "robot_modes",
    "dashboard",
];


const D10E_TERMINAL_LABELS = {
    all:
        "ALL",

    v2:
        "V2",

    mujoco:
        "MUJOCO",

    relay:
        "RELAY",

    sim_sonic:
        "SIM SONIC",

    physical_sonic:
        "PHYSICAL SONIC",

    robot_camera:
        "ROBOT CAMERA",

    robot_modes:
        "ROBOT MODES",

    dashboard:
        "DASHBOARD",
};


function d10eBuildTerminalText(
    data
) {
    const sources =
        data?.sources
        || {};


    if (
        d10eTerminalSource
        !== "all"
    ) {
        return (
            sources[
                d10eTerminalSource
            ]?.text
            || ""
        );
    }


    const sections = [];


    for (
        const key
        of D10E_TERMINAL_ORDER
    ) {
        const source =
            sources[
                key
            ]
            || {};


        sections.push(
            (
                "============================================================\n"
                +
                `[ ${D10E_TERMINAL_LABELS[key]} ]\n`
                +
                (
                    source.path
                    || "NO LOG FILE"
                )
                +
                "\n"
                +
                "============================================================\n"
                +
                (
                    source.text
                    || ""
                )
            )
        );
    }


    return sections.join(
        "\n\n"
    );
}


async function d10eRefreshTerminalLogs() {
    if (
        d10eTerminalRefreshing
    ) {
        return;
    }


    const view =
        document.getElementById(
            "view-logs"
        );


    const output =
        document.getElementById(
            "d10eTerminalOutput"
        );


    if (
        !view
        ||
        !output
        ||
        !view.classList.contains(
            "active"
        )
    ) {
        return;
    }


    d10eTerminalRefreshing =
        true;


    try {
        const data =
            await fetchJson(
                "/api/logs/terminal"
            );


        const nearBottom =
            (
                output.scrollHeight
                -
                output.scrollTop
                -
                output.clientHeight
            )
            < 50;


        output.textContent =
            d10eBuildTerminalText(
                data
            );


        const state =
            document.getElementById(
                "d10eTerminalState"
            );


        if (state) {
            let text =
                (
                    "PHYSICAL "
                    +
                    String(
                        data.physical_state
                        || "off"
                    )
                    .toUpperCase()
                );


            if (
                data.physical_error
            ) {
                text +=
                    " · "
                    +
                    data.physical_error;
            }


            state.textContent =
                text;

            state.classList.toggle(
                "error",
                Boolean(
                    data.physical_error
                )
            );
        }


        const time =
            document.getElementById(
                "d10eTerminalTime"
            );


        if (time) {
            time.textContent =
                data.server_time
                || "";
        }


        if (
            d10eTerminalAutoScroll
            &&
            nearBottom
        ) {
            output.scrollTop =
                output.scrollHeight;
        }
    }

    catch (error) {
        output.textContent =
            (
                "LOG API ERROR\n\n"
                +
                error.message
            );
    }

    finally {
        d10eTerminalRefreshing =
            false;
    }
}


function d10eSelectTerminal(
    source
) {
    d10eTerminalSource =
        source;


    document
        .querySelectorAll(
            ".d10e-terminal-tab"
        )
        .forEach(
            (
                button
            ) => {
                button.classList.toggle(
                    "active",
                    button.dataset.source
                    === source
                );
            }
        );


    const path =
        document.getElementById(
            "d10eTerminalPath"
        );


    if (path) {
        path.textContent =
            (
                source
                === "all"
                    ? "ALL TERMINALS"
                    : D10E_TERMINAL_LABELS[
                        source
                    ]
            );
    }


    d10eRefreshTerminalLogs();
}


function d10eSetupTerminalLogs() {
    const view =
        document.getElementById(
            "view-logs"
        );


    if (
        !view
        ||
        document.getElementById(
            "d10eTerminalConsole"
        )
    ) {
        return;
    }


    /*
     * Preserve the original Logs implementation in the DOM,
     * but replace its presentation with the real terminal UI.
     */
    [
        ...view.children,
    ].forEach(
        (
            child
        ) => {
            child.style.display =
                "none";
        }
    );


    const console =
        document.createElement(
            "section"
        );

    console.id =
        "d10eTerminalConsole";

    console.className =
        "d10e-terminal-console";


    const header =
        document.createElement(
            "div"
        );

    header.className =
        "d10e-terminal-header";


    const title =
        document.createElement(
            "div"
        );

    title.className =
        "d10e-terminal-title";

    title.innerHTML =
        (
            "<strong>System Terminals</strong>"
            +
            "<span id=\"d10eTerminalPath\">ALL TERMINALS</span>"
        );


    const meta =
        document.createElement(
            "div"
        );

    meta.className =
        "d10e-terminal-meta";

    meta.innerHTML =
        (
            "<span id=\"d10eTerminalState\">PHYSICAL OFF</span>"
            +
            "<span id=\"d10eTerminalTime\"></span>"
        );


    header.append(
        title,
        meta
    );


    const toolbar =
        document.createElement(
            "div"
        );

    toolbar.className =
        "d10e-terminal-toolbar";


    for (
        const source
        of [
            "all",
            ...D10E_TERMINAL_ORDER,
        ]
    ) {
        const button =
            document.createElement(
                "button"
            );

        button.type =
            "button";

        button.className =
            "d10e-terminal-tab";

        button.dataset.source =
            source;

        button.textContent =
            D10E_TERMINAL_LABELS[
                source
            ];

        button.addEventListener(
            "click",
            () => {
                d10eSelectTerminal(
                    source
                );
            }
        );


        if (
            source
            === d10eTerminalSource
        ) {
            button.classList.add(
                "active"
            );
        }


        toolbar.appendChild(
            button
        );
    }


    const spacer =
        document.createElement(
            "span"
        );

    spacer.className =
        "d10e-terminal-spacer";

    toolbar.appendChild(
        spacer
    );


    const auto =
        document.createElement(
            "button"
        );

    auto.type =
        "button";

    auto.className =
        "d10e-terminal-control";

    auto.textContent =
        "Auto-scroll ON";


    auto.addEventListener(
        "click",
        () => {
            d10eTerminalAutoScroll =
                !d10eTerminalAutoScroll;


            auto.textContent =
                (
                    "Auto-scroll "
                    +
                    (
                        d10eTerminalAutoScroll
                            ? "ON"
                            : "OFF"
                    )
                );
        }
    );


    const refresh =
        document.createElement(
            "button"
        );

    refresh.type =
        "button";

    refresh.className =
        "d10e-terminal-control";

    refresh.textContent =
        "Refresh";

    refresh.addEventListener(
        "click",
        d10eRefreshTerminalLogs
    );


    toolbar.append(
        auto,
        refresh
    );


    const output =
        document.createElement(
            "pre"
        );

    output.id =
        "d10eTerminalOutput";

    output.className =
        "d10e-terminal-output";

    output.textContent =
        "Waiting for terminal logs...";


    console.append(
        header,
        toolbar,
        output
    );


    view.appendChild(
        console
    );


    d10eTerminalTimer =
        window.setInterval(
            d10eRefreshTerminalLogs,
            1500
        );


    d10eRefreshTerminalLogs();
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        d10eSetupTerminalLogs,
        {
            once: true,
        }
    );
}

else {
    d10eSetupTerminalLogs();
}


// ------------------------------------------------------------
// Show physical deployment failures directly on Live.
// ------------------------------------------------------------

const d10ePreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d10ePreviousUpdateDemoControlStrip(
            data
        );


        if (
            selectedSystemTarget
            !== "robot"
        ) {
            return;
        }


        const physical =
            data?.physical
            || {};


        if (
            physical.state
            === "validation_failed"
        ) {
            setActionMessage(
                (
                    "VALIDATION FAILED — "
                    +
                    (
                        physical.last_error
                        ||
                        "MuJoCo validation failed."
                    )
                    +
                    " Physical robot control was not started."
                ),
                true
            );
        }

        else if (
            physical.state
            === "physical_init_failed"
            ||
            physical.state
            === "error"
        ) {
            setActionMessage(
                (
                    "PHYSICAL DEPLOYMENT FAILED — "
                    +
                    (
                        physical.last_error
                        ||
                        "Unknown deployment error."
                    )
                ),
                true
            );
        }
    };



// ============================================================
// D11B_ROBOT_CAMERA
// ============================================================

let d11bRobotCameraStreamActive =
    false;


function d11bRobotTargetSelected() {
    return (
        document
            .getElementById(
                "systemTargetSelect"
            )
            ?.value
        === "robot"
    );
}


function d11bFindRobotCameraTile() {
    return document.getElementById(
        "robotCameraView"
    );
}


function d11bCreateRobotCameraTile() {
    const existing =
        d11bFindRobotCameraTile();

    if (existing) {
        return existing;
    }


    const workspace =
        document.getElementById(
            "mediaWorkspace"
        );


    if (!workspace) {
        return null;
    }


    const slots = [
        ...workspace.querySelectorAll(
            ":scope > .workspace-slot"
        ),
    ];


    let slot =
        slots.find(
            (
                candidate
            ) =>
                !candidate.querySelector(
                    ".workspace-tile:not(.hidden)"
                )
        );


    if (!slot) {
        slot =
            slots[
                slots.length - 1
            ];
    }


    if (!slot) {
        return null;
    }


    const tile =
        document.createElement(
            "section"
        );

    tile.id =
        "robotCameraView";

    tile.className =
        (
            "workspace-tile "
            +
            "robot-camera-panel "
            +
            "hidden"
        );


    const header =
        document.createElement(
            "div"
        );

    header.className =
        "workspace-tile-header";


    const dot =
        document.createElement(
            "span"
        );

    dot.className =
        "robot-camera-header-dot";


    const label =
        document.createElement(
            "strong"
        );

    label.textContent =
        "G1 / ROBOT CAMERA";


    const state =
        document.createElement(
            "span"
        );

    state.id =
        "robotCameraTileState";

    state.className =
        "robot-camera-tile-state";

    state.textContent =
        "OFF";


    header.append(
        dot,
        label,
        state
    );


    const stage =
        document.createElement(
            "div"
        );

    stage.className =
        "camera-stage robot-camera-stage";


    const image =
        document.createElement(
            "img"
        );

    image.id =
        "robotCameraImage";

    image.alt =
        "";

    image.hidden =
        true;


    const placeholder =
        document.createElement(
            "div"
        );

    placeholder.id =
        "robotCameraPlaceholder";

    placeholder.className =
        "robot-camera-placeholder";

    placeholder.innerHTML =
        (
            "<span class=\"robot-camera-placeholder-icon\">◉</span>"
            +
            "<strong>Robot camera idle</strong>"
            +
            "<span>Deploy to Robot to start the G1 camera.</span>"
        );


    stage.append(
        image,
        placeholder
    );


    tile.append(
        header,
        stage
    );


    slot.appendChild(
        tile
    );


    slot.classList.remove(
        "workspace-slot-empty",
        "d10b-empty-slot"
    );


    if (
        typeof d7hPrepareTileDrag
        === "function"
    ) {
        try {
            d7hPrepareTileDrag(
                tile
            );
        }

        catch (error) {
            console.warn(
                "Robot camera drag setup:",
                error
            );
        }
    }


    return tile;
}


function d11bStopBrowserRobotStream() {
    const image =
        document.getElementById(
            "robotCameraImage"
        );


    if (image) {
        image.removeAttribute(
            "src"
        );
    }


    d11bRobotCameraStreamActive =
        false;
}


function d11bSyncRobotCamera(
    data
) {
    const tile =
        d11bCreateRobotCameraTile();


    if (!tile) {
        return;
    }


    const selected =
        d11bRobotTargetSelected();


    tile.classList.toggle(
        "hidden",
        !selected
    );


    if (!selected) {
        d11bStopBrowserRobotStream();

        if (
            typeof d10bCompactWorkspace
            === "function"
        ) {
            queueMicrotask(
                d10bCompactWorkspace
            );
        }

        return;
    }


    const camera =
        data?.robot_camera
        ||
        data?.physical
            ?.robot_camera
        ||
        {};


    const live =
        Boolean(
            camera.live
        );


    const image =
        document.getElementById(
            "robotCameraImage"
        );


    const placeholder =
        document.getElementById(
            "robotCameraPlaceholder"
        );


    const state =
        document.getElementById(
            "robotCameraTileState"
        );


    if (state) {
        state.textContent =
            live
                ? "LIVE"
                : (
                    camera.process_alive
                        ? "STARTING"
                        : "OFF"
                );

        state.classList.toggle(
            "live",
            live
        );
    }


    tile.classList.toggle(
        "robot-camera-live",
        live
    );


    if (
        live
        &&
        image
        &&
        !d11bRobotCameraStreamActive
    ) {
        image.src =
            (
                "/api/robot-camera/stream.mjpg"
                +
                "?session="
                +
                Date.now()
            );

        d11bRobotCameraStreamActive =
            true;
    }


    if (
        !live
        &&
        d11bRobotCameraStreamActive
    ) {
        d11bStopBrowserRobotStream();
    }


    if (image) {
        image.hidden =
            !live;
    }


    if (placeholder) {
        placeholder.hidden =
            live;

        if (!live) {
            const detail =
                placeholder
                    .querySelector(
                        "span:last-child"
                    );


            if (detail) {
                detail.textContent =
                    camera.last_error
                    ||
                    (
                        camera.process_alive
                            ? "Connecting to the G1 camera..."
                            : "Deploy to Robot to start the G1 camera."
                    );
            }
        }
    }


    if (
        typeof d10bCompactWorkspace
        === "function"
    ) {
        queueMicrotask(
            d10bCompactWorkspace
        );
    }
}


// Wrap current updater without disturbing simulation or
// physical semantics installed by D10B/D10E.
const d11bPreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d11bPreviousUpdateDemoControlStrip(
            data
        );

        d11bSyncRobotCamera(
            data
        );
    };


function d11bSetupRobotCamera() {
    d11bCreateRobotCameraTile();


    document
        .getElementById(
            "systemTargetSelect"
        )
        ?.addEventListener(
            "change",
            () => {
                if (
                    latestDemoStatus
                ) {
                    d11bSyncRobotCamera(
                        latestDemoStatus
                    );
                }
            }
        );


    if (latestDemoStatus) {
        d11bSyncRobotCamera(
            latestDemoStatus
        );
    }
}


function d11bWaitForWorkspace(
    attempts=0
) {
    if (
        document.getElementById(
            "mediaWorkspace"
        )
    ) {
        d11bSetupRobotCamera();

        return;
    }


    if (
        attempts
        >= 80
    ) {
        console.warn(
            "Robot camera: workspace not found."
        );

        return;
    }


    window.setTimeout(
        () => {
            d11bWaitForWorkspace(
                attempts + 1
            );
        },
        50
    );
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            d11bWaitForWorkspace();
        },
        {
            once: true,
        }
    );
}

else {
    d11bWaitForWorkspace();
}



// ============================================================
// D11E_UNIFIED_PREVIEW_TEXT
// ============================================================

function d11eNormalizePreviewText() {
    const wantedTitles = new Set([
        "Raw preview idle",
        "Keypoint preview idle",
        "MuJoCo preview idle",
        "Robot camera idle",
    ]);


    const strongNodes = [
        ...document.querySelectorAll(
            "#view-live strong"
        ),
    ];


    for (
        const title
        of strongNodes
    ) {
        const text =
            title.textContent
                .trim();


        if (
            !wantedTitles.has(
                text
            )
        ) {
            continue;
        }


        title.classList.add(
            "unified-preview-title"
        );


        const parent =
            title.parentElement;


        if (!parent) {
            continue;
        }


        parent.classList.add(
            "unified-preview-placeholder"
        );


        /*
         * Normalize every descriptive span belonging to the
         * same idle placeholder.
         */
        for (
            const child
            of parent.children
        ) {
            if (
                child.tagName
                === "SPAN"
                &&
                !child.classList.contains(
                    "robot-camera-placeholder-icon"
                )
            ) {
                child.classList.add(
                    "unified-preview-subtitle"
                );
            }
        }
    }


    const robotStage =
        document.querySelector(
            ".robot-camera-stage"
        );


    if (robotStage) {
        robotStage.classList.add(
            "robot-camera-stage-clean"
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
            queueMicrotask(
                d11eNormalizePreviewText
            );
        },
        {
            once: true,
        }
    );
}

else {
    queueMicrotask(
        d11eNormalizePreviewText
    );
}



// ============================================================
// D12E_ROBOT_MODES_UI
// ============================================================

let d12eModeRequestPending =
    false;

let d12eModeStatusPending =
    false;


const D12E_MODE_ACTIONS = [
    {
        action:
            "developer",

        label:
            "Dev",

        group:
            "ownership",

        title:
            "Release the active Unitree motion mode for Development / SDK control.",

        confirm:
            (
                "ENTER DEVELOPMENT / SDK CONTROL?\n\n"
                +
                "This releases the active Unitree motion mode.\n\n"
                +
                "Bacalbasa / SONIC must be stopped first.\n"
                +
                "Continue?"
            ),
    },

    {
        action:
            "restore_ai",

        label:
            "Exit Developer",

        group:
            "ownership",

        title:
            "Restore the Unitree AI motion mode.",

        confirm:
            (
                "EXIT DEVELOPMENT MODE?\n\n"
                +
                "This restores the Unitree AI motion mode.\n\n"
                +
                "Continue?"
            ),
    },

    {
        action:
            "damp",

        label:
            "Damping",

        group:
            "safety",

        title:
            "Enter the G1 damping FSM.",

        confirm:
            (
                "ACTIVATE DAMPING?\n\n"
                +
                "The G1 will change control mode and may "
                +
                "lower or move depending on its current posture.\n\n"
                +
                "Make sure the robot has clear space.\n"
                +
                "Continue?"
            ),
    },

    {
        action:
            "zero_torque",

        label:
            "Zero Torque",

        group:
            "safety",

        danger:
            true,

        title:
            "Remove commanded motor torque.",

        confirm:
            (
                "WARNING — ZERO TORQUE\n\n"
                +
                "THIS REMOVES MOTOR TORQUE.\n\n"
                +
                "A STANDING G1 CAN FALL IMMEDIATELY.\n\n"
                +
                "Only continue if the robot is supported, "
                +
                "already safely positioned, or safe to collapse.\n\n"
                +
                "Activate Zero Torque?"
            ),
    },

    {
        action:
            "walk",

        label:
            "Walk",

        group:
            "safety",

        title:
            "Switch the G1 to Walk mode.",

        confirm:
            null,
    },

    {
        action:
            "run",

        label:
            "Run",

        group:
            "safety",

        title:
            "Switch the G1 to Run mode.",

        confirm:
            null,
    },

    {
        action:
            "climb",

        label:
            "Climb",

        group:
            "safety",

        title:
            "Switch the G1 to Climb mode.",

        confirm:
            null,
    },

    {
        action:
            "sit",

        label:
            "Sit",

        group:
            "posture",

        title:
            "Command the G1 Sit FSM.",

        confirm:
            (
                "COMMAND SIT?\n\n"
                +
                "The robot will intentionally change posture.\n\n"
                +
                "Make sure the area around the G1 is clear.\n"
                +
                "Continue?"
            ),
    },

    {
        action:
            "stand_from_squat",

        label:
            "Stand from Squat",

        group:
            "posture",

        title:
            "Use only when the G1 is in the appropriate squat posture.",

        confirm:
            (
                "STAND FROM SQUAT?\n\n"
                +
                "Use this only when the G1 is actually in the "
                +
                "appropriate squat posture.\n\n"
                +
                "Continue?"
            ),
    },

    {
        action:
            "recover_from_lie",

        label:
            "Recover from Lie",

        group:
            "posture",

        title:
            "Lie-to-stand recovery.",

        confirm:
            (
                "RECOVER FROM LIE?\n\n"
                +
                "Use this only when the G1 is lying FACE-UP "
                +
                "on a hard, flat, rough surface with clear space.\n\n"
                +
                "The robot will make a large recovery movement.\n\n"
                +
                "Continue?"
            ),
    },
];


function d12ePhysicalSelected() {
    return (
        document
            .getElementById(
                "systemTargetSelect"
            )
            ?.value
        === "robot"
    );
}


function d12ePhysicalSnapshot(
    data=latestDemoStatus
) {
    return (
        data?.physical
        || {
            state:
                "off",

            active:
                false,
        }
    );
}


function d12eModesLocked(
    data=latestDemoStatus
) {
    const physical =
        d12ePhysicalSnapshot(
            data
        );


    return Boolean(
        d12eModeRequestPending
        ||
        systemRequestPending
        ||
        !state.backendOnline
        ||
        physical.active
        ||
        (
            physical.state
            &&
            physical.state
            !== "off"
        )
    );
}


function d12eModeLabel(
    mode
) {
    if (
        mode === null
        ||
        mode === undefined
    ) {
        return "RELEASED / SDK";
    }


    if (
        typeof mode
        === "string"
    ) {
        const value =
            mode.trim();

        return (
            value
                ? value.toUpperCase()
                : "RELEASED / SDK"
        );
    }


    if (
        typeof mode
        === "object"
    ) {
        const candidates = [
            mode.name,
            mode.alias,
            mode.mode,
            mode.form,
        ];


        for (
            const value
            of candidates
        ) {
            if (
                typeof value
                === "string"
                &&
                value.trim()
            ) {
                return value
                    .trim()
                    .toUpperCase();
            }
        }


        const nonEmpty =
            Object.values(
                mode
            ).some(
                (
                    value
                ) =>
                    value !== null
                    &&
                    value !== undefined
                    &&
                    String(
                        value
                    ).trim()
            );


        if (!nonEmpty) {
            return "RELEASED / SDK";
        }


        try {
            const text =
                JSON.stringify(
                    mode
                );

            return (
                text.length > 30
                    ? text.slice(
                        0,
                        27
                    ) + "..."
                    : text
            );
        }

        catch (error) {
            return "UNKNOWN";
        }
    }


    return String(
        mode
    ).toUpperCase();
}


function d12eGetModesCard() {
    return document.getElementById(
        "robotModesCard"
    );
}


function d12eBuildModesCard() {
    const existing =
        d12eGetModesCard();

    if (existing) {
        return existing;
    }


    const sidebar =
        document.querySelector(
            ".sidebar"
        );


    if (!sidebar) {
        return null;
    }


    const card =
        document.createElement(
            "section"
        );

    card.id =
        "robotModesCard";

    card.className =
        (
            "design-side-card "
            +
            "robot-modes-card"
        );

    card.hidden =
        true;


    // --------------------------------------------------------
    // Header
    // --------------------------------------------------------

    const header =
        document.createElement(
            "div"
        );

    header.className =
        "robot-modes-header";


    const title =
        document.createElement(
            "strong"
        );

    title.textContent =
        "Robot Modes";


    const refresh =
        document.createElement(
            "button"
        );

    refresh.type =
        "button";

    refresh.id =
        "robotModeRefresh";

    refresh.className =
        "robot-mode-refresh";

    refresh.title =
        "Read the current Unitree motion mode.";

    refresh.textContent =
        "Refresh";


    refresh.addEventListener(
        "click",
        () => {
            d12eRefreshModeStatus();
        }
    );


    header.append(
        title,
        refresh
    );


    // --------------------------------------------------------
    // State
    // --------------------------------------------------------

    const status =
        document.createElement(
            "div"
        );

    status.className =
        "robot-mode-status";


    const statusLabel =
        document.createElement(
            "span"
        );

    statusLabel.textContent =
        "Current Mode";


    const statusValue =
        document.createElement(
            "strong"
        );

    statusValue.id =
        "robotModeCurrent";

    statusValue.textContent =
        "NOT CHECKED";


    status.append(
        statusLabel,
        statusValue
    );


    const ownership =
        document.createElement(
            "div"
        );

    ownership.id =
        "robotModeOwnership";

    ownership.className =
        "robot-mode-ownership";

    ownership.textContent =
        "Available while physical stack is OFF";


    // --------------------------------------------------------
    // Groups
    // --------------------------------------------------------

    const grid =
        document.createElement(
            "div"
        );

    grid.className =
        "robot-mode-grid";


    const groups = [
        [
            "ownership",
            "Ownership",
        ],

        [
            "safety",
            "Safety",
        ],

        [
            "posture",
            "Posture",
        ],
    ];


    for (
        const [
            group,
            label
        ]
        of groups
    ) {
        const groupLabel =
            document.createElement(
                "div"
            );

        groupLabel.className =
            "robot-mode-group-label";

        groupLabel.textContent =
            label;

        grid.appendChild(
            groupLabel
        );


        for (
            const spec
            of D12E_MODE_ACTIONS
        ) {
            if (
                spec.group
                !== group
            ) {
                continue;
            }


            const button =
                document.createElement(
                    "button"
                );

            button.type =
                "button";

            button.className =
                "robot-mode-button";

            if (
                spec.danger
            ) {
                button.classList.add(
                    "danger"
                );
            }


            button.dataset.action =
                spec.action;

            button.title =
                spec.title;

            button.textContent =
                spec.label;


            button.addEventListener(
                "click",
                () => {
                    d12eRunModeAction(
                        spec
                    );
                }
            );


            grid.appendChild(
                button
            );
        }
    }


    card.append(
        header,
        status,
        ownership,
        grid
    );


    const footer =
        sidebar.querySelector(
            ".sidebar-footer"
        );


    if (footer) {
        sidebar.insertBefore(
            card,
            footer
        );
    }

    else {
        sidebar.appendChild(
            card
        );
    }


    return card;
}


function d12eSyncModesCard(
    data=latestDemoStatus
) {
    const card =
        d12eBuildModesCard();


    if (!card) {
        return;
    }


    const selected =
        d12ePhysicalSelected();


    card.hidden =
        !selected;


    if (!selected) {
        return;
    }


    const physical =
        d12ePhysicalSnapshot(
            data
        );


    const locked =
        d12eModesLocked(
            data
        );


    const ownership =
        document.getElementById(
            "robotModeOwnership"
        );


    if (ownership) {
        if (
            physical.active
            ||
            (
                physical.state
                &&
                physical.state
                !== "off"
            )
        ) {
            ownership.textContent =
                (
                    "LOCKED · "
                    +
                    String(
                        physical.state
                        || "ACTIVE"
                    )
                    .replaceAll(
                        "_",
                        " "
                    )
                    .toUpperCase()
                    +
                    " · STOP SYSTEM FIRST"
                );

            ownership.classList.add(
                "locked"
            );
        }

        else {
            ownership.textContent =
                "Robot-mode controls available";

            ownership.classList.remove(
                "locked"
            );
        }
    }


    card
        .querySelectorAll(
            ".robot-mode-button"
        )
        .forEach(
            (
                button
            ) => {
                button.disabled =
                    locked;
            }
        );


    const refresh =
        document.getElementById(
            "robotModeRefresh"
        );


    if (refresh) {
        // Avoid creating an additional DDS client while
        // SONIC owns the physical robot.
        refresh.disabled =
            locked
            ||
            d12eModeStatusPending;
    }
}


async function d12eRefreshModeStatus() {
    if (
        !d12ePhysicalSelected()
        ||
        d12eModesLocked()
        ||
        d12eModeStatusPending
    ) {
        return;
    }


    d12eModeStatusPending =
        true;

    d12eSyncModesCard();


    const value =
        document.getElementById(
            "robotModeCurrent"
        );


    if (value) {
        value.textContent =
            "CHECKING...";
    }


    try {
        const result =
            await fetchJson(
                "/api/robot/modes/status"
            );


        if (value) {
            value.textContent =
                d12eModeLabel(
                    result.display_mode
                    ?? result.mode
                );
        }
    }

    catch (error) {
        if (value) {
            value.textContent =
                "UNAVAILABLE";
        }


        setActionMessage(
            (
                "Could not read robot mode: "
                +
                error.message
            ),
            true
        );
    }

    finally {
        d12eModeStatusPending =
            false;

        d12eSyncModesCard();
    }
}


async function d12eRunModeAction(
    spec
) {
    if (
        d12eModesLocked()
        ||
        d12eModeRequestPending
    ) {
        setActionMessage(
            (
                "Robot mode controls are locked. "
                +
                "Use Stop System first."
            ),
            true
        );

        return;
    }


    if (
        spec.confirm
        &&
        !window.confirm(
            spec.confirm
        )
    ) {
        return;
    }


    d12eModeRequestPending =
        true;

    d12eSyncModesCard();


    setActionMessage(
        (
            "Robot mode request: "
            +
            spec.label
            +
            "..."
        )
    );


    try {
        const result =
            await fetchJson(
                (
                    "/api/robot/modes/"
                    +
                    encodeURIComponent(
                        spec.action
                    )
                ),
                {
                    method:
                        "POST",
                }
            );


        setActionMessage(
            (
                spec.label
                +
                " completed"
                +
                (
                    result.requested_mode
                        ? (
                            " · "
                            +
                            result.requested_mode
                        )
                        : ""
                )
            )
        );


        // Action already interacted with the robot, so reading
        // its resulting mode afterward is appropriate.
        window.setTimeout(
            d12eRefreshModeStatus,
            350
        );
    }

    catch (error) {
        setActionMessage(
            (
                spec.label
                +
                " failed: "
                +
                error.message
            ),
            true
        );
    }

    finally {
        d12eModeRequestPending =
            false;

        await refreshStatus();

        d12eSyncModesCard();
    }
}


// ------------------------------------------------------------
// Keep card synchronized with every dashboard state update.
// ------------------------------------------------------------

const d12ePreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d12ePreviousUpdateDemoControlStrip(
            data
        );

        d12eSyncModesCard(
            data
        );
    };


function d12eSetupModesUI() {
    d12eBuildModesCard();


    document
        .getElementById(
            "systemTargetSelect"
        )
        ?.addEventListener(
            "change",
            () => {
                d12eSyncModesCard(
                    latestDemoStatus
                );
            }
        );


    d12eSyncModesCard(
        latestDemoStatus
    );
}


function d12eWaitForSidebar(
    attempt=0
) {
    if (
        document.querySelector(
            ".sidebar"
        )
        &&
        document.getElementById(
            "systemTargetSelect"
        )
    ) {
        d12eSetupModesUI();

        return;
    }


    if (
        attempt >= 80
    ) {
        console.warn(
            "D12E: sidebar not ready."
        );

        return;
    }


    window.setTimeout(
        () => {
            d12eWaitForSidebar(
                attempt + 1
            );
        },
        50
    );
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            d12eWaitForSidebar();
        },
        {
            once: true,
        }
    );
}

else {
    d12eWaitForSidebar();
}



// ============================================================
// D12G_ROBOT_MODES_CLEANUP
// ============================================================


/*
 * Present Unitree's short motion-switcher aliases as readable
 * dashboard state names.
 */
const d12gPreviousModeLabel =
    d12eModeLabel;


d12eModeLabel =
    function (
        mode
    ) {
        const label =
            d12gPreviousModeLabel(
                mode
            );


        const normalized =
            String(
                label
            )
            .trim()
            .toUpperCase();


        if (
            normalized === "AI"
        ) {
            return "AI MODE";
        }


        if (
            normalized === "NORMAL"
        ) {
            return "NORMAL MODE";
        }


        if (
            normalized === "ADVANCED"
        ) {
            return "ADVANCED MODE";
        }


        if (
            normalized === "RELEASED / SDK"
        ) {
            return "DEVELOPER / SDK";
        }


        return label;
    };


/*
 * Remove posture controls from the dashboard UI.
 *
 * Backend support is intentionally untouched; this is only a
 * presentation change.
 */
function d12gRemovePostureControls() {
    const card =
        document.getElementById(
            "robotModesCard"
        );


    if (!card) {
        return;
    }


    for (
        const action
        of [
            "sit",
            "stand_from_squat",
            "recover_from_lie",
        ]
    ) {
        card
            .querySelector(
                `[data-action="${action}"]`
            )
            ?.remove();
    }


    card
        .querySelectorAll(
            ".robot-mode-group-label"
        )
        .forEach(
            (
                label
            ) => {
                if (
                    label.textContent
                        .trim()
                        .toLowerCase()
                    === "posture"
                ) {
                    label.remove();
                }
            }
        );
}


/*
 * D12E may create the card after this code is parsed, so hook
 * the regular synchronizer as well.
 */
const d12gPreviousSyncModesCard =
    d12eSyncModesCard;


d12eSyncModesCard =
    function (
        data=latestDemoStatus
    ) {
        d12gPreviousSyncModesCard(
            data
        );

        d12gRemovePostureControls();
    };


function d12gApplyCleanup() {
    d12gRemovePostureControls();


    /*
     * Re-render an already displayed mode value through the
     * readable label mapper where possible.
     */
    const current =
        document.getElementById(
            "robotModeCurrent"
        );


    if (current) {
        const text =
            current.textContent
                .trim();


        if (
            text.toUpperCase()
            === "AI"
        ) {
            current.textContent =
                "AI MODE";
        }
    }
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            window.setTimeout(
                d12gApplyCleanup,
                100
            );
        },
        {
            once: true,
        }
    );
}

else {
    window.setTimeout(
        d12gApplyCleanup,
        100
    );
}



// ============================================================
// D12H_R1B_FLAT_MODES
// ============================================================

function d12hR1bFlattenModesCard() {
    const card =
        document.getElementById(
            "robotModesCard"
        );

    if (!card) {
        return;
    }


    // Remove:
    // "Robot-mode controls available"
    document
        .getElementById(
            "robotModeOwnership"
        )
        ?.remove();


    const labels = [
        ...card.querySelectorAll(
            ".robot-mode-group-label"
        ),
    ];


    /*
     * After D12G the Posture section is already gone.
     *
     * Keep only ONE label and call it MODES.
     */
    if (labels.length > 0) {
        labels[0].textContent =
            "Modes";

        for (
            const label
            of labels.slice(1)
        ) {
            label.remove();
        }
    }
}


/*
 * Hook the existing synchronizer so D12E cannot recreate
 * the old split presentation after a status refresh.
 */
const d12hR1bPreviousSyncModesCard =
    d12eSyncModesCard;


d12eSyncModesCard =
    function (
        data=latestDemoStatus
    ) {
        d12hR1bPreviousSyncModesCard(
            data
        );

        d12hR1bFlattenModesCard();
    };


function d12hR1bApply() {
    d12hR1bFlattenModesCard();
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            window.setTimeout(
                d12hR1bApply,
                100
            );
        },
        {
            once: true,
        }
    );
}

else {
    window.setTimeout(
        d12hR1bApply,
        100
    );
}



// ============================================================
// D12I_TWO_COLOR_PALETTE
// ============================================================


/*
 * Dashboard accent policy:
 *
 *   GREEN
 *   WAITING AMBER
 *
 * Do not introduce additional semantic accent colors.
 */


// ------------------------------------------------------------
// CLEAN CURRENT MODE NAMES
// ------------------------------------------------------------

const d12iPreviousModeLabel =
    d12eModeLabel;


d12eModeLabel =
    function (
        mode
    ) {
        const label =
            String(
                d12iPreviousModeLabel(
                    mode
                )
            )
            .trim()
            .toUpperCase();


        if (
            label === "AI MODE"
        ) {
            return "AI";
        }


        if (
            label === "DEVELOPER"
            ||
            label === "DEVELOPMENT"
            ||
            label === "DEVELOPER / SDK"
            ||
            label === "RELEASED / SDK"
            ||
            label === "DEVELOPMENT / SDK"
        ) {
            return "DEV";
        }


        if (
            label === "NORMAL MODE"
        ) {
            return "NORMAL";
        }


        if (
            label === "ADVANCED MODE"
        ) {
            return "ADVANCED";
        }


        return label;
    };


// ------------------------------------------------------------
// CAPTURE THE EXISTING WAITING COLOR
// ------------------------------------------------------------

function d12iFindWaitingColor() {
    const nodes = [
        ...document.querySelectorAll(
            ".sidebar *"
        ),
    ];


    const waiting =
        nodes.find(
            (
                node
            ) =>
                node.children.length === 0
                &&
                node.textContent
                    .trim()
                    .toUpperCase()
                === "WAITING"
        );


    if (waiting) {
        const color =
            window
                .getComputedStyle(
                    waiting
                )
                .color;


        if (color) {
            document
                .documentElement
                .style
                .setProperty(
                    "--bacalbasa-waiting-accent",
                    color
                );


            try {
                localStorage.setItem(
                    "bacalbasaWaitingAccent",
                    color
                );
            }

            catch (error) {
                // Non-critical.
            }


            return color;
        }
    }


    try {
        return localStorage.getItem(
            "bacalbasaWaitingAccent"
        );
    }

    catch (error) {
        return null;
    }
}


// ------------------------------------------------------------
// ZERO TORQUE = SAME VISUAL STYLE AS ALL OTHER MODE BUTTONS
// ------------------------------------------------------------

function d12iNormalizeZeroTorque() {
    const button =
        document.querySelector(
            '#robotModesCard [data-action="zero_torque"]'
        );


    if (!button) {
        return;
    }


    button.classList.remove(
        "danger"
    );
}


// ------------------------------------------------------------
// STOP SYSTEM = EXISTING WAITING AMBER
// ------------------------------------------------------------

function d12iStyleStopSystem() {
    const waitingColor =
        d12iFindWaitingColor();


    if (!waitingColor) {
        return;
    }


    const buttons = [
        ...document.querySelectorAll(
            "button"
        ),
    ];


    const stopButton =
        buttons.find(
            (
                button
            ) =>
                button.textContent
                    .trim()
                    .toLowerCase()
                === "stop system"
        );


    if (!stopButton) {
        return;
    }


    stopButton.classList.add(
        "bacalbasa-waiting-stop"
    );


    stopButton.style.setProperty(
        "--bacalbasa-stop-accent",
        waitingColor
    );
}


// ------------------------------------------------------------
// UPDATE CURRENTLY DISPLAYED VALUE TOO
// ------------------------------------------------------------

function d12iCleanDisplayedMode() {
    const current =
        document.getElementById(
            "robotModeCurrent"
        );


    if (!current) {
        return;
    }


    const text =
        current.textContent
            .trim()
            .toUpperCase();


    if (
        text === "AI MODE"
    ) {
        current.textContent =
            "AI";
    }


    if (
        text === "DEVELOPER / SDK"
        ||
        text === "RELEASED / SDK"
    ) {
        current.textContent =
            "DEVELOPER";
    }
}


function d12iApplyPalette() {
    d12iNormalizeZeroTorque();
    d12iStyleStopSystem();
    d12iCleanDisplayedMode();
}


// Keep it correct after every dashboard state update.
const d12iPreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d12iPreviousUpdateDemoControlStrip(
            data
        );


        window.requestAnimationFrame(
            d12iApplyPalette
        );
    };


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            window.setTimeout(
                d12iApplyPalette,
                100
            );
        },
        {
            once: true,
        }
    );
}

else {
    window.setTimeout(
        d12iApplyPalette,
        100
    );
}



// ============================================================
// D12J_DIRECT_TARGET_MODE_UI
// ============================================================

function d12jConfigureTargetModes() {

    /*
     * The mode array itself is mutable even though it was
     * declared with const.
     *
     * Remove the old "Exit Developer" action entirely.
     */
    const restoreIndex =
        D12E_MODE_ACTIONS.findIndex(
            (
                spec
            ) =>
                spec.action
                === "restore_ai"
        );


    if (
        restoreIndex >= 0
    ) {
        D12E_MODE_ACTIONS.splice(
            restoreIndex,
            1
        );
    }


    /*
     * Developer is now a target mode just like Damping and
     * Zero Torque.
     */
    const developer =
        D12E_MODE_ACTIONS.find(
            (
                spec
            ) =>
                spec.action
                === "developer"
        );


    if (developer) {
        developer.label =
            "Dev";

        developer.title =
            "Switch directly to Development / SDK control.";

        developer.confirm =
            (
                "SWITCH TO DEVELOPMENT MODE?\n\n"
                +
                "This releases the Unitree motion service "
                +
                "for Development / SDK ownership.\n\n"
                +
                "Continue?"
            );
    }
}


function d12jCleanExistingModeCard() {
    const card =
        document.getElementById(
            "robotModesCard"
        );


    if (!card) {
        return;
    }


    /*
     * Remove an Exit Developer button if D12E created the
     * card before this patch ran.
     */
    card
        .querySelector(
            '[data-action="restore_ai"]'
        )
        ?.remove();


    /*
     * Rename existing Developer button.
     */
    const developerButton =
        card.querySelector(
            '[data-action="developer"]'
        );


    if (developerButton) {
        developerButton.textContent =
            "Dev";

        developerButton.title =
            (
                "Switch directly to "
                +
                "Development / SDK control."
            );
    }
}


/*
 * Configure the data model immediately.
 */
d12jConfigureTargetModes();


/*
 * Also enforce the presentation after every normal Robot
 * Modes synchronization.
 */
const d12jPreviousSyncModesCard =
    d12eSyncModesCard;


d12eSyncModesCard =
    function (
        data=latestDemoStatus
    ) {
        d12jPreviousSyncModesCard(
            data
        );

        d12jCleanExistingModeCard();
    };


function d12jApplyTargetModeUI() {
    d12jCleanExistingModeCard();
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            window.setTimeout(
                d12jApplyTargetModeUI,
                100
            );
        },
        {
            once: true,
        }
    );
}

else {
    window.setTimeout(
        d12jApplyTargetModeUI,
        100
    );
}



// ============================================================
// D12K_SEGMENTED_SYSTEM_CONTROL
// ============================================================

function d12kFindSystemButtons() {
    const buttons = [
        ...document.querySelectorAll(
            "button"
        ),
    ];


    const deploy =
        buttons.find(
            button =>
                [
                    "deploy to robot",
                    "start",
                    "robot live",
                ].includes(
                    button.textContent
                        .trim()
                        .toLowerCase()
                )
        );


    const stop =
        buttons.find(
            button =>
                button.textContent
                    .trim()
                    .toLowerCase()
                === "stop system"
        );


    return {
        deploy,
        stop,
    };
}


function d12kApplySystemSwitch() {
    const {
        deploy,
        stop,
    } = d12kFindSystemButtons();


    if (
        !deploy
        ||
        !stop
    ) {
        return;
    }


    deploy.classList.add(
        "bacalbasa-system-segment",
        "bacalbasa-system-segment-primary"
    );


    stop.classList.add(
        "bacalbasa-system-segment",
        "bacalbasa-system-segment-stop"
    );


    const parent =
        deploy.parentElement;


    if (
        parent
        &&
        parent
        === stop.parentElement
    ) {
        parent.classList.add(
            "bacalbasa-system-switch"
        );
    }
}


const d12kPreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d12kPreviousUpdateDemoControlStrip(
            data
        );

        requestAnimationFrame(
            d12kApplySystemSwitch
        );
    };


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            setTimeout(
                d12kApplySystemSwitch,
                100
            );
        },
        {
            once: true,
        }
    );
}

else {
    setTimeout(
        d12kApplySystemSwitch,
        100
    );
}



// ============================================================
// D12M_CONNECTION_GATE
// ============================================================

let d12mDashboardConnected =
    true;


// ------------------------------------------------------------
// DEFAULT TARGET = PHYSICAL ROBOT
// ------------------------------------------------------------

function d12mDefaultPhysicalRobot() {
    const select =
        document.getElementById(
            "systemTargetSelect"
        );


    if (
        select
        &&
        select.value
        !== "robot"
    ) {
        select.value =
            "robot";

        select.dispatchEvent(
            new Event(
                "change",
                {
                    bubbles:
                        true,
                }
            )
        );
    }
}


// ------------------------------------------------------------
// DEFAULT SHOW BOTH = ON
// ------------------------------------------------------------

function d12mFindLeafText(
    wanted
) {
    const target =
        wanted
        .trim()
        .toLowerCase();


    return [
        ...document.querySelectorAll(
            ".sidebar *"
        ),
    ].find(
        (
            element
        ) =>
            element.children.length === 0
            &&
            element.textContent
                .trim()
                .toLowerCase()
            === target
    ) || null;
}


function d12mFindRowControl(
    label
) {
    let node =
        label;


    for (
        let depth = 0;
        node
        &&
        depth < 6;
        depth += 1
    ) {
        const controls = [
            ...node.querySelectorAll(
                (
                    'input[type="checkbox"],'
                    +
                    'button,'
                    +
                    '[role="switch"]'
                )
            ),
        ];


        if (
            controls.length
            === 1
        ) {
            return controls[
                0
            ];
        }


        node =
            node.parentElement;
    }


    return null;
}


function d12mControlIsOn(
    control
) {
    if (!control) {
        return false;
    }


    if (
        control.matches(
            'input[type="checkbox"]'
        )
    ) {
        return Boolean(
            control.checked
        );
    }


    if (
        control.getAttribute(
            "aria-checked"
        )
        === "true"
    ) {
        return true;
    }


    return (
        control.classList.contains(
            "active"
        )
        ||
        control.classList.contains(
            "on"
        )
        ||
        control.classList.contains(
            "enabled"
        )
    );
}


function d12mDefaultShowBoth() {
    const label =
        d12mFindLeafText(
            "Show Both"
        );


    const control =
        d12mFindRowControl(
            label
        );


    if (
        control
        &&
        !d12mControlIsOn(
            control
        )
    ) {
        control.click();
    }
}


// ------------------------------------------------------------
// WINDOW NAMES
// ------------------------------------------------------------

const D12M_WINDOW_NAMES = {
    "RAW / OPTICAL":
        "RAW CAMERA",

    "SPATIAL KEYPOINTS":
        "KEYPOINT CAMERA",

    "SIM / VIRTUAL":
        "SIMULATION",

    "G1 / ROBOT CAMERA":
        "ROBOT CAMERA",
};


function d12mRenameWindows() {
    const nodes = [
        ...document.querySelectorAll(
            (
                "#view-live strong,"
                +
                ".workspace-tile-header strong,"
                +
                ".camera-feed-label strong,"
                +
                ".panel-header strong"
            )
        ),
    ];


    for (
        const node
        of nodes
    ) {
        const current =
            node.textContent
                .trim()
                .toUpperCase();


        const replacement =
            D12M_WINDOW_NAMES[
                current
            ];


        if (replacement) {
            node.textContent =
                replacement;
        }
    }
}


// ------------------------------------------------------------
// CONNECTIVITY BAR
// ------------------------------------------------------------

function d12mFindConnectionBar() {
    const candidates = [
        ...document.querySelectorAll(
            ".sidebar *"
        ),
    ].filter(
        (
            element
        ) => {
            const text =
                element.textContent
                    .trim()
                    .toUpperCase();


            return (
                text.startsWith(
                    "CONNECTED"
                )
                ||
                text.startsWith(
                    "DISCONNECTED"
                )
                ||
                text.startsWith(
                    "CHECKING"
                )
            );
        }
    );


    if (
        candidates.length
        === 0
    ) {
        return null;
    }


    candidates.sort(
        (
            a,
            b
        ) =>
            a.children.length
            -
            b.children.length
    );


    return candidates[
        0
    ];
}


function d12mReplaceConnectionText(
    element,
    value
) {
    if (!element) {
        return;
    }


    const walker =
        document.createTreeWalker(
            element,
            NodeFilter.SHOW_TEXT
        );


    let replaced =
        false;


    while (
        walker.nextNode()
    ) {
        const node =
            walker.currentNode;


        const text =
            node.nodeValue
                || "";


        if (
            /(CONNECTED|DISCONNECTED|CHECKING)/i.test(
                text
            )
        ) {
            node.nodeValue =
                text.replace(
                    /(CONNECTED|DISCONNECTED|CHECKING).*$/i,
                    value
                );

            replaced =
                true;

            break;
        }
    }


    if (!replaced) {
        element.textContent =
            value;
    }
}


// ------------------------------------------------------------
// CONNECT / DISCONNECT BUTTON
// ------------------------------------------------------------

function d12mBuildConnectionButton() {
    let button =
        document.getElementById(
            "robotConnectionToggle"
        );


    if (button) {
        return button;
    }


    const bar =
        d12mFindConnectionBar();


    if (!bar) {
        return null;
    }


    button =
        document.createElement(
            "button"
        );

    button.id =
        "robotConnectionToggle";

    button.type =
        "button";

    button.className =
        "robot-connection-toggle";


    let anchor =
        bar.closest(
            "div"
        )
        || bar;


    anchor.insertAdjacentElement(
        "afterend",
        button
    );


    button.addEventListener(
        "click",
        async () => {

            const physical =
                latestDemoStatus
                    ?.physical
                || {};


            if (
                physical.active
                ||
                (
                    physical.state
                    &&
                    physical.state
                    !== "off"
                )
            ) {
                setActionMessage(
                    (
                        "Stop System before changing "
                        +
                        "the dashboard robot connection."
                    ),
                    true
                );

                return;
            }


            if (
                d12mDashboardConnected
            ) {
                d12mDashboardConnected =
                    false;

                d12mApplyConnectionGate();

                setActionMessage(
                    "Dashboard disconnected from physical robot."
                );

                return;
            }


            button.disabled =
                true;


            try {
                const result =
                    await fetchJson(
                        "/api/robot/connectivity"
                    );


                const reachable =
                    Boolean(
                        result.connected
                        ??
                        result.reachable
                        ??
                        result.ok
                    );


                if (!reachable) {
                    throw new Error(
                        "G1 is not reachable."
                    );
                }


                d12mDashboardConnected =
                    true;

                d12mApplyConnectionGate();

                setActionMessage(
                    "Physical robot connected."
                );
            }

            catch (error) {
                d12mDashboardConnected =
                    false;

                d12mApplyConnectionGate();

                setActionMessage(
                    (
                        "Could not connect to G1: "
                        +
                        error.message
                    ),
                    true
                );
            }

            finally {
                button.disabled =
                    false;
            }
        }
    );


    return button;
}


function d12mFindDeployButton() {
    return [
        ...document.querySelectorAll(
            "button"
        ),
    ].find(
        (
            button
        ) => {
            const text =
                button.textContent
                    .trim()
                    .toLowerCase();


            return (
                text === "deploy to robot"
                ||
                text === "start"
                ||
                text === "robot live"
            );
        }
    ) || null;
}


function d12mApplyConnectionGate() {
    const button =
        d12mBuildConnectionButton();


    const bar =
        d12mFindConnectionBar();


    if (bar) {
        d12mReplaceConnectionText(
            bar,
            (
                d12mDashboardConnected
                    ? "CONNECTED"
                    : "DISCONNECTED"
            )
        );

        bar.classList.toggle(
            "dashboard-disconnected",
            !d12mDashboardConnected
        );
    }


    if (button) {
        button.textContent =
            (
                d12mDashboardConnected
                    ? "Disconnect"
                    : "Connect"
            );


        button.dataset.state =
            (
                d12mDashboardConnected
                    ? "connected"
                    : "disconnected"
            );
    }


    /*
     * Disconnect is a dashboard ownership gate.
     * It does not disable the robot's network interface.
     */
    const deploy =
        d12mFindDeployButton();


    if (
        deploy
        &&
        !d12mDashboardConnected
    ) {
        deploy.disabled =
            true;
    }


    document
        .querySelectorAll(
            "#robotModesCard .robot-mode-button"
        )
        .forEach(
            (
                modeButton
            ) => {
                if (
                    !d12mDashboardConnected
                ) {
                    modeButton.disabled =
                        true;
                }
            }
        );
}


// ------------------------------------------------------------
// INITIAL CONNECTION STATE
// ------------------------------------------------------------

function d12mInitialConnectionState() {
    const bar =
        d12mFindConnectionBar();


    if (bar) {
        const text =
            bar.textContent
                .trim()
                .toUpperCase();


        d12mDashboardConnected =
            text.startsWith(
                "CONNECTED"
            );
    }
}


// ------------------------------------------------------------
// KEEP PRESENTATION CONSISTENT
// ------------------------------------------------------------

const d12mPreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d12mPreviousUpdateDemoControlStrip(
            data
        );


        requestAnimationFrame(
            () => {
                d12mRenameWindows();
                d12mApplyConnectionGate();
            }
        );
    };


// ------------------------------------------------------------
// PAGE DEFAULTS
// ------------------------------------------------------------

function d12mInitialize() {
    d12mDefaultPhysicalRobot();

    d12mInitialConnectionState();

    d12mBuildConnectionButton();

    d12mRenameWindows();

    d12mApplyConnectionGate();


    /*
     * Let the existing target/layout handlers finish before
     * enabling Show Both.
     */
    window.setTimeout(
        d12mDefaultShowBoth,
        250
    );
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        () => {
            window.setTimeout(
                d12mInitialize,
                100
            );
        },
        {
            once:
                true,
        }
    );
}

else {
    window.setTimeout(
        d12mInitialize,
        100
    );
}



// ============================================================
// D12N_FIXED_WORKSPACE_AND_STATUS
// ============================================================


// ------------------------------------------------------------
// ROBUST WINDOW TITLES
// ------------------------------------------------------------

const D12N_WINDOW_NAMES = {
    "RAW / OPTICAL":
        "RAW CAMERA",

    "RAW CAMERA":
        "RAW CAMERA",

    "SPATIAL KEYPOINTS":
        "KEYPOINT CAMERA",

    "KEYPOINT CAMERA":
        "KEYPOINT CAMERA",

    "SIM / VIRTUAL":
        "SIMULATION",

    "SIMULATION":
        "SIMULATION",

    "G1 / ROBOT CAMERA":
        "ROBOT CAMERA",

    "ROBOT CAMERA":
        "ROBOT CAMERA",
};


function d12nRenameWindows() {
    const elements = [
        ...document.querySelectorAll(
            "#view-live *"
        ),
    ];


    for (
        const element
        of elements
    ) {
        if (
            element.children.length
            !== 0
        ) {
            continue;
        }


        const current =
            element.textContent
                .trim()
                .toUpperCase();


        const replacement =
            D12N_WINDOW_NAMES[
                current
            ];


        /*
         * D14Q — IDEMPOTENT WINDOW RENAME
         *
         * d12nInstallObserver watches childList mutations in the
         * workspace. Reassigning textContent when the text is
         * already correct creates another childList mutation and
         * can repeatedly reschedule d12nApplyLayout().
         *
         * Only touch the DOM when the visible text truly changes.
         */
        if (
            replacement
            &&
            element.textContent
                .trim()
            !== replacement
        ) {
            element.textContent =
                replacement;
        }
    }
}


// ------------------------------------------------------------
// FIXED 2x2 MEDIA ORDER
//
//   RAW CAMERA       | SIMULATION
//   KEYPOINT CAMERA  | ROBOT CAMERA
// ------------------------------------------------------------

function d12nFixWorkspaceOrder() {
    /*
     * D14N — PRESERVE MANUAL WORKSPACE ORDER
     *
     * D12N was added by the visual overhaul to establish the
     * initial 2x2 presentation:
     *
     *   Raw        | Simulation
     *   Keypoints  | Robot Camera
     *
     * Once the user manually drags a tile, D7H owns workspace
     * order completely. Presentation refreshes must never move
     * those tiles back to the canonical visual arrangement.
     */
    if (
        typeof d7hWorkspaceManualLayout
            !== "undefined"
        &&
        d7hWorkspaceManualLayout
    ) {
        return;
    }


    const workspace =
        document.getElementById(
            "mediaWorkspace"
        );


    if (!workspace) {
        return;
    }


    let slots = [
        ...workspace.querySelectorAll(
            ":scope > .workspace-slot"
        ),
    ];


    /*
     * Normally four slots already exist. Create missing ones
     * defensively instead of allowing a tile to fall below
     * the workspace.
     */
    while (
        slots.length < 4
    ) {
        const slot =
            document.createElement(
                "div"
            );

        slot.className =
            "workspace-slot";

        workspace.appendChild(
            slot
        );

        slots = [
            ...workspace.querySelectorAll(
                ":scope > .workspace-slot"
            ),
        ];
    }


    const raw =
        document.getElementById(
            "rawCameraView"
        );


    const keypoints =
        document.getElementById(
            "keypointCameraView"
        );


    const simulation =
        document.querySelector(
            ".workspace-tile.mujoco-panel"
        )
        ||
        document.querySelector(
            ".mujoco-panel"
        );


    const robot =
        document.getElementById(
            "robotCameraView"
        );


    const desired = [
        raw,
        simulation,
        keypoints,
        robot,
    ];


    desired.forEach(
        (
            tile,
            index
        ) => {
            if (
                !tile
                ||
                !slots[
                    index
                ]
            ) {
                return;
            }


            if (
                tile.parentElement
                !== slots[
                    index
                ]
            ) {
                slots[
                    index
                ].appendChild(
                    tile
                );
            }
        }
    );


    /*
     * Recompute empty-slot state after moving the tiles.
     */
    slots.forEach(
        (
            slot
        ) => {
            const hasVisible =
                [
                    ...slot.children,
                ].some(
                    (
                        child
                    ) =>
                        !child.classList.contains(
                            "hidden"
                        )
                );


            slot.classList.toggle(
                "workspace-slot-empty",
                !hasVisible
            );


            slot.classList.toggle(
                "d10b-empty-slot",
                !hasVisible
            );
        }
    );
}


// ------------------------------------------------------------
// CONNECTION ROW
// ------------------------------------------------------------

function d12nConnectionLeaf() {
    if (
        typeof d12mFindConnectionBar
        === "function"
    ) {
        const found =
            d12mFindConnectionBar();

        if (found) {
            return found;
        }
    }


    return [
        ...document.querySelectorAll(
            ".sidebar *"
        ),
    ].find(
        (
            element
        ) => {
            const text =
                element.textContent
                    .trim()
                    .toUpperCase();


            return (
                text.startsWith(
                    "CONNECTED"
                )
                ||
                text.startsWith(
                    "DISCONNECTED"
                )
                ||
                text.startsWith(
                    "CHECKING"
                )
            );
        }
    ) || null;
}


function d12nConnectionRow() {
    const leaf =
        d12nConnectionLeaf();


    if (!leaf) {
        return null;
    }


    /*
     * D12M uses this same closest-div relationship when
     * placing the Connect / Disconnect button.
     */
    return (
        leaf.closest(
            "div"
        )
        ||
        leaf
    );
}


function d12nNormalizeConnectionRow() {
    const row =
        d12nConnectionRow();


    if (!row) {
        return;
    }


    const connected =
        (
            typeof d12mDashboardConnected
            !== "undefined"
        )
        ?
            Boolean(
                d12mDashboardConnected
            )
        :
            !row.textContent
                .trim()
                .toUpperCase()
                .startsWith(
                    "DISCONNECTED"
                );


    row.classList.add(
        "d12n-connection-row"
    );


    row.classList.toggle(
        "d12n-connected",
        connected
    );


    row.classList.toggle(
        "d12n-disconnected",
        !connected
    );


    row.dataset.connectionLabel =
        connected
            ? "CONNECTED"
            : "DISCONNECTED";
}


// ------------------------------------------------------------
// MOVE "NODE STATUS" BELOW PHYSICAL ROBOT SELECT
// ------------------------------------------------------------

function d12nRelocateStatusHeading() {
    const row =
        d12nConnectionRow();


    if (
        !row
        ||
        !row.parentElement
    ) {
        return;
    }


    let heading =
        document.querySelector(
            ".d12n-status-heading"
        );


    if (!heading) {
        heading = [
            ...document.querySelectorAll(
                ".sidebar *"
            ),
        ].find(
            (
                element
            ) =>
                element.children.length === 0
                &&
                element.textContent
                    .trim()
                    .toUpperCase()
                === "NODE STATUS"
        );
    }


    if (!heading) {
        return;
    }


    heading.textContent =
        "STATUS";


    heading.classList.add(
        "d12n-status-heading"
    );


    /*
     * Connection row is directly below the Physical Robot
     * selector, so inserting STATUS immediately before it
     * produces:
     *
     * Physical Robot
     * STATUS
     * CONNECTED / DISCONNECTED
     */
    if (
        heading.nextElementSibling
        !== row
    ) {
        row.parentElement.insertBefore(
            heading,
            row
        );
    }
}


// ------------------------------------------------------------
// ONE AUTHORITATIVE PRESENTATION PASS
// ------------------------------------------------------------

function d12nApplyLayout() {
    d12nRenameWindows();
    d12nFixWorkspaceOrder();
    d12nNormalizeConnectionRow();
    d12nRelocateStatusHeading();
}


// Existing status updates can rebuild / compact several of
// these elements. Reapply after each normal update.
const d12nPreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d12nPreviousUpdateDemoControlStrip(
            data
        );


        requestAnimationFrame(
            d12nApplyLayout
        );


        /*
         * Give old workspace-compaction handlers time to
         * finish, then establish the requested final order.
         */
        window.setTimeout(
            d12nApplyLayout,
            30
        );
    };


// Robot-camera tile is created dynamically, so also observe
// the workspace for that first insertion.
function d12nInstallObserver() {
    const workspace =
        document.getElementById(
            "mediaWorkspace"
        );


    if (!workspace) {
        return;
    }


    const observer =
        new MutationObserver(
            () => {
                requestAnimationFrame(
                    d12nApplyLayout
                );
            }
        );


    observer.observe(
        workspace,
        {
            childList:
                true,

            subtree:
                true,
        }
    );
}


function d12nInitialize() {
    d12nApplyLayout();
    d12nInstallObserver();


    window.setTimeout(
        d12nApplyLayout,
        100
    );


    window.setTimeout(
        d12nApplyLayout,
        300
    );
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        d12nInitialize,
        {
            once:
                true,
        }
    );
}

else {
    d12nInitialize();
}



// ============================================================
// D12O_CONNECTION_PRESENTATION
// ============================================================


function d12oCaptureWaitingAccent() {
    const waiting =
        [
            ...document.querySelectorAll(
                ".sidebar *"
            ),
        ].find(
            (
                element
            ) =>
                element.children.length === 0
                &&
                element.textContent
                    .trim()
                    .toUpperCase()
                === "WAITING"
        );


    if (!waiting) {
        return;
    }


    const color =
        window
            .getComputedStyle(
                waiting
            )
            .color;


    if (color) {
        document
            .documentElement
            .style
            .setProperty(
                "--bacalbasa-runtime-amber",
                color
            );
    }
}


function d12oPhysicalSelected() {
    return (
        document
            .getElementById(
                "systemTargetSelect"
            )
            ?.value
        === "robot"
    );
}


function d12oConnectionButtonVisibility() {
    const button =
        document.getElementById(
            "robotConnectionToggle"
        );


    if (!button) {
        return;
    }


    /*
     * Connection control belongs only to Physical Robot.
     */
    button.hidden =
        !d12oPhysicalSelected();
}


function d12oConnectionPresentation() {
    d12oCaptureWaitingAccent();


    const row =
        document.querySelector(
            ".d12n-connection-row"
        );


    if (row) {
        /*
         * Reassert the current state because older connection
         * styles may still be present underneath D12N.
         */
        const connected =
            (
                typeof d12mDashboardConnected
                !== "undefined"
            )
            &&
            Boolean(
                d12mDashboardConnected
            );


        row.classList.toggle(
            "d12n-connected",
            connected
        );


        row.classList.toggle(
            "d12n-disconnected",
            !connected
        );


        row.dataset.connectionLabel =
            connected
                ? "CONNECTED"
                : "DISCONNECTED";
    }


    d12oConnectionButtonVisibility();
}


const d12oPreviousUpdateDemoControlStrip =
    updateDemoControlStrip;


updateDemoControlStrip =
    function (
        data
    ) {
        d12oPreviousUpdateDemoControlStrip(
            data
        );


        requestAnimationFrame(
            d12oConnectionPresentation
        );
    };


function d12oInitialize() {
    d12oConnectionPresentation();


    document
        .getElementById(
            "systemTargetSelect"
        )
        ?.addEventListener(
            "change",
            () => {
                requestAnimationFrame(
                    d12oConnectionPresentation
                );
            }
        );


    window.setTimeout(
        d12oConnectionPresentation,
        150
    );
}


if (
    document.readyState
    === "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        d12oInitialize,
        {
            once: true,
        }
    );
}

else {
    d12oInitialize();
}
