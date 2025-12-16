# Installation Guide for GIMP AI Plugin

Short, correct install instructions for the current **ComfyUI-only**, **multi-file** version of the plugin.

---

## What you'll need

Before starting, make sure you have:

1. **GIMP 3.0.4 or newer** installed (download from [gimp.org](https://www.gimp.org))
2. **ComfyUI (local)** installed and running
3. **ComfyUI workflows** exported in **API format** for:
   - Inpaint (Focused)
   - ImageEdit (1-image, 2-image, 3-image)
   - Image Generation
   - Outpaint

> Important: this plugin requires **GIMP 3.0.4 or newer**.

---

## Quick overview

You will:

- Copy **all plugin Python files** into a `gimp-comfy-ai/` subfolder inside your GIMP plug-ins directory
- Configure ComfyUI + workflow paths in `Filters → AI → Settings`

---

## Step 1: Get the plugin files

Clone/download this repo, or download a release bundle.

You will copy these Python files into GIMP:

- `gimp-comfy-ai.py` (entrypoint; must be executable on Linux/macOS)
- `comfyui.py`
- `composite.py`
- `config.py`
- `dialogs.py`
- `generator.py`
- `image_processing.py`
- `inpaint.py`
- `outpaint.py`
- `settings.py`
- `utils.py`

Don’t copy the `tests/` folder into GIMP.

---

## Step 2: Find your GIMP plug-ins directory

The plugin directory location depends on your operating system.

### Windows

1. Press `Windows + R` to open the Run dialog
2. Type `%APPDATA%\GIMP` and press Enter
3. You should see one or more folders like `3.0`, `3.1`, `3.2`, etc. (depending on your GIMP version)
4. Choose your GIMP version folder (use the latest stable version - even numbers like 3.0, 3.2, 3.4)
5. Open that folder, then open the `plug-ins` folder

**Full path example**: `C:\Users\YourName\AppData\Roaming\GIMP\3.0\plug-ins\`

> **Tip**: If you can't find the `AppData` folder, make sure "Hidden items" is checked in Windows Explorer's View menu.
> **Multiple versions?** Stable releases use even minor version numbers (3.0, 3.2, 3.4). Development versions use odd numbers (3.1, 3.3).

### macOS

1. Open Finder
2. Press `Cmd + Shift + G` (Go to Folder)
3. Enter: `~/Library/Application Support/GIMP/`
4. Press Enter - you'll see folders like `3.0`, `3.1`, `3.2`, etc.
5. Choose your GIMP version folder (use the latest stable version - even numbers like 3.0, 3.2, 3.4)
6. Open that folder, then open the `plug-ins` folder

**Full path example**: `/Users/YourName/Library/Application Support/GIMP/3.0/plug-ins/`

> **Tip**: If the `Library` folder is hidden, press `Cmd + Shift + .` (period) in Finder to show hidden files.
> **Multiple versions?** Stable releases use even minor version numbers (3.0, 3.2, 3.4). Development versions use odd numbers (3.1, 3.3).

### Linux

The plugin directory is at: `~/.config/GIMP/<version>/plug-ins/` where `<version>` is your GIMP version (3.0, 3.1, 3.2, etc.)

First, check which GIMP versions you have:

```bash
ls ~/.config/GIMP/
```

Choose your GIMP version (use the latest stable version - even numbers like 3.0, 3.2, 3.4), then navigate to its plug-ins directory:

```bash
cd ~/.config/GIMP/3.0/plug-ins/
```

**If the directory doesn't exist**, create it (replace `3.0` with your version):

```bash
mkdir -p ~/.config/GIMP/3.0/plug-ins/
```

> **Multiple versions?** Stable releases use even minor version numbers (3.0, 3.2, 3.4). Development versions use odd numbers (3.1, 3.3).

### Flatpak GIMP (Linux)

If you installed GIMP via Flatpak, the directory is different:

```bash
~/.var/app/org.gimp.GIMP/config/GIMP/<version>/plug-ins/
```

Check which versions you have:

```bash
ls ~/.var/app/org.gimp.GIMP/config/GIMP/
```

---

## Step 3: Create the plugin folder

Inside your GIMP `plug-ins` directory, you need to create a **subdirectory** named `gimp-comfy-ai`.

### Visual Directory Structure

Your final structure should look like this:

```
plug-ins/
└── gimp-comfy-ai/          ← Create this folder
    ├── gimp-comfy-ai.py
    ├── comfyui.py
    ├── composite.py
    ├── config.py
    ├── dialogs.py
    ├── generator.py
    ├── image_processing.py
    ├── inpaint.py
    ├── outpaint.py
    ├── settings.py
    └── utils.py
```

### How to Create the Folder

**Windows:**

1. Right-click in the `plug-ins` folder
2. Select "New" → "Folder"
3. Name it exactly: `gimp-comfy-ai`

**macOS:**

1. Right-click (or Ctrl+click) in the `plug-ins` folder
2. Select "New Folder"
3. Name it exactly: `gimp-comfy-ai`

**Linux:**

```bash
# Replace 3.0 with your GIMP version
mkdir ~/.config/GIMP/3.0/plug-ins/gimp-comfy-ai
```

> **Important**: The folder name must be exactly `gimp-comfy-ai` (with a hyphen, not underscore).

---

## Step 4: Copy the plugin files

Copy **all files listed in Step 1** into the `gimp-comfy-ai` folder you just created.

### Where to Copy:

- **From**: Where you downloaded/extracted the files
- **To**: `plug-ins/gimp-comfy-ai/` (the folder you just created)

### What to Copy:

- `gimp-comfy-ai.py` plus the other `*.py` modules listed above

All files must be in the same `gimp-comfy-ai` folder.

---

## Step 5: Set file permissions (Linux/macOS only)

**Windows users can skip this step.**

On Linux and macOS, you need to make the main plugin file executable:

### macOS:

```bash
# Replace 3.0 with your GIMP version
chmod +x ~/Library/Application\ Support/GIMP/3.0/plug-ins/gimp-comfy-ai/gimp-comfy-ai.py
```

### Linux:

```bash
# Replace 3.0 with your GIMP version
chmod +x ~/.config/GIMP/3.0/plug-ins/gimp-comfy-ai/gimp-comfy-ai.py
```

### Flatpak (Linux):

```bash
# Replace 3.0 with your GIMP version
chmod +x ~/.var/app/org.gimp.GIMP/config/GIMP/3.0/plug-ins/gimp-comfy-ai/gimp-comfy-ai.py
```

---

## Step 6: Restart GIMP

If GIMP is currently running:

1. **Save your work**
2. **Quit GIMP completely** (don't just close windows - actually quit the application)
3. **Start GIMP again**

> **Important**: You must fully restart GIMP for it to detect the new plugin.

---

## Step 7: Configure ComfyUI

This plugin requires **ComfyUI** to be installed and running locally.

### Prerequisites

1. **ComfyUI** must be installed and running (see [ComfyUI documentation](https://github.com/comfyanonymous/ComfyUI))
2. **ComfyUI server** must be accessible at `http://127.0.0.1:8188` (or your custom URL)
3. **Workflow JSON files** exported in **API format** (not the full UI export)

### Where to keep workflows

This repo is expected to have a `workflows/` directory containing your workflow JSON files (see `workflows/README.md`). You can:

- Copy those workflow JSON files into your ComfyUI workflows folder, or
- Point GIMP’s Settings fields directly at this repo’s `workflows/*.json` paths

### Required Workflows

You need to create and export (in API format) the following workflows:

1. **Inpaint (Focused)** - For focused inpainting with selection masks
2. **ImageEdit (1-image)** - For full-image editing (used by "Full Image" inpaint mode)
3. **ImageEdit (2-image)** - For compositing 2 layers
4. **ImageEdit (3-image)** - For compositing 3 layers
5. **Image Generation** - For generating new images from prompts
6. **Outpaint** - For extending images beyond boundaries

### Configuration Steps

1. In GIMP, go to `Filters` → `AI` → `Settings`
2. Set **Server URL** (default `http://127.0.0.1:8188`)
3. Set **ComfyUI `input_dir`** and **`output_dir`** (absolute paths)
4. For each workflow tab, set:
   - **Workflow Path (JSON)** (API format)
   - **Node overrides** (Node ID + Field) as required by that workflow

The plug-in saves settings to your GIMP user directory as `gimp-comfy-ai/config.json`.

---

## Step 8: Test the plugin

Let's verify everything is working:

1. **Open any image** in GIMP (or create a new one)
2. **Look for the AI menu**: `Filters` → `AI`
3. You should see these options:
   - **Inpainting** - Fill areas with AI-generated content
   - **Image Generator** - Create new images from text
   - **Layer Composite** - Blend layers with AI (2-3 layers)
   - **Outpaint** - Extend images beyond boundaries
   - **Settings** - Configure ComfyUI

### Quick Test:

1. Go to `Filters` → `AI` → `Image Generator`
2. Enter a simple prompt like "blue sky with clouds"
3. Click OK
4. After a few seconds, you should see a new layer with AI-generated content!

---

## Troubleshooting

### I don't see "Filters → AI" in GIMP

Check these things:

1. **Did you restart GIMP completely?** (Quit and reopen)
2. **Are the files in the right place?**
   ```
   plug-ins/gimp-comfy-ai/gimp-comfy-ai.py
   plug-ins/gimp-comfy-ai/utils.py
   ```
3. **Is the folder named exactly `gimp-comfy-ai`?** (not `gimp_comfy_ai` or `gimp-comfy`)
4. **Do you have GIMP 3.0.4 or newer?** Check: `Help` → `About GIMP`
5. **Linux/macOS: Did you make the file executable?** (Step 5)
6. **Are you looking in the right version folder?** (Check the version folder matches your installed GIMP)

### "ComfyUI is not configured" Error

1. Make sure you configured ComfyUI settings (Step 7)
2. Verify server URL is correct (default: `http://127.0.0.1:8188`)
3. Verify input_dir and output_dir paths are correct (absolute paths)
4. Verify workflow JSON paths are correct and files exist
5. Make sure ComfyUI server is running

### "Workflow JSON does not look like ComfyUI API format" Error

1. Make sure you exported workflows in **API format** (not full UI export)
2. In ComfyUI, enable "Dev mode Options" in settings
3. Use "Save (API Format)" option when exporting workflows

### Plugin Causes GIMP to Crash

1. Check `Windows` → `Error Console` in GIMP for error messages
2. Try with a small test image first (under 1024px)
3. Make sure you're using GIMP 3.0.4 or newer

### Still Having Issues?

See the detailed [TROUBLESHOOTING.md](TROUBLESHOOTING.md) guide or report issues at:
`https://github.com/lukaso/gimp-ai/issues`

---

## You're done

Congratulations! You've successfully installed the GIMP AI Plugin.

### Next Steps:

- Read the [README.md](README.md) to learn about all features
- Try the **Inpainting** feature on a photo
- Generate some AI images with **Image Generator**

### Getting Help:

- **Issues**: [GitHub Issues](https://github.com/lukaso/gimp-ai/issues)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## Updating the plugin

To update to a newer version:

1. Download the new plugin files
2. Replace the old files in `plug-ins/gimp-comfy-ai/`
3. Restart GIMP

Your ComfyUI settings will be preserved.

---

## Uninstalling

To remove the plugin:

1. Delete the `gimp-comfy-ai` folder from your plug-ins directory
2. Restart GIMP

Your ComfyUI configuration will remain in your GIMP user directory (`gimp-comfy-ai/config.json`).

---

Need more help? Check out the [TROUBLESHOOTING.md](TROUBLESHOOTING.md) guide!
