#!/usr/bin/env python3
"""輔助比較原圖與渲染；不同畫布比例須明確指定內容視窗。"""
import argparse
import json
import math
from PIL import Image,ImageChops,ImageStat
from workflow import cli_error
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('render');p.add_argument('--viewport',nargs=4,type=int,metavar=('X','Y','W','H'));a=p.parse_args()
    try:
        source=Image.open(a.source).convert('RGB');render=Image.open(a.render).convert('RGB')
        if a.viewport:
            x,y,w,h=a.viewport
            if x<0 or y<0 or w<=0 or h<=0 or x+w>render.width or y+h>render.height:raise ValueError('內容視窗超出渲染圖片。')
            render=render.crop((x,y,x+w,y+h))
        if abs(source.width/source.height-render.width/render.height)>.01:raise ValueError('原圖與渲染比例不同，請明確指定留邊後的 --viewport；不會拉伸圖片來掩蓋比例問題。')
        render=render.resize(source.size,Image.Resampling.LANCZOS)
        stat=ImageStat.Stat(ImageChops.difference(source,render));rmse=math.sqrt(sum(v*v for v in stat.rms)/3)
        print(json.dumps({'rmse_0_to_255':round(rmse,4),'similarity_0_to_1':round(max(0,1-rmse/255),6),
                          'note':'此分數只供輔助；字型反鋸齒會影響數值，仍須逐頁對照文字、圖層及版面。'},ensure_ascii=False,indent=2));return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
