import os
import sys
import shutil
import time
from PIL import Image, ImageFilter

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scanner import Scanner
from core.blur_detector import BlurDetector
from core.hash_engine import HashEngine
from core.group_builder import GroupBuilder
from core.rule_engine import RuleEngine
from core.executor import Executor

def create_test_data(root_dir):
    if os.path.exists(root_dir):
        shutil.rmtree(root_dir)
    os.makedirs(root_dir)
    
    # Create base image with pattern (lines) to test blur
    img = Image.new('RGB', (200, 200), color = 'white')
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    for i in range(0, 200, 10):
        draw.line((i, 0, i, 200), fill='black', width=1)
        draw.line((0, i, 200, i), fill='black', width=1)
    
    img.save(os.path.join(root_dir, 'original.jpg'))
    
    # Create duplicate
    shutil.copy(os.path.join(root_dir, 'original.jpg'), os.path.join(root_dir, 'duplicate.jpg'))
    
    # Create similar (resize)
    img_resized = img.resize((100, 100))
    img_resized.save(os.path.join(root_dir, 'similar_small.jpg'))
    
    # Create blurry
    img_blur = img.filter(ImageFilter.GaussianBlur(5))
    img_blur.save(os.path.join(root_dir, 'blurry.jpg'))
    
    print(f"Test data created in {root_dir}")

def main():
    test_dir = "test_images"
    create_test_data(test_dir)
    
    print("--- 1. Scanning ---")
    files = Scanner.scan_directory(os.path.abspath(test_dir))
    print(f"Found {len(files)} files.")
    
    print("--- 2. Blur Detection ---")
    for f in files:
        score = BlurDetector.calculate_blur_score(f)
        is_blur = BlurDetector.is_blurry(score, threshold=100) # Threshold might need tuning for flat images
        print(f"{os.path.basename(f)}: Score={score:.2f}, Blurry={is_blur}")
        
    print("--- 3. Hashing & Grouping ---")
    hashes = []
    for f in files:
        h = HashEngine.compute_hash(f)
        hashes.append((f, h))
        print(f"{os.path.basename(f)}: {h}")
        
    # Print distances
    for i in range(len(hashes)):
        for j in range(i+1, len(hashes)):
            h1 = hashes[i][1]
            h2 = hashes[j][1]
            if h1 and h2:
                print(f"Dist {os.path.basename(hashes[i][0])} - {os.path.basename(hashes[j][0])}: {h1 - h2}")

    groups = GroupBuilder.build_groups(hashes)
    print(f"Found {len(groups)} groups.")
    for i, g in enumerate(groups):
        print(f"Group {i+1}: {[os.path.basename(p) for p in g]}")
        
    print("--- 4. Rule Engine ---")
    actions = {}
    for g in groups:
        group_actions = RuleEngine.apply_rules(g)
        actions.update(group_actions)
        
    print("Actions:", {os.path.basename(k): v for k, v in actions.items()})
    
    print("--- 5. Execution ---")
    # Executor.execute_actions(actions, backup_root=os.path.abspath("test_trash"))
    # print("Execution done. Check test_trash folder.")

if __name__ == "__main__":
    main()
