import cv2
import numpy as np
from typing import Optional
import imagehash
from PIL import Image

class VideoHash:
    @staticmethod
    def extract_middle_frame(video_path: str) -> Optional[np.ndarray]:
        """Extract the middle frame from a video."""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
                
            # Get total frames
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                cap.release()
                return None
                
            # Seek to middle frame
            middle_frame = total_frames // 2
            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
            
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                return frame
            return None
        except Exception as e:
            print(f"Error extracting frame from {video_path}: {e}")
            return None
            
    @staticmethod
    def compute_hash(video_path: str, method: str = 'phash'):
        """Compute perceptual hash from video's middle frame."""
        try:
            frame = VideoHash.extract_middle_frame(video_path)
            if frame is None:
                return None
                
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert to PIL Image
            pil_image = Image.fromarray(frame_rgb)
            
            # Compute hash
            if method == 'phash':
                return imagehash.phash(pil_image)
            elif method == 'ahash':
                return imagehash.average_hash(pil_image)
            elif method == 'dhash':
                return imagehash.dhash(pil_image)
            else:
                return imagehash.phash(pil_image)
        except Exception as e:
            print(f"Error hashing video {video_path}: {e}")
            return None
