"""
ComfyUI integration mixin for GIMP AI Plugin.
"""

import os
import json
import uuid
import urllib.request
import urllib.parse
import urllib.error
import base64
import gi
from gi.repository import Gimp, Gio, Gegl


class ComfyUIMixin:
    """Mixin class providing ComfyUI API integration methods"""
    
    def _ai_generate_threaded(self, prompt, size="auto", progress_label=None, image=None, seed=None):
        """
        ComfyUI image generation.
        Returns: (success, message, png_bytes)
        """
        # If caller asked for "auto" sizing, prefer the current canvas size
        # so generator outputs match the active GIMP image dimensions.
        if size == "auto" and image is not None:
            try:
                size = f"{int(image.get_width())}x{int(image.get_height())}"
            except Exception:
                pass
        return self._call_comfyui_generate_threaded(
            prompt=prompt, size=size, progress_label=progress_label, seed=seed
        )

    def _ai_edit_threaded(
        self, image_data, mask_data, prompt, size="1024x1024", progress_label=None, action=None, pad=None, seed=None
    ):
        """
        ComfyUI inpaint/edit/composite.
        Supports:
        - single image mode: image_data is base64 str, mask_data is png bytes
        - array mode: image_data is list[png bytes], mask_data optional png bytes
        Returns: (success, message, png_bytes)
        """
        return self._call_comfyui_edit_threaded(
            image_data=image_data,
            mask_data=mask_data,
            prompt=prompt,
            size=size,
            progress_label=progress_label,
            action=action,
            pad=pad,
            seed=seed,
        )

    def _call_comfyui_generate_threaded(self, prompt, size="auto", progress_label=None, seed=None):
        def operation():
            try:
                png_bytes = self._comfyui_run_workflow(
                    action="generator",
                    prompt_text=prompt,
                    size=size,
                    input_images=None,
                    input_mask=None,
                    progress_label=progress_label,
                    seed=seed,
                )
                return {
                    "success": True,
                    "message": "ComfyUI generation successful",
                    "data": png_bytes,
                }
            except Exception as e:
                return {"success": False, "message": str(e), "data": None}

        return self._run_threaded_operation(
            operation, "ComfyUI generation", progress_label, max_wait_time=600
        )

    def _call_comfyui_edit_threaded(
        self, image_data, mask_data, prompt, size="1024x1024", progress_label=None, action=None, pad=None, seed=None
    ):
        def operation():
            try:
                # image_data supports:
                # - base64 str (single image inpaint path)
                # - list[png bytes] (composite path)
                if isinstance(image_data, str):
                    img_bytes = base64.b64decode(image_data)
                    input_images = [img_bytes]
                elif isinstance(image_data, (bytes, bytearray)):
                    input_images = [bytes(image_data)]
                elif isinstance(image_data, list):
                    input_images = image_data
                else:
                    raise Exception(f"Unsupported image_data type for ComfyUI: {type(image_data)}")

                # If action not provided, infer from image count (backward compatibility)
                # Use a local variable to avoid Python's "local variable referenced before assignment" error
                workflow_action = action
                if workflow_action is None:
                    if len(input_images) == 1:
                        workflow_action = "inpaint_focused"
                    elif len(input_images) == 2:
                        workflow_action = "imageedit_2"
                    elif len(input_images) == 3:
                        workflow_action = "imageedit_3"
                    else:
                        raise Exception(f"Cannot infer action from {len(input_images)} images")

                png_bytes = self._comfyui_run_workflow(
                    action=workflow_action,
                    prompt_text=prompt,
                    size=size,
                    input_images=input_images,
                    input_mask=mask_data,
                    progress_label=progress_label,
                    pad=pad,
                    seed=seed,
                )
                return {
                    "success": True,
                    "message": "ComfyUI edit successful",
                    "data": png_bytes,
                }
            except Exception as e:
                return {"success": False, "message": str(e), "data": None}

        return self._run_threaded_operation(
            operation, "ComfyUI edit", progress_label, max_wait_time=900
        )

    def _comfyui_run_workflow(
        self,
        action,
        prompt_text,
        size,
        input_images,
        input_mask,
        progress_label=None,
        pad=None,
        seed=None,
    ):
        """
        Execute a ComfyUI workflow for the given action and return PNG bytes.

        Assumptions/contract:
        - workflow JSON on disk must be in ComfyUI API format (top-level dict mapping node_id -> node def)
        - node overrides are configured in config under workflows.<action>.overrides
        - SaveImage filename_prefix override is used to make outputs deterministic
        """
        if not self._provider_is_configured(action=action):
            raise Exception(f"ComfyUI is not configured for action '{action}' (check Settings).")

        comfy = self._get_comfyui_config()
        server_url = (comfy.get("server_url") or "").rstrip("/")
        input_dir = (comfy.get("input_dir") or "").strip()
        output_dir = (comfy.get("output_dir") or "").strip()

        wf_entry = (self.config.get("workflows", {}) or {}).get(action, {}) or {}
        wf_path = (wf_entry.get("path") or "").strip()
        overrides = (wf_entry.get("overrides") or {}) if isinstance(wf_entry, dict) else {}

        run_id = uuid.uuid4().hex

        if progress_label:
            self._update_progress(progress_label, "Preparing workflow inputs...")

        # Write input files (filesystem transport)
        subdir = os.path.join(input_dir, "gimp_ai")
        os.makedirs(subdir, exist_ok=True)

        # For imageedit workflows, split prompt into positive/negative
        # For other workflows, use single promptText
        if action in ("imageedit_1", "imageedit_2", "imageedit_3"):
            # Split prompt by newline or "|" separator if present, otherwise use same for both
            if "|" in prompt_text:
                parts = prompt_text.split("|", 1)
                runtime_values = {
                    "promptTextPositive": parts[0].strip(),
                    "promptTextNegative": parts[1].strip() if len(parts) > 1 else "",
                }
            else:
                # Use the prompt as positive, empty string as negative
                runtime_values = {
                    "promptTextPositive": prompt_text,
                    "promptTextNegative": "",
                }
        else:
            runtime_values = {"promptText": prompt_text}

        # Parse size if provided as WxH
        width = None
        height = None
        if isinstance(size, str) and "x" in size:
            try:
                parts = size.lower().split("x")
                width = int(parts[0])
                height = int(parts[1])
            except Exception:
                width = None
                height = None
        runtime_values["width"] = width
        runtime_values["height"] = height

        # Handle seed: randomize if not provided
        import random
        if seed is not None:
            runtime_values["seed"] = int(seed)
        else:
            # Randomize seed if not provided
            runtime_values["seed"] = random.randint(0, 2**31 - 1)

        # Deterministic filename prefix for SaveImage-style nodes
        runtime_values["saveFilenamePrefix"] = f"gimp_ai/{action}/{run_id}"

        if action == "generator":
            # no input files
            pass
        elif action == "upscaler_4x":
            if not input_images or len(input_images) != 1:
                raise Exception("Upscaler workflow requires exactly 1 input image")
            image_filename = f"gimp_ai/{run_id}_image.png"
            with open(os.path.join(input_dir, image_filename), "wb") as f:
                f.write(input_images[0])
            runtime_values["inputImageFilename"] = image_filename
        elif action == "inpaint_focused":
            if not input_images or len(input_images) != 1:
                raise Exception("Inpaint workflow requires exactly 1 input image")
            wants_separate_mask = isinstance(overrides, dict) and ("inputMaskFilename" in overrides)
            if wants_separate_mask and not input_mask:
                raise Exception("Inpaint workflow requires a mask image (inputMaskFilename override is configured)")

            image_filename = f"gimp_ai/{run_id}_image.png"
            with open(os.path.join(input_dir, image_filename), "wb") as f:
                f.write(input_images[0])

            runtime_values["inputImageFilename"] = image_filename
            if wants_separate_mask:
                mask_filename = f"gimp_ai/{run_id}_mask.png"
                with open(os.path.join(input_dir, mask_filename), "wb") as f:
                    f.write(input_mask)
                runtime_values["inputMaskFilename"] = mask_filename

        elif action == "imageedit_1":
            if not input_images or len(input_images) != 1:
                raise Exception("ImageEdit 1-image workflow requires exactly 1 input image")
            img1_filename = f"gimp_ai/{run_id}_img1.png"
            with open(os.path.join(input_dir, img1_filename), "wb") as f:
                f.write(input_images[0])
            runtime_values["img1Filename"] = img1_filename

        elif action == "imageedit_2":
            if not input_images or len(input_images) != 2:
                raise Exception("ImageEdit 2-image workflow requires exactly 2 input images")
            img1_filename = f"gimp_ai/{run_id}_img1.png"
            img2_filename = f"gimp_ai/{run_id}_img2.png"
            with open(os.path.join(input_dir, img1_filename), "wb") as f:
                f.write(input_images[0])
            with open(os.path.join(input_dir, img2_filename), "wb") as f:
                f.write(input_images[1])
            runtime_values["img1Filename"] = img1_filename
            runtime_values["img2Filename"] = img2_filename

        elif action == "imageedit_3":
            if not input_images or len(input_images) != 3:
                raise Exception("ImageEdit 3-image workflow requires exactly 3 input images")
            img1_filename = f"gimp_ai/{run_id}_img1.png"
            img2_filename = f"gimp_ai/{run_id}_img2.png"
            img3_filename = f"gimp_ai/{run_id}_img3.png"
            with open(os.path.join(input_dir, img1_filename), "wb") as f:
                f.write(input_images[0])
            with open(os.path.join(input_dir, img2_filename), "wb") as f:
                f.write(input_images[1])
            with open(os.path.join(input_dir, img3_filename), "wb") as f:
                f.write(input_images[2])
            runtime_values["img1Filename"] = img1_filename
            runtime_values["img2Filename"] = img2_filename
            runtime_values["img3Filename"] = img3_filename

        elif action == "outpaint":
            if not input_images or len(input_images) != 1:
                raise Exception("Outpaint workflow requires exactly 1 input image")
            img1_filename = f"gimp_ai/{run_id}_img1.png"
            with open(os.path.join(input_dir, img1_filename), "wb") as f:
                f.write(input_images[0])
            runtime_values["img1Filename"] = img1_filename
            # Map single pad value to left/top/right/bottom (all same value)
            if pad is not None:
                pad_val = int(pad)
                runtime_values["padLeft"] = pad_val
                runtime_values["padTop"] = pad_val
                runtime_values["padRight"] = pad_val
                runtime_values["padBottom"] = pad_val

        else:
            raise Exception(f"Unknown ComfyUI workflow action: {action}")

        # Load workflow JSON
        try:
            with open(wf_path, "r") as f:
                workflow = json.load(f)
        except Exception as e:
            raise Exception(f"Failed to load workflow JSON '{wf_path}': {e}")

        # Validate workflow format (API format expected)
        if not isinstance(workflow, dict) or "nodes" in workflow:
            raise Exception(
                "Workflow JSON does not look like ComfyUI API format. "
                "Please export your workflow in API format (node_id -> {class_type, inputs})."
            )

        # Apply overrides
        self._comfyui_apply_overrides(
            workflow=workflow,
            overrides=overrides,
            runtime_values=runtime_values,
            action=action,
        )

        if progress_label:
            self._update_progress(progress_label, "Queueing workflow in ComfyUI...")

        # Queue prompt
        prompt_id = self._comfyui_post_prompt(server_url, workflow, client_id=run_id)

        if progress_label:
            self._update_progress(progress_label, "Waiting for ComfyUI output...")

        history_item = self._comfyui_wait_for_history(server_url, prompt_id, timeout=900)
        preferred_output_node_id = None
        try:
            sfp = overrides.get("saveFilenamePrefix", {}) if isinstance(overrides, dict) else {}
            preferred_output_node_id = str(sfp.get("node_id") or "").strip() or None
        except Exception:
            preferred_output_node_id = None

        output_info = self._comfyui_pick_first_output_image(
            history_item, preferred_node_id=preferred_output_node_id
        )
        if not output_info:
            raise Exception("ComfyUI completed but no output images were found in history.")

        filename = output_info.get("filename")
        subfolder = output_info.get("subfolder", "")
        file_type = output_info.get("type", "output")

        # Prefer reading directly from output_dir when possible
        disk_path = os.path.join(output_dir, subfolder, filename) if subfolder else os.path.join(output_dir, filename)
        if os.path.exists(disk_path):
            with open(disk_path, "rb") as f:
                return f.read()

        # Fallback: /view endpoint
        return self._comfyui_view_image(server_url, filename, subfolder=subfolder, file_type=file_type)

    def _comfyui_apply_overrides(self, workflow, overrides, runtime_values, action):
        """
        Apply override mapping (node_id + input field) to a ComfyUI API workflow dict.
        The overrides dict is user-provided; we validate and error clearly if missing.
        """
        if overrides is None:
            overrides = {}
        if not isinstance(overrides, dict):
            raise Exception(f"Invalid overrides config for {action}: must be an object")

        def apply_one(key, value):
            mapping = overrides.get(key)
            if not mapping:
                return
            if not isinstance(mapping, dict):
                raise Exception(f"Override '{key}' must be an object with node_id/field")
            node_id = str(mapping.get("node_id", "")).strip()
            field = str(mapping.get("field", "")).strip()
            if not (node_id and field):
                raise Exception(f"Override '{key}' missing node_id/field")
            if node_id not in workflow:
                raise Exception(f"Workflow missing expected node_id '{node_id}' for override '{key}'")
            node = workflow[node_id]
            if not isinstance(node, dict):
                raise Exception(f"Workflow node '{node_id}' is not an object")
            node.setdefault("inputs", {})
            if not isinstance(node["inputs"], dict):
                raise Exception(f"Workflow node '{node_id}' inputs is not an object")
            node["inputs"][field] = value

        # Common
        # Support both single promptText and separate positive/negative prompts
        if "promptTextPositive" in runtime_values or "promptTextNegative" in runtime_values:
            apply_one("promptTextPositive", runtime_values.get("promptTextPositive"))
            apply_one("promptTextNegative", runtime_values.get("promptTextNegative"))
        else:
            apply_one("promptText", runtime_values.get("promptText"))
        apply_one("saveFilenamePrefix", runtime_values.get("saveFilenamePrefix"))
        if runtime_values.get("width") is not None:
            apply_one("width", runtime_values.get("width"))
        if runtime_values.get("height") is not None:
            apply_one("height", runtime_values.get("height"))
        if runtime_values.get("seed") is not None:
            apply_one("seed", runtime_values.get("seed"))

        # Inpaint focused
        if action == "inpaint_focused":
            apply_one("inputImageFilename", runtime_values.get("inputImageFilename"))
            apply_one("inputMaskFilename", runtime_values.get("inputMaskFilename"))

        # Upscaler
        if action == "upscaler_4x":
            apply_one("inputImageFilename", runtime_values.get("inputImageFilename"))

        # ImageEdit workflows
        if action in ("imageedit_1", "imageedit_2", "imageedit_3"):
            apply_one("img1Filename", runtime_values.get("img1Filename"))
            if action in ("imageedit_2", "imageedit_3"):
                apply_one("img2Filename", runtime_values.get("img2Filename"))
            if action == "imageedit_3":
                apply_one("img3Filename", runtime_values.get("img3Filename"))

        # Outpaint
        if action == "outpaint":
            apply_one("img1Filename", runtime_values.get("img1Filename"))
            if "padLeft" in runtime_values:
                apply_one("padLeft", runtime_values.get("padLeft"))
            if "padTop" in runtime_values:
                apply_one("padTop", runtime_values.get("padTop"))
            if "padRight" in runtime_values:
                apply_one("padRight", runtime_values.get("padRight"))
            if "padBottom" in runtime_values:
                apply_one("padBottom", runtime_values.get("padBottom"))

    def _comfyui_post_prompt(self, server_url, workflow, client_id=None):
        payload = {"prompt": workflow}
        if client_id:
            payload["client_id"] = client_id
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{server_url}/prompt",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._make_url_request(req, timeout=30) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
        prompt_id = resp_json.get("prompt_id")
        if not prompt_id:
            raise Exception(f"Unexpected ComfyUI /prompt response: {resp_json}")
        return prompt_id

    def _comfyui_wait_for_history(self, server_url, prompt_id, timeout=600):
        import time

        start = time.time()
        last_err = None
        while time.time() - start < timeout:
            try:
                with self._make_url_request(f"{server_url}/history/{prompt_id}", timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                # Some versions return {prompt_id: {...}}
                if isinstance(data, dict) and prompt_id in data:
                    item = data[prompt_id]
                else:
                    item = data
                if item and isinstance(item, dict) and item.get("outputs"):
                    return item
            except Exception as e:
                last_err = e
            time.sleep(0.5)
        raise Exception(f"Timed out waiting for ComfyUI history for prompt_id {prompt_id}: {last_err}")

    def _comfyui_pick_first_output_image(self, history_item, preferred_node_id=None):
        try:
            outputs = history_item.get("outputs", {})
            if not isinstance(outputs, dict):
                return None
            # outputs keyed by node id -> {images:[...]}
            if preferred_node_id and preferred_node_id in outputs:
                out = outputs.get(preferred_node_id)
                if isinstance(out, dict):
                    images = out.get("images")
                    if isinstance(images, list) and images:
                        first = images[0]
                        if isinstance(first, dict) and "filename" in first:
                            return first
            for _node_id, out in outputs.items():
                if not isinstance(out, dict):
                    continue
                images = out.get("images")
                if isinstance(images, list) and images:
                    first = images[0]
                    if isinstance(first, dict) and "filename" in first:
                        return first
        except Exception:
            return None
        return None

    def _comfyui_view_image(self, server_url, filename, subfolder="", file_type="output"):
        params = {
            "filename": filename,
            "subfolder": subfolder or "",
            "type": file_type or "output",
        }
        url = f"{server_url}/view?{urllib.parse.urlencode(params)}"
        with self._make_url_request(url, timeout=60) as resp:
            return resp.read()

    def _comfyui_embed_mask_into_image_alpha(self, image_png_bytes, mask_png_bytes, strength_percent=None):
        """
        Build a single PNG suitable for ComfyUI LoadImage's mask output:
        - selected area becomes transparent (alpha=0)
        - non-selected area remains opaque (alpha=1)

        This uses GEGL compositing: dst-out (punch out) with the mask image.
        The provided mask is expected to have opaque pixels where the selection is.
        """
        import tempfile

        # Write both PNGs to disk and load via GIMP
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False, mode="wb") as f_img:
            img_path = f_img.name
            f_img.write(image_png_bytes)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False, mode="wb") as f_mask:
            mask_path = f_mask.name
            f_mask.write(mask_png_bytes)

        try:
            img_g = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(img_path))
            mask_g = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(mask_path))
            if not img_g or not mask_g:
                raise Exception("Failed to load temp PNGs into GIMP")

            img_layer = img_g.get_layers()[0]
            mask_layer = mask_g.get_layers()[0]

            # Ensure sizes match
            if img_layer.get_width() != mask_layer.get_width() or img_layer.get_height() != mask_layer.get_height():
                mask_g.scale(img_layer.get_width(), img_layer.get_height())
                mask_layer = mask_g.get_layers()[0]

            # dst-out: keep destination where aux is transparent, punch out where aux is opaque
            img_buf = img_layer.get_buffer()
            mask_buf = mask_layer.get_buffer()
            shadow = img_layer.get_shadow_buffer()

            graph = Gegl.Node()
            src = graph.create_child("gegl:buffer-source")
            src.set_property("buffer", img_buf)
            aux = graph.create_child("gegl:buffer-source")
            aux.set_property("buffer", mask_buf)

            # Scale mask strength (reduces hard-edge artifacts around selection)
            # 100% => fully punch out selection; 0% => no punch out.
            try:
                if strength_percent is None:
                    strength_percent = int(self.config.get("comfyui_inpaint_mask_strength", 75) or 75)
                strength = max(0.0, min(1.0, float(strength_percent) / 100.0))
            except Exception:
                strength = 0.75

            opacity = graph.create_child("gegl:opacity")
            opacity.set_property("value", float(strength))
            aux.link(opacity)
            op = graph.create_child("gegl:dst-out")
            out = graph.create_child("gegl:write-buffer")
            out.set_property("buffer", shadow)

            src.link(op)
            opacity.connect_to("output", op, "aux")
            op.link(out)
            out.process()

            shadow.flush()
            img_layer.merge_shadow(True)
            img_layer.update(0, 0, img_layer.get_width(), img_layer.get_height())

            # Export the modified image to PNG bytes
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f_out:
                out_path = f_out.name
            try:
                pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
                pdb_config = pdb_proc.create_config()
                pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                pdb_config.set_property("image", img_g)
                pdb_config.set_property("file", Gio.File.new_for_path(out_path))
                pdb_config.set_property("options", None)
                result = pdb_proc.run(pdb_config)
                if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                    raise Exception("PNG export failed for embedded-mask image")
                with open(out_path, "rb") as f:
                    return f.read()
            finally:
                try:
                    os.unlink(out_path)
                except Exception:
                    pass
        finally:
            try:
                os.unlink(img_path)
            except Exception:
                pass
            try:
                os.unlink(mask_path)
            except Exception:
                pass
            try:
                if "img_g" in locals() and img_g:
                    img_g.delete()
            except Exception:
                pass
            try:
                if "mask_g" in locals() and mask_g:
                    mask_g.delete()
            except Exception:
                pass

