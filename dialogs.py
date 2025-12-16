"""
Dialog UI mixin for GIMP AI Plugin.
"""

import gi
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import GimpUi, Gtk, Gdk, GLib


class DialogsMixin:
    """Mixin class providing UI dialog methods"""
    
    def _init_gimp_ui(self):
        """Initialize GIMP UI system if not already done"""
        if not hasattr(self, "_ui_initialized"):
            GimpUi.init("gimp-comfy-ai")
            self._ui_initialized = True

    def _create_dialog_base(self, title="Dialog", size=(500, 400)):
        """Create a standard GIMP dialog with consistent styling"""
        self._init_gimp_ui()

        # Create dialog with header bar detection
        use_header_bar = Gtk.Settings.get_default().get_property(
            "gtk-dialogs-use-header"
        )
        dialog = GimpUi.Dialog(use_header_bar=use_header_bar, title=title)

        # Set up dialog properties
        dialog.set_default_size(size[0], size[1])
        dialog.set_resizable(True)

        return dialog

    def _setup_dialog_content_area(self, dialog, spacing=15, margin=20):
        """Set up dialog content area with consistent styling"""
        content_area = dialog.get_content_area()
        content_area.set_spacing(spacing)
        content_area.set_margin_start(margin)
        content_area.set_margin_end(margin)
        content_area.set_margin_top(margin)
        content_area.set_margin_bottom(margin)
        return content_area

    def _add_api_warning_bar(self, content_area, dialog, action=None):
        """
        Add provider configuration warning info bar if needed.
        Returns (warning_bar, ok_button_needs_config).
        """
        if self._provider_is_configured(action=action):
            return None, False

        # Create warning info bar
        api_warning_bar = Gtk.InfoBar()
        api_warning_bar.set_message_type(Gtk.MessageType.WARNING)
        api_warning_bar.set_show_close_button(False)

        # Warning message
        warning_label = Gtk.Label()
        warning_label.set_markup("⚠️ ComfyUI is not configured")
        warning_label.set_halign(Gtk.Align.START)

        # Configure button - connect to main dialog response
        configure_button = api_warning_bar.add_button(
            "Configure Now", Gtk.ResponseType.APPLY
        )

        # Connect the InfoBar response to the main dialog
        def on_configure_clicked(infobar, response_id):
            if response_id == Gtk.ResponseType.APPLY:
                dialog.response(Gtk.ResponseType.APPLY)

        api_warning_bar.connect("response", on_configure_clicked)

        # Add label to info bar content area
        info_content = api_warning_bar.get_content_area()
        info_content.pack_start(warning_label, False, False, 0)

        content_area.pack_start(api_warning_bar, False, False, 5)

        return api_warning_bar, True

    def _create_progress_widget(self):
        """Create progress label widget for dialogs"""
        progress_frame = Gtk.Frame()
        progress_frame.set_label("Status")
        progress_frame.set_margin_top(10)

        progress_label = Gtk.Label()
        progress_label.set_text("Ready to start...")
        progress_label.set_halign(Gtk.Align.START)
        progress_label.set_margin_start(10)
        progress_label.set_margin_end(10)
        progress_label.set_margin_top(5)
        progress_label.set_margin_bottom(10)

        progress_frame.add(progress_label)

        return progress_frame, progress_label

    def _create_progress_callback(self, progress_label):
        """Create a reusable progress callback for threading"""

        def progress_callback(message):
            def update_ui():
                self._update_progress(progress_label, message)
                return False

            GLib.idle_add(update_ui)

        return progress_callback

    def _show_prompt_dialog(
        self, title="AI Prompt", default_text="", show_mode_selection=True, image=None
    ):
        """Show a GIMP UI dialog to get user input for AI prompt"""
        # Use last prompt as default if available, otherwise use provided default
        if not default_text:
            default_text = self._get_last_prompt()
        if not default_text:
            if title == "AI Inpaint":
                default_text = "Describe the area to inpaint (e.g. 'remove object', 'fix background')"
            else:
                default_text = "Describe what you want to generate..."
        try:
            # Create dialog using helper methods
            dialog = self._create_dialog_base(title, (600, 300))

            # Add buttons using GIMP's standard approach
            dialog.add_button(
                "Settings", Gtk.ResponseType.HELP
            )  # Use HELP for Settings
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            ok_button = dialog.add_button("OK", Gtk.ResponseType.OK)
            ok_button.set_can_default(True)
            ok_button.grab_default()

            # Set up content area using helper
            content_area = self._setup_dialog_content_area(dialog, spacing=10)

            # Label - will automatically use theme colors
            label = Gtk.Label(label="Enter your AI prompt:")
            label.set_halign(Gtk.Align.START)
            content_area.pack_start(label, False, False, 0)

            # Add API warning bar using helper
            action = "inpaint" if title == "AI Inpaint" else "generator"
            api_warning_bar, needs_config = self._add_api_warning_bar(
                content_area, dialog, action=action
            )
            if needs_config:
                # Disable OK button when no API key
                ok_button.set_sensitive(False)
                ok_button.set_label("Configure & Continue")

            # Prompt history dropdown
            history = self._get_prompt_history()
            history_combo = None
            if history:
                history_label = Gtk.Label(label="Recent prompts:")
                history_label.set_halign(Gtk.Align.START)
                content_area.pack_start(history_label, False, False, 0)

                history_combo = Gtk.ComboBoxText()
                history_combo.append_text("Select from recent prompts...")
                for prompt in history:
                    # Truncate long prompts for display
                    display_prompt = prompt[:60] + "..." if len(prompt) > 60 else prompt
                    history_combo.append_text(display_prompt)
                history_combo.set_active(0)
                content_area.pack_start(history_combo, False, False, 0)

            # Multiline text view for prompts
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
            )
            scrolled_window.set_size_request(560, 150)

            text_view = Gtk.TextView()
            text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            text_view.set_border_width(8)

            # Set default text
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(default_text)

            scrolled_window.add(text_view)
            content_area.pack_start(scrolled_window, True, True, 0)

            # Add mode selection (only for inpainting)
            focused_radio = None
            full_radio = None
            mask_strength_scale = None
            if show_mode_selection:
                mode_frame = Gtk.Frame(label="Processing Mode:")
                mode_frame.set_margin_top(10)
                content_area.pack_start(mode_frame, False, False, 0)

                mode_box = Gtk.VBox()
                mode_box.set_margin_start(10)
                mode_box.set_margin_end(10)
                mode_box.set_margin_top(5)
                mode_box.set_margin_bottom(10)
                mode_frame.add(mode_box)

                # Get last used mode from config
                config = self._load_config()
                last_mode = config.get("last_mode", "contextual")

                # Radio buttons for mode selection
                focused_radio = Gtk.RadioButton.new_with_label(
                    None,
                    "Focused (High Detail) - Best for small edits, maximum resolution",
                )
                focused_radio.set_name("contextual")
                mode_box.pack_start(focused_radio, False, False, 2)

                full_radio = Gtk.RadioButton.new_with_label_from_widget(
                    focused_radio,
                    "Full Image (Consistent) - Best for large changes, visual consistency",
                )
                full_radio.set_name("full_image")
                mode_box.pack_start(full_radio, False, False, 2)

                # Set active radio based on last used mode
                if last_mode == "full_image":
                    full_radio.set_active(True)
                else:
                    focused_radio.set_active(True)

                # ComfyUI-only: Mask strength slider (controls how strongly we punch out alpha)
                strength_frame = Gtk.Frame(label="ComfyUI Mask Strength")
                strength_frame.set_margin_top(10)
                content_area.pack_start(strength_frame, False, False, 0)

                strength_box = Gtk.VBox(spacing=6)
                strength_box.set_margin_start(10)
                strength_box.set_margin_end(10)
                strength_box.set_margin_top(5)
                strength_box.set_margin_bottom(10)
                strength_frame.add(strength_box)

                strength_label = Gtk.Label(
                    label="Lower values reduce hard-edge artifacts; higher values enforce the mask more strongly."
                )
                strength_label.set_halign(Gtk.Align.START)
                strength_label.get_style_context().add_class("dim-label")
                strength_box.pack_start(strength_label, False, False, 0)

                default_strength = int(self.config.get("comfyui_inpaint_mask_strength", 99) or 99)
                adj = Gtk.Adjustment(
                    value=float(default_strength),
                    lower=0.0,
                    upper=100.0,
                    step_increment=1.0,
                    page_increment=5.0,
                    page_size=0.0,
                )
                mask_strength_scale = Gtk.Scale(
                    orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj
                )
                mask_strength_scale.set_digits(0)
                mask_strength_scale.set_value_pos(Gtk.PositionType.RIGHT)
                mask_strength_scale.set_hexpand(True)
                mask_strength_scale.set_tooltip_text("Mask strength percent (0–100). Default 99.")
                strength_box.pack_start(mask_strength_scale, False, False, 0)

            # Seed input (for all dialogs)
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

            # Connect Enter to activate OK button, Shift+Enter for new line
            def on_key_press(widget, event):
                if event.keyval == Gdk.KEY_Return:
                    # Shift+Enter: Allow new line (default behavior)
                    if event.state & Gdk.ModifierType.SHIFT_MASK:
                        return False  # Let default behavior handle it
                    # Plain Enter or Ctrl+Enter: Submit dialog
                    else:
                        dialog.response(Gtk.ResponseType.OK)
                        return True
                return False

            text_view.connect("key-press-event", on_key_press)

            # Connect history selection to populate text view
            if history_combo:

                def on_history_changed(combo):
                    active = combo.get_active()
                    if active > 0:  # Skip the placeholder item
                        selected_prompt = history[
                            active - 1
                        ]  # -1 because of placeholder
                        text_buffer.set_text(selected_prompt)
                        text_view.grab_focus()
                        text_buffer.select_range(
                            text_buffer.get_start_iter(), text_buffer.get_end_iter()
                        )

                history_combo.connect("changed", on_history_changed)

            # Add progress widget
            progress_frame, progress_label = self._create_progress_widget()
            content_area.pack_start(progress_frame, False, False, 0)

            # Show all widgets
            content_area.show_all()

            # Focus the text view and select all text for easy editing
            text_view.grab_focus()
            text_buffer.select_range(
                text_buffer.get_start_iter(), text_buffer.get_end_iter()
            )

            # Run dialog in loop to handle Settings button
            print("DEBUG: About to call dialog.run()...")
            while True:
                response = dialog.run()
                print(f"DEBUG: Dialog response: {response}")

                if response == Gtk.ResponseType.OK:
                    # First check if provider is configured (for "Configure & Continue" button)
                    if not self._provider_is_configured(action=action):
                        print("DEBUG: OK clicked but provider not configured, opening settings")
                        self._show_settings_dialog(dialog)

                        # Re-check after settings dialog
                        if self._provider_is_configured(action=action):
                            # Provider now configured - update UI
                            if api_warning_bar:
                                api_warning_bar.hide()
                            ok_button.set_sensitive(True)
                            ok_button.set_label("OK")
                            print("DEBUG: Provider configured, enabled OK button")
                        else:
                            print("DEBUG: Provider still not configured")
                            continue  # Keep dialog open

                    # Now validate the prompt
                    start_iter = text_buffer.get_start_iter()
                    end_iter = text_buffer.get_end_iter()
                    prompt = text_buffer.get_text(start_iter, end_iter, False).strip()

                    # Check if user entered actual content (not just placeholder)
                    placeholder_texts = [
                        "Describe what you want to generate...",
                        "Describe the area to inpaint (e.g. 'remove object', 'fix background')",
                    ]

                    is_placeholder = prompt in placeholder_texts or not prompt.strip()

                    if is_placeholder:
                        # Show error message and keep dialog open
                        error_dialog = Gtk.MessageDialog(
                            parent=dialog,
                            flags=Gtk.DialogFlags.MODAL,
                            message_type=Gtk.MessageType.WARNING,
                            buttons=Gtk.ButtonsType.OK,
                            text="Please enter a prompt description",
                        )
                        error_dialog.format_secondary_text(
                            "You need to describe what you want to generate or change before proceeding."
                        )
                        error_dialog.run()
                        error_dialog.destroy()
                        continue  # Keep the main dialog open

                    # Get selected mode
                    selected_mode = "contextual"  # default
                    if show_mode_selection and full_radio and full_radio.get_active():
                        selected_mode = "full_image"
                    elif (
                        show_mode_selection
                        and focused_radio
                        and focused_radio.get_active()
                    ):
                        selected_mode = "contextual"
                    # If no mode selection UI, use default "contextual" (for image generator)

                    print(
                        f"DEBUG: Got prompt text: '{prompt}', mode: '{selected_mode}', disabling OK button..."
                    )
                    # Disable OK button to prevent multiple clicks
                    ok_button.set_sensitive(False)
                    ok_button.set_label("Processing...")

                    # Update progress
                    self._update_progress(progress_label, "Validating configuration...")

                    if prompt:
                        self._add_to_prompt_history(prompt)
                        # Save the selected mode to config
                        self.config["last_mode"] = selected_mode
                        self._save_config()

                    # Reset cancel flag for new operation
                    self._cancel_requested = False

                    # Add cancel handler to keep dialog responsive during processing
                    def on_dialog_response(dialog, response_id):
                        if response_id == Gtk.ResponseType.CANCEL:
                            print("DEBUG: Cancel button clicked during processing")
                            self._cancel_requested = True
                            return True  # Keep dialog open
                        return False

                    dialog.connect("response", on_dialog_response)

                    # Get seed value (if provided)
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
                            continue  # Keep dialog open

                    # Return dialog, progress_label, and prompt data for processing
                    mask_strength = None
                    if mask_strength_scale is not None:
                        try:
                            mask_strength = int(mask_strength_scale.get_value())
                            self.config["comfyui_inpaint_mask_strength"] = mask_strength
                            self._save_config()
                        except Exception:
                            mask_strength = None

                    return (dialog, progress_label, prompt, selected_mode, mask_strength, seed_value) if prompt else None
                elif response == Gtk.ResponseType.APPLY:  # Configure Now button
                    print("DEBUG: Configure Now button clicked")
                    self._show_settings_dialog(dialog)

                    # Re-check after settings dialog
                    if self._provider_is_configured(action=action):
                        # Provider now configured - update UI
                        if api_warning_bar:
                            api_warning_bar.hide()
                        ok_button.set_sensitive(True)
                        ok_button.set_label("OK")
                        print("DEBUG: Provider configured, enabled OK button")
                    else:
                        print("DEBUG: Provider still not configured")
                    # Continue loop to keep main dialog open
                elif response == Gtk.ResponseType.HELP:  # Settings button
                    print("DEBUG: Settings button clicked")
                    self._show_settings_dialog(dialog)
                    # Continue loop to keep main dialog open
                else:
                    print("DEBUG: Dialog cancelled, destroying...")
                    dialog.destroy()
                    return None

        except Exception as e:
            print(f"DEBUG: Dialog error: {e}")
            # Fallback to default prompt if dialog fails
            return default_text if default_text else "fill this area naturally"

