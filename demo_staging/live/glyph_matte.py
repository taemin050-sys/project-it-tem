"""Model-generated glyph matte compositing; never a font or spelling renderer.

A flat text specimen avoids asking an image model to relight an advertisement.
Only the deliberate ROI is restored into the source. Occluded background is
estimated from the surrounding band, so busy/ambiguous backgrounds fail closed
and the result always requires human review.
"""
from io import BytesIO
from PIL import Image, ImageDraw
from .contracts import LiveGateError

def png(im):
    b=BytesIO();im.save(b,'PNG');return b.getvalue()

def _lum(p):return sum(p)/3

def prepare(source,box):
    im=Image.open(BytesIO(source)).convert('RGB');w,h=im.size
    l,t,r,b=box
    if w>1536 or b-t>480:raise LiveGateError('MATTE_CONTEXT_TOO_LARGE')
    top=max(0,t-20);bottom=min(h-1,b+20);left=(1536-w)//2;offset=(1024-(bottom-top+1))//2
    # Fit a local vertical background surface from rows outside the text.
    border=[im.getpixel((x,y)) for x in range(l,r) for y in (top,bottom)]
    background=tuple(sum(p[c] for p in border)/len(border) for c in range(3))
    colors=sorted([im.getpixel((x,y)) for y in range(t,b) for x in range(l,r)],key=_lum)
    candidates=[colors[len(colors)//50],colors[min(len(colors)-1,len(colors)*49//50)]]
    ink=max(candidates,key=lambda p:abs(_lum(p)-_lum(background)))
    contrast=_lum(background)-_lum(ink)
    if abs(contrast)<45:raise LiveGateError('MATTE_TEXT_CONTRAST_AMBIGUOUS')
    def bg(x,y):
        f=(y-top)/(bottom-top)
        a,z=im.getpixel((x,top)),im.getpixel((x,bottom))
        return tuple(a[c]*(1-f)+z[c]*f for c in range(3))
    canvas=Image.new('RGB',(1536,1024),'white')
    for y in range(top,bottom+1):
        for x in range(w):
            alpha=max(0,min(1,(_lum(bg(x,y))-_lum(im.getpixel((x,y))))/contrast))
            v=round(255*(1-alpha));canvas.putpixel((x+left,y-top+offset),(v,v,v))
    mask=Image.new('RGBA',canvas.size,(255,255,255,255))
    mapped=(l+left,t-top+offset,r+left,b-top+offset)
    ImageDraw.Draw(mask).rectangle((mapped[0],mapped[1],mapped[2]-1,mapped[3]-1),fill=(255,255,255,0))
    geometry={'version':'glyph-matte-v1','native_box':list(box),'provider_box':list(mapped),
        'band':[top,bottom],'offset':[left,offset],'ink_rgb':list(ink),'contrast':contrast}
    return png(canvas),png(mask),geometry

def compose(source,generated,geometry):
    original=Image.open(BytesIO(source)).convert('RGB');model=Image.open(BytesIO(generated)).convert('RGB')
    if model.size!=(1536,1024):raise LiveGateError('MATTE_MODEL_SIZE_CHANGED')
    l,t,r,b=geometry['native_box'];ml,mt,mr,mb=geometry['provider_box'];top,bottom=geometry['band'];ink=geometry['ink_rgb'];contrast=geometry['contrast']
    out=original.copy();changed=0;new_ink=0
    for y in range(t,b):
        for x in range(l,r):
            p=model.getpixel((ml+x-l,mt+y-t))
            if max(p)-min(p)>24:raise LiveGateError('MATTE_MODEL_NOT_NEUTRAL')
            alpha=max(0,min(1,1-_lum(p)/255))
            if alpha<.04:alpha=0
            f=(y-top)/(bottom-top);a,z=original.getpixel((x,top)),original.getpixel((x,bottom))
            bg=tuple(a[c]*(1-f)+z[c]*f for c in range(3));old=original.getpixel((x,y))
            old_alpha=max(0,min(1,(_lum(bg)-_lum(old))/contrast))
            # Leave visible source background exact, reconstruct only old ink.
            base=bg if old_alpha>.04 else old
            v=tuple(max(0,min(255,round(base[c]*(1-alpha)+ink[c]*alpha))) for c in range(3))
            out.putpixel((x,y),v);changed+=v!=old;new_ink+=alpha>.5
    if not new_ink:raise LiveGateError('MATTE_NO_CORRECTED_GLYPH')
    return png(out),{'changed_pixels':changed,'new_ink_pixels':new_ink,'outside_roi_exact':True,
        'background_method':'source_pixels_and_local_band_interpolation','font_renderer':None,
        'glyph_origin':'ACTUAL_IMAGE_MODEL','style_acceptance':'HUMAN_REVIEW_REQUIRED'}
