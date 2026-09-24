"""Turn generated photos into seamless PBR tiles: albedo (flat-lit), normal, height."""
import sys, numpy as np
from PIL import Image, ImageFilter

def gauss(a, r):
    # periodic gaussian blur in the frequency domain
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]; fx = np.fft.fftfreq(w)[None, :]
    k = np.exp(-2 * (np.pi * r) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * k)).astype(np.float32)

def seamless(img):
    # blend with a half-offset copy using a mask that is 0 at the borders of the original
    h, w, _ = img.shape
    off = np.roll(np.roll(img, h // 2, 0), w // 2, 1)
    y = np.abs(np.linspace(-1, 1, h))[:, None]
    x = np.abs(np.linspace(-1, 1, w))[None, :]
    m = np.clip(np.maximum(x, y) * 1.35 - 0.35, 0, 1) ** 1.5  # 1 near borders -> use offset copy
    m = m[..., None]
    return img * (1 - m) + off * m

def flatten(img, radius):
    # remove low-frequency lighting / vignetting, keep mean colour
    lum = img.mean(axis=2)
    low = gauss(lum, radius)
    return img * (lum.mean() / np.maximum(low, 1e-3))[..., None]

def main(src, out, size, flat_radius, height_blur, strength):
    img = np.asarray(Image.open(src).convert('RGB').resize((size, size), Image.LANCZOS), dtype=np.float32) / 255.0
    img = flatten(img, flat_radius)
    img = seamless(img)
    img = flatten(img, flat_radius)  # the blend can leave soft seams in brightness
    # keep colour gentle: pull saturation down towards lunar grey
    g = img.mean(axis=2, keepdims=True)
    img = g + (img - g) * 0.45
    img = img * (0.5 / img.mean())
    img = np.clip(img, 0, 1)
    Image.fromarray((img * 255).astype(np.uint8)).save(out + '_albedo.jpg', quality=90)
    # height from luminance (bright grains stand up), tile-aware blur via wrap padding
    lum = img.mean(axis=2)
    pad = size // 8
    lp = np.pad(lum, pad, mode='wrap')
    hgt = gauss(lp, height_blur)[pad:-pad, pad:-pad]
    hgt -= gauss(np.pad(hgt, pad, mode='wrap'), size / 16)[pad:-pad, pad:-pad]
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) * strength
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) * strength
    n = np.stack([-gx, gy, np.ones_like(gx)], axis=2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(out + '_normal.jpg', quality=92)
    print(out, 'mean albedo', img.mean(axis=(0, 1)))

if __name__ == '__main__':
    src, out, size, fr, hb, st = sys.argv[1:]
    main(src, out, int(size), float(fr), float(hb), float(st))
