"""
Image generation mixin for GIMP AI Plugin.
"""

import gi
from gi.repository import Gimp, GLib


class GeneratorMixin:
    """Mixin class providing image generation functionality"""
    
    def run_layer_generator(
        self, procedure, run_mode, image, drawables, config, run_data
    ):
        print("DEBUG: Image Generator called!")

        # Show prompt dialog with API key checking (no mode selection for image generator)
        dialog_result = self._show_prompt_dialog(
            "Image Generator", "", show_mode_selection=False
        )
        if not dialog_result:
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Extract dialog, progress_label, prompt and mode from dialog result
        # (mask_strength is only used for inpaint)
        dialog, progress_label, prompt, _, _mask_strength, seed = dialog_result

        try:
            # Validate ComfyUI configuration
            if not self._provider_is_configured(action="generator"):
                self._update_progress(progress_label, "❌ ComfyUI is not configured!")
                Gimp.message("❌ ComfyUI is not configured!\n\nPlease configure ComfyUI settings in:\nFilters → AI → Settings")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
                )

            # Update dialog immediately when processing starts
            self._update_progress(progress_label, "🎨 Generating image with AI...")

            # Use threaded generation to keep UI responsive like other functions
            self._update_progress(progress_label, "🚀 Starting image generation...")

            success, message, image_data = self._ai_generate_threaded(
                prompt, size="auto", progress_label=progress_label, image=image, seed=seed
            )
            if success and image_data:
                # Create layer from the generated image data
                layer_success = self._add_layer_from_data(image, image_data)
                result = layer_success
            else:
                # Check if this was a cancellation vs actual failure
                if "cancelled" in message.lower():
                    self._update_progress(progress_label, "❌ Operation cancelled")
                    Gimp.message("❌ Operation cancelled by user")
                else:
                    self._update_progress(
                        progress_label, f"❌ Generation failed: {message}"
                    )
                    Gimp.message(f"❌ Generation failed: {message}")
                result = False
            if result:
                self._update_progress(
                    progress_label, "✅ Image generation complete!"
                )
                Gimp.message("✅ Image generation complete!")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.SUCCESS, GLib.Error()
                )
            else:
                return procedure.new_return_values(
                    Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
                )

        except Exception as e:
            error_msg = f"Error during image generation: {str(e)}"
            self._update_progress(progress_label, f"❌ Error: {str(e)}")
            print(f"ERROR: {error_msg}")
            Gimp.message(f"❌ {error_msg}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )
        finally:
            dialog.destroy()

