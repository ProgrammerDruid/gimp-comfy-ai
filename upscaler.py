"""
Upscaler mixin for GIMP Comfy AI Plugin.

Runs a ComfyUI workflow that upscales the current image using RealESRGAN 4x
and opens the result as a NEW GIMP image.
"""

import os
import tempfile
import gi
from gi.repository import Gimp, Gtk, GLib, Gio


class UpscalerMixin:
    """Mixin class providing upscaling functionality"""

    def _show_upscaler_dialog(self):
        """Show dialog for the Upscaler tool (no prompt required)."""
        try:
            dialog = self._create_dialog_base("AI Upscaler (RealESRGAN 4x)", (560, 260))

            dialog.add_button("Settings", Gtk.ResponseType.HELP)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            ok_button = dialog.add_button("Upscale 4x", Gtk.ResponseType.OK)
            ok_button.set_can_default(True)
            ok_button.grab_default()

            content_area = self._setup_dialog_content_area(dialog, spacing=10)

            title_label = Gtk.Label()
            title_label.set_markup("<b>AI Upscaler (RealESRGAN 4x)</b>")
            title_label.set_halign(Gtk.Align.START)
            content_area.pack_start(title_label, False, False, 0)

            info_label = Gtk.Label()
            info_label.set_text(
                "Upscales the current image using your configured ComfyUI workflow.\n"
                "The result will open in a new GIMP image."
            )
            info_label.set_halign(Gtk.Align.START)
            info_label.set_line_wrap(True)
            content_area.pack_start(info_label, False, False, 0)

            api_warning_bar, needs_config = self._add_api_warning_bar(
                content_area, dialog, action="upscaler_4x"
            )
            if needs_config:
                ok_button.set_sensitive(False)
                ok_button.set_label("Configure & Continue")

            progress_frame, progress_label = self._create_progress_widget()
            content_area.pack_start(progress_frame, False, False, 0)

            content_area.show_all()

            while True:
                response = dialog.run()
                if response == Gtk.ResponseType.OK:
                    if not self._provider_is_configured(action="upscaler_4x"):
                        self._show_settings_dialog(dialog)
                        if self._provider_is_configured(action="upscaler_4x"):
                            if api_warning_bar:
                                api_warning_bar.hide()
                            ok_button.set_sensitive(True)
                            ok_button.set_label("Upscale 4x")
                        continue

                    ok_button.set_sensitive(False)
                    ok_button.set_label("Processing...")
                    self._cancel_requested = False
                    return (dialog, progress_label)

                if response == Gtk.ResponseType.APPLY:
                    self._show_settings_dialog(dialog)
                    if self._provider_is_configured(action="upscaler_4x"):
                        if api_warning_bar:
                            api_warning_bar.hide()
                        ok_button.set_sensitive(True)
                        ok_button.set_label("Upscale 4x")
                    continue

                if response == Gtk.ResponseType.HELP:
                    self._show_settings_dialog(dialog)
                    continue

                dialog.destroy()
                return None

        except Exception as e:
            print(f"DEBUG: Upscaler dialog error: {e}")
            return None

    def run_upscaler_4x(self, procedure, run_mode, image, drawables, config, run_data):
        """Upscale current image 4x using ComfyUI workflow and open result as new image."""
        print("DEBUG: Upscaler 4x called!")

        dialog_result = self._show_upscaler_dialog()
        if not dialog_result:
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        dialog, progress_label = dialog_result

        try:
            if not self._provider_is_configured(action="upscaler_4x"):
                self._update_progress(progress_label, "❌ ComfyUI is not configured!")
                Gimp.message(
                    "❌ ComfyUI is not configured!\n\nPlease configure ComfyUI settings in:\nFilters → AI → Settings"
                )
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

            self._update_progress(progress_label, "🔍 Preparing image...")

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
                    raise Exception("Failed to export image for upscaling")

                with open(temp_filename, "rb") as f:
                    image_bytes = f.read()
            finally:
                try:
                    os.unlink(temp_filename)
                except Exception:
                    pass

            self._update_progress(progress_label, "🚀 Starting upscaler workflow...")

            api_success, api_message, api_response = self._ai_edit_threaded(
                image_bytes,
                None,
                "",  # No prompt needed for upscaler
                size="auto",
                progress_label=progress_label,
                action="upscaler_4x",
                seed=None,
            )

            if api_success and api_response:
                self._update_progress(progress_label, "✅ Opening upscaled image...")

                new_image = self._create_image_from_data(api_response)
                if not new_image:
                    raise Exception("Failed to load upscaled image into GIMP")

                Gimp.Display.new(new_image)
                self._update_progress(progress_label, "✅ Upscale Complete!")
                Gimp.message("✅ Upscale Complete! New image created.")
                return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

            if "cancelled" in (api_message or "").lower():
                self._update_progress(progress_label, "❌ Operation cancelled")
                Gimp.message("❌ Operation cancelled by user")
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

            self._update_progress(progress_label, f"❌ Upscale failed: {api_message}")
            Gimp.message(f"❌ Upscale failed: {api_message}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )

        except Exception as e:
            error_msg = f"Error during upscaling: {str(e)}"
            self._update_progress(progress_label, f"❌ Error: {str(e)}")
            print(f"ERROR: {error_msg}")
            Gimp.message(f"❌ {error_msg}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )
        finally:
            try:
                dialog.destroy()
            except Exception:
                pass


