import os
from PIL import Image
from typing import List, Dict, Any
from .blur_detector import BlurDetector

class RuleEngine:
    @staticmethod
    def apply_rules(group: List[str], preferences: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Determines which images to keep and which to delete in a group.
        
        Args:
            group: List of image paths in the group.
            preferences: Dict of preferences (e.g., 'prefer_resolution', 'prefer_size').
            
        Returns:
            Dict mapping path -> 'keep' or 'delete'.
        """
        if not group:
            return {}
            
        if len(group) == 1:
            return {group[0]: 'keep'}
            
        # Gather metadata
        metadata = []
        for path in group:
            try:
                size = os.path.getsize(path)
                with Image.open(path) as img:
                    width, height = img.size
                    resolution = width * height
                
                # Calculate blur score if needed (or pass it in if already calculated)
                # For now, we calculate it here, but ideally it should be cached.
                blur_score = BlurDetector.calculate_blur_score(path)
                
                metadata.append({
                    'path': path,
                    'size': size,
                    'resolution': resolution,
                    'blur_score': blur_score
                })
            except Exception as e:
                print(f"Error reading metadata for {path}: {e}")
                # Default to keeping if we can't read it
                metadata.append({
                    'path': path,
                    'size': 0,
                    'resolution': 0,
                    'blur_score': 0
                })
        
        # Sort based on criteria
        # Default: High resolution > Large size > High sharpness
        
        def sort_key(item):
            return (
                item['resolution'],
                item['size'],
                item['blur_score']
            )
            
        sorted_items = sorted(metadata, key=sort_key, reverse=True)
        
        # Keep the best one
        best = sorted_items[0]
        
        result = {}
        for item in metadata:
            if item['path'] == best['path']:
                result[item['path']] = 'keep'
            else:
                result[item['path']] = 'delete'
                
        return result
