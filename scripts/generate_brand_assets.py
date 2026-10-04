"""Generate all Treasury Flow brand assets from a single source logo.

Usage: py scripts/generate_brand_assets.py <path-to-source-png>
"""
import os
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, 'static')
BRAND = os.path.join(STATIC, 'img', 'brand')
BG = (254, 254, 254, 255)  # #FEFEFE - avoids Android dark-mode icon inversion


def square_trim(img):
    """Trim transparent margin, then pad back to a centered square."""
    img = img.convert('RGBA')
    bbox = img.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
    if bbox:
        img = img.crop(bbox)
    side = max(img.size)
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    return canvas


def fit(logo, size, scale=1.0, bg=None):
    """Place logo on a size x size canvas at `scale` of the canvas."""
    canvas = Image.new('RGBA', (size, size), bg or (0, 0, 0, 0))
    inner = max(1, int(size * scale))
    resized = logo.resize((inner, inner), Image.LANCZOS)
    off = (size - inner) // 2
    canvas.alpha_composite(resized, (off, off))
    return canvas


def save_rgb(img, path, fmt='PNG'):
    img.convert('RGB').save(path, fmt, optimize=True) if fmt == 'PNG' else img.convert('RGB').save(path, fmt, quality=92)


def main(src):
    os.makedirs(BRAND, exist_ok=True)
    logo = square_trim(Image.open(src))

    # UI logos (transparent)
    fit(logo, 512).save(os.path.join(BRAND, 'logo.png'), optimize=True)
    fit(logo, 128).save(os.path.join(BRAND, 'logo_128.png'), optimize=True)

    # PWA icons (solid background so OS dark mode cannot invert them)
    save_rgb(fit(logo, 192, 0.92, BG), os.path.join(BRAND, 'icon_192.png'))
    save_rgb(fit(logo, 512, 0.92, BG), os.path.join(BRAND, 'icon_512.png'))
    # Maskable: keep logo inside the 80% safe zone
    save_rgb(fit(logo, 512, 0.72, BG), os.path.join(BRAND, 'icon_maskable_512.png'))
    save_rgb(fit(logo, 192, 0.72, BG), os.path.join(BRAND, 'icon_maskable_192.png'))
    # Apple touch icon (iOS adds its own rounded corners, no transparency allowed)
    save_rgb(fit(logo, 180, 0.88, BG), os.path.join(BRAND, 'apple-touch-icon.png'))

    # Favicons (transparent)
    fit(logo, 32).save(os.path.join(BRAND, 'favicon-32.png'), optimize=True)
    fit(logo, 16).save(os.path.join(BRAND, 'favicon-16.png'), optimize=True)
    fav = fit(logo, 256)
    fav.save(os.path.join(STATIC, 'favicon.ico'), sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

    # PDF header logo (RGB on white for FPDF compatibility)
    save_rgb(fit(logo, 400, 1.0, (255, 255, 255, 255)), os.path.join(BRAND, 'logo_pdf.png'))

    # Overwrite legacy files so any forgotten/old reference also shows the new logo
    legacy_solid = {
        os.path.join(STATIC, 'img', 'logo_v5_512.png'): 512,
        os.path.join(STATIC, 'img', 'logo_v5_192.png'): 192,
        os.path.join(STATIC, 'img', 'logo_v4.png'): 512,
        os.path.join(STATIC, 'img', 'logo_512.png'): 512,
        os.path.join(STATIC, 'img', 'logo_192.png'): 192,
        os.path.join(STATIC, 'icon-512x512.png'): 512,
    }
    for path, size in legacy_solid.items():
        save_rgb(fit(logo, size, 0.92, BG), path)
    save_rgb(fit(logo, 512, 0.92, (255, 255, 255, 255)), os.path.join(STATIC, 'logo.jpg'), 'JPEG')

    print('Brand assets generated in', BRAND)


if __name__ == '__main__':
    main(sys.argv[1])
