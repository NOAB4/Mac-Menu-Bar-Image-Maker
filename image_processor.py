from PIL import Image, ImageDraw
import numpy as np


# Frame = (RGB/RGBA image, duration_ms)
Frame = tuple[Image.Image, int]


def extract_frames(path: str) -> list[Frame]:
    """Open any image and return a list of (RGB image, duration_ms) frames.
    Static images return a single frame with duration 0.
    Animated GIFs return one entry per frame with their durations."""
    img = Image.open(path)
    frames: list[Frame] = []
    try:
        while True:
            duration = int(img.info.get('duration', 100))
            frames.append((img.convert('RGB').copy(), duration))
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    if not frames:
        frames = [(img.convert('RGB'), 0)]
    return frames


def detect_background(img: Image.Image) -> str:
    """Detect whether the image background is predominantly white or black
    by sampling the border pixels."""
    rgb = np.array(img.convert('RGB'))
    h, w = rgb.shape[:2]
    border = np.concatenate([
        rgb[0, :],       # top row
        rgb[-1, :],      # bottom row
        rgb[:, 0],       # left col
        rgb[:, -1],      # right col
    ])
    avg = border.mean()
    return 'white' if avg > 128 else 'black'


def remove_background(img: Image.Image, threshold: int, bg: str) -> Image.Image:
    """Remove white or black background from a B&W image.

    threshold (0–255): how aggressively to erase.
      - For white bg: pixels with all channels >= threshold become transparent.
      - For black bg: pixels with all channels <= (255 - threshold) become transparent.
    """
    rgba = img.convert('RGBA')
    data = np.array(rgba, dtype=np.uint8)
    r, g, b = data[:, :, 0], data[:, :, 1], data[:, :, 2]

    if bg == 'white':
        mask = (r >= threshold) & (g >= threshold) & (b >= threshold)
    else:
        inv = 255 - threshold
        mask = (r <= inv) & (g <= inv) & (b <= inv)

    data[:, :, 3][mask] = 0
    return Image.fromarray(data, 'RGBA')


def to_grayscale(img: Image.Image) -> Image.Image:
    """Convert an image to black & white (grayscale kept as RGB)."""
    return img.convert('L').convert('RGB')


def invert_image(img: Image.Image) -> Image.Image:
    """Invert the RGB channels of an image, leaving any alpha channel unchanged."""
    rgb = img.convert('RGB')
    data = np.array(rgb, dtype=np.uint8)
    data = 255 - data
    return Image.fromarray(data, 'RGB')


def round_corners(img: Image.Image, radius: int) -> Image.Image:
    """Mask an RGBA image to have rounded corners.
    Combines the rounded mask with any existing alpha so transparency is preserved."""
    img = img.convert('RGBA')
    corner_mask = Image.new('L', img.size, 0)
    draw = ImageDraw.Draw(corner_mask)
    draw.rounded_rectangle([(0, 0), (img.width - 1, img.height - 1)], radius=radius, fill=255)
    # AND with existing alpha so bg-removed pixels stay transparent
    existing = np.array(img.split()[3])
    combined = np.minimum(existing, np.array(corner_mask))
    result = img.copy()
    result.putalpha(Image.fromarray(combined, 'L'))
    return result


def with_checkerboard(img: Image.Image, square: int = 10) -> Image.Image:
    """Composite an RGBA image over a grey checkerboard to visualise transparency."""
    w, h = img.size
    xs = np.arange(w) // square
    ys = np.arange(h) // square
    grid = (xs[np.newaxis, :] + ys[:, np.newaxis]) % 2
    light = np.array([210, 210, 210], dtype=np.uint8)
    dark  = np.array([160, 160, 160], dtype=np.uint8)
    checker = np.where(grid[:, :, np.newaxis], dark, light).astype(np.uint8)
    checker_img = Image.fromarray(checker, 'RGB').convert('RGBA')
    checker_img.paste(img, mask=img.split()[3])
    return checker_img
