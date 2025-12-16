# Troubleshooting Guide

Common issues and solutions for the GIMP AI Plugin.

> **First time installing?** Check the [INSTALL.md](INSTALL.md) guide for complete step-by-step instructions.

---

## Installation issues

### Plugin Not Appearing in GIMP Menus

**Symptoms**: No "AI" submenu under Filters menu

**Solutions**:

1. **Verify you installed the plug-in files** in the correct structure:

   ```
   plug-ins/
   └── gimp-comfy-ai/          ← Must be this exact folder name
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

2. **Check plugin directory location for your OS**:

   - **macOS**: `~/Library/Application Support/GIMP/3.1/plug-ins/gimp-comfy-ai/` (or 3.0)
   - **Linux**: `~/.config/GIMP/3.1/plug-ins/gimp-comfy-ai/` (or 3.0)
   - **Windows**: `%APPDATA%\GIMP\3.1\plug-ins\gimp-comfy-ai\` (or 3.0)

   > **Tip**: See [INSTALL.md](INSTALL.md) for detailed instructions on finding these directories.

3. **Check file permissions** (Linux/macOS):

   ```bash
  chmod +x ~/path/to/gimp-comfy-ai/gimp-comfy-ai.py
   ```

4. **Restart GIMP completely** (quit and reopen, don't just close windows)

5. **Check GIMP version**: Plugin requires GIMP 3.0.4+
   - In GIMP: `Help` → `About GIMP`

6. **Check GIMP Error Console** for any error messages:
   - In GIMP: `Windows` → `Dockable Dialogs` → `Error Console`

### Wrong GIMP Version Directory

**Symptoms**: Plugin installed but not loading

**Solution**: Check your GIMP version:

- Open GIMP → Help → About GIMP
- Use matching directory (3.0 vs 3.1)
- Install in correct version-specific folder

### Missing plugin module file (import error)

**Symptoms**: Plugin appears but crashes immediately, or Error Console shows `ModuleNotFoundError: No module named ...`

**Solution**: This plug-in is multi-file. Make sure **all** of these files are present in the same folder as `gimp-comfy-ai.py`:

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

> **Tip**: If you installed from a repo checkout, copying “all `*.py` files” into the folder is usually the simplest way to avoid missing one.

---

## Configuration issues

### "ComfyUI is not configured" error

**Symptoms**: Error dialog when trying to use any AI feature

**Solutions**:

1. Go to `Filters → AI → Settings`
2. In the **General** tab, set:
   - `server_url` (default `http://127.0.0.1:8188`)
   - `input_dir` (your ComfyUI `input` folder; absolute path)
   - `output_dir` (your ComfyUI `output` folder; absolute path)
3. In each **workflow tab**, set:
   - Workflow JSON path (API format)
   - Node overrides (node id + field)

### Settings Not Persisting

**Symptoms**: Settings reset every restart / settings don't save

**Solutions**:

1. **Check GIMP user directory permissions** (GIMP needs to write a config file)
2. **Config file location**:
   - **macOS**: `~/Library/Application Support/GIMP/3.1/gimp-comfy-ai/config.json`
   - **Linux**: `~/.config/GIMP/3.1/gimp-comfy-ai/config.json`
   - **Windows**: `%APPDATA%\GIMP\3.1\gimp-comfy-ai\config.json`

---

## Platform-specific issues

### macOS Issues

**"Python not found" error**:

- GIMP 3.x includes Python - shouldn't happen
- If it does, reinstall GIMP from official source

**Permission denied errors**:

```bash
xattr -d com.apple.quarantine ~/Library/Application\ Support/GIMP/3.1/plug-ins/gimp-comfy-ai/gimp-comfy-ai.py
```

### Linux Issues

**Plugin directory doesn't exist**:

```bash
mkdir -p ~/.config/GIMP/3.1/plug-ins/gimp-comfy-ai/
```

**Python import errors**:

- Check if GIMP was compiled with Python support
- Some package managers have GIMP without Python

**Flatpak GIMP**:

