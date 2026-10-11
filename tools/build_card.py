#!/usr/bin/env python3
"""Build every generated asset for the NFC business card from card/profile.json.

Outputs (in card/):
  front.jpg, back.jpg   card faces (used by the web page and the AR model)
  avatar.jpg            monogram photo embedded in the contact
  contact.vcf           contact card (opens the native iOS contact sheet)
  card.usdz             animated metal card for AR Quick Look

Requires: pip install usd-core pillow qrcode numpy
"""
import base64
import io
import json
import math
import os
import shutil
import tempfile

import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARD = os.path.join(ROOT, "card")
P = json.load(open(os.path.join(CARD, "profile.json"), encoding="utf-8"))
FULL = " ".join(x for x in [P["firstName"], P.get("lastName", "")] if x).strip()
INITIAL = (P["firstName"][:1] or "S").upper()

W, H = 2048, 1292  # ISO card ratio 85.6 x 54
SILVER_HI, SILVER_LO = (242, 242, 245), (150, 150, 156)
GRAY, GRAY_DIM = (142, 142, 147), (104, 104, 110)


# ---------- fonts (Linux paths first, macOS fallbacks) ----------
def font(kind, size):
    cands = {
        "display": ["/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf",
                    "/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc"],
        "medium": ["/usr/share/fonts/opentype/inter/Inter-Medium.otf",
                   "/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc"],
        "mono": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                 "/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Menlo.ttc"],
    }[kind]
    for c in cands:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default(size)


# ---------- drawing helpers ----------
def brushed_base(seed):
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, (H, W)).astype(np.float32)
    # horizontal brushing: heavy blur along x only
    k = 181
    kernel = np.ones(k, np.float32) / k
    noise = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="same"), 1, noise)
    noise = noise / (np.abs(noise).max() + 1e-6)
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    base = 15 + 9 * (1 - y) + 5 * x + 7 * noise
    rgb = np.stack([base, base, base * 1.03], -1).clip(0, 255).astype(np.uint8)
    rough = (120 + 18 * noise).clip(0, 255).astype(np.uint8)  # ~0.47 matte
    return Image.fromarray(rgb, "RGB"), Image.fromarray(rough, "L")


def spaced(draw, xy, text, fnt, fill, spacing):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing
    return x


def spaced_width(draw, text, fnt, spacing):
    return sum(draw.textlength(c, font=fnt) + spacing for c in text) - spacing


def gradient_text(img, rough, xy, text, fnt):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(xy, text, font=fnt, fill=255)
    bbox = mask.getbbox()
    grad = Image.new("RGB", img.size)
    gd = ImageDraw.Draw(grad)
    top, bot = bbox[1], bbox[3]
    for yy in range(top, bot + 1):
        t = (yy - top) / max(1, bot - top)
        c = tuple(int(SILVER_HI[i] * (1 - t) + SILVER_LO[i] * t) for i in range(3))
        gd.line([(0, yy), (W, yy)], fill=c)
    img.paste(grad, (0, 0), mask)
    rough.paste(30, (0, 0), mask)  # polished


def contactless(draw, rdraw, cx, cy, s):
    for i in range(4):
        r = s * (0.28 + i * 0.24)
        box = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(box, -42, 42, fill=SILVER_LO, width=int(s * 0.075))
        rdraw.arc(box, -42, 42, fill=30, width=int(s * 0.075))


def frame(draw, rdraw):
    m = 56
    draw.rounded_rectangle([m, m, W - m, H - m], radius=46, outline=(78, 78, 84), width=5)
    rdraw.rounded_rectangle([m, m, W - m, H - m], radius=46, outline=40, width=5)


def monogram(img, rough, cx, cy, d):
    draw, rdraw = ImageDraw.Draw(img), ImageDraw.Draw(rough)
    box = [cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2]
    draw.ellipse(box, outline=SILVER_LO, width=7)
    rdraw.ellipse(box, outline=30, width=7)
    f = font("display", int(d * 0.56))
    tw = draw.textlength(INITIAL, font=f)
    asc, desc = f.getmetrics()
    gradient_text(img, rough, (cx - tw / 2, cy - (asc + desc) / 2 - d * 0.02), INITIAL, f)


