"""
Layer compositing mixin for GIMP AI Plugin.
"""

import os
import tempfile
import gi
from gi.repository import Gimp, Gtk, GLib, Gio, GimpUi

# Import coordinate utilities
from utils import get_optimal_openai_shape, calculate_padding_for_shape


class CompositeMixin:
    """Mixin class providing layer compositing functionality"""
    
    def _show_composite_dialog(self, image):
        """Show dedicated dialog for Layer Composite with visible layers info"""
        try:
            print("DEBUG: Creating Layer Composite dialog")

            # Get visible layers (image.get_layers() returns top-to-bottom order)
            all_layers = image.get_layers()
            visible_layers = [layer for layer in all_layers if layer.get_visible()]

            if len(visible_layers) < 2:
                error_dialog = Gtk.MessageDialog(
                    parent=None,
                    flags=Gtk.DialogFlags.MODAL,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text="Not enough visible layers",
                )
                error_dialog.format_secondary_text(
                    "Layer Composite requires at least 2 visible layers.\n\n"
                    "Please make sure you have at least 2 visible layers in your image."
                )
                error_dialog.run()
                error_dialog.destroy()
                return None

            # Create dialog using helper methods
            dialog = self._create_dialog_base("AI Layer Composite", (600, 500))

            # Add buttons
            dialog.add_button("Settings", Gtk.ResponseType.HELP)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            ok_button = dialog.add_button("Composite", Gtk.ResponseType.OK)
            ok_button.set_can_default(True)
            ok_button.grab_default()

            # Set up content area
            content_area = self._setup_dialog_content_area(dialog, spacing=10)

            # Title
            title_label = Gtk.Label()
            title_label.set_markup("<b>AI Layer Composite</b>")
            title_label.set_halign(Gtk.Align.START)
            content_area.pack_start(title_label, False, False, 0)

            # Info about visible layers
            info_text = f"Found {len(visible_layers)} visible layer(s).\n"
            info_text += "Top 3 layers (starting from top) will be used for compositing."
            info_label = Gtk.Label()
            info_label.set_text(info_text)
            info_label.set_halign(Gtk.Align.START)
            info_label.set_line_wrap(True)
            content_area.pack_start(info_label, False, False, 0)

            # Add API warning bar
            api_warning_bar, needs_config = self._add_api_warning_bar(
                content_area, dialog, action="imageedit_2"
            )
            if needs_config:
                ok_button.set_sensitive(False)
                ok_button.set_label("Configure & Continue")

            # Layer list
            layers_frame = Gtk.Frame(label="Layers to composite (top to bottom):")
            layers_frame.set_margin_top(10)
            content_area.pack_start(layers_frame, False, False, 0)

            layers_box = Gtk.VBox(spacing=5)
            layers_box.set_margin_start(10)
            layers_box.set_margin_end(10)
            layers_box.set_margin_top(5)
            layers_box.set_margin_bottom(10)
            layers_frame.add(layers_box)

            # Show up to 3 layers
            display_layers = visible_layers[:3]
            for i, layer in enumerate(display_layers, 1):
                layer_label = Gtk.Label()
                layer_label.set_text(f"{i}. {layer.get_name()}")
                layer_label.set_halign(Gtk.Align.START)
                layers_box.pack_start(layer_label, False, False, 0)

            if len(visible_layers) > 3:
                warning_label = Gtk.Label()
                warning_label.set_text(
                    f"⚠️ Only top 3 layers will be used ({len(visible_layers) - 3} more layers ignored)"
                )
                warning_label.set_halign(Gtk.Align.START)
                layers_box.pack_start(warning_label, False, False, 0)

            # Prompt text area
            prompt_label = Gtk.Label(label="Describe how to composite these layers:")
            prompt_label.set_halign(Gtk.Align.START)
            prompt_label.set_margin_top(10)
            content_area.pack_start(prompt_label, False, False, 0)

            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
            )
            scrolled_window.set_min_content_height(100)

            text_view = Gtk.TextView()
            text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            text_view.set_border_width(8)

            default_prompt = self._get_last_prompt()
            if not default_prompt:
                default_prompt = "Composite these layers naturally"
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(default_prompt)

            scrolled_window.add(text_view)
            content_area.pack_start(scrolled_window, True, True, 0)

            # Mask option
            use_mask_check = Gtk.CheckButton(label="Include selection mask (if available)")
            use_mask_check.set_active(False)
            use_mask_check.set_margin_top(10)
            content_area.pack_start(use_mask_check, False, False, 0)

            # Seed input
            seed_frame = Gtk.Frame(label="Seed (optional, leave empty for random):")
            seed_frame.set_margin_top(10)
            content_area.pack_start(seed_frame, False, False, 0)

            seed_box = Gtk.HBox(spacing=6)
            seed_box.set_margin_start(10)
            seed_box.set_margin_end(10)
            seed_box.set_margin_top(5)
            seed_box.set_margin_bottom(10)
            seed_frame.add(seed_box)

            seed_entry = Gtk.Entry()
            seed_entry.set_placeholder_text("Random")
            seed_entry.set_tooltip_text("Leave empty for random seed, or enter a specific seed number")
            seed_box.pack_start(seed_entry, True, True, 0)

            # Progress widget
            progress_frame, progress_label = self._create_progress_widget()
            content_area.pack_start(progress_frame, False, False, 0)

            # Show dialog
            content_area.show_all()
            text_view.grab_focus()

            # Run dialog loop
            while True:
                response = dialog.run()

                if response == Gtk.ResponseType.OK:
                    # Check if provider is configured
                    if not self._provider_is_configured(action="imageedit_2"):
                        self._show_settings_dialog(dialog)
                        if self._provider_is_configured(action="imageedit_2"):
                            if api_warning_bar:
                                api_warning_bar.hide()
                            ok_button.set_sensitive(True)
                            ok_button.set_label("Composite")
                        continue

                    # Get prompt
                    start_iter = text_buffer.get_start_iter()
                    end_iter = text_buffer.get_end_iter()
                    prompt = text_buffer.get_text(start_iter, end_iter, False).strip()

                    if not prompt:
                        error_dialog = Gtk.MessageDialog(
                            parent=dialog,
                            flags=Gtk.DialogFlags.MODAL,
                            message_type=Gtk.MessageType.WARNING,
                            buttons=Gtk.ButtonsType.OK,
                            text="Please enter a prompt",
                        )
                        error_dialog.format_secondary_text(
                            "You need to describe how to composite the layers."
                        )
                        error_dialog.run()
                        error_dialog.destroy()
                        continue

                    # Get seed value
                    seed_text = seed_entry.get_text().strip()
                    seed_value = None
                    if seed_text:
                        try:
                            seed_value = int(seed_text)
                        except ValueError:
                            error_dialog = Gtk.MessageDialog(
                                parent=dialog,
                                flags=Gtk.DialogFlags.MODAL,
                                message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.OK,
                                text="Invalid seed value",
                            )
                            error_dialog.format_secondary_text("Seed must be a number. Please enter a valid number or leave empty for random.")
                            error_dialog.run()
                            error_dialog.destroy()
                            continue

                    # Save prompt to history
                    if prompt:
                        self._add_to_prompt_history(prompt)

                    # Disable OK button
                    ok_button.set_sensitive(False)
                    ok_button.set_label("Processing...")

                    # Reset cancel flag
                    self._cancel_requested = False

                    return (
                        dialog,
                        progress_label,
                        prompt,
                        visible_layers[:3],  # Return up to 3 layers
                        use_mask_check.get_active(),
                        seed_value,
                    )

                elif response == Gtk.ResponseType.APPLY:  # Configure Now
                    self._show_settings_dialog(dialog)
                    if self._provider_is_configured(action="imageedit_2"):
                        if api_warning_bar:
                            api_warning_bar.hide()
                        ok_button.set_sensitive(True)
                        ok_button.set_label("Composite")
                elif response == Gtk.ResponseType.HELP:  # Settings
                    self._show_settings_dialog(dialog)
                else:
                    dialog.destroy()
                    return None

        except Exception as e:
            print(f"DEBUG: Composite dialog error: {e}")
            return None

    def _prepare_layers_for_composite(self, selected_layers):
        """Prepare multiple layers for OpenAI composite API - each layer as separate PNG"""
        try:
            print(f"DEBUG: Preparing {len(selected_layers)} layers for composite API")

            layer_data_list = []

            # Process primary layer (bottom/first) with full optimization
            primary_layer = selected_layers[0]
            print(f"DEBUG: Processing primary layer: {primary_layer.get_name()}")

            # Create temporary image with just the primary layer
            primary_temp_image = Gimp.Image.new(
                primary_layer.get_width(),
                primary_layer.get_height(),
                Gimp.ImageBaseType.RGB,
            )

            # Use GIMP's built-in layer copying - much more reliable than manual buffer operations
            print(f"DEBUG: Copying primary layer using new_from_drawable method")
            primary_layer_copy = Gimp.Layer.new_from_drawable(
                primary_layer, primary_temp_image
            )
            primary_layer_copy.set_name("primary_copy")
            primary_temp_image.insert_layer(primary_layer_copy, None, 0)
            print("DEBUG: Primary layer copy completed via new_from_drawable")

            # Get optimal shape for primary image (using existing logic)
            primary_width = primary_temp_image.get_width()
            primary_height = primary_temp_image.get_height()
            optimal_shape = get_optimal_openai_shape(primary_width, primary_height)
            target_width, target_height = optimal_shape

            print(
                f"DEBUG: Primary layer optimal shape: {primary_width}x{primary_height} -> {target_width}x{target_height}"
            )

            # Scale primary image to optimal shape
            primary_temp_image.scale(target_width, target_height)
            primary_layer_copy.scale(target_width, target_height, False)

            # Export primary layer to PNG
            primary_png_data = self._export_layer_to_png(primary_temp_image)
            if primary_png_data:
                layer_data_list.append(primary_png_data)
                print(f"DEBUG: Primary layer exported: {len(primary_png_data)} bytes")

            primary_temp_image.delete()

            # Process additional layers - scale proportionally to match primary
            for i, layer in enumerate(selected_layers[1:], 1):
                print(f"DEBUG: Processing additional layer {i}: {layer.get_name()}")

                # Create temporary image for this layer
                temp_image = Gimp.Image.new(
                    layer.get_width(), layer.get_height(), Gimp.ImageBaseType.RGB
                )

                # Use GIMP's built-in layer copying - much more reliable than manual buffer operations
                print(
                    f"DEBUG: Copying additional layer {i} using new_from_drawable method"
                )
                layer_copy = Gimp.Layer.new_from_drawable(layer, temp_image)
                layer_copy.set_name(f"layer_copy_{i}")
                temp_image.insert_layer(layer_copy, None, 0)
                print(
                    f"DEBUG: Additional layer {i} copy completed via new_from_drawable"
                )

                # Scale to match primary dimensions (proportional scaling)
                scale_x = target_width / layer.get_width()
                scale_y = target_height / layer.get_height()
                scale_factor = min(scale_x, scale_y)  # Maintain aspect ratio

                new_width = int(layer.get_width() * scale_factor)
                new_height = int(layer.get_height() * scale_factor)

                print(
                    f"DEBUG: Scaling layer {i}: {layer.get_width()}x{layer.get_height()} -> {new_width}x{new_height}"
                )

                temp_image.scale(new_width, new_height)
                layer_copy.scale(new_width, new_height, False)

                # If smaller than target, pad with transparency
                if new_width < target_width or new_height < target_height:
                    offset_x = (target_width - new_width) // 2
                    offset_y = (target_height - new_height) // 2
                    temp_image.resize(target_width, target_height, offset_x, offset_y)

                # Export layer to PNG
                layer_png_data = self._export_layer_to_png(temp_image)
                if layer_png_data:
                    layer_data_list.append(layer_png_data)
                    print(
                        f"DEBUG: Additional layer {i} exported: {len(layer_png_data)} bytes"
                    )

                temp_image.delete()

            print(
                f"DEBUG: Successfully prepared {len(layer_data_list)} layers for composite"
            )
            return (
                True,
                f"Prepared {len(layer_data_list)} layers",
                layer_data_list,
                optimal_shape,
            )

        except Exception as e:
            print(f"DEBUG: Layer preparation failed: {e}")
            return False, f"Layer preparation failed: {str(e)}", None, None

    def _export_layer_to_png(self, temp_image):
        """Helper function to export a GIMP image to PNG bytes"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

            # Export using GIMP's PNG export
            file = Gio.File.new_for_path(temp_path)
            pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
            pdb_config = pdb_proc.create_config()
            pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
            pdb_config.set_property("image", temp_image)
            pdb_config.set_property("file", file)
            pdb_config.set_property("options", None)
            result = pdb_proc.run(pdb_config)

            if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                os.unlink(temp_path)
                return None

            # Read the PNG data
            with open(temp_path, "rb") as f:
                png_data = f.read()

            # Debug the exported PNG
            print(f"DEBUG: Exported PNG size: {len(png_data)} bytes")
            print(
                f"DEBUG: Image dimensions: {temp_image.get_width()}x{temp_image.get_height()}"
            )
            print(
                f"DEBUG: Expected raw size: {temp_image.get_width() * temp_image.get_height() * 4} bytes (RGBA)"
            )
            print(
                f"DEBUG: Compression ratio: {len(png_data) / (temp_image.get_width() * temp_image.get_height() * 4):.4f}"
            )

            os.unlink(temp_path)
            return png_data

        except Exception as e:
            print(f"DEBUG: PNG export failed: {e}")
            return None

    def run_layer_composite(
        self, procedure, run_mode, image, drawables, config, run_data
    ):
        """Layer Composite - combine multiple layers using OpenAI API"""
        print("DEBUG: Layer Composite called!")

        # Save the currently selected layers before showing dialog (which queries layers and might clear selection)
        original_selected_layers = image.get_selected_layers()
        print(f"DEBUG: Saved {len(original_selected_layers)} originally selected layers")

        # Step 1: Show prompt dialog with layer selection
        print("DEBUG: Showing layer composite dialog...")
        dialog_result = self._show_composite_dialog(image)
        print(f"DEBUG: Dialog returned: {repr(dialog_result)}")

        if not dialog_result:
            print("DEBUG: User cancelled prompt dialog")
            # Restore layer selection before returning
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after dialog cancel")
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Handle composite dialog result: (dialog, progress_label, prompt, layers, use_mask)
        dialog, progress_label, prompt, selected_layers, use_mask, seed = dialog_result
        print(
            f"DEBUG: Layer composite mode: {len(selected_layers)} layers, mask: {use_mask}, seed: {seed}"
        )

        try:
            # Step 2: Validate ComfyUI configuration
            if not self._provider_is_configured(action="imageedit_2"):
                self._update_progress(progress_label, "❌ ComfyUI is not configured!")
                Gimp.message(
                    "❌ ComfyUI is not configured!\n\nPlease configure ComfyUI settings in:\nFilters → AI → Settings"
                )
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            # Use existing layer preparation method
            self._update_progress(progress_label, "🔧 Preparing layers...")
            print("DEBUG: Preparing layers for composite...")

            # Take top-most layers (up to 3) for ImageEdit workflows
            num_layers = len(selected_layers)
            if num_layers > 3:
                selected_layers = selected_layers[:3]
                num_layers = 3
                print(f"DEBUG: Limited to top 3 layers for ImageEdit workflow")

            # Select action based on layer count
            if num_layers == 2:
                action = "imageedit_2"
            elif num_layers == 3:
                action = "imageedit_3"
            else:
                self._update_progress(progress_label, "❌ Layer Composite requires 2-3 layers!")
                Gimp.message("❌ Layer Composite requires 2-3 visible layers.")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            # Validate configuration for the selected action
            if not self._provider_is_configured(action=action):
                self._update_progress(progress_label, f"❌ ComfyUI {action} workflow not configured!")
                Gimp.message(
                    f"❌ ComfyUI {action} workflow not configured!\n\nPlease configure the workflow path in:\nFilters → AI → Settings"
                )
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            # Reverse layer order so base layer (last in dialog list) is first for API
            layers_for_api = list(reversed(selected_layers))

            # Use the existing preparation method
            success, message, layer_data_list, optimal_shape = (
                self._prepare_layers_for_composite(layers_for_api)
            )
            if not success:
                self._update_progress(
                    progress_label, f"❌ Layer preparation failed: {message}"
                )
                Gimp.message(f"❌ Layer Preparation Failed: {message}")
                print(f"DEBUG: Layer preparation failed: {message}")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            print(f"DEBUG: Layer preparation succeeded: {message}, using action: {action}")

            # Always create context_info for result processing (padding removal and scaling)
            img_width = image.get_width()
            img_height = image.get_height()
            target_width, target_height = optimal_shape

            # Create context_info for result processing
            context_info = {
                "mode": "full",
                "selection_bounds": (
                    0,
                    0,
                    img_width,
                    img_height,
                ),  # Default to full image
                "extract_region": (0, 0, img_width, img_height),  # Full image
                "target_shape": (target_width, target_height),
                "target_size": max(target_width, target_height),
                "needs_padding": True,
                "padding_info": calculate_padding_for_shape(
                    img_width, img_height, target_width, target_height
                ),
                "has_selection": False,  # Will be updated if mask is used
            }

            self._update_progress(progress_label, "Creating mask...")

            # Prepare mask if requested
            mask_data = None
            if use_mask:
                print("DEBUG: Preparing mask for primary layer...")
                # Use the same context-based mask approach as inpainting
                selection_bounds = Gimp.Selection.bounds(image)
                if len(selection_bounds) >= 5 and selection_bounds[0]:
                    print("DEBUG: Creating context-aware mask for layer composite...")

                    # Get selection bounds
                    sel_x1 = selection_bounds[2] if len(selection_bounds) > 2 else 0
                    sel_y1 = selection_bounds[3] if len(selection_bounds) > 3 else 0
                    sel_x2 = (
                        selection_bounds[4] if len(selection_bounds) > 4 else img_width
                    )
                    sel_y2 = (
                        selection_bounds[5] if len(selection_bounds) > 5 else img_height
                    )

                    # Update context_info with actual selection bounds
                    context_info["selection_bounds"] = (sel_x1, sel_y1, sel_x2, sel_y2)
                    context_info["has_selection"] = True

                    # Create mask using the same function as inpainting
                    mask_data = self._create_context_mask(
                        image, context_info, context_info["target_size"]
                    )
                    print(
                        f"DEBUG: Created context-aware selection mask for composite {target_width}x{target_height}"
                    )
                else:
                    # ERROR: User checked the mask box but there's no selection
                    print("DEBUG: ERROR - Use mask checked but no selection found")
                    self._update_progress(
                        progress_label, "❌ No selection found for mask"
                    )
                    Gimp.message(
                        "❌ Selection Required for Mask\n\n"
                        "You checked 'Include selection mask' but no selection was found.\n\n"
                        "Please either:\n"
                        "• Make a selection on your image, or\n"
                        "• Uncheck 'Include selection mask'"
                    )
                    return procedure.new_return_values(
                        Gimp.PDBStatusType.CANCEL, GLib.Error()
                    )

            self._update_progress(progress_label, "🚀 Starting AI processing...")

            # Call ComfyUI with layer array using optimal shape
            target_width, target_height = optimal_shape
            api_size = f"{target_width}x{target_height}"
            print(
                f"DEBUG: Calling ComfyUI {action} workflow with {len(layer_data_list)} layers, size={api_size}..."
            )

            api_success, api_message, api_response = self._ai_edit_threaded(
                layer_data_list,
                mask_data,
                prompt,
                size=api_size,
                progress_label=progress_label,
                action=action,
                seed=seed,
            )

            if api_success and api_response:
                self._update_progress(progress_label, "✅ Loading composite image...")

                # Load the composite image as a new GIMP image (not a layer)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                    temp_filename = temp_file.name
                    temp_file.write(api_response)

                try:
                    file = Gio.File.new_for_path(temp_filename)
                    new_image = Gimp.file_load(
                        run_mode=Gimp.RunMode.NONINTERACTIVE, file=file
                    )

                    if new_image:
                        # Display the new image
                        Gimp.Display.new(new_image)
                        self._update_progress(progress_label, "✅ Layer Composite Complete!")
                        Gimp.message("✅ Layer Composite Complete! New image created.")
                        print("DEBUG: Layer composite successful - new image created")
                    else:
                        raise Exception("Failed to load composite image")
                finally:
                    os.unlink(temp_filename)

                return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
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
                print("DEBUG: Restored layer selection after composite operation")

