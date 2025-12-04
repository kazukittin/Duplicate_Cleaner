import cv2
import numpy as np

class BlurDetector:
    @staticmethod
    def calculate_blur_score(image_path: str) -> float:
        """
        Calculates the Laplacian variance of the image.
        Lower score means more blurry.
        """
        try:
            # Read image using opencv
            # cv2.imread doesn't handle non-ascii paths well on Windows sometimes, 
            # but usually okay. For robustness with unicode paths:
            stream = open(image_path, "rb")
            bytes_data = stream.read()
            array = np.frombuffer(bytes_data, dtype=np.uint8)
            image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
            stream.close()

            if image is None:
                print(f"Warning: Could not decode image {image_path}")
                return 0.0

            return cv2.Laplacian(image, cv2.CV_64F).var()
        except (OSError, IOError) as e:
            print(f"Warning: Could not read file {image_path}: {e}")
            return 0.0
        except Exception as e:
            print(f"Unexpected error processing {image_path}: {e}")
            return 0.0

    @staticmethod
    def is_blurry(score: float, threshold: float = 50.0) -> bool:
        return score < threshold