def front():
    img, rough = brushed_base(7)
    d, rd = ImageDraw.Draw(img), ImageDraw.Draw(rough)
    frame(d, rd)
    monogram(img, rough, 230, 236, 190)
    contactless(d, rd, W - 250, 236, 150)
    name_f = font("display", 220 if len(FULL) <= 12 else int(220 * 12 / len(FULL)))
    gradient_text(img, rough, (150, 600), FULL, name_f)
    title_f = font("medium", 60)
    spaced(d, (156, 900), P["title"].upper(), title_f, GRAY, 9)
    spaced(rd, (156, 900), P["title"].upper(), title_f, 50, 9)
    loc_f = font("mono", 52)
    d.text((156, 1120), P.get("location", ""), font=loc_f, fill=GRAY_DIM)
    host = P["url"].split("//")[-1].split("/")[0]
    tw = d.textlength(host, font=loc_f)
    d.text((W - 156 - tw, 1120), host, font=loc_f, fill=GRAY_DIM)
    return img, rough


def back():
    img, rough = brushed_base(11)
    d, rd = ImageDraw.Draw(img), ImageDraw.Draw(rough)
    frame(d, rd)
    q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1)
    q.add_data(P["url"])
    q.make(fit=True)
    m = np.array(q.get_matrix(), dtype=bool)
    size = 640
    cell = size // m.shape[0]
    size = cell * m.shape[0]
    x0, y0 = (W - size) // 2, 250
    for (r, c), on in np.ndenumerate(m):
        if on:
            box = [x0 + c * cell, y0 + r * cell, x0 + (c + 1) * cell - 1, y0 + (r + 1) * cell - 1]
            d.rectangle(box, fill=(228, 228, 234))
            rd.rectangle(box, fill=30)
    lab_f = font("medium", 44)
    label = "ESCANEA · GUARDA MI CONTACTO"
    tw = spaced_width(d, label, lab_f, 8)
    spaced(d, ((W - tw) / 2, 140), label, lab_f, GRAY, 8)
    url_f = font("mono", 48)
    u = P["url"].split("//")[-1].rstrip("/")
    tw = d.textlength(u, font=url_f)
    d.text(((W - tw) / 2, y0 + size + 60), u, font=url_f, fill=GRAY_DIM)
    monogram(img, rough, W // 2, H - 180, 120)
    return img, rough


def avatar():
    s = 600
    img = Image.new("RGB", (s, s), (14, 14, 16))
    g = Image.new("L", (s, s), 0)
    ImageDraw.Draw(g).ellipse([-s * 0.2, -s * 0.4, s * 1.0, s * 0.8], fill=60)
    img.paste((40, 40, 46), (0, 0), g.filter(ImageFilter.GaussianBlur(80)))
    f = font("display", 330)
    d = ImageDraw.Draw(img)
    tw = d.textlength(INITIAL, font=f)
    asc, desc = f.getmetrics()
    rough = Image.new("L", (s, s))
    big = img.resize((W, H))  # gradient_text works on full card size; draw on a temp canvas instead
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).text(((s - tw) / 2, (s - asc - desc) / 2 - 10), INITIAL, font=f, fill=255)
    grad = Image.new("RGB", (s, s))
    gd = ImageDraw.Draw(grad)
    for yy in range(s):
        t = yy / s
        gd.line([(0, yy), (s, yy)], fill=tuple(int(SILVER_HI[i] * (1 - t) + SILVER_LO[i] * t) for i in range(3)))
    img.paste(grad, (0, 0), mask)
    return img


