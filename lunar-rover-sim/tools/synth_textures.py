"""Procedural, seamlessly tiling lunar surface textures: albedo + height -> normal."""
import numpy as np
from PIL import Image

N = 1024
rng = np.random.default_rng(7)

def spectral(beta, lo=1.0, seed=None):
    r = np.random.default_rng(seed)
    f = np.fft.fftfreq(N)[:, None] ** 2 + np.fft.fftfreq(N)[None, :] ** 2
    f = np.sqrt(f) * N
    amp = np.where(f > 0, 1.0 / np.maximum(f, lo) ** beta, 0.0)
    ph = np.exp(2j * np.pi * r.random((N, N)))
    x = np.real(np.fft.ifft2(amp * ph))
    return (x - x.mean()) / x.std()

yy, xx = np.mgrid[0:N, 0:N]

def stamp(canvas_h, canvas_a, cx, cy, rad, height, alb, shape='blob', sharp=0.0, rr=None):
    """Paint an object with wrap-around. shape: blob (rounded) or rock (faceted)."""
    r = int(np.ceil(rad * 1.6)) + 2
    xs = (np.arange(int(cx) - r, int(cx) + r + 1)) % N
    ys = (np.arange(int(cy) - r, int(cy) + r + 1)) % N
    gx, gy = np.meshgrid(np.arange(-r, r + 1) + (int(cx) - cx), np.arange(-r, r + 1) + (int(cy) - cy))
    ang = np.arctan2(gy, gx)
    rr = rr if rr is not None else rng.random(5) * 6.28
    k = 1 + 0.22 * np.sin(2 * ang + rr[0]) + 0.12 * np.sin(3 * ang + rr[1]) + 0.07 * np.sin(5 * ang + rr[2])
    d = np.sqrt(gx ** 2 + gy ** 2) / (rad * k)
    if shape == 'rock':
        # faceted: max of a few plane distances
        n = 5 + int(rr[3] % 3)
        a0 = rr[4]
        pl = np.max([np.cos(ang - (a0 + i * 6.283 / n)) * np.sqrt(gx ** 2 + gy ** 2) for i in range(n)], axis=0) / rad
        d = 0.6 * d + 0.4 * pl
        h = np.clip(1 - d, 0, 1) ** 0.6
    else:
        h = np.sqrt(np.clip(1 - d * d, 0, 1))
    m = (d < 1).astype(np.float32)
    edge = np.clip((1 - d) * 6, 0, 1)
    sub_h = canvas_h[np.ix_(ys, xs)]
    canvas_h[np.ix_(ys, xs)] = np.maximum(sub_h, h * height)
    sub_a = canvas_a[np.ix_(ys, xs)]
    canvas_a[np.ix_(ys, xs)] = sub_a * (1 - edge[..., None] * m[..., None]) + alb * edge[..., None] * m[..., None]

def normals(h, strength):
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.stack([-gx, gy, np.ones_like(gx)], 2)
    return n / np.linalg.norm(n, axis=2, keepdims=True)

def save(name, alb, h, strength):
    lum = alb.mean(2)
    alb = alb * (0.5 / lum.mean())
    Image.fromarray((np.clip(alb, 0, 1) * 255).astype(np.uint8)).save(f'{name}_albedo.jpg', quality=90)
    n = normals(h, strength)
    Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(f'{name}_normal.png')
    print(name, 'albedo range', np.percentile(alb.mean(2), [2, 50, 98]).round(3))

def tint(g, warm=0.02):
    g = np.asarray(g, dtype=np.float64)
    return np.stack([g * (1 + warm), g, g * (1 - warm * 1.4)], -1)

