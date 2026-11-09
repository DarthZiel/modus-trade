from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import json,wave,math,subprocess,re,sys
R=Path(__file__).resolve().parent
scenes=json.loads((R/'storyboard.json').read_text())
W,H=1920,1080
BG='#171d23'; WHITE='#f5f6f7'; MUTED='#adb5bf'; ORANGE='#ff9261'; BORDER='#414a54'
(R/'frames').mkdir(exist_ok=True);(R/'clips').mkdir(exist_ok=True)
def font(size,weight=450):
 f=ImageFont.truetype(str(R/'GolosText.ttf'),size)
 try:f.set_variation_by_axes([weight])
 except:pass
 return f
def wrap(text,f,width):
 lines=[]
 for para in text.split('\n'):
  line=''
  for word in para.split():
   x=(line+' '+word).strip()
   if f.getlength(x)>width and line:lines.append(line);line=word
   else:line=x
  lines.append(line)
 return lines
def txt(d,xy,text,size=24,width=370,fill=WHITE,weight=450,gap=8):
 f=font(size,weight);x,y=xy
 for line in wrap(text,f,width):d.text((x,y),line,font=f,fill=fill);y+=size+gap
 return y

def at(t,ass=False):
 if ass:
  cs=round(t*100);return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
 ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

ASS='''[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Golos Text,27,&H00FFFFFF,&H00FFFFFF,&H00171D23,&H00171D23,0,0,0,0,100,100,0,0,1,2,0,2,100,100,20,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
chapters=['Подача предложения','Назначение','Работа и обсуждение','Проверка экспериментом','Решение','Подтверждение автора']
def chapter(i):
 return 0 if i<=4 else 1 if i<=6 else 2 if i<=8 else 3 if i<=12 else 4 if i<=14 else 5
allsubs=[];offset=0;manifest=[]
for s in scenes:
 i=s['index']; wav=R/'audio'/f'{i:02}.wav'
 with wave.open(str(wav)) as f:audiodur=f.getnframes()/f.getframerate()
 speed=1.2;voice=audiodur/speed;duration=voice+1.2
 im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
 txt(d,(34,23),'МОДУС ТРЕЙД  /  ФИДБЕК',21,800,ORANGE,650)
 txt(d,(34,57),'От предложения сотрудника до подтверждённого результата',24,1400,WHITE,550)
 txt(d,(1490,32),'ДЕМОНСТРАЦИОННЫЙ\nСЦЕНАРИЙ',15,390,MUTED,500,5)
 shot=Image.open(R/'screens'/s['screen']).convert('RGB').resize((1392,870),Image.LANCZOS)
 im.paste(shot,(32,110));d.rectangle((31,109,1425,981),outline=BORDER,width=1)
 x=1460;d.rounded_rectangle((x,112,x+108,162),radius=8,fill=ORANGE)
 d.text((x+17,121),f'{i:02} / 18',font=font(24,650),fill=BG)
 y=txt(d,(x,184),s['role'],19,418,ORANGE,550)
 y=txt(d,(x,y+18),s['title'],34,410,WHITE,650,8)
 d.line((x,y+22,1876,y+22),fill=BORDER,width=1)
 y=txt(d,(x,y+47),s['thesis'],24,408,WHITE,500,9)
 for b in s['bullets']:
  y=txt(d,(x,y+20),b,20,408,MUTED,450,8)
 cy=max(650,y+42)
 for k,c in enumerate(chapters):
  active=k==chapter(i);done=k<chapter(i)
  d.ellipse((x,cy+8,x+7,cy+15),fill=ORANGE if active or done else '#4c5662')
  txt(d,(x+20,cy),c,18,388,WHITE if active else MUTED,600 if active else 400,4)
  cy+=43
 txt(d,(1460,946),'MT-000018  ·  Склад и логистика',15,418,MUTED,450)
 d.line((32,994,1888,994),fill=BORDER,width=1)
 # Bottom progress is functional: position within the complete workflow.
 d.rectangle((32,992,32+round(1856*i/18),995),fill=ORANGE)
 frame=R/'frames'/f'{i:02}.png';im.save(frame)
 sentences=re.split(r'(?<=[.!?])\s+',s['narration'])
 total=sum(len(t) for t in sentences);local=.4;events=[]
 for sentence in sentences:
  end=local+voice*len(sentence)/total
  lines=wrap(sentence,font(27),1730)
  text='\\N'.join(lines)
  events.append(f'Dialogue: 0,{at(local,True)},{at(end,True)},Default,,0,0,0,,{{\\fad(100,100)}}{text}')
  allsubs.append((offset+local,offset+end,sentence));local=end
 ass=R/'frames'/f'{i:02}.ass';ass.write_text(ASS+'\n'.join(events)+'\n')
 manifest.append(dict(index=i,title=s['title'],start=round(offset,3),duration=round(duration,3)))
 offset+=duration
 (R/'clips'/f'{i:02}.duration').write_text(str(duration))
(R/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(R/'subtitles-ru.srt').write_text('\n\n'.join(f'{j+1}\n{at(a)} --> {at(b)}\n{t}' for j,(a,b,t) in enumerate(allsubs))+'\n')
concat_lines = ["file '" + str(R/'clips'/(str(s['index']).zfill(2)+'.mp4')) + "'\n" for s in scenes]
(R/'frames'/'concat.txt').write_text(''.join(concat_lines))
meta = ';FFMETADATA1\ntitle=Модус Трейд · Фидбек — полный цикл предложения\nartist=Modus Feedback\ncomment=Демонстрационные данные. Русская синтетическая озвучка.\n'
for chapter_meta in manifest:
 meta += '[CHAPTER]\nTIMEBASE=1/1000\nSTART='+str(round(chapter_meta['start']*1000))+'\nEND='+str(round((chapter_meta['start']+chapter_meta['duration'])*1000))+'\ntitle='+chapter_meta['title']+'\n'
(R/'chapters.ffmeta').write_text(meta)
print(f'Frames ready, duration {offset:.1f}s',flush=True)
if __name__=='__main__' and '--frames-only' not in sys.argv:
 import concurrent.futures
 def encode(s):
  i=s['index'];dur=float((R/'clips'/f'{i:02}.duration').read_text())
  cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-threads','2','-i',str(R/'frames'/f'{i:02}.png'),'-i',str(R/'audio'/f'{i:02}.wav'),'-vf',f"loop=loop=-1:size=1:start=0,setpts=N/(25*TB),subtitles={R/'frames'/f'{i:02}.ass'}:fontsdir={R},fade=t=in:st=0:d=0.25,fade=t=out:st={dur-.25:.3f}:d=0.25",'-af','atempo=1.2,adelay=400|400,apad=pad_dur=1.0,loudnorm=I=-16:TP=-1.5:LRA=9','-t',f'{dur:.3f}','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-threads','2','-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(R/'clips'/f'{i:02}.mp4')]
  subprocess.run(cmd,check=True);print('rendered',i,flush=True)
 selected = [s for s in scenes if len(sys.argv)<2 or s["index"] in [int(x) for x in sys.argv[1].split(",")]]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(encode,selected))
 if all((R/'clips'/f'{s["index"]:02}.mp4').exists() for s in scenes):
  subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(R/'frames'/'concat.txt'),'-i',str(R/'chapters.ffmeta'),'-map','0','-map_metadata','1','-map_chapters','1','-c','copy','-movflags','+faststart',str(R/'Modus-Trade-Feedback-demo.mp4')],check=True)
 print('DONE',flush=True)