# ---------- vCard ----------
def vcard(photo_jpg):
    b64 = base64.b64encode(photo_jpg).decode()
    lines = [
        "BEGIN:VCARD", "VERSION:3.0",
        f"N:{P.get('lastName', '')};{P['firstName']};;;",
        f"FN:{FULL}",
        f"TITLE:{P['title']}",
        f"TEL;TYPE=CELL,VOICE:{P['phone']}",
    ]
    if P.get("email"):
        lines.append(f"EMAIL;TYPE=INTERNET:{P['email']}")
    lines.append(f"item1.URL:{P['url']}")
    lines.append("item1.X-ABLabel:Tarjeta")
    n = 2
    for key, label in [("linkedin", "LinkedIn"), ("github", "GitHub")]:
        if P.get(key):
            lines.append(f"item{n}.URL:{P[key]}")
            lines.append(f"item{n}.X-ABLabel:{label}")
            n += 1
    photo = f"PHOTO;ENCODING=b;TYPE=JPEG:{b64}"
    folded = [photo[:75]] + [" " + photo[i:i + 74] for i in range(75, len(photo), 74)]
    lines += folded
    lines.append("END:VCARD")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


# ---------- AR model ----------
def build_usdz(front_jpg, front_rough, back_jpg, back_rough, out_path):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils

    tmp = tempfile.mkdtemp()
    for name, im in [("front.jpg", front_jpg), ("front_r.jpg", front_rough),
                     ("back.jpg", back_jpg), ("back_r.jpg", back_rough)]:
        im.convert("RGB").resize((1536, 969), Image.LANCZOS).save(os.path.join(tmp, name), quality=88)

    cw, ch, ct, cr = 0.32, 0.32 * 54 / 85.6, 0.007, 0.32 * 3.18 / 85.6  # oversized card, metres
    seg = 10
    ring = []
    corners = [(cw / 2 - cr, ch / 2 - cr, 0), (-cw / 2 + cr, ch / 2 - cr, 90),
               (-cw / 2 + cr, -ch / 2 + cr, 180), (cw / 2 - cr, -ch / 2 + cr, 270)]
    for cx, cy, a0 in corners:
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            ring.append((cx + cr * math.cos(a), cy + cr * math.sin(a), math.cos(a), math.sin(a)))
    n = len(ring)

    usdc = os.path.join(tmp, "card.usdc")
    stage = Usd.Stage.CreateNew(usdc)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    frames = 360
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(frames)
    stage.SetTimeCodesPerSecond(30)
    root = UsdGeom.Xform.Define(stage, "/Card")
    stage.SetDefaultPrim(root.GetPrim())
    spin = UsdGeom.Xform.Define(stage, "/Card/Spin")
    t_op, ry_op, rx_op = spin.AddTranslateOp(), spin.AddRotateYOp(), spin.AddRotateXOp()
    rx_op.Set(-6.0)
    for f in range(frames + 1):
        t = f / frames
        t_op.Set(Gf.Vec3d(0, 0.20 + 0.012 * math.sin(4 * math.pi * t), 0), f)
        ry_op.Set(360.0 * t, f)

    def material(name, tex=None, rough_tex=None):
        mat = UsdShade.Material.Define(stage, f"/Card/{name}")
        sh = UsdShade.Shader.Define(stage, f"/Card/{name}/PBR")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(1.0)
        if tex:
            st = UsdShade.Shader.Define(stage, f"/Card/{name}/st")
            st.CreateIdAttr("UsdPrimvarReader_float2")
            st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
            for asset, inp, out, cs in [(tex, "diffuseColor", "rgb", "sRGB"), (rough_tex, "roughness", "r", "raw")]:
                tx = UsdShade.Shader.Define(stage, f"/Card/{name}/{inp}Tex")
                tx.CreateIdAttr("UsdUVTexture")
                tx.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(f"./{asset}")
                tx.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set(cs)
                tx.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
                otype = Sdf.ValueTypeNames.Float3 if out == "rgb" else Sdf.ValueTypeNames.Float
                tx.CreateOutput(out, otype)
                itype = Sdf.ValueTypeNames.Color3f if out == "rgb" else Sdf.ValueTypeNames.Float
                sh.CreateInput(inp, itype).ConnectToSource(tx.ConnectableAPI(), out)
        else:
            sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.62, 0.62, 0.66))
            sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.22)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        return mat

    def face(path, z, facing, tex, rtex, mirror):
        pts = [(0.0, 0.0)] + [(p[0], p[1]) for p in ring]
        tris = []
        for i in range(n):
            a, b = 1 + i, 1 + (i + 1) % n
            tris += [0, a, b] if facing > 0 else [0, b, a]
        m = UsdGeom.Mesh.Define(stage, path)
        m.CreatePointsAttr([Gf.Vec3f(x, y, z) for x, y in pts])
        m.CreateFaceVertexCountsAttr([3] * n)
        m.CreateFaceVertexIndicesAttr(tris)
        m.CreateNormalsAttr([Gf.Vec3f(0, 0, facing)] * len(pts))
        m.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        m.CreateExtentAttr([Gf.Vec3f(-cw / 2, -ch / 2, z), Gf.Vec3f(cw / 2, ch / 2, z)])
        uv = []
        for x, y in pts:
            u = x / cw + 0.5
            uv.append(Gf.Vec2f(1 - u if mirror else u, y / ch + 0.5))
        pv = UsdGeom.PrimvarsAPI(m).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
        pv.Set(uv)
        UsdShade.MaterialBindingAPI.Apply(m.GetPrim()).Bind(material(path.split("/")[-1] + "Mat", tex, rtex))

    spin_path = "/Card/Spin"
    face(f"{spin_path}/Front", ct / 2, 1, "front.jpg", "front_r.jpg", False)
    face(f"{spin_path}/Back", -ct / 2, -1, "back.jpg", "back_r.jpg", True)

    edge = UsdGeom.Mesh.Define(stage, f"{spin_path}/Edge")
    pts, nrm, idx = [], [], []
    for x, y, nx, ny in ring:
        pts += [Gf.Vec3f(x, y, ct / 2), Gf.Vec3f(x, y, -ct / 2)]
        nrm += [Gf.Vec3f(nx, ny, 0)] * 2
    for i in range(n):
        j = (i + 1) % n
        idx += [2 * i, 2 * i + 1, 2 * j + 1, 2 * j]
    edge.CreatePointsAttr(pts)
    edge.CreateFaceVertexCountsAttr([4] * n)
    edge.CreateFaceVertexIndicesAttr(idx)
    edge.CreateNormalsAttr(nrm)
    edge.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    edge.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    edge.CreateExtentAttr([Gf.Vec3f(-cw / 2, -ch / 2, -ct / 2), Gf.Vec3f(cw / 2, ch / 2, ct / 2)])
    UsdShade.MaterialBindingAPI.Apply(edge.GetPrim()).Bind(material("EdgeMat"))

    stage.GetRootLayer().Save()
    ok = UsdUtils.CreateNewARKitUsdzPackage(usdc, out_path)
    shutil.rmtree(tmp, ignore_errors=True)
    return ok


def main():
    f_img, f_rough = front()
    b_img, b_rough = back()
    # web copies pre-scaled for ~400px cards on 3x screens (browsers filter poorly inside 3D transforms)
    web = (1240, int(1240 * H / W))
    f_img.resize(web, Image.LANCZOS).save(os.path.join(CARD, "front.jpg"), quality=90)
    b_img.resize(web, Image.LANCZOS).save(os.path.join(CARD, "back.jpg"), quality=90)
    av = avatar()
    buf = io.BytesIO()
    av.resize((400, 400), Image.LANCZOS).save(buf, "JPEG", quality=85)
    av.save(os.path.join(CARD, "avatar.jpg"), quality=88)
    open(os.path.join(CARD, "contact.vcf"), "wb").write(vcard(buf.getvalue()))
    ok = build_usdz(f_img, f_rough, b_img, b_rough, os.path.join(CARD, "card.usdz"))
    print("built:", ", ".join(sorted(os.listdir(CARD))), "| usdz ok:", ok)


if __name__ == "__main__":
    main()
