"""Render the preserved eight-second limestone illustration as local RGBA frames.

This is a fixed, image-registered case recipe. New images or scientific topics
require changing the paths, labels and timing. No model job or media upload.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def make_renderer(image_path, font_path, scale=1):
    if scale not in (1, 2):
        raise ValueError('Use scale 1 (preview) or 2 (native drawing grid).')
    with Image.open(image_path) as probe:
        if probe.size != (1536, 864):
            raise ValueError('The preserved geometry expects the 1536x864 case base.')
    W,H=1080,780;SS=2
    native=Path(image_path)
    picture=Image.open(native).convert('RGB').resize((W*SS,608*SS),Image.Resampling.LANCZOS)
    fonts={n:ImageFont.truetype(str(font_path),n*SS) for n in [24,28,32,36,38]}
    def smooth(x):x=max(0,min(1,x));return x*x*(3-2*x)
    def curve(points,count=300):
     p=np.array([points[0],*points,points[-1]],dtype=float);out=[]
     for i in range(1,len(p)-2):
      for u in np.linspace(0,1,max(2,count//(len(points)-1)),endpoint=False):
       out.append(.5*((2*p[i])+(-p[i-1]+p[i+1])*u+(2*p[i-1]-5*p[i]+4*p[i+1]-p[i+2])*u*u+(-p[i-1]+3*p[i]-3*p[i+1]+p[i+2])*u*u*u))
     out.append(p[-2]);return np.array(out)
    flow=curve([(284,310),(319,318),(356,359),(405,405),(487,447),(590,482),(690,525)])
    deposit=curve([(558,551),(602,546),(647,538),(690,525),(728,512),(762,500)])
    rock=curve([(280,317),(270,333),(277,354),(311,362),(334,349),(340,325),(320,309),(280,317)])
    def pos(a,u):return a[min(len(a)-1,max(0,int(u*(len(a)-1))))]
    def lines(d,pts,fill,width):d.line([tuple(np.array(p)*SS) for p in pts],fill=fill,width=max(1,round(width*SS)),joint='curve')
    def txt(d,xy,text,size=32,fill=(29,56,55,255)):
     d.text(tuple(v*SS for v in xy),text,font=fonts[size],fill=fill,stroke_width=0)
    def pill(d,xy,text,size=32,accent=(32,84,88,255),alpha=1):
     x,y=xy;b=d.textbbox((0,0),text,font=fonts[size]);tw=(b[2]-b[0])/SS;th=size+20
     d.rounded_rectangle((x*SS,y*SS,(x+tw+28)*SS,(y+th)*SS),radius=12*SS,fill=(250,249,243,round(245*alpha)),outline=accent[:3]+(round(150*alpha),),width=SS)
     txt(d,(x+14,y+7),text,size,accent[:3]+(round(255*alpha),));return tw+28,th
    def dot(d,xy,r,fill,outline=None):
     x,y=xy;d.ellipse(((x-r)*SS,(y-r)*SS,(x+r)*SS,(y+r)*SS),fill=fill,outline=outline,width=SS)
    def arrow(d,u,alpha=1):
     a=pos(flow,u);b=pos(flow,min(.999,u+.022));v=b-a;v=v/(np.linalg.norm(v)+.0001);n=np.array([-v[1],v[0]])
     tri=[a+v*10,a-v*7+n*6,a-v*7-n*6];d.polygon([tuple(p*SS) for p in tri],fill=(33,133,177,round(230*alpha)))
    def draw(frame):
        if not 0 <= frame < 240:
            raise ValueError("Frame must be between 0 and 239.")
        t=frame/30
        im=Image.new('RGBA',(W*SS,H*SS),(239,235,226,255));im.paste(picture,(0,95*SS))
        # The base is held stable so arrows, labels and geological targets remain spatially registered.
        layer=Image.new('RGBA',im.size);d=ImageDraw.Draw(layer)
        d.rounded_rectangle((20*SS,15*SS,1060*SS,84*SS),radius=15*SS,fill=(248,248,242,246))
        phase=0 if t<2.48 else (1 if t<4.22 else 2)
        titles=['① 水流过石灰岩','② 钙被带进水里','③ 慢慢沉积成钙华']
        txt(d,(40,28),titles[phase],38)
        txt(d,(927,34),'示意',24,(89,107,102,255))
        # Process progress is grouped into three quiet bars, not a second text-heavy legend.
        for k in range(3):
         d.rounded_rectangle(((40+k*330)*SS,88*SS,(352+k*330)*SS,92*SS),radius=2*SS,fill=(42,112,121,235) if k<=phase else (178,181,170,160))
        # Contact target is explicitly the exposed grey natural rock, not the preexisting ivory tufa rim.
        ra=.8 if t<2.5 else .34
        lines(d,rock,(180,125,54,round(220*ra)),3)
        pill(d,(46,245),'石灰岩',32,(90,75,53,255))
        lines(d,[(183,271),(224,271),(296,333)],(90,75,53,210),2)
        dot(d,(296,333),4,(90,75,53,255))
        reveal=smooth(t/1.6);end=max(2,int(len(flow)*reveal))
        lines(d,flow[:end],(250,255,255,170),9)
        lines(d,flow[:end],(36,137,177,195 if phase<2 else 115),4)
        for k in range(3):
         u=(t*.22+k/3)%1
         if u<reveal:arrow(d,u,.95 if phase<2 else .55)
        if t<2.65:
         a=1-smooth((t-2.25)/.4);pill(d,(420,307),'水流',28,(27,111,151,round(255*a)),a)
        # Dissolved calcium is abstracted as warm dots; same dots travel with the flow then become a thin pale coating.
        if t>=2.42:
         a=smooth((t-2.42)/.25)
         pill(d,(89,481),'溶出的钙',32,(126,84,26,255),a)
         lines(d,[(299,506),(333,506),(422,429)],(126,84,26,round(210*a)),2)
         dot(d,(422,429),4,(177,123,40,round(255*a)))
        for j in range(26):
         born=2.42+j*.125;u=(t-born)/1.85
         if 0<=u<=1:
          x,y=pos(flow,.26+.74*u);y+=math.sin(j*2.1)*5
          r=5.0+((j%3)*.5)
          mix=smooth((u-.82)/.18) if t>=4.22 else 0
          fill=tuple(round(a*(1-mix)+b*mix) for a,b in zip((245,191,77),(255,244,206)))+(255,)
          dot(d,(x,y),r*(1-.45*mix),fill,(109,74,25,255))
          # Flat schematic dots, deliberately no specular highlights.
        # Growth stays a thin coating on the near shore, never a tall wall or instant dam.
        growth=smooth((t-4.22)/2.7)
        if growth>0:
         center=int(len(deposit)*.67);left=max(0,int(center*(1-growth)));right=min(len(deposit),center+max(2,int((len(deposit)-center)*growth)));seg=deposit[left:right]
         lines(d,seg,(166,122,49,230),9)
         lines(d,seg,(255,244,206,255),6)
         # Small uneven pale accretions are attached to the rim, not floating crystals.
         for j in range(int(45*growth)):
          x,y=pos(deposit,j/44);dot(d,(x,y+math.sin(j*1.7)*2),2.2+(j%3)*.45,(248,235,192,255))
         if t<6.35:
          pill(d,(744,556),'碳酸钙沉积',28,(108,85,40,255))
         else:
          pill(d,(762,550),'钙华沉积',36,(100,77,34,255))
         lines(d,[(776,552),(767,537),(728,514)],(130,96,43,240),2)
         dot(d,(728,514),4,(156,113,47,255))
         # A concise condition prevents the graphic from suggesting unconditional precipitation.
         txt(d,(294,723),'条件合适时，逐渐沉积',28,(71,83,75,255))
        else:
         pass
        im=Image.alpha_composite(im,layer).resize((W*scale,H*scale),Image.Resampling.LANCZOS)
        a=Image.new('L',(W*scale,H*scale));da=ImageDraw.Draw(a);da.rounded_rectangle((0,0,W*scale-1,H*scale-1),radius=22*scale,fill=255)
        fade=smooth(t/.18)*smooth((8-t)/.20);im.putalpha(a.point(lambda v:round(v*fade)))

        return im
    return draw


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scale', type=int, choices=[1, 2], default=1)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--frames', type=int, nargs='+')
    selection.add_argument('--all-frames', action='store_true')
    args = parser.parse_args()
    frames = list(range(240)) if args.all_frames else (args.frames or [45, 90, 147, 207, 228])
    if len(set(frames)) != len(frames) or any(f < 0 or f >= 240 for f in frames):
        parser.error('Choose unique frame indices between 0 and 239.')
    draw = make_renderer(args.image, args.font, args.scale)
    args.output.mkdir(parents=True, exist_ok=False)
    for frame in frames:
        draw(frame).save(args.output / f'{frame:04d}.png')
    receipt = {'kind':'fixed_limestone_case_rgba_frames', 'fps':30, 'frames_written':frames,
               'complete_sequence':len(frames)==240, 'size':[1080*args.scale,780*args.scale],
               'image_sha256':sha(args.image), 'font_sha256':sha(args.font),
               'renderer_sha256':sha(__file__), 'color':'sRGB with straight alpha; convert explicitly when compositing to SDR BT.709',
               'human_reviewed':False, 'generated_voice':False, 'model_job_submitted':False}
    (args.output/'render_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
