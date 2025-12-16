"""
Configuration management mixin for GIMP AI Plugin.
"""

import os
import json
import gi
from gi.repository import Gimp


class ConfigMixin:
    """Mixin class providing configuration management methods"""

    # Used for on-disk folder names under GIMP directories.
    # Keep this stable to avoid breaking existing installs/config.
    PLUGIN_DIRNAME = "gimp-comfy-ai"
    
    def _load_config(self):
        """Load configuration from various locations"""
        # Use GIMP API for primary config location
        try:
            plugin_dir = Gimp.PlugIn.directory()
            gimp_config_path = os.path.join(plugin_dir, self.PLUGIN_DIRNAME, "config.json")
        except:
            gimp_config_path = None

        config_paths = []

        # Try GIMP preferences directory first (where we want to save)
        try:
            gimp_user_dir = Gimp.directory()
            gimp_prefs_path = os.path.join(
                gimp_user_dir, self.PLUGIN_DIRNAME, "config.json"
            )
            config_paths.append(gimp_prefs_path)

            # Backward-compat: older installs may have used this folder name.
            config_paths.append(
                os.path.join(gimp_user_dir, "gimp-ai-plugin", "config.json")
            )
        except:
            pass

        # Then try user config directory (migration path)
        config_paths.append(os.path.expanduser("~/.config/gimp-ai/config.json"))

        # Then try GIMP plugin directory
        if gimp_config_path:
            config_paths.append(gimp_config_path)

        # Fallback paths for backward compatibility
        config_paths.extend(
            [
                os.path.expanduser("~/.gimp-ai-config.json"),
                os.path.expanduser("~/gimp-ai-config.json"),
            ]
        )

        # Try to load from first existing path
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        print(f"DEBUG: Loaded config from {config_path}")
                        return config
                except Exception as e:
                    print(f"DEBUG: Failed to load config from {config_path}: {e}")
                    continue

        # No config found, return empty dict
        print("DEBUG: No existing config found, using defaults")
        return {}

    def _ensure_config_defaults(self):
        """Ensure config has required default values"""
        if "comfyui" not in self.config:
            self.config["comfyui"] = {}
        if "workflows" not in self.config:
            self.config["workflows"] = {}
        if "settings" not in self.config:
            self.config["settings"] = {}

    def _get_comfyui_config(self):
        """Get ComfyUI configuration section"""
        return self.config.get("comfyui", {})

    def _provider_is_configured(self, action=None):
        """
        Check if ComfyUI is configured for the given action.
        
        Args:
            action: Optional action name to check specific workflow configuration
            
        Returns:
            bool: True if configured, False otherwise
        """
        comfy = self._get_comfyui_config()
        server_url = (comfy.get("server_url") or "").strip()
        input_dir = (comfy.get("input_dir") or "").strip()
        output_dir = (comfy.get("output_dir") or "").strip()

        if not (server_url and input_dir and output_dir):
            return False

        # If action specified, also check workflow path
        if action:
            workflows = self.config.get("workflows", {})
            wf_entry = workflows.get(action, {}) or {}
            wf_path = (wf_entry.get("path") or "").strip() if isinstance(wf_entry, dict) else ""
            if not wf_path:
                return False

        return True

    def _save_config(self):
        """Save configuration to GIMP preferences directory"""
        try:
            gimp_user_dir = Gimp.directory()
            config_dir = os.path.join(gimp_user_dir, self.PLUGIN_DIRNAME)
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, "config.json")

            with open(config_path, "w") as f:
                json.dump(self.config, f, indent=2)
            print(f"DEBUG: Saved config to {config_path}")
        except Exception as e:
            print(f"ERROR: Failed to save config: {e}")

