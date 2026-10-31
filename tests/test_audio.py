import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from audio import AudioCleaner
sr=16000; rng=np.random.default_rng(0)
t=np.arange(sr*6)/sr
# "voz": tono modulado con armonicos entre 2 y 5 s, mas ruido blanco y zumbido grave
voz=sum(np.sin(2*np.pi*f*t)/k for k,f in enumerate([220,440,660,880],1))*0.12
voz*= ((t>2)&(t<5)).astype(float)*(0.6+0.4*np.sin(2*np.pi*3*t))
ruido=rng.normal(0,0.03,len(t))+0.05*np.sin(2*np.pi*50*t)
x=(voz+ruido).astype(np.float32)
c=AudioCleaner(); out=np.concatenate([c.process(x[i:i+1600]) for i in range(0,len(x),1600)])
def rms(a): return float(np.sqrt(np.mean(a**2)))
ru_in, ru_out = rms(x[:sr]), rms(out[:sr]*1)   # solo ruido (0-1 s)
ruido_fin_in, ruido_fin_out = rms(x[-sr:]), rms(out[-sr:])
print("ruido entrada %.4f -> salida %.4f  (%.1f dB menos)" % (ruido_fin_in, ruido_fin_out, 20*np.log10(ruido_fin_in/ruido_fin_out)))
seg=slice(int(2.5*sr),int(4.5*sr))
print("voz presente en salida (rms) %.3f ; entrada %.3f" % (rms(out[seg]), rms(x[seg])))
assert len(out)==len(x)
assert ruido_fin_out < 0.5*ruido_fin_in
assert rms(out[seg])>0.03
print("AUDIO OK")
