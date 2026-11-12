"""Model-generated glyph matte compositing; never a font or spelling renderer.

A flat text specimen avoids asking an image model to relight an advertisement.
Only the deliberate ROI is restored into the source. Occluded background is
estimated from the surrounding band, so busy/ambiguous backgrounds fail closed
and the result always requires human review.
"""
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps, ImageFilter, ImageChops
from .contracts import LiveGateError

def png(im):
    b=BytesIO();im.save(b,'PNG');return b.getvalue()

def _lum(p):return sum(p)/3

def prepare(source,box,*,fit=False,lines=1):
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
    if fit:
        geometry.update(version='glyph-matte-fit-v2',text_lines=lines)
        coverage=_source_coverage(im,geometry)
        canvas=Image.new('RGB',(1536,1024),'white')
        canvas.paste(ImageOps.invert(coverage).convert('RGB'),mapped[:2])
    return png(canvas),png(mask),geometry

def _text_components(alpha,width,height,lines):
    """Keep glyph components; reject tall foliage and long underline ornaments."""
    w,h=alpha.size;active=bytearray(alpha.point(lambda a:255 if a>=96 else 0).tobytes())
    result=bytearray(w*h)
    for seed in range(len(active)):
        if not active[seed]:continue
        active[seed]=0;todo=[seed];pixels=[];l=w;t=h;r=b=0
        while todo:
            i=todo.pop();pixels.append(i);x,y=i%w,i//w
            l=min(l,x);r=max(r,x+1);t=min(t,y);b=max(b,y+1)
            for yy in range(max(0,y-1),min(h,y+2)):
                for xx in range(max(0,x-1),min(w,x+2)):
                    n=yy*w+xx
                    if active[n]:active[n]=0;todo.append(n)
        if len(pixels)<2:continue
        if b-t>height/max(1,lines)*1.6:continue
        if r-l>width*.22 and r-l>6*(b-t):continue
        for i in pixels:result[i]=255
    keep=Image.frombytes('L',(w,h),bytes(result)).filter(ImageFilter.MaxFilter(3))
    return ImageChops.multiply(alpha,keep)

def _background(original,geometry):
    l,t,r,b=geometry['native_box'];pad=8
    region=(max(0,l-pad),max(0,t-pad),min(original.width,r+pad),min(original.height,b+pad))
    clean=original.crop(region).filter(ImageFilter.MedianFilter(15))
    return clean.crop((l-region[0],t-region[1],r-region[0],b-region[1]))

def _source_coverage(original,geometry):
    l,t,r,b=geometry['native_box'];ink=geometry['ink_rgb']
    alpha=Image.new('L',(r-l,b-t));background=_background(original,geometry)
    for y in range(t,b):
        for x in range(l,r):
            bg=background.getpixel((x-l,y-t));p=original.getpixel((x,y))
            v=[bg[c]-ink[c] for c in range(3)];norm=sum(n*n for n in v)
            weight=max(0,min(1,sum((bg[c]-p[c])*v[c] for c in range(3))/max(1,norm)))
            residual=max(abs(p[c]-(bg[c]*(1-weight)+ink[c]*weight)) for c in range(3))
            if residual<=max(8,abs(geometry['contrast'])*.07):alpha.putpixel((x-l,y-t),round(weight*255))
    return _text_components(alpha,r-l,b-t,geometry.get('text_lines',1))

def _heal_ink(original,geometry,source_coverage):
    l,t,r,b=geometry['native_box'];pad=20
    region=(max(0,l-pad),max(0,t-pad),min(original.width,r+pad),min(original.height,b+pad))
    image=original.crop(region);remove=Image.new('L',image.size)
    remove.paste(source_coverage.point(lambda a:255 if a>=24 else 0).filter(ImageFilter.MaxFilter(5)),(l-region[0],t-region[1]))
    known=ImageOps.invert(remove);weights=known.filter(ImageFilter.GaussianBlur(12))
    sampled=ImageChops.multiply(image,known.convert('RGB')).filter(ImageFilter.GaussianBlur(12))
    clean=image.copy()
    for y in range(t-region[1],b-region[1]):
        for x in range(l-region[0],r-region[0]):
            if remove.getpixel((x,y)):
                weight=weights.getpixel((x,y))
                if weight<4:raise LiveGateError('MATTE_BACKGROUND_NOT_RECOVERABLE')
                clean.putpixel((x,y),tuple(min(255,round(c*255/weight)) for c in sampled.getpixel((x,y))))
    return clean.crop((l-region[0],t-region[1],r-region[0],b-region[1]))

