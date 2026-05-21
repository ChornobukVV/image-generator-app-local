# Project Flow

This backend connects a phone/app or browser page with ComfyUI.

The phone sends a text prompt to this FastAPI server. The server inserts that text into the positive prompt node inside `api.json`, sends the workflow to ComfyUI at `http://127.0.0.1:8188`, waits until generation is finished, finds the newest image in the ComfyUI output folder, and returns a URL for the phone to load that image.

## Files

### `app/main.py`

Main FastAPI application.

What it does:

- starts the HTTP API server;
- serves the browser page at `GET /`;
- accepts generation requests from the phone;
- remembers the last received prompt in `last_received_prompt`;
- exposes generated images through `/outputs/...`;
- returns both `image_url` and `imageUrl` so different clients can read the result.

Important routes:

- `GET /` - opens a simple web page where you can paste a prompt and send it to ComfyUI.
- `GET /api/status` - checks if the backend is running.
- `GET /api/last-prompt` - returns the last prompt received by the backend.
- `POST /generate` - accepts prompt from the phone/app.
- `POST /generate-image` - same as `/generate`, kept for browser/frontend compatibility.

Request body for generation:

```json
{
  "prompt": "your prompt text"
}
```

Full optional request body:

```json
{
  "prompt": "your prompt text",
  "negative_prompt": "bad anatomy, blurry, low quality",
  "width": 512,
  "height": 512,
  "steps": 20,
  "cfg": 7
}
```

Successful response:

```json
{
  "status": "success",
  "prompt": "your prompt text",
  "image_url": "http://192.168.0.112:8000/outputs/ComfyUI_00018_.png",
  "imageUrl": "http://192.168.0.112:8000/outputs/ComfyUI_00018_.png",
  "filename": "ComfyUI_00018_.png"
}
```

### `app/comfy_client.py`

ComfyUI API client.

What it does:

- reads settings from `.env`;
- loads the ComfyUI workflow from `api.json`;
- inserts the phone prompt into the positive prompt node;
- optionally updates negative prompt, image size, steps, CFG, seed, and checkpoint;
- sends the workflow to ComfyUI by calling `POST /prompt`;
- waits for the job by polling `GET /history/{prompt_id}`;
- finds the newest generated image in the ComfyUI output folder.

Important values:

- `WORKFLOW_PATH = api.json`
- `POSITIVE_PROMPT_NODE_ID = "2"`
- `NEGATIVE_PROMPT_NODE_ID = "3"`
- `LATENT_NODE_ID = "4"`
- `SAMPLER_NODE_ID = "5"`
- `CHECKPOINT_NODE_ID = "13"`

The positive prompt is inserted here:

```python
workflow["2"]["inputs"]["text"] = prompt
```

### `api.json`

The ComfyUI API workflow.

This is the workflow that gets sent to ComfyUI.

Important nodes:

- node `2` - `CLIP Text Encode (Prompt) positiv`; receives the prompt from the phone.
- node `3` - negative `CLIP Text Encode`; receives `negative_prompt`.
- node `4` - image size and batch size.
- node `5` - sampler settings: seed, steps, cfg.
- node `7` - `SaveImage`; saves the final generated image.
- node `10` - LoRA loader.
- node `13` - checkpoint loader.

### `.env`

Runtime settings.

Current values:

```env
COMFY_URL=http://127.0.0.1:8188
COMFY_CHECKPOINT=dreamshaper_8.safetensors
COMFY_OUTPUT_DIR=E:\ComfyUI_windows_portable\ComfyUI\output
```

Meaning:

- `COMFY_URL` - where ComfyUI is running.
- `COMFY_CHECKPOINT` - checkpoint name inserted into node `13`.
- `COMFY_OUTPUT_DIR` - folder where ComfyUI saves generated images.

### `requirements.txt`

Python dependencies for the backend.

Current dependencies:

- `fastapi`
- `uvicorn[standard]`
- `httpx`
- `python-dotenv`

### `workflows/text_to_image.json`

Old workflow file.

It is currently not used by the backend because `app/comfy_client.py` now loads `api.json`.

### `app/__init__.py`

Marks the `app` folder as a Python package so imports like `from app.comfy_client import ...` work.

### `outputs/`

Old local output folder.

It is currently not used for new images. The backend now serves images directly from:

```text
E:\ComfyUI_windows_portable\ComfyUI\output
```

## Data Flow

1. Phone opens the backend:

```text
http://192.168.0.112:8000
```

2. Phone sends a prompt:

```http
POST /generate
Content-Type: application/json
```

```json
{
  "prompt": "example prompt"
}
```

3. FastAPI receives the request in `app/main.py`.

4. `app/main.py` calls:

```python
generate_image(...)
```

5. `app/comfy_client.py` loads `api.json`.

6. The prompt is inserted into node `2`:

```json
"2": {
  "class_type": "CLIPTextEncode",
  "_meta": {
    "title": "CLIP Text Encode (Prompt) positiv"
  }
}
```

7. Backend sends the workflow to ComfyUI:

```http
POST http://127.0.0.1:8188/prompt
```

8. ComfyUI returns `prompt_id`.

9. Backend waits until ComfyUI finishes by checking:

```http
GET http://127.0.0.1:8188/history/{prompt_id}
```

10. ComfyUI saves the image into:

```text
E:\ComfyUI_windows_portable\ComfyUI\output
```

11. Backend finds the newest image created after the request started.

12. Backend returns image URL to the phone:

```json
{
  "imageUrl": "http://192.168.0.112:8000/outputs/ComfyUI_00018_.png"
}
```

13. Phone loads that URL and displays the image.

## How To Run

Start ComfyUI first:

```powershell
cd E:\ComfyUI_windows_portable
.\run_nvidia_gpu.bat
```

Make sure ComfyUI opens here:

```text
http://127.0.0.1:8188
```

Start the backend in a second console:

```powershell
cd C:\Users\ukrvo\Documents\GitHub\image-generator-app-local\image-backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open from phone:

```text
http://192.168.0.112:8000
```

The phone and the computer must be on the same Wi-Fi/local network.

## Test With PowerShell

You can test generation from the computer:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/generate -Method Post -ContentType "application/json" -Body '{"prompt":"test prompt"}'
```

You can test backend status:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
```

## Common Problems

### `404 Not Found` for `/generate`

The client is calling a route that does not exist. This backend supports both:

```text
/generate
/generate-image
```

### `imageUrl is null`

The phone expects a field named `imageUrl`. The backend returns both `imageUrl` and `image_url`.

### Phone cannot open the backend

Check that the backend was started with:

```powershell
--host 0.0.0.0
```

Also check Windows Firewall and make sure the phone is on the same network.

### ComfyUI error

Check that ComfyUI is running:

```text
http://127.0.0.1:8188
```

Also check that the checkpoint and LoRA names used in `api.json` exist inside your ComfyUI models folders.
