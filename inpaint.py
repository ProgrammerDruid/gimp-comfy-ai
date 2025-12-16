"""
Inpainting mixin for GIMP AI Plugin.
"""

import os
import tempfile
import base64
import gi
from gi.repository import Gimp, Gio, Gegl, GLib

# Import coordinate utilities
from utils import (
    extract_context_with_selection,
    validate_context_info,
    get_optimal_openai_shape,
    calculate_padding_for_shape,
    calculate_placement_coordinates,
)


class InpaintMixin:
    """Mixin class providing inpainting functionality"""
    
    def _calculate_context_extraction(self, image):
        """Calculate smart context extraction area around selection using optimal shapes"""
        try:
            print("DEBUG: Calculating smart context extraction with optimal shapes")

            # Get image dimensions
            img_width = image.get_width()
            img_height = image.get_height()
            print(f"DEBUG: Original image size: {img_width}x{img_height}")

            # Check for selection
            selection_bounds = Gimp.Selection.bounds(image)
            print(f"DEBUG: Selection bounds raw: {selection_bounds}")

            if len(selection_bounds) < 5 or not selection_bounds[0]:
                print("DEBUG: No selection found, using center area")
                # Use new shape-aware function with no selection
                return extract_context_with_selection(
                    img_width,
                    img_height,
                    0,
                    0,
                    0,
                    0,
                    mode="focused",
                    has_selection=False,
                )

            # Extract selection bounds
            sel_x1 = selection_bounds[2] if len(selection_bounds) > 2 else 0
            sel_y1 = selection_bounds[3] if len(selection_bounds) > 3 else 0
            sel_x2 = selection_bounds[4] if len(selection_bounds) > 4 else 0
            sel_y2 = selection_bounds[5] if len(selection_bounds) > 5 else 0

            sel_width = sel_x2 - sel_x1
            sel_height = sel_y2 - sel_y1
            print(
                f"DEBUG: Selection: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2}), size: {sel_width}x{sel_height}"
            )

            # Use new shape-aware function for calculation
            context_info = extract_context_with_selection(
                img_width,
                img_height,
                sel_x1,
                sel_y1,
                sel_x2,
                sel_y2,
                mode="focused",
                has_selection=True,
            )

            # Log the optimal shape selected
            print(f"DEBUG: Optimal shape selected: {context_info['target_shape']}")

            # Extract dimensions for any code that still expects target_size
            target_w, target_h = context_info["target_shape"]
            context_info["target_size"] = max(target_w, target_h)

            # Validate still works but now with shape support
            is_valid, error_msg = validate_context_info(context_info)
            if not is_valid:
                print(f"DEBUG: Context validation failed: {error_msg}")
                # Fallback to center extraction
                return extract_context_with_selection(
                    img_width,
                    img_height,
                    0,
                    0,
                    0,
                    0,
                    mode="focused",
                    has_selection=False,
                )

            # Add debug output for the calculated values
            extract_x1, extract_y1, extract_width, extract_height = context_info[
                "extract_region"
            ]
            target_w, target_h = context_info["target_shape"]

            print(
                f"DEBUG: Extract region: ({extract_x1},{extract_y1}) to ({extract_x1+extract_width},{extract_y1+extract_height}), size: {extract_width}x{extract_height}"
            )
            print(f"DEBUG: Target shape for OpenAI: {target_w}x{target_h}")

            if "padding_info" in context_info:
                padding_info = context_info["padding_info"]
                print(f"DEBUG: Scale factor: {padding_info['scale_factor']}")
                print(f"DEBUG: Padding: {padding_info['padding']}")

            return context_info

        except Exception as e:
            print(f"DEBUG: Context calculation failed: {e}")
            # Fallback to simple center extraction
            return extract_context_with_selection(
                img_width, img_height, 0, 0, 0, 0, mode="focused", has_selection=False
            )

    def _calculate_full_image_context_extraction(self, image):
        """Calculate context extraction for full image (GPT-Image-1 mode)"""
        try:
            print("DEBUG: Calculating full image context extraction")

            # Get full image dimensions
            orig_width = image.get_width()
            orig_height = image.get_height()
            print(f"DEBUG: Original full image size: {orig_width}x{orig_height}")

            # Use full image bounds as "selection"
            full_x1, full_y1 = 0, 0
            full_x2, full_y2 = orig_width, orig_height

            print(
                f"DEBUG: Full image bounds: ({full_x1},{full_y1}) to ({full_x2},{full_y2})"
            )

            # For full image mode, select optimal OpenAI shape
            target_shape = get_optimal_openai_shape(orig_width, orig_height)
            target_width, target_height = target_shape
            target_size = max(target_width, target_height)  # For backward compatibility

            print(f"DEBUG: Target OpenAI shape: {target_width}x{target_height}")

            # For full image, the context covers the entire original image
            ctx_x1 = 0
            ctx_y1 = 0

            print(
                f"DEBUG: Context region covers entire image: {orig_width}x{orig_height}"
            )

            # Check if there's actually a selection - if not, use full image for transformation
            selection_bounds = Gimp.Selection.bounds(image)
            has_real_selection = (
                selection_bounds[0] if len(selection_bounds) > 0 else False
            )

            if has_real_selection:
                # Use actual selection bounds
                sel_bounds = (
                    selection_bounds[2],
                    selection_bounds[3],
                    selection_bounds[4],
                    selection_bounds[5],
                )
            else:
                # No selection - transform entire image ("Image to Image" mode)
                sel_bounds = (full_x1, full_y1, full_x2, full_y2)

            return {
                "mode": "full",
                "selection_bounds": sel_bounds,
                "extract_region": (
                    0,
                    0,
                    orig_width,
                    orig_height,
                ),  # Extract entire image
                "target_shape": target_shape,
                "target_size": max(target_shape),  # For backward compatibility
                "needs_padding": True,
                "padding_info": calculate_padding_for_shape(
                    orig_width, orig_height, target_shape[0], target_shape[1]
                ),
                "has_selection": has_real_selection,
                "original_bounds": (full_x1, full_y1, full_x2, full_y2),
            }

        except Exception as e:
            print(f"DEBUG: Failed to calculate full image context extraction: {e}")
            return None

    def _extract_context_region(self, image, context_info):
        """Extract context region and scale to optimal OpenAI shape"""
        try:
            print("DEBUG: Extracting context region for AI with optimal shape")

            # Get parameters for the extract region
            ctx_x1, ctx_y1, ctx_width, ctx_height = context_info["extract_region"]
            target_shape = context_info["target_shape"]
            target_width, target_height = target_shape
            orig_width = image.get_width()
            orig_height = image.get_height()

            print(
                f"DEBUG: Extract region: ({ctx_x1},{ctx_y1}) to ({ctx_x1+ctx_width},{ctx_y1+ctx_height}) size={ctx_width}x{ctx_height}"
            )
            print(f"DEBUG: Original image: {orig_width}x{orig_height}")
            print(f"DEBUG: Target shape: {target_width}x{target_height}")

            # Create a new canvas with the extract region size
            extract_image = Gimp.Image.new(ctx_width, ctx_height, image.get_base_type())
            if not extract_image:
                return False, "Failed to create extract canvas", None

            # Calculate what part of the original image intersects with our extract region
            intersect_x1 = max(0, ctx_x1)
            intersect_y1 = max(0, ctx_y1)
            intersect_x2 = min(orig_width, ctx_x1 + ctx_width)
            intersect_y2 = min(orig_height, ctx_y1 + ctx_height)

            intersect_width = intersect_x2 - intersect_x1
            intersect_height = intersect_y2 - intersect_y1

            print(
                f"DEBUG: Image intersection: ({intersect_x1},{intersect_y1}) to ({intersect_x2},{intersect_y2})"
            )
            print(f"DEBUG: Intersection size: {intersect_width}x{intersect_height}")

            if intersect_width > 0 and intersect_height > 0:
                # Create a temporary image with just the intersecting region
                temp_image = image.duplicate()
                temp_image.crop(
                    intersect_width, intersect_height, intersect_x1, intersect_y1
                )

                # Create a layer from this region
                merged_layer = temp_image.merge_visible_layers(
                    Gimp.MergeType.CLIP_TO_IMAGE
                )
                if not merged_layer:
                    temp_image.delete()
                    extract_image.delete()
                    return False, "Failed to merge layers", None

                # Copy this layer to our extract canvas at the correct position
                layer_copy = Gimp.Layer.new_from_drawable(merged_layer, extract_image)
                extract_image.insert_layer(layer_copy, None, 0)

                # Position the layer correctly within the extract region
                # The layer should be at the same relative position as in the extract region
                paste_x = intersect_x1 - ctx_x1  # Offset within the extract region
                paste_y = intersect_y1 - ctx_y1  # Offset within the extract region
                layer_copy.set_offsets(paste_x, paste_y)

                print(
                    f"DEBUG: Placed image content at offset ({paste_x},{paste_y}) within extract region"
                )

                # Clean up temp image
                temp_image.delete()
            else:
                print(
                    "DEBUG: No intersection with original image - creating empty extract region"
                )

            # Scale and pad to target shape for OpenAI (preserve aspect ratio)
            if ctx_width != target_width or ctx_height != target_height:
                # Get padding info to preserve aspect ratio
                if "padding_info" in context_info:
                    padding_info = context_info["padding_info"]
                    scale_factor = padding_info["scale_factor"]
                    scaled_w, scaled_h = padding_info["scaled_size"]
                    pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

                    print(f"DEBUG: Using aspect-ratio preserving scaling:")
                    print(f"  Scale factor: {scale_factor}")
                    print(f"  Scaled size: {scaled_w}x{scaled_h}")
                    print(
                        f"  Padding: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}"
                    )

                    # First scale preserving aspect ratio
                    if scale_factor != 1.0:
                        extract_image.scale(scaled_w, scaled_h)
                        print(
                            f"DEBUG: Scaled to {scaled_w}x{scaled_h} preserving aspect ratio"
                        )

                    # Then add padding to reach target dimensions
                    if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
                        # Resize canvas to add padding
                        extract_image.resize(
                            target_width, target_height, pad_left, pad_top
                        )
                        print(
                            f"DEBUG: Added padding to reach {target_width}x{target_height}"
                        )
                else:
                    # Fallback: calculate padding on the fly
                    padding_info = calculate_padding_for_shape(
                        ctx_width, ctx_height, target_width, target_height
                    )
                    scale_factor = padding_info["scale_factor"]
                    scaled_w, scaled_h = padding_info["scaled_size"]
                    pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

                    print(f"DEBUG: Calculating padding on the fly:")
                    print(f"  Scale factor: {scale_factor}")
                    print(
                        f"  Padding: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}"
                    )

                    # First scale preserving aspect ratio
                    extract_image.scale(scaled_w, scaled_h)

                    # Then add padding
                    extract_image.resize(target_width, target_height, pad_left, pad_top)

                print(
                    f"DEBUG: Final extract image size: {target_width}x{target_height} (aspect ratio preserved)"
                )

            # Export to PNG
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name

            try:
                # Export using GIMP's PNG export
                file = Gio.File.new_for_path(temp_filename)

                pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
                pdb_config = pdb_proc.create_config()
                pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                pdb_config.set_property("image", extract_image)
                pdb_config.set_property("file", file)
                pdb_config.set_property("options", None)

                result = pdb_proc.run(pdb_config)
                if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                    print(f"DEBUG: PNG export failed: {result.index(0)}")
                    extract_image.delete()
                    return False, "PNG export failed", None

                # Read the exported file and encode to base64
                with open(temp_filename, "rb") as f:
                    png_data = f.read()

                base64_data = base64.b64encode(png_data).decode("utf-8")

                # Clean up
                os.unlink(temp_filename)
                extract_image.delete()

                info = f"Extracted context region: {len(png_data)} bytes as PNG, base64 length: {len(base64_data)}"
                print(f"DEBUG: {info}")
                return True, info, base64_data

            except Exception as e:
                print(f"DEBUG: Context extraction export failed: {e}")
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                extract_image.delete()
                return False, f"Export failed: {str(e)}", None

        except Exception as e:
            print(f"DEBUG: Context extraction failed: {e}")
            return False, f"Context extraction error: {str(e)}", None

    def _prepare_full_image(self, image):
        """Prepare full image for GPT-Image-1 processing with optimal shape"""
        try:
            print("DEBUG: Preparing full image for transformation with optimal shape")

            width = image.get_width()
            height = image.get_height()

            print(f"DEBUG: Original image size: {width}x{height}")

            # Get optimal OpenAI shape for this image
            target_shape = get_optimal_openai_shape(width, height)
            target_width, target_height = target_shape

            print(
                f"DEBUG: Optimal OpenAI shape selected: {target_width}x{target_height}"
            )

            # Calculate padding info for this shape
            padding_info = calculate_padding_for_shape(
                width, height, target_width, target_height
            )
            scale = padding_info["scale_factor"]
            scaled_width, scaled_height = padding_info["scaled_size"]

            print(f"DEBUG: Scale factor: {scale:.3f}")
            print(f"DEBUG: Scaled size: {scaled_width}x{scaled_height}")

            # Create context_info with both old and new format for compatibility
            context_info = {
                "mode": "full_image",
                "original_size": (width, height),
                "scaled_size": (scaled_width, scaled_height),
                "scale_factor": scale,
                "target_shape": target_shape,  # New: optimal shape tuple
                "target_size": (
                    target_width
                    if target_width == target_height
                    else max(target_width, target_height)
                ),  # Old format fallback
                "padding_info": padding_info,
                "has_selection": True,  # Always true for this mode
            }

            return context_info

        except Exception as e:
            print(f"DEBUG: Full image preparation failed: {e}")
            # Fallback to square
            return {
                "mode": "full_image",
                "original_size": (1024, 1024),
                "scaled_size": (1024, 1024),
                "scale_factor": 1.0,
                "target_shape": (1024, 1024),
                "target_size": 1024,
                "has_selection": True,
            }

    def _extract_full_image(self, image, context_info):
        """Extract and scale the full image for GPT-Image-1"""
        try:
            target_width, target_height = context_info["scaled_size"]
            print(
                f"DEBUG: Extracting full image, scaling to {target_width}x{target_height}"
            )

            # Create a copy of the image
            original_width = image.get_width()
            original_height = image.get_height()

            # Create image copy for processing
            temp_image = image.duplicate()

            # Flatten the image to get composite result
            if len(temp_image.get_layers()) > 1:
                temp_image.flatten()

            # Get the flattened layer
            layer = temp_image.get_layers()[0]

            # Scale the layer to target size
            layer.scale(target_width, target_height, False)

            # Scale the image canvas to match
            temp_image.scale(target_width, target_height)

            # Export to PNG in memory
            print("DEBUG: Exporting full image as PNG...")

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

            # Use GIMP's export function like the existing code
            file = Gio.File.new_for_path(temp_path)
            pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
            pdb_config = pdb_proc.create_config()
            pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
            pdb_config.set_property("image", temp_image)
            pdb_config.set_property("file", file)
            pdb_config.set_property("options", None)
            result = pdb_proc.run(pdb_config)

            if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                temp_image.delete()
                raise Exception("Failed to export full image")

            # Read the exported PNG
            with open(temp_path, "rb") as f:
                image_bytes = f.read()

            # Clean up
            os.unlink(temp_path)
            temp_image.delete()

            # Convert to base64 for API
            image_data = base64.b64encode(image_bytes).decode("utf-8")

            print(
                f"DEBUG: Full image extracted: {len(image_bytes)} bytes, base64 length: {len(image_data)}"
            )
            return (
                True,
                f"Extracted full image: {len(image_bytes)} bytes as PNG, base64 length: {len(image_data)}",
                image_data,
            )

        except Exception as e:
            print(f"DEBUG: Full image extraction failed: {e}")
            return False, f"Full image extraction failed: {str(e)}", None

    def _create_full_size_mask_then_scale(self, image, selection_channel, context_info):
        """Create mask at full original size, then scale/pad using same operations as image"""
        try:
            target_shape = context_info["target_shape"]
            target_width, target_height = target_shape
            padding_info = context_info["padding_info"]
            scale_factor = padding_info["scale_factor"]
            scaled_w, scaled_h = padding_info["scaled_size"]
            pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

            # IMPORTANT: build the mask in EXTRACT REGION coordinates so it matches the
            # extracted context image (which is a crop around the selection).
            ctx_x1, ctx_y1, ctx_w, ctx_h = context_info["extract_region"]
            mask_base_width = ctx_w
            mask_base_height = ctx_h
            print(
                f"DEBUG: Creating mask in extract-region coords {mask_base_width}x{mask_base_height} (ctx origin {ctx_x1},{ctx_y1}), then scaling/padding like image"
            )

            # Use the EXISTING working mask creation logic, but at correct base size
            mask_image = Gimp.Image.new(
                mask_base_width, mask_base_height, Gimp.ImageBaseType.RGB
            )
            mask_layer = Gimp.Layer.new(
                mask_image,
                "selection_mask",
                mask_base_width,
                mask_base_height,
                Gimp.ImageType.RGBA_IMAGE,
                100.0,
                Gimp.LayerMode.NORMAL,
            )
            mask_image.insert_layer(mask_layer, None, 0)

            # Fill with black (preserve areas)
            black_color = Gegl.Color.new("black")
            Gimp.context_set_foreground(black_color)
            mask_layer.edit_fill(Gimp.FillType.FOREGROUND)

            # Copy selection shape exactly as the working code does
            selection_buffer = selection_channel.get_buffer()
            mask_shadow_buffer = mask_layer.get_shadow_buffer()

            # Use the WORKING Gegl approach from the existing code
            graph = Gegl.Node()

            mask_source = graph.create_child("gegl:buffer-source")
            mask_source.set_property("buffer", mask_layer.get_buffer())

            selection_source = graph.create_child("gegl:buffer-source")
            selection_source.set_property("buffer", selection_buffer)

            # Translate the selection channel into extract-region space
            translate = graph.create_child("gegl:translate")
            translate.set_property("x", float(-ctx_x1))
            translate.set_property("y", float(-ctx_y1))
            selection_source.link(translate)

            composite = graph.create_child("gegl:over")
            output = graph.create_child("gegl:write-buffer")
            output.set_property("buffer", mask_shadow_buffer)

            mask_source.link(composite)
            translate.connect_to("output", composite, "aux")
            composite.link(output)
            output.process()

            mask_shadow_buffer.flush()
            mask_layer.merge_shadow(True)
            mask_layer.update(0, 0, mask_base_width, mask_base_height)

            # Mask polarity differs by backend:
            # - OpenAI edits: selection areas should be transparent (inpaint area)
            # - ComfyUI workflows often use LoadImage mask output (alpha) where white=edit.
            #   For ComfyUI we make the *background* transparent and keep selection opaque.
            transparency_graph = Gegl.Node()
            layer_buffer = mask_layer.get_buffer()
            shadow_buffer = mask_layer.get_shadow_buffer()

            buffer_source = transparency_graph.create_child("gegl:buffer-source")
            buffer_source.set_property("buffer", layer_buffer)

            color_to_alpha = transparency_graph.create_child("gegl:color-to-alpha")
            # Make background transparent; selection remains opaque white (ComfyUI behavior).
            target_color = Gegl.Color.new("black")
            color_to_alpha.set_property("color", target_color)

            buffer_write = transparency_graph.create_child("gegl:write-buffer")
            buffer_write.set_property("buffer", shadow_buffer)

            buffer_source.link(color_to_alpha)
            color_to_alpha.link(buffer_write)
            buffer_write.process()

            shadow_buffer.flush()
            mask_layer.merge_shadow(True)
            mask_layer.update(0, 0, mask_base_width, mask_base_height)

            print(
                "DEBUG: Created mask with transparent background and opaque selection (ComfyUI)"
            )

            # NOW scale using SAME operations as image
            if scale_factor != 1.0:
                mask_image.scale(scaled_w, scaled_h)
                print(f"DEBUG: Scaled mask to {scaled_w}x{scaled_h}")

            if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
                mask_image.resize(target_width, target_height, pad_left, pad_top)
                print(
                    f"DEBUG: Added padding to mask to reach {target_width}x{target_height}"
                )

            # Export (same as working code)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name

            file = Gio.File.new_for_path(temp_filename)
            pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
            pdb_config = pdb_proc.create_config()
            pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
            pdb_config.set_property("image", mask_image)
            pdb_config.set_property("file", file)
            pdb_config.set_property("options", None)

            result = pdb_proc.run(pdb_config)

            if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                mask_image.delete()
                image.remove_channel(selection_channel)
                os.unlink(temp_filename)
                raise Exception("PNG export failed")

            with open(temp_filename, "rb") as f:
                png_data = f.read()

            os.unlink(temp_filename)
            mask_image.delete()
            image.remove_channel(selection_channel)

            print(f"DEBUG: Created full-size-then-scaled mask: {len(png_data)} bytes")
            return png_data

        except Exception as e:
            print(f"DEBUG: Full size mask creation failed: {e}")
            if "mask_image" in locals():
                mask_image.delete()
            if "selection_channel" in locals():
                image.remove_channel(selection_channel)
            raise Exception(f"Full size mask creation failed: {e}")

    def _create_context_mask(self, image, context_info, target_size):
        """Create mask from actual selection shape using pixel-by-pixel copying"""
        try:
            target_shape = context_info.get("target_shape", (target_size, target_size))
            target_width, target_height = target_shape
            print(
                f"DEBUG: Creating pixel-perfect selection mask {target_width}x{target_height}"
            )

            if not context_info["has_selection"]:
                raise Exception(
                    "No selection available - selection-shaped mask requires an active selection"
                )

            # Get extract region info
            ctx_x1, ctx_y1, ctx_width, ctx_height = context_info["extract_region"]
            print(
                f"DEBUG: Extract region: ({ctx_x1},{ctx_y1}) size {ctx_width}x{ctx_height}"
            )

            # Step 1: Save original selection as channel to preserve its exact shape
            selection_channel = Gimp.Selection.save(image)
            if not selection_channel:
                raise Exception("Failed to save selection as channel")
            print("DEBUG: Saved selection as channel for pixel copying")

            # For any mode with padding, use simplified approach that mirrors image processing
            if "padding_info" in context_info:
                return self._create_full_size_mask_then_scale(
                    image, selection_channel, context_info
                )

            # Step 2: Create target-shaped mask image (RGBA for transparency)
            mask_image = Gimp.Image.new(
                target_width, target_height, Gimp.ImageBaseType.RGB
            )
            if not mask_image:
                image.remove_channel(selection_channel)
                raise Exception("Failed to create mask image")

            mask_layer = Gimp.Layer.new(
                mask_image,
                "selection_mask",
                target_width,
                target_height,
                Gimp.ImageType.RGBA_IMAGE,
                100.0,
                Gimp.LayerMode.NORMAL,
            )
            if not mask_layer:
                mask_image.delete()
                image.remove_channel(selection_channel)
                raise Exception("Failed to create mask layer")

            mask_image.insert_layer(mask_layer, None, 0)

            # Fill with black background (preserve all areas initially)
            black_color = Gegl.Color.new("black")
            Gimp.context_set_foreground(black_color)
            mask_layer.edit_fill(Gimp.FillType.FOREGROUND)
            print("DEBUG: Created black background mask (preserve all areas)")

            # Force layer update to make sure black fill is committed
            mask_layer.update(0, 0, target_width, target_height)

            # Explicitly ensure extension areas stay black by filling the entire target area
            print(
                f"DEBUG: Ensuring all extension areas are black in {target_width}x{target_height} mask"
            )

            # Step 3: Copy only the original image area, leave extended context white

            # Calculate where original image appears in context square
            orig_width, orig_height = image.get_width(), image.get_height()
            img_offset_x = max(
                0, -ctx_x1
            )  # where original image starts in context square
            img_offset_y = max(
                0, -ctx_y1
            )  # where original image starts in context square
            # Calculate where the original image content appears in the final padded target shape
            # Account for both extract region and padding
            if "padding_info" in context_info:
                padding_info = context_info["padding_info"]
                scale_factor = padding_info["scale_factor"]
                pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

                # Original content is scaled and then padded
                img_end_x = min(
                    target_width - pad_left - pad_right, int(orig_width * scale_factor)
                )
                img_end_y = min(
                    target_height - pad_top - pad_bottom,
                    int(orig_height * scale_factor),
                )

                print(
                    f"DEBUG: Accounting for padding in mask - scale={scale_factor}, padding=({pad_left},{pad_top},{pad_right},{pad_bottom})"
                )
            else:
                # Fallback to simple calculation
                img_end_x = min(
                    ctx_width, orig_width - ctx_x1 if ctx_x1 >= 0 else orig_width
                )
                img_end_y = min(
                    ctx_height, orig_height - ctx_y1 if ctx_y1 >= 0 else orig_height
                )

            print(
                f"DEBUG: Original image appears at ({img_offset_x},{img_offset_y}) to ({img_end_x},{img_end_y}) in context square"
            )

            # Only process if there's an intersection
            if img_end_x > img_offset_x and img_end_y > img_offset_y:
                # Get buffers for pixel-level operations
                selection_buffer = selection_channel.get_buffer()
                if not selection_buffer:
                    mask_image.delete()
                    image.remove_channel(selection_channel)
                    raise Exception("Failed to get selection channel buffer")

                mask_shadow_buffer = mask_layer.get_shadow_buffer()
                if not mask_shadow_buffer:
                    mask_image.delete()
                    image.remove_channel(selection_channel)
                    raise Exception("Failed to get mask shadow buffer")

                print("DEBUG: Starting Gegl pixel copying from selection channel")

                # Create Gegl processing graph for selection shape copying
                graph = Gegl.Node()

                # Source 1: Current mask buffer (black background)
                mask_source = graph.create_child("gegl:buffer-source")
                mask_source.set_property("buffer", mask_layer.get_buffer())

                # Source 2: Selection channel buffer (contains exact selection shape)
                selection_source = graph.create_child("gegl:buffer-source")
                selection_source.set_property("buffer", selection_buffer)

                # Scale selection if needed to match the final image scaling
                if "padding_info" in context_info:
                    padding_info = context_info["padding_info"]
                    scale_factor = padding_info["scale_factor"]

                    if abs(scale_factor - 1.0) > 0.001:  # Need scaling
                        print(
                            f"DEBUG: Scaling selection channel by factor {scale_factor}"
                        )
                        scale_op = graph.create_child("gegl:scale-ratio")
                        scale_op.set_property("x", float(scale_factor))
                        scale_op.set_property("y", float(scale_factor))
                        selection_source.link(scale_op)
                        selection_input = scale_op
                    else:
                        selection_input = selection_source
                else:
                    selection_input = selection_source

                # Translate selection to correct position in padded target shape
                # For full image with padding, the selection has been scaled and needs padding offset
                if "padding_info" in context_info:
                    padding_info = context_info["padding_info"]
                    pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

                    # Selection has already been scaled, just add padding offset
                    translate_x = pad_left
                    translate_y = pad_top

                    print(
                        f"DEBUG: Mask translation for padded image: translate by ({translate_x},{translate_y})"
                    )
                else:
                    # Original logic for non-padded extracts
                    translate_x = -ctx_x1
                    translate_y = -ctx_y1

                translate = graph.create_child("gegl:translate")
                translate.set_property("x", float(translate_x))
                translate.set_property("y", float(translate_y))

                # Connect scaled selection through translate to composite
                selection_input.link(translate)

                # Composite the translated selection over the black background
                # This preserves the black background in extension areas
                composite = graph.create_child("gegl:over")

                # Write to mask shadow buffer
                output = graph.create_child("gegl:write-buffer")
                output.set_property("buffer", mask_shadow_buffer)

                # Link the processing chain:
                # mask_source (black bg) + translated_selection → composite → output
                selection_source.link(translate)
                mask_source.link(composite)
                translate.connect_to("output", composite, "aux")
                composite.link(output)

                print(
                    f"DEBUG: Compositing selection over black background: translate by ({translate_x},{translate_y})"
                )

                # Process the graph to composite selection shape over black background
                output.process()
                print(
                    "DEBUG: Successfully composited selection shape over black background preserving extension areas"
                )

                # Flush and merge shadow buffer to make changes visible
                mask_shadow_buffer.flush()
                mask_layer.merge_shadow(True)
                print("DEBUG: Merged shadow buffer with base layer")
            else:
                print("DEBUG: No intersection - mask remains fully white")

            # Force complete layer update
            mask_layer.update(0, 0, target_width, target_height)

            # Force flush all changes to ensure PNG export sees the correct data
            Gimp.displays_flush()

            print("DEBUG: Successfully copied exact selection shape to mask using Gegl")

            # Step 4: Mask is already at target shape, no scaling needed
            # (Previous version scaled square masks, but we now create masks at target shape)
            print(f"DEBUG: Mask created at target shape {target_width}x{target_height}")

            # Step 4.5: Make selection areas transparent (the one simple change requested)
            # Current state: black background, white selection copied from channel
            # Needed: black background (preserve), transparent selection (inpaint)
            print("DEBUG: Making background transparent for ComfyUI mask polarity")
            scaled_mask_layer = mask_image.get_layers()[0]

            # Create a simple color-to-alpha operation to make selection areas transparent
            transparency_graph = Gegl.Node()

            # Get layer buffer
            layer_buffer = scaled_mask_layer.get_buffer()
            shadow_buffer = scaled_mask_layer.get_shadow_buffer()

            # Source buffer
            buffer_source = transparency_graph.create_child("gegl:buffer-source")
            buffer_source.set_property("buffer", layer_buffer)

            # Convert a target color to alpha: black(background) -> transparent (selection stays opaque)
            color_to_alpha = transparency_graph.create_child("gegl:color-to-alpha")
            target_color = Gegl.Color.new("black")
            color_to_alpha.set_property("color", target_color)

            # Output buffer
            buffer_write = transparency_graph.create_child("gegl:write-buffer")
            buffer_write.set_property("buffer", shadow_buffer)

            # Process: source → color-to-alpha → output
            buffer_source.link(color_to_alpha)
            color_to_alpha.link(buffer_write)
            buffer_write.process()

            # Merge changes
            shadow_buffer.flush()
            scaled_mask_layer.merge_shadow(True)
            scaled_mask_layer.update(0, 0, target_size, target_size)

            print(
                "DEBUG: Background is now transparent (ignore), selection remains opaque (edit) for ComfyUI"
            )

            # Step 5: Export as PNG for OpenAI
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name

            try:
                file = Gio.File.new_for_path(temp_filename)

                pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
                pdb_config = pdb_proc.create_config()
                pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                pdb_config.set_property("image", mask_image)
                pdb_config.set_property("file", file)
                pdb_config.set_property("options", None)

                result = pdb_proc.run(pdb_config)
                if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                    mask_image.delete()
                    image.remove_channel(selection_channel)
                    raise Exception(f"PNG export failed with status: {result.index(0)}")

                # Read the exported mask PNG
                with open(temp_filename, "rb") as f:
                    png_data = f.read()

                if len(png_data) == 0:
                    raise Exception("Exported PNG file is empty")

                # Clean up
                os.unlink(temp_filename)
                mask_image.delete()
                image.remove_channel(selection_channel)

                print(
                    f"DEBUG: Created pixel-perfect selection mask PNG: {len(png_data)} bytes"
                )
                return png_data

            except Exception as e:
                print(f"DEBUG: Mask export failed: {e}")
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                mask_image.delete()
                image.remove_channel(selection_channel)
                raise Exception(f"Mask export failed: {str(e)}")

        except Exception as e:
            print(f"DEBUG: Context mask creation failed: {e}")
            raise Exception(f"Selection-shaped mask creation failed: {str(e)}")

    def _apply_smart_mask_feathering(self, mask, image):
        """Apply smart feathering to mask edges for better blending while preserving selection size"""
        try:
            print("DEBUG: Applying smart mask feathering for enhanced edge blending")

            # Get mask dimensions and buffer
            mask_width = mask.get_width()
            mask_height = mask.get_height()
            mask_buffer = mask.get_buffer()
            shadow_buffer = mask.get_shadow_buffer()

            print(f"DEBUG: Processing mask {mask_width}x{mask_height}")

            # Simplified approach: Apply graduated gaussian blur
            # This softens edges without changing the overall selection area
            graph = Gegl.Node()

            # Source: Current mask buffer
            source = graph.create_child("gegl:buffer-source")
            source.set_property("buffer", mask_buffer)

            # Apply moderate gaussian blur to soften edges
            # Use smaller blur to maintain selection size while softening transitions
            blur = graph.create_child("gegl:gaussian-blur")
            blur.set_property("std-dev-x", 4.0)  # Moderate blur for edge softening
            blur.set_property("std-dev-y", 4.0)

            # Output to shadow buffer
            output = graph.create_child("gegl:write-buffer")
            output.set_property("buffer", shadow_buffer)

            # Link the chain: source -> blur -> output
            source.link(blur)
            blur.link(output)

            # Process the graph
            print("DEBUG: Processing edge feathering...")
            output.process()

            # Merge changes
            shadow_buffer.flush()
            mask.merge_shadow(True)
            mask.update(0, 0, mask_width, mask_height)

            print(
                "DEBUG: Smart edge feathering applied - edges softened while preserving selection area"
            )

        except Exception as e:
            print(f"DEBUG: Smart mask feathering failed (using simple feathering): {e}")
            # Fallback: apply light gaussian blur to entire mask
            try:
                mask_buffer = mask.get_buffer()
                shadow_buffer = mask.get_shadow_buffer()

                # Simple fallback: light gaussian blur on entire mask
                graph = Gegl.Node()

                source = graph.create_child("gegl:buffer-source")
                source.set_property("buffer", mask_buffer)

                blur = graph.create_child("gegl:gaussian-blur")
                blur.set_property("std-dev-x", 2.0)
                blur.set_property("std-dev-y", 2.0)

                output = graph.create_child("gegl:write-buffer")
                output.set_property("buffer", shadow_buffer)

                source.link(blur)
                blur.link(output)
                output.process()

                shadow_buffer.flush()
                mask.merge_shadow(True)
                mask.update(0, 0, mask.get_width(), mask.get_height())

                print("DEBUG: Applied fallback simple feathering")

            except Exception as e2:
                print(
                    f"DEBUG: Both smart and simple feathering failed, using original mask: {e2}"
                )

    def _sample_boundary_colors(self, image, context_info):
        """Sample colors around selection boundary for color matching"""
        try:
            print("DEBUG: Sampling boundary colors for color matching")

            if not context_info.get("has_selection", False):
                return None

            # Get selection bounds
            sel_x1, sel_y1, sel_x2, sel_y2 = context_info["selection_bounds"]

            # Sample from a ring around the selection edge
            # Inner ring: just inside selection
            # Outer ring: just outside selection
            sample_width = min(10, (sel_x2 - sel_x1) // 10)  # Adaptive sample width

            # Get the flattened image for color sampling
            merged_layer = None
            try:
                # Create a temporary flattened copy for sampling
                temp_image = image.duplicate()
                merged_layer = temp_image.flatten()

                # Sample colors using GEGL buffer operations
                layer_buffer = merged_layer.get_buffer()

                # Sample pixels around selection boundary
                inner_samples = []
                outer_samples = []

                # Sample points along the selection perimeter
                sample_points = 20  # Number of sample points

                for i in range(sample_points):
                    # Calculate position along selection perimeter
                    t = i / sample_points

                    # Sample along top and bottom edges
                    if i < sample_points // 2:
                        x = int(sel_x1 + t * 2 * (sel_x2 - sel_x1))
                        y_inner = sel_y1 + sample_width // 2
                        y_outer = sel_y1 - sample_width // 2
                    else:
                        x = int(sel_x2 - (t - 0.5) * 2 * (sel_x2 - sel_x1))
                        y_inner = sel_y2 - sample_width // 2
                        y_outer = sel_y2 + sample_width // 2

                    # Ensure coordinates are within image bounds
                    x = max(0, min(x, image.get_width() - 1))
                    y_inner = max(0, min(y_inner, image.get_height() - 1))
                    y_outer = max(0, min(y_outer, image.get_height() - 1))

                    try:
                        # Sample inner color (inside selection)
                        inner_rect = Gegl.Rectangle.new(x, y_inner, 1, 1)
                        inner_pixel = layer_buffer.get(
                            inner_rect, 1.0, "R'G'B'A u8", Gegl.AbyssPolicy.CLAMP
                        )
                        if len(inner_pixel) >= 3:
                            inner_samples.append(
                                (inner_pixel[0], inner_pixel[1], inner_pixel[2])
                            )

                        # Sample outer color (outside selection)
                        outer_rect = Gegl.Rectangle.new(x, y_outer, 1, 1)
                        outer_pixel = layer_buffer.get(
                            outer_rect, 1.0, "R'G'B'A u8", Gegl.AbyssPolicy.CLAMP
                        )
                        if len(outer_pixel) >= 3:
                            outer_samples.append(
                                (outer_pixel[0], outer_pixel[1], outer_pixel[2])
                            )

                    except Exception as sample_e:
                        print(f"DEBUG: Sample point {i} failed: {sample_e}")
                        continue

                # Calculate average colors
                if inner_samples and outer_samples:
                    # Calculate averages
                    inner_avg = tuple(
                        sum(channel) // len(inner_samples)
                        for channel in zip(*inner_samples)
                    )
                    outer_avg = tuple(
                        sum(channel) // len(outer_samples)
                        for channel in zip(*outer_samples)
                    )

                    # Calculate differences for color correction
                    hue_diff = 0  # Simplified - could calculate actual hue difference
                    brightness_diff = (sum(outer_avg) // 3) - (sum(inner_avg) // 3)

                    color_info = {
                        "inner_avg": inner_avg,
                        "outer_avg": outer_avg,
                        "brightness_diff": brightness_diff,
                        "hue_diff": hue_diff,
                    }

                    print(
                        f"DEBUG: Sampled colors - Inner: {inner_avg}, Outer: {outer_avg}"
                    )
                    print(f"DEBUG: Brightness difference: {brightness_diff}")

                    return color_info
                else:
                    print("DEBUG: No valid color samples collected")
                    return None

            finally:
                # Clean up temporary image
                if merged_layer and hasattr(merged_layer, "get_image"):
                    temp_image = merged_layer.get_image()
                    if temp_image:
                        temp_image.delete()

        except Exception as e:
            print(f"DEBUG: Color sampling failed: {e}")
            return None

    def _apply_color_matching(self, result_layer, color_info):
        """Apply color correction to match sampled boundary colors"""
        if not color_info:
            print("DEBUG: No color info available - skipping color matching")
            return

        try:
            print("DEBUG: Applying color matching based on boundary samples")

            # Get layer buffer
            layer_buffer = result_layer.get_buffer()
            shadow_buffer = result_layer.get_shadow_buffer()

            # Create color correction graph
            graph = Gegl.Node()

            # Source buffer
            source = graph.create_child("gegl:buffer-source")
            source.set_property("buffer", layer_buffer)

            # Apply brightness/levels adjustment if significant difference
            brightness_diff = color_info.get("brightness_diff", 0)
            if abs(brightness_diff) > 10:  # Only apply if difference is noticeable
                levels = graph.create_child("gegl:levels")

                # Adjust gamma based on brightness difference
                gamma_adjust = 1.0 + (brightness_diff / 255.0)
                gamma_adjust = max(0.5, min(2.0, gamma_adjust))  # Clamp gamma

                levels.set_property("in-low", 0.0)
                levels.set_property("in-high", 1.0)
                levels.set_property("gamma", gamma_adjust)
                levels.set_property("out-low", 0.0)
                levels.set_property("out-high", 1.0)

                source.link(levels)
                current_node = levels

                print(f"DEBUG: Applied gamma correction: {gamma_adjust}")
            else:
                current_node = source
                print(
                    "DEBUG: No significant brightness difference - skipping levels adjustment"
                )

            # Output buffer
            output = graph.create_child("gegl:write-buffer")
            output.set_property("buffer", shadow_buffer)

            current_node.link(output)

            # Process color correction
            output.process()

            # Merge changes
            shadow_buffer.flush()
            result_layer.merge_shadow(True)
            result_layer.update(
                0, 0, result_layer.get_width(), result_layer.get_height()
            )

            print("DEBUG: Color matching applied successfully")

        except Exception as e:
            print(f"DEBUG: Color matching failed: {e}")

    def run_inpaint(self, procedure, run_mode, image, drawables, config, run_data):
        print("DEBUG: AI Inpaint Selection called!")

        # Save the currently selected layers before any API calls that might clear them
        original_selected_layers = image.get_selected_layers()
        print(f"DEBUG: Saved {len(original_selected_layers)} originally selected layers")

        # Step 1: Check for active selection FIRST
        print("DEBUG: Checking for active selection...")
        selection_bounds = Gimp.Selection.bounds(image)
        has_selection = len(selection_bounds) >= 5 and selection_bounds[0]

        if not has_selection:
            print("DEBUG: No selection found - showing error message")
            Gimp.message(
                "❌ No Selection Found!\n\n"
                "AI Inpainting requires an active selection to define the area to modify.\n\n"
                "Please:\n"
                "1. Use selection tools (Rectangle, Ellipse, Free Select, etc.)\n"
                "2. Select the area you want to inpaint\n"
                "3. Run AI Inpaint Selection again"
            )
            # Restore layer selection before returning
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after no canvas selection error")
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        print("DEBUG: Selection found - proceeding with inpainting")

        # Step 2: Get user prompt
        print("DEBUG: About to show prompt dialog...")
        dialog_result = self._show_prompt_dialog(
            "AI Inpaint",
            "",
            show_mode_selection=True,
            image=image,
        )
        print(f"DEBUG: Dialog returned: {repr(dialog_result)}")

        if not dialog_result:
            print("DEBUG: User cancelled prompt dialog")
            # Restore layer selection before returning
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after dialog cancel")
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Extract dialog, progress_label, prompt, mode, and optional mask strength
        dialog, progress_label, prompt, selected_mode, mask_strength, seed = dialog_result
        print(f"DEBUG: Extracted prompt: '{prompt}', mode: '{selected_mode}', seed: {seed}")

        try:
            # Step 3: Validate ComfyUI configuration
            if not self._provider_is_configured(action="inpaint_focused"):
                self._update_progress(progress_label, "❌ ComfyUI is not configured!")
                Gimp.message(
                    "❌ ComfyUI is not configured!\n\nPlease configure ComfyUI settings in:\nFilters → AI → Settings"
                )
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            # Create progress callback for thread-to-UI communication
            progress_callback = self._create_progress_callback(progress_label)

            # Do GIMP operations on main thread, only thread the API call
            mode = self._get_processing_mode(selected_mode)
            print(f"DEBUG: Using processing mode: {mode}")

            self._update_progress(progress_label, "🔍 Processing image...")

            if mode == "full_image":
                print("DEBUG: Calculating full-image context extraction...")
                context_info = self._calculate_full_image_context_extraction(image)
            elif mode == "contextual":
                print("DEBUG: Calculating contextual selection-based extraction...")
                context_info = self._calculate_context_extraction(image)
            else:
                print("DEBUG: Unknown mode, defaulting to contextual extraction...")
                context_info = self._calculate_context_extraction(image)

            self._update_progress(progress_label, "🔍 Analyzing image context...")

            # Sample boundary colors for contextual mode (before inpainting)
            color_info = None
            if (
                mode == "contextual"
                and context_info
                and context_info.get("has_selection", False)
            ):
                print("DEBUG: Sampling boundary colors for color matching...")
                color_info = self._sample_boundary_colors(image, context_info)

            # Extract context region with padding (works for both modes)
            print("DEBUG: Extracting context region...")
            success, message, image_data = self._extract_context_region(
                image, context_info
            )
            if not success:
                self._update_progress(
                    progress_label, f"❌ Context extraction failed: {message}"
                )
                Gimp.message(f"❌ Context Extraction Failed: {message}")
                print(f"DEBUG: Context extraction failed: {message}")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )
            print(f"DEBUG: Context extraction succeeded: {message}")

            self._update_progress(progress_label, "🎭 Creating selection mask...")

            # Create smart mask that respects selection within context
            print("DEBUG: Creating context-aware mask...")
            if not context_info:
                self._update_progress(progress_label, "❌ Context info not available")
                Gimp.message("❌ Context info not available")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            mask_data = self._create_context_mask(
                image, context_info, context_info["target_size"]
            )

            self._update_progress(progress_label, "🚀 Starting AI processing...")

            # Route based on mode:
            # - "contextual" (Focused) -> inpaint_focused workflow
            # - "full_image" -> imageedit_1 workflow
            if mode == "full_image":
                action = "imageedit_1"
                # For full image mode, we don't need a mask
                mask_data = None
            else:
                action = "inpaint_focused"
                # ComfyUI v2 workflows can derive mask from image alpha (single file).
                # If the inpaint workflow does NOT provide an inputMaskFilename override,
                # embed the selection into the image alpha (selected area becomes transparent)
                # and skip sending a separate mask file.
                wf = (self.config.get("workflows", {}) or {}).get("inpaint_focused", {}) or {}
                overrides = (wf.get("overrides") or {}) if isinstance(wf, dict) else {}
                if isinstance(overrides, dict) and ("inputMaskFilename" not in overrides):
                    try:
                        img_bytes = base64.b64decode(image_data)
                        embedded = self._comfyui_embed_mask_into_image_alpha(
                            img_bytes, mask_data, strength_percent=mask_strength
                        )
                        image_data = embedded  # pass bytes through to ComfyUI runner
                        mask_data = None
                        print("DEBUG: Using embedded alpha mask image for ComfyUI inpaint (single input)")
                    except Exception as e:
                        print(f"DEBUG: Failed to embed mask into alpha (fallback to separate mask): {e}")

            # Determine the optimal size for ComfyUI
            if context_info and "target_shape" in context_info:
                target_w, target_h = context_info["target_shape"]
                api_size = f"{target_w}x{target_h}"
            elif context_info and "target_size" in context_info:
                # Fallback to square for old format
                size = context_info["target_size"]
                api_size = f"{size}x{size}"
            else:
                api_size = "1024x1024"  # Default

            print(f"DEBUG: Using ComfyUI size: {api_size}, action: {action}")

            api_success, api_message, api_response = self._ai_edit_threaded(
                image_data,
                mask_data,
                prompt,
                size=api_size,
                progress_label=progress_label,
                action=action,
                seed=seed,
            )

            if api_success:
                print(f"DEBUG: AI API succeeded: {api_message}")
                self._update_progress(progress_label, "Processing AI response...")

                # Download and composite result with proper masking
                # Note: _download_and_composite_result is in ImageProcessingMixin
                import_success, import_message = self._download_and_composite_result(
                    image, api_response, context_info, mode, color_info
                )

                if import_success:
                    self._update_progress(progress_label, "✅ AI Inpaint Complete!")
                    print(f"DEBUG: AI Inpaint Complete - {import_message}")
                else:
                    self._update_progress(
                        progress_label, f"⚠️ Import Failed: {import_message}"
                    )
                    Gimp.message(
                        f"⚠️ AI Generated but Import Failed!\n\nPrompt: {prompt}\nAPI: {api_message}\nImport Error: {import_message}"
                    )
                    print(f"DEBUG: Import failed: {import_message}")
            else:
                # Check if this was a cancellation vs actual API failure
                if "cancelled" in api_message.lower():
                    self._update_progress(
                        progress_label, "❌ Operation cancelled by user"
                    )
                    Gimp.message("❌ Operation cancelled by user")
                else:
                    self._update_progress(
                        progress_label, f"❌ AI API Failed: {api_message}"
                    )
                    Gimp.message(f"❌ AI API Failed: {api_message}")
                print(f"DEBUG: AI API failed: {api_message}")

            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

        finally:
            # Always destroy the dialog
            if dialog:
                dialog.destroy()
            # Always restore original layer selection after any operation outcome
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after inpaint operation")