# ---------------- regolith: powder, grains, clods, pebbles ----------------
def regolith(name, rocks=0, seed=1):
    global rng
    rng = np.random.default_rng(seed)
    base = 0.5 + 0.05 * spectral(1.3, 4, seed) + 0.035 * spectral(0.6, 1, seed + 1)
    h = 0.25 * spectral(1.6, 3, seed + 2) + 0.08 * spectral(0.9, 1, seed + 3)
    a = tint(base)
    grain = spectral(0.2, 1, seed + 4)
    a *= (1 + 0.07 * grain)[..., None]
    h += 0.05 * grain
    # clods & grains
    for _ in range(9000):
        rad = 0.8 + rng.random() ** 3 * 5
        v = 0.5 * (1 + rng.normal(0, 0.12))
        stamp(h, a, rng.random() * N, rng.random() * N, rad, 0.15 + rad * 0.06, tint(v).reshape(1, 1, 3))
    # pebbles
    for _ in range(420 + rocks * 260):
        rad = 2.5 + rng.random() ** 3 * (12 + rocks * 26)
        v = 0.5 * np.clip(rng.normal(0.93, 0.13), 0.6, 1.4)
        stamp(h, a, rng.random() * N, rng.random() * N, rad, rad * 0.5, tint(np.array(v), 0.01).reshape(1, 1, 3), 'rock')
    # internal texture of grains and stones, and a dust veil over everything
    a *= (1 + 0.12 * spectral(0.15, 1, seed + 9) + 0.05 * spectral(0.8, 1, seed + 10))[..., None]
    a = a * 0.85 + 0.15 * a.mean()
    # dust settling in low spots darkens slightly, crests brighten
    hl = h - np.real(np.fft.ifft2(np.fft.fft2(h) * np.exp(-(np.fft.fftfreq(N)[:, None] ** 2 + np.fft.fftfreq(N)[None, :] ** 2) * (N / 8) ** 2)))
    a *= (1 + 0.08 * np.tanh(hl * 2))[..., None]
    save(name, a, h, 3.0)

# ---------------- rocks ----------------
def voronoi_edges(nc, seed):
    r = np.random.default_rng(seed)
    pts = r.random((nc, 2)) * N
    d1 = np.full((N, N), 1e9); d2 = np.full((N, N), 1e9); idx = np.zeros((N, N), int)
    for i, (px, py) in enumerate(pts):
        dx = np.abs(xx - px); dx = np.minimum(dx, N - dx)
        dy = np.abs(yy - py); dy = np.minimum(dy, N - dy)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        idx = np.where(closer, i, idx)
        d1 = np.where(closer, d, d1)
    return d2 - d1, idx

def basalt(name, seed=11):
    global rng
    rng = np.random.default_rng(seed)
    g = 0.5 + 0.06 * spectral(1.2, 2, seed) + 0.05 * spectral(0.1, 1, seed + 1)
    h = 0.4 * spectral(1.5, 2, seed + 2) + 0.05 * spectral(0.3, 1, seed + 3)
    a = tint(g, 0.015)
    # crystals speckle
    sp = spectral(0.0, 1, seed + 4)
    a *= (1 + 0.1 * np.clip(sp - 1.2, 0, 3))[..., None]
    # vesicles: dark pits with a bright rim
    hneg = -h
    for _ in range(420):
        cx, cy = rng.random(2) * N
        rad = 1.2 + rng.random() ** 3 * 7
        stamp(hneg, a, cx, cy, rad, rad * 0.35, tint(np.array(0.34)).reshape(1, 1, 3))
    h = -hneg
    # fractures
    e, _ = voronoi_edges(28, seed)
    crack = np.exp(-e / 1.2) * (0.5 + 0.5 * (spectral(1.0, 2, seed + 5) > 0))
    a *= (1 - 0.3 * crack)[..., None]
    h -= crack * 0.4
    save(name, a, h, 2.5)

def breccia(name, seed=23):
    global rng
    rng = np.random.default_rng(seed)
    g = 0.5 + 0.05 * spectral(1.1, 2, seed)
    a = tint(g, 0.01)
    h = 0.3 * spectral(1.4, 2, seed + 1)
    e, idx = voronoi_edges(420, seed + 2)
    clast = rng.random(420)
    tone = np.where(clast < 0.25, 1.28, np.where(clast < 0.4, 0.72, 1.0))[idx]
    has = (clast < 0.4)[idx] & (e > 2.0)
    a *= np.where(has, tone, 1.0)[..., None]
    h += np.where(has, 0.25, 0.0) * np.clip(e / 6, 0, 1)
    a *= (1 + 0.12 * spectral(0.1, 1, seed + 3) + 0.05 * spectral(1.0, 2, seed + 6))[..., None]
    crack = np.exp(-e / 0.9) * (spectral(1.2, 2, seed + 4) > 0.9)
    a *= (1 - 0.4 * crack)[..., None]
    save(name, a, h, 2.5)

regolith('regolith', 0, 1)
regolith('rubble', 1, 5)
basalt('basalt')
breccia('breccia')
