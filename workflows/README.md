# Workflows

This directory is intended to hold the **ComfyUI workflow JSON** files used by the GIMP plug-in.

## Requirements

- Workflows must be exported from ComfyUI in **API format** (not the full UI export).
- The plug-in submits workflows via ComfyUI’s HTTP API (`POST /prompt`) and uses filesystem-based transport:
  - Writes input images/masks into your configured **ComfyUI `input_dir`**
  - Reads generated outputs from your configured **ComfyUI `output_dir`**

## Expected workflows

The plug-in expects you to configure these workflow paths in `Filters → AI → Settings`:

- **Focused inpaint**: `inpaint_focused`
- **Image edit (1 image)**: `imageedit_1`
- **Image edit (2 images)**: `imageedit_2`
- **Image edit (3 images)**: `imageedit_3`
- **Generator**: `generator`
- **Outpaint**: `outpaint`
- **Upscaler (RealESRGAN 4x)**: `upscaler_4x`

You can either:

- Copy the workflow JSON files from this directory into your ComfyUI workflows folder, or
- Point the plug-in directly at this repo’s `workflows/*.json` paths.

> This repo does not ship model weights or ComfyUI custom nodes; your ComfyUI environment is expected to already have the required nodes/models installed for your workflows.


