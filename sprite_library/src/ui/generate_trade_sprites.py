"""Generate trade window sprites programmatically."""
from PIL import Image, ImageDraw, ImageFont
import os

def create_trade_window_background(width=400, height=300):
    """Create the trade window background panel."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Main panel with gradient effect (dark blue-gray)
    for y in range(height):
        alpha = int(230 - (y / height) * 20)
        color = (22, 26, 35, alpha)
        draw.line([(0, y), (width, y)], fill=color)

    # Border (golden/bronze)
    border_color = (180, 145, 85, 255)
    draw.rectangle([0, 0, width-1, height-1], outline=border_color, width=2)

    # Inner highlight line
    highlight_color = (60, 70, 90, 180)
    draw.rectangle([3, 3, width-4, height-4], outline=highlight_color, width=1)

    return img

def create_button(width=120, height=40, color=(76, 175, 80), icon="✓"):
    """Create accept/decline buttons with icon."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded rectangle background with gradient
    for y in range(height):
        # Darken towards bottom
        darken = int((y / height) * 30)
        r = max(0, color[0] - darken)
        g = max(0, color[1] - darken)
        b = max(0, color[2] - darken)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 240))

    # Border
    border = (255, 255, 255, 100)
    draw.rounded_rectangle([0, 0, width-1, height-1], radius=6, outline=border, width=2)

    # Icon/text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), icon, font=font)
    icon_width = bbox[2] - bbox[0]
    icon_height = bbox[3] - bbox[1]
    x = (width - icon_width) // 2
    y = (height - icon_height) // 2 - 3

    # Shadow
    draw.text((x+1, y+1), icon, font=font, fill=(0, 0, 0, 100))
    draw.text((x, y), icon, font=font, fill=(255, 255, 255, 255))

    return img

def create_button_lit(width=120, height=40, color=(76, 175, 80), glow_color=(100, 255, 100)):
    """Create lit/active version of button with glow."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Glow effect
    for i in range(8, 0, -1):
        alpha = int(30 - i * 3)
        glow = (*glow_color[:3], alpha)
        draw.rounded_rectangle([-i, -i, width+i, height+i], radius=8, outline=glow, width=2)

    # Brighter gradient
    for y in range(height):
        brighten = int((1 - y / height) * 40)
        r = min(255, color[0] + brighten)
        g = min(255, color[1] + brighten)
        b = min(255, color[2] + brighten)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Bright border
    draw.rounded_rectangle([0, 0, width-1, height-1], radius=6, outline=(255, 255, 255, 200), width=2)

    # Checkmark/X
    icon = "✓"
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), icon, font=font)
    icon_width = bbox[2] - bbox[0]
    icon_height = bbox[3] - bbox[1]
    x = (width - icon_width) // 2
    y = (height - icon_height) // 2 - 3

    draw.text((x, y), icon, font=font, fill=(255, 255, 255, 255))

    return img

def create_item_slot(width=60, height=60):
    """Create empty item slot."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark background
    draw.rounded_rectangle([2, 2, width-3, height-3], radius=4, fill=(35, 40, 50, 200))

    # Border
    draw.rounded_rectangle([0, 0, width-1, height-1], radius=4, outline=(100, 110, 130, 150), width=1)

    return img

def create_coin_sprite(width=32, height=32):
    """Create a simple coin sprite."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = width // 2, height // 2
    radius = width // 2 - 2

    # Gold coin gradient
    for r in range(radius, 0, -1):
        ratio = r / radius
        gold = int(255 - ratio * 60)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(gold, gold - 40, 0, 255))

    # Shine
    draw.ellipse([cx-radius//2, cy-radius, cx+radius//3, cy-radius//3], fill=(255, 255, 200, 180))

    return img

if __name__ == "__main__":
    output_dir = os.path.dirname(os.path.abspath(__file__))

    # Generate all sprites
    create_trade_window_background().save(os.path.join(output_dir, "trade_window.png"))
    create_button(color=(76, 175, 80), icon="✓").save(os.path.join(output_dir, "trade_accept.png"))
    create_button(color=(220, 80, 60), icon="✕").save(os.path.join(output_dir, "trade_decline.png"))
    create_button_lit(color=(76, 175, 80), glow_color=(100, 255, 100)).save(os.path.join(output_dir, "trade_accept_lit.png"))
    create_button_lit(color=(220, 80, 60), glow_color=(255, 100, 100)).save(os.path.join(output_dir, "trade_decline_lit.png"))
    create_item_slot().save(os.path.join(output_dir, "trade_item_slot.png"))
    create_coin_sprite().save(os.path.join(output_dir, "trade_coin.png"))

    print("Trade sprites generated successfully!")
