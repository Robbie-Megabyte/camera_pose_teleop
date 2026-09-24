#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import torch

from hmr4d.utils.smplx_utils import make_smplx


class GVHMRSMPL24Adapter:
    """
    Generic GVHMR-compatible SMPL-parameter -> canonical SMPL24 adapter.

    Accepted parameter contract:
        body_pose      (..., 63)
        betas          (..., 10)
        global_orient  (..., 3)
        transl         (..., 3)

    Conversion path is the same official GVHMR mesh path used by
    tools/demo/demo.py:

        GVHMR params
            -> make_smplx("supermotion")
            -> smplx2smpl_sparse.pt
            -> smpl_neutral_J_regressor.pt
            -> canonical 24 SMPL joints

    No 21->23 pose padding or custom joint fabrication is performed.
    """

    PARAM_DIMS = {
        "body_pose": 63,
        "betas": 10,
        "global_orient": 3,
        "transl": 3,
    }

    def __init__(
        self,
        gvhmr_root: str | Path | None = None,
        device: str | torch.device = "cuda",
    ):
        self.gvhmr_root = (
            Path(gvhmr_root)
            if gvhmr_root is not None
            else Path.home() / "GVHMR"
        )

        self.device = torch.device(device)

        self.smplx2smpl_path = (
            self.gvhmr_root
            / "hmr4d/utils/body_model/"
              "smplx2smpl_sparse.pt"
        )

        self.j_regressor_path = (
            self.gvhmr_root
            / "hmr4d/utils/body_model/"
              "smpl_neutral_J_regressor.pt"
        )

        for path in (
            self.smplx2smpl_path,
            self.j_regressor_path,
        ):
            if not path.exists():
                raise FileNotFoundError(path)

        self.supermotion = (
            make_smplx("supermotion")
            .to(self.device)
            .eval()
        )

        self.smplx2smpl = torch.load(
            self.smplx2smpl_path,
            map_location=self.device,
        )

        if self.smplx2smpl.layout == torch.sparse_coo:
            self.smplx2smpl = (
                self.smplx2smpl
                .coalesce()
            )

        self.j_regressor = torch.load(
            self.j_regressor_path,
            map_location=self.device,
        ).float()

        if tuple(self.smplx2smpl.shape) != (
            6890,
            10475,
        ):
            raise RuntimeError(
                "Unexpected SMPL-X->SMPL mapping shape: "
                f"{tuple(self.smplx2smpl.shape)}"
            )

        if tuple(self.j_regressor.shape) != (
            24,
            6890,
        ):
            raise RuntimeError(
                "Unexpected SMPL joint regressor shape: "
                f"{tuple(self.j_regressor.shape)}"
            )

    def _prepare_params(
        self,
        params: dict,
    ):
        tensors = {}
        leading_shape = None

        for key, expected_dim in self.PARAM_DIMS.items():
            if key not in params:
                raise KeyError(
                    f"Missing required SMPL parameter: {key}"
                )

            value = torch.as_tensor(
                params[key],
                dtype=torch.float32,
                device=self.device,
            )

            if value.shape[-1] != expected_dim:
                raise ValueError(
                    f"{key}: expected final dimension "
                    f"{expected_dim}, got {tuple(value.shape)}"
                )

            this_leading = tuple(
                value.shape[:-1]
            )

            if leading_shape is None:
                leading_shape = this_leading
            elif this_leading != leading_shape:
                raise ValueError(
                    "SMPL parameter leading dimensions differ: "
                    f"{key} has {this_leading}, "
                    f"expected {leading_shape}"
                )

            tensors[key] = value.reshape(
                -1,
                expected_dim,
            )

        return tensors, leading_shape

    @torch.inference_mode()
    def joints24(
        self,
        params: dict,
    ) -> torch.Tensor:
        tensors, leading_shape = (
            self._prepare_params(
                params
            )
        )

        body = self.supermotion(
            **tensors
        )

        verts_x = body.vertices

        verts_smpl = torch.stack(
            [
                torch.matmul(
                    self.smplx2smpl,
                    verts,
                )
                for verts in verts_x
            ],
            dim=0,
        )

        joints24 = torch.einsum(
            "jv,bvi->bji",
            self.j_regressor,
            verts_smpl,
        )

        if not torch.isfinite(
            joints24
        ).all():
            raise RuntimeError(
                "Non-finite SMPL24 joints"
            )

        return joints24.reshape(
            *leading_shape,
            24,
            3,
        )
