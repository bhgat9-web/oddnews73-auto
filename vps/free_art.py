"""Original no-fee, story-specific illustrations drawn locally with Pillow.

Deliberately narrow visual vocabulary: reject unsupported stories instead of
inventing unrelated stock graphics. No remote images, AI-image fees or downloads.
"""
from __future__ import annotations
import hashlib
import io
import math
import random
import re
from PIL import Image, ImageDraw, ImageFilter

W,H=1080,1350
PALETTES={
    "deep_sea": ((4,23,49),(8,72,103),(77,213,224)),
    "fish": ((5,33,65),(6,106,137),(244,184,71)),
    "snake": ((16,43,42),(43,102,66),(223,184,86)),
    "flower": ((27,30,58),(102,69,99),(233,173,112)),
    "archaeology": ((53,39,48),(154,97,65),(238,191,119)),
    "fossil": ((50,43,47),(146,99,68),(233,175,108)),
    "space": ((10,15,47),(39,44,101),(245,177,97)),
    "nature": ((9,45,54),(43,101,71),(205,220,134)),
}


def category(title: str) -> str | None:
    """Require meaningful subject words, NOT an ambiguous 'weird' headline."""
    s=title.lower()
    if any(x in s for x in ("submarine","submersible","underwater","deep sea","trench")):
        return "deep_sea"
    if any(x in s for x in ("burbot","fish","shark","whale","octopus","jellyfish")):
        return "fish"
    if any(x in s for x in ("snake","serpent","python","cobra")):
        return "snake"
    if any(x in s for x in ("flower","petal","bloom","pollen","plant fossil")):
        return "flower"
    if any(x in s for x in ("burial","tomb","grave","cemetery","sutton hoo","archaeolog")):
        return "archaeology"
    if any(x in s for x in ("fossil","prehistoric","dinosaur","amber")):
        return "fossil"
    if any(x in s for x in ("comet","asteroid","meteor","planet","moon","star","galaxy")):
        return "space"
    if any(x in s for x in ("forest","tree","mushroom","fungus")):
        return "nature"
    return None


def lerp(a,b,t):
    return tuple(round(x*(1-t)+y*t) for x,y in zip(a,b))


def ellipse(d,xy,fill,outline=None,width=1):
    d.ellipse(tuple(map(int,xy)),fill=fill,outline=outline,width=width)


def backdrop(d,kind,seed):
    rng=random.Random(seed)
    c0,c1,accent=PALETTES[kind]
    for y in range(H):
        t=min(1, y/H)
        tone=lerp(c0,c1, math.pow(t,.85))
        d.line((0,y,W,y),fill=tone)
    for _ in range(92):
        x=rng.randrange(40,W-40); y=rng.randrange(160,H-130)
        radius=rng.choice([1,1,2,3])
        col=lerp(c0,accent,rng.uniform(.12,.31))
        ellipse(d,(x-radius,y-radius,x+radius,y+radius),col)
    for k in range(6):
        x=rng.randint(50,W-50); y=rng.randint(280,H-80)
        rr=rng.randint(30,120)
        d.arc((x-rr,y-rr,x+rr,y+rr),0,260,
              fill=lerp(c0,accent,.12),width=2)
    return accent


def fish(d,rng,accent):
    # Detailed side-profile: body, fins, gills, scales and bioluminescent bubbles.
    for _ in range(23):
        x=rng.randrange(25,W); y=rng.randrange(285,1170); z=rng.randrange(3,11)
        ellipse(d,(x,y,x+z,y+z),(89,171,185),width=1)
    for k in range(7):
        y=970+k*35
        d.arc((-90,y,1170,y+240),185,348,fill=(18,140,154),width=3)
    d.polygon([(780,625),(1045,455),(1030,860)],fill=(195,119,36))
    d.polygon([(385,520),(580,325),(710,553)],fill=(245,169,53))
    d.polygon([(370,715),(610,930),(710,770)],fill=(234,139,46))
    ellipse(d,(245,440,840,825),(241,170,61),outline=(255,221,116),width=9)
    ellipse(d,(300,487,765,785),(236,183,93))
    d.polygon([(240,570),(155,614),(250,685)],fill=(233,147,68))
    for row in range(5):
        for col in range(8):
            x=395+col*44+(row%2)*21; y=528+row*43
            if ((x-545)/240)**2+((y-634)/160)**2<1:
                d.arc((x-20,y-20,x+38,y+35),50,290,fill=(158,96,36),width=3)
    ellipse(d,(335,558,374,601),(11,31,48),outline=(253,233,168),width=5)
    ellipse(d,(346,566,357,580),(255,255,232))
    for x in (408,434):
        d.arc((x,557,x+40,710),100,270,fill=(130,80,44),width=4)


