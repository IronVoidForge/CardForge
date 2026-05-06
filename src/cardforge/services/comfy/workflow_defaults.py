from __future__ import annotations

from typing import Any

DEFAULT_CARD_ART_WORKFLOW_KEY = "stub.card_art.t2i.v1"

DEFAULT_CARD_ART_API_WORKFLOW: dict[str, Any] = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 1000, "steps": 28, "cfg": 6.5, "sampler_name": "euler", "scheduler": "normal", "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 768, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "card art prompt", "clip": ["4", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "text, watermark, logo, low quality", "clip": ["4", 1]}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "cardforge/card_art", "images": ["8", 0]}},
}

DEFAULT_PATCH_POINTS: dict[str, dict[str, Any]] = {
    "positive_prompt": {"node_id": "6", "path": ["inputs", "text"]},
    "negative_prompt": {"node_id": "7", "path": ["inputs", "text"]},
    "seed": {"node_id": "3", "path": ["inputs", "seed"]},
    "width": {"node_id": "5", "path": ["inputs", "width"]},
    "height": {"node_id": "5", "path": ["inputs", "height"]},
    "batch_size": {"node_id": "5", "path": ["inputs", "batch_size"]},
    "save_prefix": {"node_id": "9", "path": ["inputs", "filename_prefix"]},
}

DEFAULT_COMFY_WORKFLOWS: dict[str, dict[str, Any]] = {
    DEFAULT_CARD_ART_WORKFLOW_KEY: {
        "workflow_key": DEFAULT_CARD_ART_WORKFLOW_KEY,
        "name": "Stub Card Art T2I v1",
        "workflow_filename": f"{DEFAULT_CARD_ART_WORKFLOW_KEY}.json",
        "supported_job_type": "art_prepare_comfy",
        "patch_points": DEFAULT_PATCH_POINTS,
        "default_settings": {"width": 1024, "height": 768, "batch_size": 1, "steps": 28, "cfg": 6.5},
        "workflow_payload": DEFAULT_CARD_ART_API_WORKFLOW,
    }
}
