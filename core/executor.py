import os
import shutil
import datetime
from typing import List, Dict

class Executor:
    @staticmethod
    def execute_actions(actions: Dict[str, str], backup_root: str = None) -> str:
        """
        Executes the delete actions by moving files to a backup folder.
        
        Args:
            actions: Dict mapping path -> 'keep' or 'delete'.
            backup_root: Root directory for backups. If None, uses a default in the parent of the first file.
            
        Returns:
            Path to the log file.
        """
        if not actions:
            return ""
            
        # Determine backup folder
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"_TrashFromTool_{timestamp}"
        
        if backup_root:
            trash_dir = os.path.join(backup_root, folder_name)
        else:
            # Use parent of the first file as base
            first_path = next(iter(actions.keys()))
            base_dir = os.path.dirname(os.path.dirname(first_path)) # Go up one level from the file? Or just same dir?
            # Usually safer to put it in the scan root. But we don't know scan root here.
            # Let's put it in the same directory as the file for now, or maybe just a fixed place?
            # User requirement: "指定フォルダへ移動" (Move to specified folder).
            # We will assume the caller provides a valid backup_root or we create one relative to execution.
            # Let's try to find a common root or just use the directory of the first file.
            base_dir = os.path.dirname(first_path)
            trash_dir = os.path.join(base_dir, folder_name)
            
        os.makedirs(trash_dir, exist_ok=True)
        
        log_lines = []
        log_lines.append(f"Execution Log - {timestamp}")
        log_lines.append(f"Backup Folder: {trash_dir}")
        log_lines.append("-" * 40)
        
        for path, action in actions.items():
            if action == 'delete':
                try:
                    filename = os.path.basename(path)
                    dest_path = os.path.join(trash_dir, filename)
                    
                    # Handle name collision in trash
                    if os.path.exists(dest_path):
                        base, ext = os.path.splitext(filename)
                        dest_path = os.path.join(trash_dir, f"{base}_{timestamp}{ext}")
                    
                    shutil.move(path, dest_path)
                    log_lines.append(f"[MOVED] {path} -> {dest_path}")
                except Exception as e:
                    log_lines.append(f"[ERROR] Failed to move {path}: {e}")
            else:
                log_lines.append(f"[KEPT] {path}")
                
        # Write log
        log_path = os.path.join(trash_dir, "execution_log.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))
            
        return log_path