- Plugin directory: `~/.var/app/org.gimp.GIMP/config/GIMP/3.1/plug-ins/gimp-comfy-ai/`
- May have restricted network access (ensure it can reach `127.0.0.1:8188` if ComfyUI is running on the host)

### Windows Issues

**Path not found**:

- Use Windows Explorer to navigate to `%APPDATA%\GIMP\3.1\plug-ins\gimp-comfy-ai\`
- Create directory if it doesn't exist

**Antivirus blocking**:

- Some antivirus software blocks .py files
- Add plugin directory to exceptions

---

## ComfyUI connection issues

### "Connection timeout" Errors

**Symptoms**: Operations fail with timeout messages

**Solutions**:

1. Ensure ComfyUI is running and reachable (default `http://127.0.0.1:8188`)
2. Verify the Settings `server_url` matches where ComfyUI is listening
3. Verify filesystem paths:
   - GIMP must be able to write to `input_dir`
   - GIMP must be able to read from `output_dir`
4. Try a smaller image first (e.g. under 1024px) to validate the pipeline

### Slow Performance

**Symptoms**: Operations take very long to complete

**Solutions**:

1. **Image size**: Try images under 1024px first
2. **ComfyUI runtime**: Model + sampler choices in your workflow dominate performance
3. **Hardware**: GPU acceleration and VRAM availability matter significantly

---

## Runtime errors

### "Selection not found" Error

**Symptoms**: Inpainting fails even with selection

**Solutions**:

1. **Make selection before** running inpainting
2. **Check selection visibility**: View → Show Selection
3. **Refresh selection**: Select → None, then reselect

### Plugin Crashes GIMP

**Symptoms**: GIMP closes unexpectedly

**Solutions**:

1. **Check GIMP Error Console**: Windows → Error Console
2. **Update GIMP**: Use latest 3.1.x if possible
3. **Reduce image size**: Try smaller images
4. **Report bug**: Include error console output

### "Coordinate transformation failed"

**Symptoms**: Error in coordinate calculations

**Solutions**:

1. **Check image dimensions**: Very unusual sizes may fail
2. **Selection bounds**: Ensure selection is within image
3. **Try simple rectangular selection** first

---

## Performance optimization

### Reduce Processing Time

1. **Resize large images** before processing
2. **Use smaller selections** for inpainting
3. **Simple prompts** process faster than complex ones

---

## Getting help

### Before Reporting Issues

1. **Check this guide** for common solutions
2. **Try with a simple test image** (small, basic selection)
3. **Check GIMP Error Console** for detailed errors
4. **Confirm ComfyUI is running** and the configured `input_dir`/`output_dir` are correct

### Reporting Bugs (Beta Testing)

Include this information:

- **OS and version** (e.g., "Windows 11", "Ubuntu 22.04", "macOS Ventura")
- **GIMP version** (exact version from Help → About)
- **Plugin version** (see `VERSION` at the top of `gimp-comfy-ai.py`)
- **Error messages** from GIMP Error Console
- **Steps to reproduce** the issue
- **Image details** (size, format, what you were trying to do)

### Beta Feedback Template

```
**Platform**: [Windows/Linux/macOS + version]
**GIMP Version**: [e.g., 3.1.2]
**Issue Type**: [Installation/Configuration/Runtime/Performance]
**Description**: [What happened vs what you expected]
**Error Messages**: [Any error dialog text or console output]
**Steps**: [Exact steps to reproduce]
**Image Details**: [Size, format, selection details if relevant]
```

---

## Logs and debugging

### Enable Debug Output

Currently, debug output goes to GIMP's Error Console:

- **View logs**: Windows → Dockable Dialogs → Error Console
- **Clear logs**: Right-click in console → Clear
- **Save logs**: Copy text from console for bug reports

### Temporary Workarounds

- **Restart GIMP** often resolves temporary issues
- **Try smaller images** if processing fails
- **Use simple selections** (rectangles) for testing
- **Test with basic prompts** like "blue sky" or "green grass"

---

_This troubleshooting guide will be updated based on feedback. Report new issues on GitHub!_
