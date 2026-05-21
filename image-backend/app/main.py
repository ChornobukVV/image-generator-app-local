from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.comfy_client import COMFY_OUTPUT_DIR, ComfyUIError, generate_image


app = FastAPI(title="Mobile Image Generator API")

last_received_prompt: str = ""


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount(
    "/outputs",
    StaticFiles(directory=str(COMFY_OUTPUT_DIR), check_dir=False),
    name="outputs",
)


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    negative_prompt: str = (
        "bad anatomy, extra limbs, deformed hands, distorted body, ugly face, "
        "blurry, low quality, messy background, watermark, text, logo"
    )
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg: float = 7.0


@app.get("/", response_class=HTMLResponse)
def root():
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Prompt Sender</title>
        <style>
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f4f6f8;
                color: #15191f;
            }}
            main {{
                max-width: 720px;
                margin: 0 auto;
                padding: 24px 16px;
            }}
            h1 {{
                font-size: 24px;
                margin: 0 0 16px;
            }}
            textarea {{
                width: 100%;
                min-height: 160px;
                box-sizing: border-box;
                padding: 12px;
                border: 1px solid #c9d1db;
                border-radius: 8px;
                font-size: 16px;
                resize: vertical;
            }}
            button {{
                width: 100%;
                margin-top: 12px;
                padding: 14px;
                border: 0;
                border-radius: 8px;
                background: #136f63;
                color: white;
                font-size: 16px;
                font-weight: 700;
            }}
            button:disabled {{
                opacity: 0.65;
            }}
            .box {{
                margin-top: 18px;
                padding: 14px;
                background: white;
                border: 1px solid #d9e0e7;
                border-radius: 8px;
                word-break: break-word;
            }}
            img {{
                width: 100%;
                max-width: 512px;
                display: block;
                margin-top: 12px;
                border-radius: 8px;
            }}
            .muted {{
                color: #5c6670;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <main>
            <h1>Prompt Sender</h1>
            <textarea id="prompt" placeholder="Paste prompt from phone...">{last_received_prompt}</textarea>
            <button id="send">Send to ComfyUI</button>

            <div class="box">
                <div class="muted">Last prompt:</div>
                <div id="lastPrompt">{last_received_prompt or "No prompt yet"}</div>
            </div>

            <div class="box">
                <div class="muted">Result:</div>
                <div id="result">Waiting</div>
            </div>
        </main>

        <script>
            const button = document.getElementById("send");
            const promptInput = document.getElementById("prompt");
            const lastPrompt = document.getElementById("lastPrompt");
            const result = document.getElementById("result");

            button.addEventListener("click", async () => {{
                const prompt = promptInput.value.trim();

                if (prompt.length < 3) {{
                    result.textContent = "Prompt must be at least 3 characters.";
                    return;
                }}

                button.disabled = true;
                button.textContent = "Generating...";
                result.textContent = "Prompt sent to ComfyUI. Waiting for result.";
                lastPrompt.textContent = prompt;

                try {{
                    const response = await fetch("/generate-image", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ prompt }})
                    }});

                    const data = await response.json();

                    if (!response.ok) {{
                        throw new Error(data.detail || "Generation error");
                    }}

                    result.innerHTML = `
                        <div>Done: ${{data.filename}}</div>
                        <img src="${{data.image_url}}" alt="Generated image">
                    `;
                }} catch (error) {{
                    result.textContent = error.message;
                }} finally {{
                    button.disabled = false;
                    button.textContent = "Send to ComfyUI";
                }}
            }});
        </script>
    </body>
    </html>
    """


@app.get("/api/status")
def status():
    return {
        "status": "ok",
        "message": "Image backend is running",
        "last_prompt": last_received_prompt,
        "comfy_output_dir": str(COMFY_OUTPUT_DIR),
    }


@app.get("/api/last-prompt")
def get_last_prompt():
    return {"prompt": last_received_prompt}


async def run_generation(data: GenerateImageRequest, request: Request):
    global last_received_prompt
    last_received_prompt = data.prompt

    try:
        filename = await generate_image(
            prompt=data.prompt,
            negative_prompt=data.negative_prompt,
            width=data.width,
            height=data.height,
            steps=data.steps,
            cfg=data.cfg,
        )

        base_url = str(request.base_url).rstrip("/")
        image_path = quote(filename, safe="/")

        return {
            "status": "success",
            "prompt": data.prompt,
            "image_url": f"{base_url}/outputs/{image_path}",
            "imageUrl": f"{base_url}/outputs/{image_path}",
            "filename": filename,
        }

    except ComfyUIError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {error}") from error


@app.post("/generate")
async def generate_endpoint(data: GenerateImageRequest, request: Request):
    return await run_generation(data, request)


@app.post("/generate-image")
async def generate_image_endpoint(data: GenerateImageRequest, request: Request):
    return await run_generation(data, request)
