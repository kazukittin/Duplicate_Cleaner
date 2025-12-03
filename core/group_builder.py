from typing import List, Dict, Tuple
import imagehash

class GroupBuilder:
    @staticmethod
    def build_groups(image_hashes: List[Tuple[str, imagehash.ImageHash]], threshold: int = 5) -> List[List[str]]:
        """
        Groups images based on hash distance.
        This is a naive O(N^2) implementation for MVP.
        
        Args:
            image_hashes: List of (path, hash) tuples.
            threshold: Hamming distance threshold.
            
        Returns:
            List of groups, where each group is a list of file paths.
            Only returns groups with size > 1.
        """
        groups = []
        visited = set()
        
        # Filter out None hashes
        valid_hashes = [item for item in image_hashes if item[1] is not None]
        
        for i in range(len(valid_hashes)):
            path_i, hash_i = valid_hashes[i]
            
            if path_i in visited:
                continue
                
            current_group = [path_i]
            visited.add(path_i)
            
            for j in range(i + 1, len(valid_hashes)):
                path_j, hash_j = valid_hashes[j]
                
                if path_j in visited:
                    continue
                
                # Calculate distance
                dist = hash_i - hash_j
                if dist <= threshold:
                    current_group.append(path_j)
                    visited.add(path_j)
            
            if len(current_group) > 1:
                groups.append(current_group)
                
        return groups
