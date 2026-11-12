from io import BytesIO
from PIL import Image,ImageDraw
import pytest
from demo_staging.live.glyph_matte import prepare,compose,png
from demo_staging.live.contracts import LiveGateError

def sample():
 im=Image.new('RGB',(300,400),(220,230,210));ImageDraw.Draw(im).rectangle((110,130,113,170),fill=(60,90,40));return im

def test_flat_specimen_and_model_matte_preserve_original_outside_roi():
 src=sample();box=(100,120,140,180);wire,mask,g=prepare(png(src),box)
 assert Image.open(BytesIO(wire)).size==(1536,1024)
 assert Image.open(BytesIO(mask)).getchannel('A').getextrema()==(0,255)
 model=Image.new('RGB',(1536,1024),'white');x,y,_,_=g['provider_box'];ImageDraw.Draw(model).rectangle((x+20,y+10,x+23,y+50),fill='black')
 raw,report=compose(png(src),png(model),g);out=Image.open(BytesIO(raw))
 assert report['font_renderer'] is None and report['glyph_origin']=='ACTUAL_IMAGE_MODEL'
 assert out.getpixel((111,140))==(220,230,210) # old ink removed
 assert out.getpixel((121,140))==(60,90,40) # model ink restores source color
 for yy in range(400):
  for xx in range(300):
   if not(100<=xx<140 and 120<=yy<180):assert out.getpixel((xx,yy))==src.getpixel((xx,yy))

def test_ambiguous_low_contrast_and_colored_model_fail_closed():
 with pytest.raises(LiveGateError):prepare(png(Image.new('RGB',(300,400),'gray')),(100,120,140,180))
 src=sample();_,_,g=prepare(png(src),(100,120,140,180));m=Image.new('RGB',(1536,1024),'white');x,y,_,_=g['provider_box'];m.putpixel((x,y),(255,0,0))
 with pytest.raises(LiveGateError):compose(png(src),png(m),g)
