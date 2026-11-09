from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from piper import PiperVoice, SynthesisConfig
import json,wave,subprocess,math,os
R=Path(__file__).resolve().parent
scenes=json.loads((R/'storyboard.json').read_text())
F=R.parent/'demo-video/GolosText.ttf'
BG='#171d23'; FG='#f4f2ee'; ACC='#ff9261'; MUT='#aeb5bd'
def font(n,w=550):
 f=ImageFont.truetype(str(F),n)
 f.set_variation_by_axes([w]); return f
def text(d,pos,t,n,color=FG,w=550):
 x,y=pos
 for line in t.split('\n'):
  assert font(n,w).getlength(line)<1760,(t,n)
  d.text((x,y),line,font=font(n,w),fill=color); y+=int(n*1.2)
 return y
voice=PiperVoice.load(os.environ.get('MODUS_PIPER_MODEL','/tmp/modus-pitch-irina.onnx'))
offset=0; subs=[]; manifest=[]
for i,s in enumerate(scenes,1):
 wav=R/'audio'/f'{i:02}.wav'
 if not wav.exists():
  with wave.open(str(wav),'wb') as out:voice.synthesize_wav(s['voice'],out,syn_config=SynthesisConfig(length_scale=1.0))
 with wave.open(str(wav)) as inp: spoken=inp.getnframes()/inp.getframerate()/1.13
 dur=math.ceil((spoken+1.0)*24)/24
 im=Image.new('RGB',(1920,1080),BG);d=ImageDraw.Draw(im)
 text(d,(84,45),'modus / feedback',25,ACC,650)
 text(d,(1510,49),'ПИТЧ ПРОЕКТА',17,MUT)
 d.line((84,105,1836,105),fill='#394149',width=1)
 text(d,(84,140),s['tag'],20,ACC,550)
 if 'screen' in s:
  text(d,(84,184),s['title'],54)
  shot=Image.open(R/'assets'/s['screen']).convert('RGB')
  shot.thumbnail((1510,670),Image.Resampling.LANCZOS)
  x=(1920-shot.width)//2;y=284
  d.rounded_rectangle((x-8,y-8,x+shot.width+8,y+shot.height+8),radius=12,fill='#3c444d')
  im.paste(shot,(x,y))
  text(d,(84,967),'ТЕКУЩИЙ ИНТЕРФЕЙС · ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ',16,MUT)
 else:
  y=text(d,(84,290),s['title'],78,FG,650)
  d.line((88,y+48,238,y+48),fill=ACC,width=5)
  text(d,(88,y+93),s.get('body',''),31,MUT,450)
 text(d,(1740,965),f'{i:02} / 09',19,MUT)
 im.save(R/'frames'/f'{i:02}.png')
 # Subtitles follow short clauses rather than an entire paragraph.
 words=s['voice'].split();chunks=[];chunk=[]
 for word in words:
  if len(' '.join(chunk+[word]))>76:chunks.append(' '.join(chunk));chunk=[]
  chunk.append(word)
 if chunk:chunks.append(' '.join(chunk))
 def ts(t):
  cs=round(t*100);return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
 ass='''[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Golos Text,28,&H00FFFFFF,&H00FFFFFF,&H00171D23,&H00171D23,0,0,0,0,100,100,0,0,1,2,0,2,80,80,24,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
 t=.35
 for chunk in chunks:
  end=t+spoken*len(chunk.split())/len(words)
  ass+=f'Dialogue: 0,{ts(t)},{ts(end)},Default,,0,0,0,,{chunk}\n';subs.append((offset+t,offset+end,chunk));t=end
 (R/'frames'/f'{i:02}.ass').write_text(ass)
 clip=R/'clips'/f'{i:02}.mp4'
 if not clip.exists():
  vf=f"zoompan=z='1+0.012*on/{round(dur*24)}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={round(dur*24)}:s=1920x1080:fps=24,subtitles=frames/{i:02}.ass:fontsdir=../demo-video,fade=t=in:st=0:d=0.24,fade=t=out:st={dur-.24}:d=0.24"
  subprocess.run(['ffmpeg','-v','error','-y','-i',str(R/'frames'/f'{i:02}.png'),'-i',str(wav),'-vf',vf,'-af','atempo=1.13,adelay=350,apad,loudnorm=I=-16:TP=-1.5:LRA=9','-t',str(dur),'-c:v','libx264','-preset','veryfast','-crf','19','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k',str(clip)],check=True,cwd=R)
 manifest.append(dict(scene=i,title=s['title'],start=offset,duration=dur));offset+=dur
 print(i,round(offset,2),flush=True)
(R/'concat.txt').write_text(''.join(f"file 'clips/{i:02}.mp4'\n" for i in range(1,len(scenes)+1)))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i','concat.txt','-c:v','copy','-c:a','aac','-ar','48000','-b:a','160k','-movflags','+faststart','Modus-Feedback-pitch-1080p.mp4'],cwd=R,check=True)
def srt(t):
 ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
(R/'subtitles-ru.srt').write_text('\n\n'.join(f'{i}\n{srt(a)} --> {srt(b)}\n{t}' for i,(a,b,t) in enumerate(subs,1))+'\n')
(R/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