def submarine(d,rng,accent):
    # ROV with dual thrusters and two spotlights aimed at volcanic sea-floor.
    d.polygon([(0,1120),(240,1015),(500,1080),(735,980),(1080,1080),(1080,1350),(0,1350)],
              fill=(17,56,67))
    for x,y,r in [(115,1072,86),(350,1130,65),(780,1060,108),(1005,1102,61)]:
        d.polygon([(x-r,y+r),(x-r//2,y-r//2),(x+15,y-r),(x+r,y+r)],
                  fill=(50,87,85))
        d.line((x-r//2,y-r//2,x+r//2,y+r//2),fill=(127,170,135),width=5)
    d.polygon([(295,710),(40,940),(350,852)], fill=(55,150,164))
    d.polygon([(715,735),(1060,985),(700,840)],fill=(55,150,164))
    d.line((250,730,800,730),fill=(83,209,212),width=12)
    d.rounded_rectangle((250,555,820,790),radius=48,fill=(232,151,75),outline=(250,219,153),width=9)
    d.rounded_rectangle((335,608,730,746),radius=30,fill=(29,70,83),outline=(111,210,219),width=9)
    for x in (285,750):
        ellipse(d,(x-54,585,x+54,710),(9,44,63),outline=(202,215,168),width=12)
        for k in range(6):
            a=k*math.pi/3; xx=x+36*math.cos(a); yy=645+36*math.sin(a)
            d.line((x,645,xx,yy),fill=(108,181,178),width=7)
    for x in (330,745):
        ellipse(d,(x-30,750,x+30,808),(249,215,129),outline=(255,248,206),width=5)
    for _ in range(32):
        x=rng.randint(60,1020);y=rng.randint(850,1115)
        ellipse(d,(x,y,x+5,y+5),(81,168,159))
    d.line((540,554,535,465,660,465),fill=(111,197,212),width=8)
    ellipse(d,(650,445,675,471),(249,202,105))


def snake(d,rng,accent):
    # A visibly coiled snake, rather than a generic eye/orbit symbol.
    d.polygon([(0,1080),(320,995),(670,1100),(1080,1025),(1080,1350),(0,1350)],fill=(38,78,51))
    for width,col in [(114,(112,145,63)),(87,(218,191,96)),(13,(87,101,44))]:
        points=[]
        for t in range(350):
            a=math.pi*.18+t/350*math.pi*3.9
            rr=310*(1-t/520)
            x=548+rr*math.cos(a);y=777+rr*.64*math.sin(a)
            points.append((int(x),int(y)))
        d.line(points,fill=col,width=width,joint="curve")
    for k in range(60):
        a=k*.58
        r=100+(k%12)*14
        x=548+r*math.cos(a); y=757+r*.61*math.sin(a)
        ellipse(d,(x-8,y-8,x+8,y+8),(241,213,127))
    d.polygon([(550,595),(615,517),(706,517),(754,575),(734,637),(645,650)],
              fill=(198,175,92))
    ellipse(d,(675,546,702,565),(24,44,36),outline=(250,223,129),width=3)
    d.line((735,620,770,648,798,635),fill=(233,113,105),width=5)


def flower(d,rng,accent):
    d.rounded_rectangle((140,290,975,1200),radius=115,fill=(156,108,83),outline=(236,187,121),width=22)
    d.rounded_rectangle((198,355,916,1144),radius=95,fill=(84,68,85),outline=(200,153,113),width=7)
    cx,cy=545,775
    d.line((cx,800,cx-68,1055),fill=(222,156,103),width=19)
    d.line((cx-30,920,cx-176,869),fill=(220,151,107),width=9)
    d.line((cx-44,974,cx+135,945),fill=(220,151,107),width=9)
    for a in range(9):
        ang=a*math.tau/9
        px=cx+165*math.cos(ang);py=cy+165*math.sin(ang)
        ellipse(d,(px-102,py-102,px+102,py+102),
                (228,156,117),outline=(250,203,141),width=6)
    ellipse(d,(cx-92,cy-92,cx+92,cy+92),(118,78,76),outline=(255,205,137),width=17)
    for j in range(15):
        a=j*math.tau/15
        x=cx+57*math.cos(a);y=cy+57*math.sin(a)
        ellipse(d,(x-6,y-6,x+6,y+6),(243,206,144))
    for _ in range(42):
        x=rng.randint(226,879);y=rng.randint(390,1100)
        ellipse(d,(x,y,x+4,y+4),(211,163,120))


def archaeology(d,rng,accent):
    for k in range(22):
        y=465+k*31
        col=lerp((117,70,52),(215,157,104),k/25)
        d.line((0,y,W,y+int(22*math.sin(k*.6))),fill=col,width=32)
    # Excavated outline traced in earth, with an associated pottery vessel.
    d.ellipse((214,565,864,1080),outline=(254,223,153),width=27)
    d.ellipse((248,587,825,1049),outline=(76,50,52),width=14)
    d.line((537,570,542,1025),fill=(82,64,68),width=17)
    d.arc((388,722,688,995),10,175,fill=(252,197,123),width=12)
    d.polygon([(715,835),(861,825),(889,1052),(687,1045)],fill=(153,88,65))
    d.arc((708,812,872,870),0,180,fill=(248,207,148),width=12)
    for i in range(6):
        x=711+i*26
        d.line((x,887,x+12,1019),fill=(223,148,97),width=5)
    for _ in range(45):
        x=rng.randrange(50,W-50);y=rng.randrange(480,1250)
        rr=rng.randrange(2,11)
        ellipse(d,(x-rr,y-rr,x+rr,y+rr),(235,188,129))


def fossil(d,rng,accent):
    d.rounded_rectangle((120,335,990,1190),radius=100,fill=(145,102,74),
                        outline=(244,199,142),width=22)
    d.rounded_rectangle((210,430,895,1100),radius=85,fill=(88,70,67),
                        outline=(184,135,91),width=8)
    cx,cy=540,725
    d.arc((320,540,780,960),40,315,fill=(241,204,158),width=18)
    for k in range(11):
        a=math.radians(52+k*24)
        x=cx+160*math.cos(a);y=cy+165*math.sin(a)
        d.line((cx,cy,x,y),fill=(241,202,146),width=11)
        ellipse(d,(x-14,y-14,x+14,y+14),(246,212,169))
    for _ in range(27):
        x=rng.randint(220,870);y=rng.randint(445,1075)
        ellipse(d,(x,y,x+6,y+6),(224,165,103))


def space(d,rng,accent):
    for k in range(75):
        x=rng.randrange(30,W-30);y=rng.randrange(235,H-120);r=rng.choice([1,2,3,4])
        ellipse(d,(x-r,y-r,x+r,y+r),(186,181,195))
    ellipse(d,(320,470,880,1030),(175,123,112),outline=(248,204,147),width=8)
    ellipse(d,(340,505,846,995),(210,151,119))
    for x,y,r in [(500,620,66),(700,785,38),(450,830,46),(790,631,19)]:
        ellipse(d,(x-r,y-r,x+r,y+r),(134,110,119),outline=(221,180,145),width=4)
    d.polygon([(0,820),(180,740),(280,765),(0,925)],fill=(253,187,111))
    d.polygon([(0,840),(240,778),(275,785),(0,915)],fill=(243,214,173))


def nature(d,rng,accent):
    d.polygon([(0,1000),(320,830),(670,925),(1080,730),(1080,1350),(0,1350)],fill=(27,72,58))
    for i,(x,y) in enumerate([(120,1000),(450,925),(780,1010),(975,900)]):
        d.line((x,y,x,y-360),fill=(131,91,67),width=25)
        for k in range(7):
            a=k*math.tau/7
            r=140+(k%2)*28
            ellipse(d,(x+r*math.cos(a)-125,y-435+r*.75*math.sin(a)-95,
                       x+r*math.cos(a)+125,y-435+r*.75*math.sin(a)+95),
                       (47+i*5,126+i*8,93),outline=(144,184,112),width=5)


DRAWERS={"deep_sea":submarine,"fish":fish,"snake":snake,"flower":flower,
         "archaeology":archaeology,"fossil":fossil,"space":space,"nature":nature}


def render(title: str) -> bytes:
    kind=category(title)
    if not kind:
        raise ValueError("No source-specific original illustration available for this subject")
    seed=int(hashlib.sha256(title.encode("utf-8")).hexdigest()[:10],16)
    rng=random.Random(seed)
    image=Image.new("RGB",(W,H))
    d=ImageDraw.Draw(image)
    accent=backdrop(d,kind,seed)
    DRAWERS[kind](d,rng,accent)
    out=io.BytesIO()
    image.save(out,format="PNG",optimize=True)
    return out.getvalue()
