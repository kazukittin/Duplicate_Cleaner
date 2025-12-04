import json
import os

class Settings:
    """Manage application settings"""
    
    DEFAULT_SETTINGS = {
        'thumbnail_size': 120,
        'window_geometry': None,
        'splitter_sizes': None,
    }
    
    def __init__(self, settings_file=None):
        if settings_file is None:
            # Store settings in user's home directory
            home = os.path.expanduser("~")
            self.settings_file = os.path.join(home, '.duplicate_cleaner_settings.json')
        else:
            self.settings_file = settings_file
        
        self.settings = self.DEFAULT_SETTINGS.copy()
        self.load()
    
    def load(self):
        """Load settings from file"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                print(f"Failed to load settings: {e}")
    
    def save(self):
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")
    
    def get(self, key, default=None):
        """Get a setting value"""
        return self.settings.get(key, default)
    
    def set(self, key, value):
        """Set a setting value"""
        self.settings[key] = value
        self.save()
