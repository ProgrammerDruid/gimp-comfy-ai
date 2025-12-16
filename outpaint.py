"""
Outpainting mixin for GIMP AI Plugin.
"""

import os
import tempfile
import gi
from gi.repository import Gimp, GimpUi, Gtk, GLib, Gio


class OutpaintMixin:
    """Mixin class providing outpainting functionality"""
    
    def _show_outpaint_dialog(self, image):
        """Show dialog for Outpaint with prompt and pad options"""
        try:
            print("DEBUG: Creating Outpaint dialog")

            # Create dialog using helper methods
            dialog = self._create_dialog_base("AI Outpaint")

            # Add buttons
            dialog.add_button("Settings", Gtk.ResponseType.HELP)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            ok_button = dialog.add_button("Outpaint", Gtk.ResponseType.OK)
            ok_button.set_can_default(True)
            ok_button.grab_default()

            # Set up content area
            content_area = self._setup_dialog_content_area(dialog)

            # Title
            title_label = Gtk.Label()
            title_label.set_markup("<b>AI Outpaint</b>")
            title_label.set_halign(Gtk.Align.START)
            content_area.pack_start(title_label, False, False, 0)

            info_label = Gtk.Label()
            info_label.set_text(
                "Extend the image beyond its current boundaries using AI."
            )
            info_label.set_halign(Gtk.Align.START)
            content_area.pack_start(info_label, False, False, 0)

            # Add API warning bar
            api_warning_bar, needs_config = self._add_api_warning_bar(
                content_area, dialog, action="outpaint"
            )
            if needs_config:
                ok_button.set_sensitive(False)
                ok_button.set_label("Configure & Continue")

            # Prompt text area
            prompt_label = Gtk.Label(label="Describe how to extend the image:")
            prompt_label.set_halign(Gtk.Align.START)
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
                default_prompt = "Extend the image naturally"
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(default_prompt)

            scrolled_window.add(text_view)
            content_area.pack_start(scrolled_window, True, True, 0)

            # Pad input
            pad_label = Gtk.Label(label="Padding (pixels):")
            pad_label.set_halign(Gtk.Align.START)
            content_area.pack_start(pad_label, False, False, 0)

            pad_entry = Gtk.SpinButton()
            pad_entry.set_adjustment(Gtk.Adjustment(value=128, lower=32, upper=512, step_increment=32, page_increment=64))
            pad_entry.set_numeric(True)
            content_area.pack_start(pad_entry, False, False, 0)

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
                    if not self._provider_is_configured(action="outpaint"):
                        self._show_settings_dialog(dialog)
                        if self._provider_is_configured(action="outpaint"):
                            if api_warning_bar:
                                api_warning_bar.hide()
                            ok_button.set_sensitive(True)
                            ok_button.set_label("Outpaint")
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
                        error_dialog.format_secondary_text("You need to describe how to extend the image.")
                        error_dialog.run()
                        error_dialog.destroy()
                        continue

                    # Get pad value
                    pad = int(pad_entry.get_value())

                    # Get seed value
                    seed_text = seed_entry.get_text().strip()
                    seed = None
                    if seed_text:
                        try:
                            seed = int(seed_text)
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

                    return (dialog, progress_label, prompt, pad, seed)

                elif response == Gtk.ResponseType.APPLY:  # Configure Now
                    self._show_settings_dialog(dialog)
                    if self._provider_is_configured(action="outpaint"):
                        if api_warning_bar:
                            api_warning_bar.hide()
                        ok_button.set_sensitive(True)
                        ok_button.set_label("Outpaint")
                elif response == Gtk.ResponseType.HELP:  # Settings
                    self._show_settings_dialog(dialog)
                else:
                    dialog.destroy()
                    return None

        except Exception as e:
            print(f"DEBUG: Outpaint dialog error: {e}")
            return None

    def run_outpaint(self, procedure, run_mode, image, drawables, config, run_data):
        """Outpaint - extend image beyond boundaries"""
        print("DEBUG: AI Outpaint called!")

        # Show dialog
        dialog_result = self._show_outpaint_dialog(image)
        if not dialog_result:
            print("DEBUG: User cancelled outpaint dialog")
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        dialog, progress_label, prompt, pad, seed = dialog_result

        try:
            # Validate ComfyUI configuration
            if not self._provider_is_configured(action="outpaint"):
                self._update_progress(progress_label, "❌ ComfyUI is not configured!")
                Gimp.message(
                    "❌ ComfyUI is not configured!\n\nPlease configure ComfyUI settings in:\nFilters → AI → Settings"
                )
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            self._update_progress(progress_label, "🔍 Preparing image...")

            # Export current image as PNG
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name

            try:
                pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
                pdb_config = pdb_proc.create_config()
                pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                pdb_config.set_property("image", image)
                pdb_config.set_property("file", Gio.File.new_for_path(temp_filename))
                pdb_config.set_property("options", None)
                result = pdb_proc.run(pdb_config)
                if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                    raise Exception("Failed to export image for outpaint")

                with open(temp_filename, "rb") as f:
                    image_bytes = f.read()
            finally:
                os.unlink(temp_filename)

            self._update_progress(progress_label, "🚀 Starting AI outpaint...")

            # Call ComfyUI outpaint workflow
            api_success, api_message, api_response = self._ai_edit_threaded(
                [image_bytes],
                None,
                prompt,
                size="1024x1024",  # Size doesn't matter for outpaint
                progress_label=progress_label,
                action="outpaint",
                pad=pad,
                seed=seed,
            )

            if api_success and api_response:
                self._update_progress(progress_label, "✅ Loading outpainted image...")

                # Load the outpainted image as a new GIMP image (not a layer)
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
                        self._update_progress(progress_label, "✅ Outpaint Complete!")
                        Gimp.message("✅ Outpaint Complete! New image created.")
                        print("DEBUG: Outpaint successful - new image created")
                    else:
                        raise Exception("Failed to load outpainted image")
                finally:
                    os.unlink(temp_filename)

                return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
            else:
                if "cancelled" in api_message.lower():
                    self._update_progress(progress_label, "❌ Operation cancelled")
                    Gimp.message("❌ Operation cancelled by user")
                else:
                    self._update_progress(progress_label, f"❌ Outpaint failed: {api_message}")
                    Gimp.message(f"❌ Outpaint failed: {api_message}")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
                )

        except Exception as e:
            error_msg = f"Error during outpaint: {str(e)}"
            self._update_progress(progress_label, f"❌ Error: {str(e)}")
            print(f"ERROR: {error_msg}")
            Gimp.message(f"❌ {error_msg}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )
        finally:
            dialog.destroy()

