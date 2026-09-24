#!/usr/bin/env python3

import cv2
import zmq
import numpy as np

WINDOW = "G1 - ViTPose Keypoints"

ctx = zmq.Context.instance()

sock = ctx.socket(zmq.SUB)
sock.setsockopt(zmq.CONFLATE, 1)
sock.setsockopt_string(zmq.SUBSCRIBE, "")
sock.connect("tcp://127.0.0.1:5601")

# GUI_NORMAL removes OpenCV's toolbar/status bar.
# FREERATIO makes the video fill the window instead of adding
# white padding when the window is resized.
cv2.namedWindow(
    WINDOW,
    cv2.WINDOW_NORMAL
    | cv2.WINDOW_GUI_NORMAL
    | cv2.WINDOW_FREERATIO,
)

cv2.resizeWindow(WINDOW, 960, 540)

print("Connected to ViTPose preview")
print("Window is freely resizable.")
print("Press q to close.")

try:
    while True:
        data = sock.recv()

        frame = cv2.imdecode(
            np.frombuffer(data, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )

        if frame is None:
            continue

        cv2.imshow(WINDOW, frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    sock.close(0)
    cv2.destroyAllWindows()