def _fit_coverage(original,model,geometry):
    l,t,r,b=geometry['native_box'];ml,mt,mr,mb=geometry['provider_box'];w,h=r-l,b-t
    margin=max(16,h//2);search=(0,max(0,mt-margin),model.width,min(model.height,mb+margin))
    patch=model.crop(search)
    alpha=_text_components(ImageOps.invert(patch.convert('L')),w,h,geometry.get('text_lines',1))
    box=alpha.getbbox()
    if not box:raise LiveGateError('MATTE_NO_CORRECTED_GLYPH')
    if box[0]==0 or box[1]==0 or box[2]==patch.width or box[3]==patch.height:
        raise LiveGateError('MATTE_GLYPH_LAYOUT_INCOMPLETE')
    source=_source_coverage(original,geometry);source_box=source.getbbox()
    if not source_box:raise LiveGateError('MATTE_SOURCE_GLYPH_NOT_ISOLATED')
    pad=max(1,min(4,min(w,h)//12));max_w=min(w-2*pad,source_box[2]-source_box[0]);max_h=min(h-2*pad,source_box[3]-source_box[1])
    scale=min(1,max_w/(box[2]-box[0]),max_h/(box[3]-box[1]))
    size=(max(1,int((box[2]-box[0])*scale)),max(1,int((box[3]-box[1])*scale)))
    glyph=alpha.crop(box).resize(size,Image.Resampling.LANCZOS)
    x=max(pad,min(w-pad-size[0],(source_box[0]+source_box[2]-size[0])//2))
    y=max(pad,min(h-pad-size[1],(source_box[1]+source_box[3]-size[1])//2))
    fitted=Image.new('L',(w,h));fitted.paste(glyph,(x,y))
    if not (pad<=x and pad<=y and x+size[0]<=w-pad and y+size[1]<=h-pad):raise LiveGateError('MATTE_FIT_OUTSIDE_SELECTION')
    return fitted,source,{'version':'glyph-fit-inside-v1','model_ink_box':[box[0],box[1]+search[1],box[2],box[3]+search[1]],
        'source_ink_box':list(source_box),'fitted_box':[x,y,x+size[0],y+size[1]],'scale':scale,'padding':pad,
        'clipped':False,'model_glyphs_resampled':True,'font_renderer':None}

def compose(source,generated,geometry,*,fit=False,lines=None):
    original=Image.open(BytesIO(source)).convert('RGB')
    raw=Image.open(BytesIO(generated)).convert('RGBA')
    white=Image.new('RGBA',raw.size,(255,255,255,255));white.alpha_composite(raw)
    model=white.convert('RGB')
    if model.size!=(1536,1024):raise LiveGateError('MATTE_MODEL_SIZE_CHANGED')
    l,t,r,b=geometry['native_box'];ml,mt,mr,mb=geometry['provider_box'];top,bottom=geometry['band'];ink=geometry['ink_rgb'];contrast=geometry['contrast']
    geometry={**geometry,**({'text_lines':lines} if lines is not None else {})}
    fit=fit or geometry['version']=='glyph-matte-fit-v2';layout=None
    if fit:
        coverage,source_coverage,layout=_fit_coverage(original,model,geometry)
        background=_heal_ink(original,geometry,source_coverage)
    out=original.copy();changed=0;new_ink=0
    for y in range(t,b):
        for x in range(l,r):
            p=model.getpixel((ml+x-l,mt+y-t))
            if max(p)-min(p)>24:raise LiveGateError('MATTE_MODEL_NOT_NEUTRAL')
            alpha=coverage.getpixel((x-l,y-t))/255 if fit else max(0,min(1,1-_lum(p)/255))
            if alpha<.04:alpha=0
            f=(y-top)/(bottom-top);a,z=original.getpixel((x,top)),original.getpixel((x,bottom))
            bg=tuple(a[c]*(1-f)+z[c]*f for c in range(3));old=original.getpixel((x,y))
            old_alpha=max(0,min(1,(_lum(bg)-_lum(old))/contrast))
            # Leave visible source background exact, reconstruct only old ink.
            base=background.getpixel((x-l,y-t)) if fit else bg if old_alpha>.04 else old
            v=tuple(max(0,min(255,round(base[c]*(1-alpha)+ink[c]*alpha))) for c in range(3))
            out.putpixel((x,y),v);changed+=v!=old;new_ink+=alpha>.5
    if not new_ink:raise LiveGateError('MATTE_NO_CORRECTED_GLYPH')
    return png(out),{**({'text_fit':layout} if layout else {}),'changed_pixels':changed,'new_ink_pixels':new_ink,'outside_roi_exact':True,
        'background_method':'source_pixels_and_normalized_local_healing' if fit else 'source_pixels_and_local_band_interpolation','font_renderer':None,
        'glyph_origin':'ACTUAL_IMAGE_MODEL','style_acceptance':'HUMAN_REVIEW_REQUIRED'}
