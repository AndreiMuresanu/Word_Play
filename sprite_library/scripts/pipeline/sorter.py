import os
import shutil
from pathlib import Path

SRC_DIR = Path("sprite_library/src")

def move_file(file_path, broad, specific):
    # original base is something like src/characters/DawnLike
    # we want to put them directly in src/characters/broad/specific
    base_category_dir = file_path.parent.parent
    target_dir = base_category_dir / broad / specific
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file_path), str(target_dir / file_path.name))

# ----------------- ITEMS: FreePixelFood -----------------
food_dir = SRC_DIR / "items" / "FreePixelFood"
if food_dir.exists():
    for f in food_dir.glob("*.png"):
        name = f.name.lower()
        if any(w in name for w in ["apple", "banana", "berry", "melon", "fruit", "orange", "grape"]):
            move_file(f, "consumables", "fruit")
        elif any(w in name for w in ["carrot", "tomato", "potato", "onion", "veg", "corn", "mushroom"]):
            move_file(f, "consumables", "vegetables")
        elif any(w in name for w in ["meat", "steak", "fish", "chicken", "bacon"]):
            move_file(f, "consumables", "meat")
        elif any(w in name for w in ["drink", "potion", "water", "beer", "wine", "milk", "coffee"]):
            move_file(f, "consumables", "beverage")
        else:
            move_file(f, "consumables", "misc_food")
    shutil.rmtree(food_dir)

# ----------------- ITEMS: ManaSeedWeapons -----------------
msw_dir = SRC_DIR / "items" / "ManaSeedWeapons"
if msw_dir.exists():
    for f in msw_dir.glob("*.png"):
        move_file(f, "equipment", "weapons")
    shutil.rmtree(msw_dir)

# ----------------- CHARACTERS: ManaSeedBase -----------------
msb_dir = SRC_DIR / "characters" / "ManaSeedBase"
if msb_dir.exists():
    for f in msb_dir.glob("*.png"):
        if "out" in f.name:
            move_file(f, "humanoids", "base")
        elif "har" in f.name:
            move_file(f, "humanoids", "hair")
        elif "hat" in f.name:
            move_file(f, "humanoids", "headgear")
        elif "tla" in f.name or "tlb" in f.name:
            move_file(f, "humanoids", "apparel")
        else:
            move_file(f, "humanoids", "components")
    shutil.rmtree(msb_dir)

# ----------------- DAWNLIKE: Characters -----------------
dl_chars = SRC_DIR / "characters" / "DawnLike"
if dl_chars.exists():
    for f in dl_chars.glob("*.png"):
        name = f.name.lower()
        
        # Broad humanoid rules
        if any(w in name for w in ["guard", "knight", "thief", "human", "mage", "archer", "monk", "healer", "warrior", "peasant", "king", "child", "woman", "man", "lord", "lady", "hero", "npc"]):
            move_file(f, "humanoids", "human")
        elif any(w in name for w in ["elf", "elven"]):
            move_file(f, "humanoids", "elf")
        elif any(w in name for w in ["orc", "goblin", "troll", "ogre", "kobold"]):
            move_file(f, "humanoids", "goblinoid")
        elif any(w in name for w in ["dwarf", "gnome"]):
            move_file(f, "humanoids", "dwarven")
            
        # Broad monster rules
        elif any(w in name for w in ["zombie", "skeleton", "ghost", "vampire", "ghoul", "lich", "mummy", "spirit", "wraith", "bone"]):
            move_file(f, "monsters", "undead")
        elif any(w in name for w in ["demon", "devil", "imp", "fiend"]):
            move_file(f, "monsters", "demonic")
        elif any(w in name for w in ["dragon", "drake", "wyvern"]):
            move_file(f, "monsters", "draconic")
        elif any(w in name for w in ["bat", "rat", "wolf", "bear", "cat", "dog", "hound", "spider", "snake", "bug", "ant", "bee", "wasp", "beast", "eel", "hog", "pelican"]):
            move_file(f, "monsters", "beast")
            
        # Others
        elif any(w in name for w in ["golem", "statue", "elemental", "gargoyle"]):
            move_file(f, "constructs", "animated")
        elif any(w in name for w in ["tree", "plant", "thorn", "fungus", "mushroom", "bloom", "flower", "moss", "shrub", "cactus"]):
            move_file(f, "flora", "plant")
        else:
            move_file(f, "monsters", "misc")
    
    # If empty, remove the source DawnLike
    if not any(dl_chars.iterdir()):
        shutil.rmtree(dl_chars)

# ----------------- DAWNLIKE: Items -----------------
dl_items = SRC_DIR / "items" / "DawnLike"
if dl_items.exists():
    for f in dl_items.glob("*.png"):
        name = f.name.lower()
        if any(w in name for w in ["sword", "blade", "axe", "mace", "bow", "arrow", "spear", "dagger", "staff", "wand", "club", "hammer"]):
            move_file(f, "equipment", "weapons")
        elif any(w in name for w in ["shield", "armor", "mail", "plate", "helm", "helmet", "boot", "glove", "gauntlet", "cloak", "robe"]):
            move_file(f, "equipment", "armor")
        elif any(w in name for w in ["ring", "amulet", "necklace", "gem", "jewel", "crown"]):
            move_file(f, "equipment", "accessories")
        elif any(w in name for w in ["potion", "flask", "vial", "elixir", "scroll", "book", "tome"]):
            move_file(f, "consumables", "magic")
        elif any(w in name for w in ["meat", "bread", "apple", "food", "drink"]):
            move_file(f, "consumables", "food")
        elif any(w in name for w in ["gold", "coin", "silver", "copper", "key"]):
            move_file(f, "materials", "valuables")
        else:
            move_file(f, "materials", "misc")
            
    if not any(dl_items.iterdir()):
        shutil.rmtree(dl_items)

# ----------------- DAWNLIKE: World Tiles -----------------
dl_tiles = SRC_DIR / "world_tiles" / "DawnLike"
if dl_tiles.exists():
    for f in dl_tiles.glob("*.png"):
        name = f.name.lower()
        if any(w in name for w in ["floor", "carpet", "rug", "tile"]):
            move_file(f, "indoors", "floors")
        elif any(w in name for w in ["wall", "pillar", "column"]):
            move_file(f, "indoors", "walls")
        elif any(w in name for w in ["door", "gate", "window", "stairs"]):
            move_file(f, "indoors", "architecture")
        elif any(w in name for w in ["grass", "tree", "plant", "bush", "flower", "dirt", "rock", "stone", "water", "river", "lake", "ocean", "sea", "sand", "snow", "ice", "bridge"]):
            move_file(f, "outdoors", "nature")
        else:
            move_file(f, "outdoors", "misc_structures")
            
    if not any(dl_tiles.iterdir()):
        shutil.rmtree(dl_tiles)

# ----------------- DAWNLIKE: VFX -----------------
dl_vfx = SRC_DIR / "vfx" / "DawnLike"
if dl_vfx.exists():
    for f in dl_vfx.glob("*.png"):
        name = f.name.lower()
        if any(w in name for w in ["beam", "burst", "spark", "explosion"]):
            move_file(f, "magic", "impacts")
        elif any(w in name for w in ["blood", "puff"]):
            move_file(f, "physical", "impacts")
        else:
            move_file(f, "magic", "misc")
            
    if not any(dl_vfx.iterdir()):
        shutil.rmtree(dl_vfx)

print("Sorting complete.")
