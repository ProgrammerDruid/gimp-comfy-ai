"""
Utility functions and mixin for GIMP AI Plugin.

Contains:
- Coordinate transformation functions (from coordinate_utils.py)
- General utility methods (UtilsMixin class)
"""

# ============================================================================
# Coordinate transformation functions (module-level, no GIMP dependencies)
# ============================================================================

def get_optimal_openai_shape(width, height):
    """
    Select optimal OpenAI shape based on image dimensions.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        tuple: (target_width, target_height) - one of (1024, 1024), (1536, 1024), (1024, 1536)
    """
    if width <= 0 or height <= 0:
        return (1024, 1024)  # Default to square for invalid dimensions
        
    aspect_ratio = width / height
    
    if aspect_ratio > 1.3:
        # Landscape orientation
        return (1536, 1024)
    elif aspect_ratio < 0.77:
        # Portrait orientation  
        return (1024, 1536)
    else:
        # Square or near-square
        return (1024, 1024)


def calculate_padding_for_shape(current_width, current_height, target_width, target_height):
    """
    Calculate padding needed to fit content into target OpenAI shape.
    
    Args:
        current_width: Current content width
        current_height: Current content height
        target_width: Target width (1024 or 1536)
        target_height: Target height (1024 or 1536)
        
    Returns:
        dict: {
            'scale_factor': Applied scaling factor,
            'scaled_size': (scaled_width, scaled_height),
            'padding': (left, top, right, bottom)
        }
    """
    # Calculate scale to fit within target
    scale_x = target_width / current_width
    scale_y = target_height / current_height
    scale = min(scale_x, scale_y)
    
    # Scale dimensions
    scaled_width = int(current_width * scale)
    scaled_height = int(current_height * scale)
    
    # Calculate padding to center
    pad_left = (target_width - scaled_width) // 2
    pad_top = (target_height - scaled_height) // 2
    pad_right = target_width - scaled_width - pad_left
    pad_bottom = target_height - scaled_height - pad_top
    
    return {
        'scale_factor': scale,
        'scaled_size': (scaled_width, scaled_height),
        'padding': (pad_left, pad_top, pad_right, pad_bottom)
    }


def extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2, 
                                  mode='focused', has_selection=True):
    """
    Extract context region around selection for inpainting with optimal shape.
    
    Args:
        img_width: Source image width
        img_height: Source image height
        sel_x1, sel_y1, sel_x2, sel_y2: Selection bounds
        mode: 'focused' for partial extraction, 'full' for whole image
        has_selection: Whether there's an active selection
        
    Returns:
        dict: Context extraction parameters with optimal shape
    """
    if not has_selection:
        # No selection - use center area
        target_shape = get_optimal_openai_shape(img_width, img_height)
        # Create a default selection in center
        size = min(img_width, img_height, 512)
        sel_x1 = (img_width - size) // 2
        sel_y1 = (img_height - size) // 2
        sel_x2 = sel_x1 + size
        sel_y2 = sel_y1 + size
        
    sel_width = sel_x2 - sel_x1
    sel_height = sel_y2 - sel_y1
    
    if mode == 'full':
        # Send entire image with mask
        target_shape = get_optimal_openai_shape(img_width, img_height)
        padding_info = calculate_padding_for_shape(img_width, img_height, 
                                                  target_shape[0], target_shape[1])
        return {
            'mode': 'full',
            'selection_bounds': (sel_x1, sel_y1, sel_x2, sel_y2),
            'extract_region': (0, 0, img_width, img_height),
            'target_shape': target_shape,
            'needs_padding': True,
            'padding_info': padding_info,
            'has_selection': has_selection
        }
    
    # Focused mode: extract region around selection
    # Calculate context padding (30-50% of selection, min 50px, max 300px)
    context_pad = max(50, min(300, int(max(sel_width, sel_height) * 0.4)))
    
    # Initial context bounds
    ctx_x1 = sel_x1 - context_pad
    ctx_y1 = sel_y1 - context_pad
    ctx_x2 = sel_x2 + context_pad
    ctx_y2 = sel_y2 + context_pad
    
    # Smart boundary handling: prefer not to extend beyond image
    if ctx_x1 < 0:
        shift = -ctx_x1
        ctx_x1 = 0
        ctx_x2 = min(img_width, ctx_x2 + shift)
    if ctx_y1 < 0:
        shift = -ctx_y1
        ctx_y1 = 0
        ctx_y2 = min(img_height, ctx_y2 + shift)
    if ctx_x2 > img_width:
        shift = ctx_x2 - img_width
        ctx_x2 = img_width
        ctx_x1 = max(0, ctx_x1 - shift)
    if ctx_y2 > img_height:
        shift = ctx_y2 - img_height
        ctx_y2 = img_height
        ctx_y1 = max(0, ctx_y1 - shift)
    
    ctx_width = ctx_x2 - ctx_x1
    ctx_height = ctx_y2 - ctx_y1
    
    # Determine optimal shape for context
    target_shape = get_optimal_openai_shape(ctx_width, ctx_height)
    target_aspect = target_shape[0] / target_shape[1]
    current_aspect = ctx_width / ctx_height if ctx_height > 0 else 1.0
    
    # Try to extend extract region to match target aspect ratio
    # This avoids padding when possible by using more of the available image
    if abs(current_aspect - target_aspect) > 0.01:  # Only if aspect ratios differ significantly
        if target_aspect > current_aspect:
            # Need wider region: extend horizontally if possible
            target_width = int(ctx_height * target_aspect)
            width_diff = target_width - ctx_width
            
            # Try to extend equally on both sides
            left_extend = width_diff // 2
            right_extend = width_diff - left_extend
            
            new_ctx_x1 = max(0, ctx_x1 - left_extend)
            new_ctx_x2 = min(img_width, ctx_x2 + right_extend)
            
            # If we hit boundaries, try to extend more on the available side
            if new_ctx_x1 == 0 and new_ctx_x2 < img_width:
                # Hit left boundary, extend right more
                remaining = target_width - (new_ctx_x2 - new_ctx_x1)
                new_ctx_x2 = min(img_width, new_ctx_x2 + remaining)
            elif new_ctx_x2 == img_width and new_ctx_x1 > 0:
                # Hit right boundary, extend left more  
                remaining = target_width - (new_ctx_x2 - new_ctx_x1)
                new_ctx_x1 = max(0, new_ctx_x1 - remaining)
                
            ctx_x1, ctx_x2 = new_ctx_x1, new_ctx_x2
            
        else:
            # Need taller region: extend vertically if possible
            target_height = int(ctx_width / target_aspect)
            height_diff = target_height - ctx_height
            
            # Try to extend equally on both sides
            top_extend = height_diff // 2
            bottom_extend = height_diff - top_extend
            
            new_ctx_y1 = max(0, ctx_y1 - top_extend)
            new_ctx_y2 = min(img_height, ctx_y2 + bottom_extend)
            
            # If we hit boundaries, try to extend more on the available side
            if new_ctx_y1 == 0 and new_ctx_y2 < img_height:
                # Hit top boundary, extend bottom more
                remaining = target_height - (new_ctx_y2 - new_ctx_y1)
                new_ctx_y2 = min(img_height, new_ctx_y2 + remaining)
            elif new_ctx_y2 == img_height and new_ctx_y1 > 0:
                # Hit bottom boundary, extend top more
                remaining = target_height - (new_ctx_y2 - new_ctx_y1)
                new_ctx_y1 = max(0, new_ctx_y1 - remaining)
                
            ctx_y1, ctx_y2 = new_ctx_y1, new_ctx_y2
    
    # Recalculate final dimensions
    ctx_width = ctx_x2 - ctx_x1
    ctx_height = ctx_y2 - ctx_y1
    
    padding_info = calculate_padding_for_shape(ctx_width, ctx_height,
                                              target_shape[0], target_shape[1])
    
    return {
        'mode': 'focused',
        'selection_bounds': (sel_x1, sel_y1, sel_x2, sel_y2),
        'extract_region': (ctx_x1, ctx_y1, ctx_width, ctx_height),
        'selection_in_extract': (
            sel_x1 - ctx_x1,
            sel_y1 - ctx_y1,
            sel_x2 - ctx_x1,
            sel_y2 - ctx_y1
        ),
        'target_shape': target_shape,
        'needs_padding': ctx_width != target_shape[0] or ctx_height != target_shape[1],
        'padding_info': padding_info,
        'has_selection': has_selection
    }


