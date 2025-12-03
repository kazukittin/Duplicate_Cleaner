import pickle
import os
from typing import Dict, Any

class Cache:
    def __init__(self, cache_file: str = ".image_cache.pkl"):
        self.cache_file = cache_file
        self.data = {}
        
    def load(self, folder: str):
        """Load cache from folder."""
        cache_path = os.path.join(folder, self.cache_file)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    self.data = pickle.load(f)
                print(f"Loaded cache with {len(self.data)} entries")
            except Exception as e:
                print(f"Failed to load cache: {e}")
                self.data = {}
        else:
            self.data = {}
            
    def save(self, folder: str):
        """Save cache to folder."""
        cache_path = os.path.join(folder, self.cache_file)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(self.data, f)
            print(f"Saved cache with {len(self.data)} entries")
        except Exception as e:
            print(f"Failed to save cache: {e}")
            
    def get(self, file_path: str, mtime: float) -> Dict[str, Any]:
        """Get cached data if file hasn't changed."""
        if file_path in self.data:
            cached = self.data[file_path]
            if cached.get('mtime') == mtime:
                return cached
        return None
        
    def set(self, file_path: str, mtime: float, hash_value, blur_score: float):
        """Set cache entry."""
        self.data[file_path] = {
            'mtime': mtime,
            'hash': hash_value,
            'blur_score': blur_score
        }
