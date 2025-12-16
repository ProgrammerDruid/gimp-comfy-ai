# GIMP AI Plugin (ComfyUI / Local)

A Python plug-in for **GIMP 3.0.4+** that integrates **local AI workflows via ComfyUI** directly into GIMP.

Inspired by the openai plugin: https://github.com/lukaso/gimp-ai


## Features

- **AI Inpainting**: Focused edits using selections + masks
- **Full-image edit**: “Full Image” mode uses an ImageEdit workflow
- **AI Image Generation**: Generate a new layer from a prompt
- **AI Layer Composite**: Composite up to 3 layers (topmost visible layers)
- **Outpaint**: Extend the canvas and create a new GIMP image from the result
- **Upscaler (RealESRGAN 4x)**: Upscale the current image and open the result as a new GIMP image
- **Settings UI**: Tabbed settings dialog for ComfyUI + per-workflow mappings

## Requirements

- **GIMP 3.0.4+**
- **ComfyUI** running locally (default: `http://127.0.0.1:8188`)
- **ComfyUI workflows** exported in **API format**

## Installation

This plug-in is **multi-file**. Install by copying the Python files into GIMP’s plug-ins directory.

### Manual install (recommended)

1. Create a folder named `gimp-comfy-ai` inside your GIMP plug-ins directory
2. Copy these files into that folder:
   - `gimp-comfy-ai.py`
   - `comfyui.py`
   - `composite.py`
   - `config.py`
   - `dialogs.py`
   - `generator.py`
   - `image_processing.py`
   - `inpaint.py`
   - `outpaint.py`
   - `upscaler.py`
   - `settings.py`
   - `utils.py`
3. Linux/macOS: `chmod +x gimp-comfy-ai.py`
4. Restart GIMP

You should now see:

- `Filters → AI → Inpainting`
- `Filters → AI → Image Generator`
- `Filters → AI → Layer Composite`
- `Filters → AI → Outpaint`
- `Filters → AI → Upscaler (RealESRGAN 4x)`
- `Filters → AI → Settings`

### Folder structure

Your final structure should look like:

```
plug-ins/
└── gimp-comfy-ai/
    ├── gimp-comfy-ai.py
    ├── comfyui.py
    ├── composite.py
    ├── config.py
    ├── dialogs.py
    ├── generator.py
    ├── image_processing.py
    ├── inpaint.py
    ├── outpaint.py
    ├── upscaler.py
    ├── settings.py
    └── utils.py
```

For OS-specific paths and troubleshooting, see **[INSTALL.md](INSTALL.md)**.

## Workflows (ComfyUI)

This plug-in submits ComfyUI workflows via `POST /prompt` and uses filesystem-based transport:

- Input images/masks are written to your configured **ComfyUI `input_dir`**
- Output images are read back from your configured **ComfyUI `output_dir`**

We keep workflow files under the repo’s `workflows/` directory (see `workflows/README.md`). You can either:

- Copy those JSON files into your ComfyUI workflows folder, or
- Point the plug-in directly at this repo’s `workflows/*.json` paths in Settings

## Configuration (GIMP)

Open: `Filters → AI → Settings`

- **General tab**: ComfyUI `server_url`, `input_dir`, `output_dir`
- **Workflow tabs**: per-workflow JSON path + node overrides (node id + field name)

The plug-in saves configuration to your GIMP user directory (as `gimp-comfy-ai/config.json`).

## Help

See **[INSTALL.md](INSTALL.md)** and **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.

## Usage (quick)

### AI Inpainting

**Fill selected areas with AI-generated content using text prompts**

1. **Open image** in GIMP
2. **Make a selection** of area to inpaint (or no selection for full image)
3. **Go to** `Filters → AI → Inpainting`
4. **Choose processing mode**:
   - **Focused (High Detail)**: Best for small edits, maximum resolution, selection required
   - **Full Image (Consistent)**: Best for large changes, works with or without selection
5. **Enter prompt** (e.g., "blue sky with clouds", "remove the object")
6. **Result**: New layer with AI-generated content, automatically masked to selection area

**Selection Mask Behavior:**

- **Soft masks**: AI can redraw content _outside_ the selection to maintain visual coherence
- **With selection**: Final result is masked to show only within selected area, but AI considers surrounding context
- **No selection** (Full Image mode): Entire image is processed and replaced
- **Smart feathering**: Automatic edge blending for seamless integration

**Important**: The AI model may modify areas outside your selection to create coherent results. Only the final output is masked to your selection.

### AI Image Generation

1. **Open or create** any GIMP document
2. **Go to** `Filters → AI → Image Generator`
3. **Enter prompt** (e.g., "a red dragon on mountain")
4. **New layer created** with generated image

### AI Layer Composite

**Intelligently combines multiple visible layers using AI guidance**

1. **Set up your layers**:

   - **Bottom layer** = base/background (what gets modified)
   - **Upper layers** = elements to integrate (people, objects, etc.)
   - Make sure desired layers are **visible**

2. **Go to** `Filters → AI → Layer Composite`

3. **Enter integration prompt** (e.g., "blend the person naturally into the forest scene")

4. **Choose mode**:

   - **Include selection mask**: Uses selection on base layer to limit where changes occur
   - **❌ No mask**: AI can modify the entire base layer to integrate upper layers

5. **Result**: A new layer is created, taking the base layer and intelligently modifying it to incorporate all visible layers

## License

MIT License — see [LICENSE](LICENSE).
