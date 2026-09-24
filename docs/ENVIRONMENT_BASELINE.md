# Known-good PC environment baseline

This document records the environment in which the current Camera Pose Teleop
pipeline was validated. It is provenance, not a requirement that every future
machine use an identical stack.

## Pose / perception runtime

- Python: 3.10.20
- PyTorch: 2.3.0+cu121
- torchvision: 0.18.0+cu121
- CUDA reported by PyTorch: 12.1
- cuDNN: 8.9.2
- ONNX Runtime GPU: 1.23.2
- OpenCV: 4.11.0
- NumPy: 1.23.5
- SciPy: 1.15.3
- pyzmq: 27.1.0
- hydra-core: 1.3.0
- pytorch3d: 0.7.6
- smplx: 0.1.28

## ViTPose acceleration

- TensorRT Python/bindings: 8.6.1
- TensorRT libraries: 8.6.1
- torch2trt: 0.5.0
- torch2trt commit:
  `19a317659e15d1307009803e7a15f264672df19d`
- local `getitem.py` compatibility patch is stored under:
  `patches/torch2trt/required/`

## HMR2 acceleration

HMR2 runs through ONNX Runtime TensorRT Execution Provider.

Known-good environment also supplies TensorRT 10.9.0.34 shared libraries
through a separate library directory.

TensorRT engines and timing caches are GPU-specific generated artifacts and
are not stored in Git.

## SONIC build/runtime

The validated PC SONIC build environment uses a separate CUDA/TensorRT toolchain.

- CUDA toolkit configuration: 12.9
- TensorRT build configuration: 10.13

Do not collapse the ViTPose, HMR2 ORT and SONIC TensorRT environments into a
single generic TensorRT installation without validating the complete pipeline.
