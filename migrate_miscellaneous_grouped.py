import os
import shutil
import re
import argparse
from collections import defaultdict
from typing import DefaultDict, List

# Configuration
ROOT_DIR = "/Volumes/media/home_videos/home"

class HomeVideo:
    def __init__(self, item_name, year, title, final_name):
        self.item_name = item_name
        self.year = year
        self.title = title
        self.final_name = final_name

def update_nfo(nfo_path, new_title, new_year, dry_run=False):
    """Updates the <title> tag in the NFO file."""
    try:
        if dry_run:
            print(f"  [DRY RUN] Would update NFO title to: {new_title} and year to: {new_year} in {nfo_path}")
            return

        with open(nfo_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex to replace title content
        # <title>Msg - ...</title> -> <title>New Title</title>
        # We use re.sub for robust XML handling (avoiding proper XML parser to keep it simple/dependency-free if possible,
        # but regex on XML is fragile. However, for simple NFOs it's usually fine).
        
        pattern = r"(<title>)(.*?)(</title>)"
        replacement = f"\\1{new_title}\\3"
        
        new_content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        if content != new_content:
            with open(nfo_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        # update the <year /> tag with the year from the new title if possible
        # Matches <year>1234</year> or <year/> or <year />
        pattern_year = r"<year(?:\s+[^>]*)?(?:>.*?</year>|(?:\s*/>))"
        replacement = f"<year>{new_year}</year>"

        new_content = re.sub(pattern_year, replacement, new_content, flags=re.IGNORECASE)

        if content != new_content:
            with open(nfo_path, 'w', encoding='utf-8') as f:
                f.write(new_content)


    except Exception as e:
        print(f"  Error updating NFO {nfo_path}: {e}")

def migrate_media(target_subdir, original_group, dry_run=False):
    print(f"Starting migration... {'(DRY RUN)' if dry_run else ''}")
    
    # We walk the tree. 
    # For each directory, we identify "groups" of files belonging to the same movie/episode.
    
    for root, dirs, files in os.walk(ROOT_DIR):
        # Determine the year from the current folder structure if possible, 
        # but we basically trust the filename first as per instructions (or the parent folder).
        # We are moving TO <Year>/<target_subdir>.
        
        # Collect all items in this directory (files + subdirectories like .trickplay)
        all_items = files + dirs
        
        # Group items by their "Base Name" (e.g. "Miscellaneous - S1989E01 - Around the house")
        # We strip extensions and "-poster" suffixes to find the common root.
        grouped_items: DefaultDict[str, List[str]] = defaultdict(list)
        home_videos = []
        
        for item in all_items:
            if not item.startswith(original_group):
                continue
                
            # Ignore if we are already in a folder (avoid processing output if re-run)
            if os.path.basename(root) == target_subdir:
                continue

            # Determine base key
            # Remove extension
            name_no_ext = os.path.splitext(item)[0]
            # Handle .trickplay folder special case 
            if item.endswith(".trickplay"):
                name_no_ext = item[:-10] # separate strip for clarity
            
            # Remove "-poster" suffix if present (common in Kodi/Plex)
            if name_no_ext.endswith("-poster"):
                name_no_ext = name_no_ext[:-7]
            
            grouped_items[name_no_ext].append(item)
            
        # Process each group
        for base_key, items in grouped_items.items():

            files_to_move : List[HomeVideo] = []

            # Parse the Name
            # Expected format: Miscellaneous - S(YYYY)E(XX) - (Title)
            pattern = rf"{re.escape(original_group)} - S(\d{{4}})E\d+ - (.*)"
            match = re.match(pattern, base_key)
            
            if not match:
                print(f"Skipping (does not match {original_group} pattern): {base_key}")
                continue
            
            year = match.group(1)
            raw_title = match.group(2).strip()

            # Construct new filename base: "Title (Year)"
            new_base_name = f"{raw_title} ({year})"
            
            # Destination directory: home/<year>/<target_subdir>    
            dest_dir = os.path.join(ROOT_DIR, year, target_subdir, new_base_name)
            
            if not os.path.exists(dest_dir):
                if dry_run:
                    # Don't create, just logging implied
                    pass
                else:
                    os.makedirs(dest_dir)
                
            # Handle Collisions (if "Title (Year)" already exists)
            # We check if ANY file in the target mapping would overwrite an existing file.
            
            final_base_name = new_base_name
            collision_counter = 1
            
            while True:
                collision_found = False
                # Check all items in this group against the destination
                for item in items:
                    # Calculate what the new name MUST be for this item
                    # We determine the suffix relative to the original base_key
                    # item: "Misc...Title-poster.jpg"
                    # base_key: "Misc...Title"
                    # suffix: "-poster.jpg"
                    
                    if not item.startswith(base_key):
                         # Should ideally not happen if grouping worked, 
                         # but safety for case sensitivity etc.
                         continue
                         
                    suffix = item[len(base_key):]
                    proposed_name = final_base_name + suffix
                    proposed_path = os.path.join(dest_dir, proposed_name)
                    
                    # If file exists and is NOT the file we are moving (in case of in-place move, though paths differ here)
                    if os.path.exists(proposed_path):
                        # Special check: is it the same file? (inode or path)
                        if os.path.abspath(proposed_path) == os.path.join(root, item):
                            continue # Ignore self
                        collision_found = True
                        break
                
                if not collision_found:
                    break
                
                # Try next counter
                collision_counter += 1
                final_base_name = f"{new_base_name} ({collision_counter})"

            # Perform Moves
            # If we had a collision, final_base_name is now "Title (Year) (2)" etc.
            for item in items:
                files_to_move.append(HomeVideo(item_name=item, year=year, title=raw_title, final_name=final_base_name))

            
            for item in files_to_move:
                source_path = os.path.join(root, item.item_name)
                
                suffix = item.item_name[len(base_key):]
                target_name = item.final_name + suffix
                target_path = os.path.join(dest_dir, target_name)
                
                action_word = "Would move" if dry_run else "Moving"
                print(f"{action_word}: '{item.item_name}' -> {target_path}")
                
                if not dry_run:
                    try:
                        shutil.move(source_path, target_path)
                        
                        if target_name.endswith(".nfo"):
                            update_nfo(target_path, item.final_name, item.year, dry_run=False)
                            
                    except Exception as e:
                        print(f"FAILED to move {item.item_name}: {e}")
                elif target_name.endswith(".nfo"):
                         # In dry run, we still want to simulate the NFO update log
                         update_nfo(target_path, item.final_name, item.year, dry_run=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="MigrateJellyfinFiles", description="Migrate directory to work with Jellyfin.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without making any changes.")
    parser.add_argument("--target-subdir", type=str, help="Target subdirectory name.", required=True)
    parser.add_argument("--original-group", type=str, help="Original group name to migrate from.", required=True)
    args = parser.parse_args()
    
    migrate_media(target_subdir=args.target_subdir, original_group=args.original_group, dry_run=args.dry_run)

