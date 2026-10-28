"""Photo adjustments for the Edit photo tool: 17 controls that mirror the Mac editor (ImageOps.adjusted).

Everything here is 8-bit Pillow work (look-up tables, blends and filters) so a 40-megapixel photo stays within the worker's memory
budget and the preview, made from a downscaled copy, looks like the full-size result: radii that depend on the picture are
expressed as fractions of its longer side. These are approximations of the Mac's Core Image filters, not bit-identical copies.
Every control is neutral at 0 (False for monochrome), and a neutral set of values returns the picture unchanged.

Order, as on the Mac: exposure, brightness/contrast/colour, highlights and shadows, vibrance, temperature and tint, dehaze,
noise reduction, clarity, sharpness, sepia, monochrome, vignette, grain."""
from __future__ import annotations

# key: (low, high, default). The Edit photo form and the validator both read this table.
LIMITS = {
    'exposure': (-2.0, 2.0, 0.0), 'brightness': (-1.0, 1.0, 0.0), 'contrast': (-1.0, 1.0, 0.0), 'highlights': (-1.0, 1.0, 0.0), 'shadows': (-1.0, 1.0, 0.0),
    'saturation': (-1.0, 1.0, 0.0), 'vibrance': (-1.0, 1.0, 0.0), 'temperature': (-1.0, 1.0, 0.0), 'tint': (-1.0, 1.0, 0.0), 'sepia': (0.0, 1.0, 0.0),
    'sharpness': (-1.0, 1.0, 0.0), 'clarity': (0.0, 1.0, 0.0), 'dehaze': (0.0, 1.0, 0.0), 'noise': (0.0, 1.0, 0.0), 'grain': (0.0, 1.0, 0.0), 'vignette': (0.0, 1.0, 0.0),
}

def clamp8(v): return 0 if v < 0 else 255 if v > 255 else int(v + .5)

def lut_all(f):
    """The same 256-entry curve for the three colour bands."""
    table = [clamp8(f(i / 255) * 255) for i in range(256)];return table * 3

def srgb_to_linear(c): return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
def linear_to_srgb(c): return c * 12.92 if c <= .0031308 else 1.055 * c ** (1 / 2.4) - .055

def exposure(im, ev):
    """Scale linear light by 2^ev, like a camera stop."""
    gain = 2 ** ev;return im.point(lut_all(lambda c: linear_to_srgb(min(1.0, srgb_to_linear(c) * gain))))

def tone(im, highlights, shadows):
    """Lift or deepen the shadows and recover or push the highlights. The change is worked out from the brightness of each pixel and
    added to all three channels alike, so colours keep their hue instead of drifting; mid-tones barely move."""
    from PIL import Image, ImageChops
    def f(c):
        w_s = (1 - c) ** 3;w_h = c ** 3;out = c
        out += shadows * w_s * (1 - c) * .55 if shadows > 0 else shadows * w_s * c * .55
        out += highlights * w_h * (1 - c) * .55 if highlights > 0 else highlights * w_h * c * .45
        return out
    shift = [f(i / 255) * 255 - i for i in range(256)];luma = im.convert('L')
    up = luma.point([clamp8(max(0, d)) for d in shift]);down = luma.point([clamp8(max(0, -d)) for d in shift]);luma.close()
    return Image.merge('RGB', [ImageChops.add(ImageChops.subtract(band, down), up) for band in im.split()])

def vibrance(im, amount):
    """Saturation boost that favours muted colours (and, when negative, mutes the vivid ones first)."""
    from PIL import Image, ImageEnhance
    sat = im.convert('HSV').getchannel('S');strong = ImageEnhance.Color(im).enhance(1 + amount * 1.5 if amount > 0 else 1 + amount * .9)
    mask = sat.point([255 - i for i in range(256)]) if amount > 0 else sat
    return Image.composite(strong, im, mask)

def white_balance(im, temperature, tint):
    """Warm/cool shifts red against blue; tint shifts green against magenta."""
    r = [clamp8(i * (1 + .3 * temperature)) for i in range(256)];g = [clamp8(i * (1 - .2 * tint)) for i in range(256)];b = [clamp8(i * (1 - .3 * temperature)) for i in range(256)]
    return im.point(r + g + b)