def calculate_result_placement(result_shape, original_shape, context_info):
    """
    Calculate placement for AI result back into original image.
    
    Args:
        result_shape: (width, height) of AI result
        original_shape: (width, height) of original image
        context_info: Context extraction info used for generation
        
    Returns:
        dict: Placement parameters
    """
    if context_info['mode'] == 'full':
        # Full image mode: scale entire result to original size
        scale_x = original_shape[0] / result_shape[0]
        scale_y = original_shape[1] / result_shape[1]
        
        return {
            'placement_mode': 'replace',
            'scale': (scale_x, scale_y),
            'position': (0, 0),
            'size': original_shape
        }
    else:
        # Focused mode: scale and position extract region
        extract_region = context_info['extract_region']
        target_shape = context_info['target_shape']
        
        # Calculate scale from result back to extract size
        scale_x = extract_region[2] / target_shape[0]
        scale_y = extract_region[3] / target_shape[1]
        
        return {
            'placement_mode': 'composite',
            'scale': (scale_x, scale_y),
            'position': (extract_region[0], extract_region[1]),
            'size': (extract_region[2], extract_region[3])
        }


def calculate_scale_from_shape(source_shape, target_shape):
    """
    Calculate scaling factors between two shapes.
    
    Args:
        source_shape: (width, height) tuple
        target_shape: (width, height) tuple
        
    Returns:
        dict: {
            'scale_x': Horizontal scale factor,
            'scale_y': Vertical scale factor,
            'uniform_scale': Min of scale_x and scale_y (preserves aspect ratio)
        }
    """
    scale_x = target_shape[0] / source_shape[0] if source_shape[0] > 0 else 1.0
    scale_y = target_shape[1] / source_shape[1] if source_shape[1] > 0 else 1.0
    
    return {
        'scale_x': scale_x,
        'scale_y': scale_y,
        'uniform_scale': min(scale_x, scale_y)
    }


def calculate_mask_coordinates(context_info, target_size):
    """
    Calculate mask coordinates for selection within extract region.

    Args:
        context_info: Context extraction info from extract_context_with_selection()
        target_size: Target size for the mask (e.g. 1024)

    Returns:
        dict with mask coordinates
    """
    if not context_info['has_selection']:
        # Create center circle mask for no selection case
        center = target_size // 2
        radius = target_size // 4
        return {
            'mask_type': 'circle',
            'center_x': center,
            'center_y': center,
            'radius': radius,
            'target_size': target_size
        }

    # Get extract region info
    sel_x1, sel_y1, sel_x2, sel_y2 = context_info['selection_bounds']
    ext_x1, ext_y1, ext_width, ext_height = context_info['extract_region']

    # Calculate selection position within the extract region
    sel_in_ext_x1 = sel_x1 - ext_x1
    sel_in_ext_y1 = sel_y1 - ext_y1
    sel_in_ext_x2 = sel_x2 - ext_x1
    sel_in_ext_y2 = sel_y2 - ext_y1

    # Scale to target size (use the larger dimension for scale factor)
    scale = target_size / max(ext_width, ext_height)
    mask_sel_x1 = int(sel_in_ext_x1 * scale)
    mask_sel_y1 = int(sel_in_ext_y1 * scale)
    mask_sel_x2 = int(sel_in_ext_x2 * scale)
    mask_sel_y2 = int(sel_in_ext_y2 * scale)

    # Ensure coordinates are within bounds
    mask_sel_x1 = max(0, min(target_size - 1, mask_sel_x1))
    mask_sel_y1 = max(0, min(target_size - 1, mask_sel_y1))
    mask_sel_x2 = max(0, min(target_size, mask_sel_x2))
    mask_sel_y2 = max(0, min(target_size, mask_sel_y2))

    return {
        'mask_type': 'rectangle',
        'x1': mask_sel_x1,
        'y1': mask_sel_y1,
        'x2': mask_sel_x2,
        'y2': mask_sel_y2,
        'target_size': target_size,
        'scale_factor': scale
    }


def calculate_placement_coordinates(context_info):
    """
    Calculate where to place the AI result back in the original image.
    
    Args:
        context_info: Context extraction info from extract_context_with_selection()
        
    Returns:
        dict with placement coordinates
    """
    ctx_x1, ctx_y1, ctx_width, ctx_height = context_info['extract_region']
    
    return {
        'paste_x': ctx_x1,
        'paste_y': ctx_y1, 
        'result_width': ctx_width,
        'result_height': ctx_height
    }


