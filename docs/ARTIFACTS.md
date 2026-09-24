# Camera Pose Teleop artifact manifest

Large ML and TensorRT artifacts are not committed to Git.

## Runtime reference artifacts committed to this repository

| Artifact | SHA256 |
|---|---|
| fixed gravity calibration | `e269df619bc7e7a27741b93dacfe57e6fde45f1969023fd8882f58b5c611e9e9` |
| F_LEFT reference | `b06f8a293f34ee7b07f09227bdba8a18a1937a604038bc9edd88a9c27627c075` |

## Downloaded source artifacts

| Artifact | Source | Known-good SHA256 |
|---|---|---|
| ViTPose-H Multi-COCO checkpoint | GVHMR model distribution | `50e33f4077ef2a6bcfd7110c58742b24c5859b7798fb0eedd6d2215e0a8980bc` |
| GVHMR temporal checkpoint | GVHMR model distribution | `4fae7da2de388d5da3514cb27a2d003f364dacb280e9cf88972b710e589c6b91` |
| HMR2 ONNX | NVIDIA GEM-X | `4f78023fd2abbaf26805b440c7e3c7a28187c920af389ddffc12e91c57a99f19` |
| HMR2 ONNX data | NVIDIA GEM-X | `9ae90b247a5b5bbd1f4fba781a67eab03aa62ae6331d2ca55d7363b1106612b1` |
| SONIC low-latency encoder | NVIDIA GEAR-SONIC | `60be43157f57d812f38bdbb740a5de5d5d070e8840d9edc16f02a91a6d06255b` |
| SONIC low-latency decoder | NVIDIA GEAR-SONIC | `c4ac2e74045e7cbfb568f15e6bf47ea7ce023df7a94322af50be223e0a628bab` |
| SONIC observation config | NVIDIA GEAR-SONIC | `582b9a273a3d69fbf49ae59b39295a3be2b4a295e195ef4cf674b5e2571c90ab` |
| YOLOX-X HumanArt ONNX | OpenMMLab | `8e9ea96a176bd48501eaaa77216e49ee30794d2f8ba80c7b9862beca4ea972da` |

## Licensed body-model assets

These are not committed.

Users must obtain SMPL / SMPL-X model assets in accordance with their
respective licenses.

Known-good local hashes:

- `SMPL_NEUTRAL.pkl`
  `4924f235e63f7c5d5b690acedf736419c2edb846a2d69fc0956169615fa75688`

- `SMPLX_NEUTRAL.npz`
  `376021446ddc86e99acacd795182bbef903e61d33b76b9d8b359c2b0865bd992`

## Generated artifacts

TensorRT engines, torch2trt states, ORT TensorRT caches and timing caches
must be generated locally for the target GPU/software stack.

The known-good RTX 3050 build is provenance only and is not portable:

- ViTPose torch2trt state:
  `a465360dd209f212e86fd1a3620e71bc9def53ae18e0bef49a353e4b7fc2122a`

- ViTPose raw TensorRT engine:
  `dc25a19b2b8e9945679cfe32cadd125a7981756bce1893bcda5e2c93b3fcd210`