def dehaze(im, amount):
    from PIL import ImageEnhance
    out = ImageEnhance.Contrast(im).enhance(1 + amount * .35);out = ImageEnhance.Color(out).enhance(1 + amount * .2);k = amount * .12
    pts = [(0, 0), (.25, max(0, .25 - k)), (.5, .5), (.75, min(1, .75 + k / 2)), (1, 1)]
    def curve(c):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if c <= x1: return y0 + (y1 - y0) * (c - x0) / (x1 - x0)
        return 1.0
    return out.point(lut_all(lambda c: curve(c) - amount * .05))

def reduce_noise(im, amount):
    from PIL import Image, ImageFilter
    return Image.blend(im, im.filter(ImageFilter.MedianFilter(3)), min(1.0, amount))

def clarity(im, amount):
    from PIL import ImageFilter
    radius = max(2.0, max(im.size) * .022);return im.filter(ImageFilter.UnsharpMask(radius=radius, percent=int(amount * 60), threshold=0))

def sharpen(im, amount):
    from PIL import ImageEnhance
    return ImageEnhance.Sharpness(im).enhance(1 + 2 * amount)

def sepia(im, amount):
    from PIL import Image
    tinted = im.convert('RGB', (.393, .769, .189, 0, .349, .686, .168, 0, .272, .534, .131, 0));return Image.blend(im, tinted, min(1.0, amount))

def monochrome(im):
    from PIL import ImageOps, ImageEnhance
    grey = ImageOps.grayscale(im).convert('RGB');return ImageEnhance.Contrast(grey).enhance(1.08)

def vignette(im, amount):
    """Darken towards the corners; the falloff starts about halfway to the edge."""
    from PIL import Image, ImageEnhance
    ramp = Image.radial_gradient('L').resize(im.size, Image.Resampling.BILINEAR).point([clamp8((i - 70) / 185 * 255 * .9) if i > 70 else 0 for i in range(256)])
    dark = ImageEnhance.Brightness(im).enhance(max(0.05, 1 - .65 * amount));return Image.composite(dark, im, ramp)

def grain(im, amount):
    """Soft-light film grain."""
    from PIL import Image, ImageChops
    noise = Image.effect_noise(im.size, 16 * amount + 1)
    bands = [ImageChops.soft_light(b, noise) for b in im.split()];return Image.merge('RGB', bands)

def is_neutral(v):
    return all(v.get(k, LIMITS[k][2]) == LIMITS[k][2] for k in LIMITS) and not v.get('monochrome')

def adjust(im, v):
    """`im` is RGB; `v` holds validated numbers keyed as in LIMITS (missing keys are neutral) plus the monochrome flag."""
    g = lambda k: float(v.get(k, LIMITS[k][2]))
    out = im
    if g('exposure'): out = exposure(out, g('exposure'))
    from PIL import ImageEnhance
    if g('brightness'): out = ImageEnhance.Brightness(out).enhance(1 + g('brightness'))
    if g('contrast'): out = ImageEnhance.Contrast(out).enhance(1 + g('contrast'))
    if g('saturation'): out = ImageEnhance.Color(out).enhance(1 + g('saturation'))
    if g('highlights') or g('shadows'): out = tone(out, g('highlights'), g('shadows'))
    if g('vibrance'): out = vibrance(out, g('vibrance'))
    if g('temperature') or g('tint'): out = white_balance(out, g('temperature'), g('tint'))
    if g('dehaze'): out = dehaze(out, g('dehaze'))
    if g('noise'): out = reduce_noise(out, g('noise'))
    if g('clarity'): out = clarity(out, g('clarity'))
    if g('sharpness'): out = sharpen(out, g('sharpness'))
    if g('sepia'): out = sepia(out, g('sepia'))
    if v.get('monochrome'): out = monochrome(out)
    if g('vignette'): out = vignette(out, g('vignette'))
    if g('grain'): out = grain(out, g('grain'))
    return out