def validate_context_info(context_info):
    """
    Validate that context_info contains all required fields with valid values.
    
    Args:
        context_info: Context info dict to validate
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    required_fields = [
        'selection_bounds', 'extract_region', 'target_shape', 'has_selection'
    ]
    
    for field in required_fields:
        if field not in context_info:
            return False, f"Missing required field: {field}"
    
    # Validate selection bounds
    sel_bounds = context_info['selection_bounds']
    if len(sel_bounds) != 4:
        return False, "selection_bounds must have 4 values (x1, y1, x2, y2)"
    
    sel_x1, sel_y1, sel_x2, sel_y2 = sel_bounds
    if sel_x2 <= sel_x1 or sel_y2 <= sel_y1:
        return False, "Invalid selection bounds: x2 <= x1 or y2 <= y1"
    
    # Validate extract region
    extract_region = context_info['extract_region']
    if len(extract_region) != 4:
        return False, "extract_region must have 4 values (x1, y1, width, height)"
    
    ext_x1, ext_y1, ext_width, ext_height = extract_region
    if ext_width <= 0 or ext_height <= 0:
        return False, "Extract region dimensions must be positive"
    
    # Validate that extract region contains selection (for focused mode)
    if context_info.get('mode') == 'focused':
        ext_x2 = ext_x1 + ext_width
        ext_y2 = ext_y1 + ext_height
        
        if not (ext_x1 <= sel_x1 and ext_y1 <= sel_y1 and ext_x2 >= sel_x2 and ext_y2 >= sel_y2):
            return False, "Extract region must contain the selection"
    
    # Validate target shape
    target_shape = context_info['target_shape']
    if not isinstance(target_shape, tuple) or len(target_shape) != 2:
        return False, "target_shape must be a tuple of (width, height)"
    valid_shapes = [(1024, 1024), (1536, 1024), (1024, 1536)]
    if target_shape not in valid_shapes:
        return False, f"target_shape must be one of {valid_shapes}"
    
    return True, ""


# ============================================================================
# UtilsMixin class - General utility methods
# ============================================================================

from gi.repository import GLib, Gimp


class UtilsMixin:
    """Mixin class providing general utility methods for GIMP AI Plugin"""
    
    def _make_url_request(self, req_or_url, timeout=60, headers=None):
        """
        Make URL request with automatic SSL fallback for certificate errors.

        Args:
            req_or_url: Either a urllib.request.Request object or URL string
            timeout: Request timeout in seconds (default: 60)
            headers: Optional dict of headers to add (only if req_or_url is string)

        Returns:
            urllib.response object

        Raises:
            urllib.error.URLError: If both normal and SSL-bypassed requests fail
        """
        import urllib.request
        import urllib.error
        import ssl
        
        try:
            # First attempt with normal SSL verification
            if isinstance(req_or_url, str):
                # Create Request object from URL string
                req = urllib.request.Request(req_or_url)
                if headers:
                    for key, value in headers.items():
                        req.add_header(key, value)
            else:
                req = req_or_url

            return urllib.request.urlopen(req, timeout=timeout)

        except (ssl.SSLError, urllib.error.URLError) as ssl_err:
            # Check if it's an SSL-related error
            if "SSL" in str(ssl_err) or "CERTIFICATE" in str(ssl_err):
                print(
                    f"DEBUG: SSL verification failed, trying with SSL bypass: {ssl_err}"
                )
            else:
                # Not an SSL error, re-raise it
                raise ssl_err

            # Fallback to unverified SSL if certificate fails
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            try:
                return urllib.request.urlopen(req, context=ctx, timeout=timeout)
            except Exception as fallback_err:
                print(f"DEBUG: SSL bypass also failed: {fallback_err}")
                raise fallback_err

    def _add_to_prompt_history(self, prompt):
        """Add prompt to history, keeping last 10 unique prompts"""
        if not prompt.strip():
            return

        # Remove if already exists to avoid duplicates
        history = self.config.get("prompt_history", [])
        if prompt in history:
            history.remove(prompt)

        # Add to beginning
        history.insert(0, prompt)

        # Keep only last 10
        history = history[:10]

        self.config["prompt_history"] = history
        self.config["last_prompt"] = prompt
        self._save_config()

    def _get_prompt_history(self):
        """Get prompt history list"""
        return self.config.get("prompt_history", [])

    def _get_last_prompt(self):
        """Get the last used prompt"""
        return self.config.get("last_prompt", "")

    def _get_processing_mode(self, dialog_mode=None):
        """Determine processing mode based on dialog selection or fallback to config"""
        if dialog_mode:
            return dialog_mode

        # Fallback to last used mode from config
        return self.config.get("last_mode", "contextual")

    def _update_progress(self, progress_label, message, gimp_progress=None):
        """Update progress message in dialog with proper emoji encoding, optionally update GIMP progress bar"""
        if progress_label:
            try:
                # Ensure the message is properly encoded for GTK
                # GTK should handle UTF-8 properly, but let's be explicit
                if isinstance(message, str):
                    encoded_message = message.encode("utf-8").decode("utf-8")
                else:
                    encoded_message = str(message)

                # Use GLib.idle_add to ensure the update happens on the main thread
                def update_ui():
                    try:
                        print(
                            f"DEBUG: Actually updating progress label to: {encoded_message}"
                        )
                        progress_label.set_text(encoded_message)
                        progress_label.set_use_markup(
                            False
                        )  # Use plain text, not markup
                        print(
                            f"DEBUG: Progress label text is now: {progress_label.get_text()}"
                        )
                        return False  # Remove from idle queue after running once
                    except Exception as e:
                        print(f"DEBUG: UI update failed: {e}")
                        return False

                # Queue the update on the main thread
                GLib.idle_add(update_ui)

            except Exception as e:
                print(f"DEBUG: Progress update failed: {e}")
                # Fallback without emojis if there's encoding issue
                fallback = (
                    message.encode("ascii", "ignore").decode("ascii")
                    if message
                    else "Processing..."
                )
                try:
                    progress_label.set_text(fallback)
                except:
                    pass

        # Update GIMP progress bar if fraction provided
        if gimp_progress is not None:
            try:
                Gimp.progress_set_text(message)
                Gimp.progress_update(gimp_progress)
                Gimp.displays_flush()
            except:
                pass  # Ignore if not in right context

        return False  # Return False for GLib.idle_add compatibility

    def _check_cancel_and_process_events(self):
        """Check if cancel was requested and process pending GTK events"""
        if self._cancel_requested:
            return True

        # Process pending GTK events to keep UI responsive
        while GLib.MainContext.default().iteration(False):
            pass

        return False

    def _is_debug_mode(self):
        """Check if debug mode is enabled (saves temp files to system temp directory)"""
        import os
        # Check config first
        debug = self.config.get("debug_mode", False)
        # Allow environment variable override
        if os.environ.get("GIMP_AI_DEBUG") == "1":
            return True
        return debug

    def _run_threaded_operation(self, operation_func, operation_name, progress_label=None, max_wait_time=300):
        """
        Run an operation in a background thread and wait for completion.
        
        Args:
            operation_func: Function to run in thread (should return dict with 'success', 'message', 'data')
            operation_name: Name of operation for logging
            progress_label: Optional Gtk.Label for progress updates
            max_wait_time: Maximum wait time in seconds
            
        Returns:
            tuple: (success: bool, message: str, data: any)
        """
        import threading
        import time
        
        result = {"success": False, "message": "Not started", "data": None, "completed": False}

        def operation_thread():
            try:
                op_result = operation_func()
                result.update(op_result)
            except Exception as e:
                print(f"ERROR: [THREAD] {operation_name} failed: {e}")
                result["success"] = False
                result["message"] = str(e)
            finally:
                result["completed"] = True

        # Start thread
        thread = threading.Thread(target=operation_thread)
        thread.daemon = True
        thread.start()

        # Keep UI responsive while waiting
        start_time = time.time()
        last_update_time = start_time

        while not result["completed"]:
            current_time = time.time()
            elapsed = current_time - start_time

            # Check timeout
            if elapsed > max_wait_time:
                print(f"ERROR: {operation_name} timed out after {max_wait_time} seconds")
                result["success"] = False
                result["message"] = f"{operation_name} timed out after {max_wait_time} seconds"
                break

            # Update progress every 10 seconds
            if progress_label and current_time - last_update_time > 10:
                minutes = int(elapsed // 60)
                if minutes > 0:
                    self._update_progress(
                        progress_label, f"⏳ Still processing... ({minutes}m elapsed)"
                    )
                else:
                    self._update_progress(progress_label, f"⏳ Processing {operation_name}...")
                last_update_time = current_time

            # Check for cancellation
            if self._check_cancel_and_process_events():
                print(f"DEBUG: {operation_name} cancelled by user")
                if progress_label:
                    self._update_progress(
                        progress_label, f"❌ {operation_name} cancelled by user"
                    )
                result["success"] = False
                result["message"] = f"{operation_name} cancelled by user"
                break

            # Small sleep to avoid busy-waiting
            time.sleep(0.1)

        # Wait for thread to finish
        thread.join(timeout=5)

        return result["success"], result["message"], result.get("data")

