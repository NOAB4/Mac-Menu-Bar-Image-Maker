# Menu Bar Image Maker

A macOS app that removes the background from a black & white image or animated GIF and pins it to your menu bar.

![macOS](https://img.shields.io/badge/macOS-only-lightgrey)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)

## Features

- Drag & drop or browse for an image (PNG, JPG, WEBP, BMP, TIFF, GIF)
- Animated GIF support — plays frame-by-frame in the menu bar
- Background removal with adjustable threshold
- Black & white, invert, and remove background toggles
- Rounded corners on the menu bar icon
- Right-click the menu bar icon to show the window, load a new image, or quit

## Setup

```bash
pip install PyQt6 Pillow numpy
python main.py
```

## Build a standalone .app

```bash
pip install pyinstaller
python -m PyInstaller MenuBarImageMaker.spec --noconfirm
```

The built app lands in `dist/`. Drag it to `/Applications` to install.
# Mac-Menu-Bar-Image-Maker
# Mac-Menu-Bar-Image-Maker
