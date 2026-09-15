/** One utterance per recording; timing is measured in milliseconds, never animation frames. */
export class TurnRecorder {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private recorder: MediaRecorder | null = null;
  private timer = 0;
  private generation = 0;
  private cancelled = false;

  stop(cancel = false) {
    this.cancelled = cancel;
    if (cancel) this.generation++;
    window.clearInterval(this.timer);
    if (this.recorder?.state === 'recording') this.recorder.stop();
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => {});
    this.context = null;
  }

  async start(onAudio: (blob: Blob) => void, onError: (message: string) => void, onLevel: (level: number) => void) {
    this.stop(true);
    const generation = ++this.generation;
    this.cancelled = false;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      onError('Bu tarayıcı mikrofon kaydını desteklemiyor. Sayfayı Chrome’da açın veya yazıyla devam edin.'); return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: {
        channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      }});
      if (generation !== this.generation) { stream.getTracks().forEach(t => t.stop()); return; }
      this.stream = stream;
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(m => MediaRecorder.isTypeSupported(m));
      const mr = new MediaRecorder(stream, mime ? {mimeType: mime} : undefined);
      this.recorder = mr;
      const chunks: BlobPart[] = [];
      mr.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      const context = new AudioContext();
      this.context = context;
      await context.resume();
      if (generation !== this.generation) return;
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      context.createMediaStreamSource(stream).connect(analyser);
      const buffer = new Float32Array(analyser.fftSize);
      const started = performance.now();
      let speechMs = 0, lastSpeech = started, previous = started, heard = false;
      mr.onstop = () => {
        if (this.cancelled || generation !== this.generation) return;
        const blob = new Blob(chunks, {type: mr.mimeType || mime || 'audio/webm'});
        onLevel(0);
        if (!heard || blob.size < 1000) onError('Net bir konuşma duyamadım. Mikrofona biraz yaklaşın veya mesajınızı yazın.');
        else onAudio(blob);
      };
      mr.onerror = () => { this.stop(true); onError('Mikrofon kaydı kesildi. Tekrar deneyin.'); };
      mr.start(200);
      this.timer = window.setInterval(() => {
        analyser.getFloatTimeDomainData(buffer);
        const rms = Math.sqrt(buffer.reduce((sum, v) => sum + v * v, 0) / buffer.length);
        const now = performance.now();
        const elapsed = Math.min(now - previous, 100); previous = now;
        onLevel(Math.min(1, rms * 12));
        if (rms > 0.012) { speechMs += elapsed; lastSpeech = now; if (speechMs >= 160) heard = true; }
        else if (!heard) speechMs = Math.max(0, speechMs - elapsed / 2);
        if ((heard && now - lastSpeech > 1400) || (!heard && now - started > 12000) || now - started > 45000) this.stop();
      }, 40);
    } catch (error) {
      if (generation !== this.generation) return;
      this.stop(true);
      onError(error instanceof DOMException && error.name === 'NotAllowedError'
        ? 'Mikrofon izni verilmedi. Tarayıcının adres çubuğundan mikrofon iznini açabilirsiniz.'
        : 'Mikrofon başlatılamadı. Başka bir uygulamanın mikrofonu kullanmadığından emin olun.');
    }
  }
}
