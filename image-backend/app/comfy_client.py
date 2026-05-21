import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()

COMFY_URL = os.getenv("COMFY_URL", "http://127.0.0.1:8188")
COMFY_CHECKPOINT = os.getenv("COMFY_CHECKPOINT", "dreamshaper_8.safetensors")
COMFY_OUTPUT_DIR = Path(
    os.getenv("COMFY_OUTPUT_DIR", r"E:\ComfyUI_windows_portable\ComfyUI\output")
)

BASE_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = BASE_DIR / "api.json"
POSITIVE_PROMPT_NODE_ID = os.getenv("POSITIVE_PROMPT_NODE_ID", "2")
NEGATIVE_PROMPT_NODE_ID = os.getenv("NEGATIVE_PROMPT_NODE_ID", "3")
LATENT_NODE_ID = os.getenv("LATENT_NODE_ID", "4")
SAMPLER_NODE_ID = os.getenv("SAMPLER_NODE_ID", "5")
CHECKPOINT_NODE_ID = os.getenv("CHECKPOINT_NODE_ID", "13")


class ComfyUIError(Exception):
    pass


def load_workflow() -> dict[str, Any]:
    if not WORKFLOW_PATH.exists():
        raise ComfyUIError(f"Workflow file not found: {WORKFLOW_PATH}")

    with open(WORKFLOW_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def prepare_workflow(
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
) -> dict[str, Any]:
    workflow = load_workflow()

    if POSITIVE_PROMPT_NODE_ID not in workflow:
        raise ComfyUIError(f"Positive prompt node not found: {POSITIVE_PROMPT_NODE_ID}")

    workflow[POSITIVE_PROMPT_NODE_ID]["inputs"]["text"] = prompt

    if NEGATIVE_PROMPT_NODE_ID in workflow:
        workflow[NEGATIVE_PROMPT_NODE_ID]["inputs"]["text"] = negative_prompt

    if CHECKPOINT_NODE_ID in workflow:
        workflow[CHECKPOINT_NODE_ID]["inputs"]["ckpt_name"] = COMFY_CHECKPOINT

    if LATENT_NODE_ID in workflow:
        workflow[LATENT_NODE_ID]["inputs"]["width"] = width
        workflow[LATENT_NODE_ID]["inputs"]["height"] = height
        workflow[LATENT_NODE_ID]["inputs"]["batch_size"] = 1

    if SAMPLER_NODE_ID in workflow:
        workflow[SAMPLER_NODE_ID]["inputs"]["seed"] = random.randint(1, 999999999)
        workflow[SAMPLER_NODE_ID]["inputs"]["steps"] = steps
        workflow[SAMPLER_NODE_ID]["inputs"]["cfg"] = cfg

    return workflow


async def queue_prompt(workflow: dict[str, Any]) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{COMFY_URL}/prompt",
            json={"prompt": workflow},
        )

    if response.status_code != 200:
        raise ComfyUIError(f"ComfyUI queue error: {response.text}")

    data = response.json()

    if "prompt_id" not in data:
        raise ComfyUIError(f"No prompt_id in ComfyUI response: {data}")

    return data["prompt_id"]


async def wait_for_result(prompt_id: str, timeout_seconds: int = 180) -> dict[str, Any]:
    start_time = asyncio.get_event_loop().time()

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            response = await client.get(f"{COMFY_URL}/history/{prompt_id}")

            if response.status_code != 200:
                raise ComfyUIError(f"ComfyUI history error: {response.text}")

            history = response.json()

            if prompt_id in history:
                return history[prompt_id]

            if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                raise ComfyUIError("Generation timeout")

            await asyncio.sleep(1)


def find_first_image(history_item: dict[str, Any]) -> dict[str, str]:
    outputs = history_item.get("outputs", {})

    for node_output in outputs.values():
        images = node_output.get("images", [])
        if images:
            return images[0]

    raise ComfyUIError("No image found in ComfyUI output")


def latest_output_image(started_at: float) -> Path:
    if not COMFY_OUTPUT_DIR.exists():
        raise ComfyUIError(f"ComfyUI output folder not found: {COMFY_OUTPUT_DIR}")

    image_paths = [
        path
        for path in COMFY_OUTPUT_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        and path.stat().st_mtime >= started_at
    ]

    if not image_paths:
        raise ComfyUIError(f"No new image found in: {COMFY_OUTPUT_DIR}")

    return max(image_paths, key=lambda path: path.stat().st_mtime)


async def generate_image(
    prompt: str,
    negative_prompt: str,
    width: int = 512,
    height: int = 768,
    steps: int = 25,
    cfg: float = 7.0,
) -> str:
    filesystem_started_at = time.time()
    workflow = prepare_workflow(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
    )

    prompt_id = await queue_prompt(workflow)
    await wait_for_result(prompt_id)
    local_path = latest_output_image(filesystem_started_at)

    return local_path.relative_to(COMFY_OUTPUT_DIR).as_posix()
