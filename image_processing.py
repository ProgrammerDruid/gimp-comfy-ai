"""
Image processing mixin for GIMP AI Plugin.
"""

import os
import tempfile
import gi
from gi.repository import Gimp, Gio, GdkPixbuf


class ImageProcessingMixin:
    """Mixin class providing image processing and manipulation methods"""
    
    def _create_multipart_data(self, fields, files):
        """
        Create multipart/form-data request body.
        
        Args:
            fields: Dict of form fields (name -> value)
            files: Dict of file fields (name -> (filename, file_data))
            
        Returns:
            tuple: (body_bytes, content_type_header)
        """
        import uuid
        
        boundary = uuid.uuid4().hex
        body_parts = []
        
        # Add form fields
        for name, value in fields.items():
            body_parts.append(f"--{boundary}\r\n".encode())
            body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n'.encode())
            body_parts.append(b"\r\n")
            body_parts.append(str(value).encode("utf-8"))
            body_parts.append(b"\r\n")
        
        # Add file fields
        for name, (filename, file_data) in files.items():
            body_parts.append(f"--{boundary}\r\n".encode())
            body_parts.append(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
            )
            body_parts.append(b"Content-Type: application/octet-stream\r\n")
            body_parts.append(b"\r\n")
            body_parts.append(file_data)
            body_parts.append(b"\r\n")
        
        # Close boundary
        body_parts.append(f"--{boundary}--\r\n".encode())
        
        body_bytes = b"".join(body_parts)
        content_type = f"multipart/form-data; boundary={boundary}"
        
        return body_bytes, content_type

    def _download_and_composite_result(
        self,
        image,
        api_response,
        context_info,
        mode,
        color_info=None,
    ):
        """
        Download/parse AI output and composite it back into the original image.

        Supports:
        - OpenAI-style dict response: api_response['data'][0]['url'|'b64_json']
        - Direct PNG bytes (ComfyUI runner)
        """
        try:
            print("DEBUG: Downloading and compositing AI result")

            if not image:
                return False, "Error: No GIMP image provided"

            # Normalize to PNG bytes
            if isinstance(api_response, (bytes, bytearray)):
                image_data = bytes(api_response)
            else:
                if not api_response or "data" not in api_response:
                    return False, "Invalid API response - no data"
                if not api_response["data"] or len(api_response["data"]) == 0:
                    return False, "Invalid API response - empty data array"

                result_data = api_response["data"][0]
                if "url" in result_data:
                    image_url = result_data["url"]
                    with self._make_url_request(image_url, timeout=60) as response:
                        image_data = response.read()
                elif "b64_json" in result_data:
                    import base64
                    image_data = base64.b64decode(result_data["b64_json"])
                else:
                    return False, "Invalid API response - no image URL or base64 data"

            # Write to temporary file (existing compositing logic loads via Gimp.file_load)
            with tempfile.NamedTemporaryFile(
                suffix=".png", delete=False, mode="wb"
            ) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(image_data)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            # Save debug copy
            if self._is_debug_mode():
                debug_dir = tempfile.gettempdir()
                debug_filename = os.path.join(debug_dir, f"gpt-image-1_result_{len(image_data)}_bytes.png")
                try:
                    with open(debug_filename, "wb") as debug_file:
                        debug_file.write(image_data)
                    print(f"DEBUG: Saved GPT-Image-1 result to {debug_filename} for inspection")
                except Exception as e:
                    print(f"DEBUG: Could not save debug file: {e}")

            try:
                # Load the AI result into a temporary image
                Gimp.progress_set_text("Loading AI result...")
                Gimp.progress_update(0.95)  # 95% - Loading
                Gimp.displays_flush()

                file = Gio.File.new_for_path(temp_filename)
                ai_result_img = Gimp.file_load(
                    run_mode=Gimp.RunMode.NONINTERACTIVE, file=file
                )

                if not ai_result_img:
                    return False, "Failed to load AI result image"

                ai_layers = ai_result_img.get_layers()
                if not ai_layers or len(ai_layers) == 0:
                    ai_result_img.delete()
                    return False, "No layers found in AI result"

                ai_layer = ai_layers[0]
                print(
                    f"DEBUG: AI result dimensions: {ai_layer.get_width()}x{ai_layer.get_height()}"
                )

                # Get original image dimensions
                orig_width = image.get_width()
                orig_height = image.get_height()

                # Get context info for compositing
                sel_x1, sel_y1, sel_x2, sel_y2 = context_info["selection_bounds"]
                ctx_x1, ctx_y1, ctx_width, ctx_height = context_info["extract_region"]
                target_shape = context_info["target_shape"]

                print(f"DEBUG: Original image: {orig_width}x{orig_height}")
                print(
                    f"DEBUG: Selection bounds: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})"
                )
                print(
                    f"DEBUG: Extract region: ({ctx_x1},{ctx_y1}), size {ctx_width}x{ctx_height}"
                )

                # Scale AI result back to extract region size if needed
                if (
                    ai_layer.get_width() != ctx_width
                    or ai_layer.get_height() != ctx_height
                ):
                    scaled_img = ai_result_img.duplicate()

                    # For any mode with padding, remove padding first, then scale.
                    # IMPORTANT: only do this if the AI output still matches the plugin's
                    # target_shape. Some ComfyUI workflows rescale internally; in that case,
                    # cropping with the original pad offsets will produce the "top-left only"
                    # artifact.
                    if (
                        "padding_info" in context_info
                        and isinstance(target_shape, (tuple, list))
                        and len(target_shape) == 2
                        and ai_layer.get_width() == int(target_shape[0])
                        and ai_layer.get_height() == int(target_shape[1])
                    ):
                        padding_info = context_info["padding_info"]
                        pad_left, pad_top, pad_right, pad_bottom = padding_info[
                            "padding"
                        ]
                        scaled_w, scaled_h = padding_info["scaled_size"]

                        print(
                            f"DEBUG: Removing padding from AI result: crop to {scaled_w}x{scaled_h}"
                        )
                        print(
                            f"DEBUG: Padding to remove: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}"
                        )

                        # Crop to remove padding (get the actual content without black bars)
                        scaled_img.crop(scaled_w, scaled_h, pad_left, pad_top)
                        print(
                            f"DEBUG: Cropped AI result to {scaled_w}x{scaled_h} (removed padding)"
                        )

                        # Now scale the unpadded result to original size
                        scaled_img.scale(ctx_width, ctx_height)
                        print(
                            f"DEBUG: Scaled unpadded result to original size: {ctx_width}x{ctx_height}"
                        )
                    else:
                        # Normal scaling for non-padded results
                        scaled_img.scale(ctx_width, ctx_height)
                        print(
                            f"DEBUG: Scaled AI result to extract region size: {ctx_width}x{ctx_height}"
                        )

                    scaled_layers = scaled_img.get_layers()
                    if scaled_layers:
                        ai_layer = scaled_layers[0]

                # USE PURE COORDINATE FUNCTION FOR PLACEMENT
                from utils import calculate_placement_coordinates
                placement = calculate_placement_coordinates(context_info)
                paste_x = placement["paste_x"]
                paste_y = placement["paste_y"]
                result_width = placement["result_width"]
                result_height = placement["result_height"]

                # Create new layer in original image for the composited result
                result_layer = Gimp.Layer.new(
                    image,
                    "AI Inpaint Result",
                    orig_width,
                    orig_height,
                    Gimp.ImageType.RGBA_IMAGE,
                    100.0,
                    Gimp.LayerMode.NORMAL,
                )

                # Insert layer at top
                image.insert_layer(result_layer, None, 0)

                print(f"DEBUG: USING PURE PLACEMENT FUNCTION:")
                print(f"DEBUG: AI result is {result_width}x{result_height} square")
                print(f"DEBUG: Placing at calculated position: ({paste_x},{paste_y})")
                print(f"DEBUG: GIMP will automatically clip to image bounds")

                # Copy the AI result content using simplified Gegl nodes
                from gi.repository import Gegl

                print(
                    f"DEBUG: Placing {ctx_width}x{ctx_height} AI result at ({paste_x},{paste_y})"
                )

                # Clear selection before Gegl processing to prevent clipping, then restore it
                print(
                    "DEBUG: Saving and clearing selection before Gegl processing to prevent clipping"
                )
                selection_channel = Gimp.Selection.save(image)
                Gimp.Selection.none(image)

                # Get buffers
                buffer = result_layer.get_buffer()
                shadow_buffer = result_layer.get_shadow_buffer()
                ai_buffer = ai_layer.get_buffer()

                # Create simplified Gegl processing graph
                graph = Gegl.Node()

                # Source: AI result square
                ai_input = graph.create_child("gegl:buffer-source")
                ai_input.set_property("buffer", ai_buffer)

                # Translate to context square position
                translate = graph.create_child("gegl:translate")
                translate.set_property("x", float(paste_x))
                translate.set_property("y", float(paste_y))

                # Write to shadow buffer without clipping
                output = graph.create_child("gegl:write-buffer")
                output.set_property("buffer", shadow_buffer)

                # Link simple chain: source -> translate -> output
                ai_input.link(translate)
                translate.link(output)

                # Process the graph
                try:
                    output.process()

                    # Flush and merge shadow buffer - update entire layer
                    shadow_buffer.flush()
                    result_layer.merge_shadow(True)

                    # Update the entire layer
                    result_layer.update(0, 0, orig_width, orig_height)

                    print(f"DEBUG: Updated entire layer: {orig_width}x{orig_height}")

                    print(
                        f"DEBUG: Successfully composited AI result using simplified Gegl graph"
                    )
                except Exception as e:
                    print(f"DEBUG: Gegl processing failed: {e}")
                    raise

                # Restore the original selection
                print("DEBUG: Restoring original selection after Gegl processing")
                try:
                    pdb = Gimp.get_pdb()
                    select_proc = pdb.lookup_procedure("gimp-image-select-item")
                    select_config = select_proc.create_config()
                    select_config.set_property("image", image)
                    select_config.set_property("operation", Gimp.ChannelOps.REPLACE)
                    select_config.set_property("item", selection_channel)
                    select_proc.run(select_config)
                    print("DEBUG: Selection successfully restored")
                except Exception as e:
                    print(f"DEBUG: Could not restore selection: {e}")
                # Clean up the temporary selection channel
                image.remove_channel(selection_channel)

                # Apply color matching for contextual mode (before masking)
                if mode == "contextual" and color_info:
                    print("DEBUG: Applying color matching to result layer...")
                    # Note: _apply_color_matching is in InpaintMixin, accessible via self
                    self._apply_color_matching(result_layer, color_info)

                # Create a layer mask for contextual mode only
                if mode == "contextual" and context_info["has_selection"]:
                    print(
                        "DEBUG: Creating selection-based mask for contextual mode while preserving full AI result in layer"
                    )

                    # Use GIMP's built-in selection mask type to automatically create properly shaped mask
                    # This preserves the full AI content in the layer but masks visibility to selection area
                    mask = result_layer.create_mask(Gimp.AddMaskType.SELECTION)
                    result_layer.add_mask(mask)

                    # Apply smart feathering to the mask for better blending
                    # Note: _apply_smart_mask_feathering is in InpaintMixin, accessible via self
                    self._apply_smart_mask_feathering(mask, image)

                    print(
                        "DEBUG: Applied selection-based layer mask with smart feathering - enhanced blending at edges"
                    )
                    print(
                        "DEBUG: Core subject preserved at 100%, edges feathered for seamless integration"
                    )
                else:
                    print(
                        "DEBUG: No selection or full_image mode - layer shows full AI result without mask"
                    )

                # VALIDATION CHECKS
                print(f"DEBUG: === SIMPLIFIED ALIGNMENT VALIDATION ===")
                print(
                    f"DEBUG: Context square positioned at: ({paste_x},{paste_y}) with size {result_width}x{result_height}"
                )
                print(
                    f"DEBUG: Original selection was: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})"
                )
                print(
                    f"DEBUG: Since we work with true squares, alignment should be perfect"
                )
                print(
                    f"DEBUG: Selection coordinates within context square: ({sel_x1-paste_x},{sel_y1-paste_y}) to ({sel_x2-paste_x},{sel_y2-paste_y})"
                )

                # Clean up temporary image
                ai_result_img.delete()
                os.unlink(temp_filename)

                # Force display update
                Gimp.displays_flush()

                layer_count = len(image.get_layers())
                print(
                    f"DEBUG: Successfully composited AI result. Total layers: {layer_count}"
                )

                return (
                    True,
                    f"AI result composited as masked layer: '{result_layer.get_name()}' (total layers: {layer_count})",
                )

            except Exception as e:
                print(f"DEBUG: Compositing failed: {e}")
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                return False, f"Failed to composite result: {str(e)}"

        except Exception as e:
            print(f"DEBUG: Download and composite failed: {e}")
            return False, f"Failed to download result: {str(e)}"

    def _create_image_from_data(self, image_data):
        """
        Create a GIMP image from image data (bytes).
        
        Args:
            image_data: Raw image bytes (PNG format)
            
        Returns:
            Gimp.Image or None
        """
        try:
            # Write to temp file
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(image_data)
            
            try:
                # Load image
                file = Gio.File.new_for_path(temp_filename)
                image = Gimp.file_load(
                    run_mode=Gimp.RunMode.NONINTERACTIVE, file=file
                )
                return image
            finally:
                # Clean up temp file
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                    
        except Exception as e:
            print(f"ERROR: Failed to create image from data: {e}")
            return None

    def _add_layer_from_data(self, image, image_data):
        """
        Add a new layer to an image from image data.
        
        Args:
            image: GIMP image object
            image_data: Raw image bytes (PNG format)
            
        Returns:
            Gimp.Layer or None
        """
        try:
            # Create image from data
            temp_image = self._create_image_from_data(image_data)
            if not temp_image:
                return None
            
            # Get layer from temp image
            temp_layer = temp_image.get_layers()[0]
            
            # Create new layer in target image
            new_layer = Gimp.Layer.new_from_drawable(temp_layer, image)
            new_layer.set_name("AI Generated")
            
            # Add to image
            image.insert_layer(new_layer, None, -1)
            
            # Clean up temp image
            temp_image.delete()
            
            return new_layer
            
        except Exception as e:
            print(f"ERROR: Failed to add layer from data: {e}")
            return None

    def _download_and_add_layer(self, image, image_url):
        """
        Download image from URL and add as new layer.
        
        Args:
            image: GIMP image object
            image_url: URL to download image from
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Download image
            response = self._make_url_request(image_url)
            image_data = response.read()
            
            # Add layer
            layer = self._add_layer_from_data(image, image_data)
            if layer:
                return True, "Layer added successfully"
            else:
                return False, "Failed to create layer from downloaded image"
                
        except Exception as e:
            print(f"ERROR: Failed to download and add layer: {e}")
            return False, f"Failed to download image: {str(e)}"

