import os
from typing import List, Generator, Callable, Dict, Any
from PIL import Image, ExifTags

class Scanner:
    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.mp4', '.avi', '.mov', '.mkv'}

    @staticmethod
    def get_exif_data(image_path: str) -> Dict[str, Any]:
        """
        Extracts basic EXIF data (DateTimeOriginal) from the image.
        """
        exif_data = {}
        try:
            with Image.open(image_path) as img:
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        decoded = ExifTags.TAGS.get(tag, tag)
                        if decoded == 'DateTimeOriginal':
                            exif_data['DateTimeOriginal'] = value
                            break # We only care about date for now
        except Exception:
            pass
        return exif_data

    @staticmethod
    def scan_directory(root_path: str, progress_callback: Callable[[int, int], None] = None) -> List[str]:
        """
        Recursively scans the directory for supported images.
        
        Args:
            root_path: The directory to scan.
            progress_callback: Optional callback (current_count, total_estimated). 
                               Note: Total estimation is hard without pre-scan, 
                               so we might just report count.
        
        Returns:
            List of absolute file paths.
        """
        image_files = []
        
        # First pass to count files (optional, but good for progress bar if needed later)
        # For now, we'll just walk and collect.
        
        for root, _, files in os.walk(root_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in Scanner.SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    image_files.append(full_path)
                    
                    if progress_callback:
                        progress_callback(len(image_files))
                        
        return image_files
