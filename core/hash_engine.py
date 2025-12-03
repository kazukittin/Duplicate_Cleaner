import imagehash
from PIL import Image
import os

class HashEngine:
    @staticmethod
    def compute_hash(image_path: str, method: str = 'phash') -> imagehash.ImageHash:
        """
        Computes the perceptual hash of an image.
        """
        try:
            img = Image.open(image_path)
            if method == 'phash':
                return imagehash.phash(img)
            elif method == 'ahash':
                return imagehash.average_hash(img)
            elif method == 'dhash':
                return imagehash.dhash(img)
            else:
                return imagehash.phash(img)
        except Exception as e:
            print(f"Error hashing {image_path}: {e}")
            return None
