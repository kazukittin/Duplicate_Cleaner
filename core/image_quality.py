"""Image quality scoring for AI-based selection"""
import os
from PIL import Image
import numpy as np

class ImageQuality:
    """Calculate image quality scores"""
    
    @staticmethod
    def calculate_quality_score(image_path, blur_score=None):
        """
        Calculate overall quality score for an image
        
        Returns a score from 0-100, higher is better
        """
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 1. Resolution score (0-30 points)
                resolution = img.width * img.height
                resolution_score = min(30, (resolution / 1000000) * 10)  # 3MP = 30 points
                
                # 2. Blur score (0-30 points)
                if blur_score is not None:
                    blur_quality = min(30, blur_score / 100 * 30)
                else:
                    blur_quality = 15  # Default if unknown
                
                # 3. Brightness/Contrast score (0-20 points)
                img_array = np.array(img)
                brightness = np.mean(img_array)
                # Optimal brightness is around 128
                brightness_score = 20 - abs(128 - brightness) / 128 * 20
                brightness_score = max(0, brightness_score)
                
                # 4. File size score (0-20 points)
                # Larger files often indicate better quality
                file_size = os.path.getsize(image_path)
                size_mb = file_size / (1024 * 1024)
                size_score = min(20, size_mb * 2)  # 10MB = 20 points
                
                # Total score
                total_score = resolution_score + blur_quality + brightness_score + size_score
                
                return min(100, total_score)
                
        except Exception as e:
            print(f"Error calculating quality for {image_path}: {e}")
            return 0
    
    @staticmethod
    def get_best_image_in_group(group, blur_scores=None):
        """
        Find the best quality image in a group
        
        Returns: (best_path, score)
        """
        best_path = None
        best_score = -1
        
        for path in group:
            blur_score = blur_scores.get(path) if blur_scores else None
            score = ImageQuality.calculate_quality_score(path, blur_score)
            
            if score > best_score:
                best_score = score
                best_path = path
        
        return best_path, best_score
