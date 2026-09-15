import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { TurnRecorder } from './recorder';
import '../../styles/voice-studio.css';

type Voice = {id: string; name: string; labels: Record<string, string>; description: string};
type Message = {role: 'user' | 'assistant'; content: string};
type Phase = 'idle' | 'listening' | 'transcribing' | 'review' | 'thinking' | 'speaking';
type Reply = {id: string; reply: string; stage: string; source: string; intent?: string; note?: string; appointment_request?: string; processing_ms?: number};
type Profile = {voice_id?: string; model?: string; speed?: number; stability?: number; style?: number};
type VoiceRole = 'receiver' | 'caller';
type RoleState = {profile: Profile; live: boolean; blockers: string[]};
type LiveVoice = {clinic: string; roles: Record<VoiceRole, RoleState>; tts_provider: string; external_enabled: boolean; server_key_configured: boolean; can_go_live: boolean};
const roleLabels: Record<VoiceRole, string> = {receiver: 'Karşılayan asistan (gelen aramalar)', caller: 'Arayan asistan (giden aramalar)'};
const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api';
const labels: Record<Phase, string> = {idle: 'Görüşmeye hazır', listening: 'Seni dinliyor', transcribing: 'Söylediklerini çözümlüyor', review: 'Duyduğumu kontrol et', thinking: 'Yanıtını hazırlıyor', speaking: 'Seninle konuşuyor'};

export function VoiceStudio() {
  const {token} = useAuth();
  useEffect(() => { const previous = document.title; document.title = 'Voice Studio · CogniVault'; return () => {document.title = previous;}; }, []);
  const [direction, setDirection] = useState<'incoming' | 'outgoing'>('outgoing');
  const [company, setCompany] = useState('Atlas Teknoloji');
  const [brand, setBrand] = useState('CogniVault');
  const [purpose, setPurpose] = useState('Yapay zekâ resepsiyon hizmetimiz için kısa bir tanışma görüşmesi ayarlamak');
  const [connected, setConnected] = useState(false);
  const [voiceEngine, setVoiceEngine] = useState<'local' | 'elevenlabs'>('local');
  const [apiKey, setApiKey] = useState('');
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceId, setVoiceId] = useState('');
  const [search, setSearch] = useState('');
  const [pageToken, setPageToken] = useState<string | null>(null);
  const [model, setModel] = useState('eleven_multilingual_v2');
  const [speed, setSpeed] = useState(1);
  const [stability, setStability] = useState(0.45);
  const [style, setStyle] = useState(0);
  const [live, setLive] = useState<LiveVoice | null>(null);
  const [useInCalls, setUseInCalls] = useState(false);
  const [saveNote, setSaveNote] = useState('');
  const [stt, setStt] = useState('local');
  const [cloudConsent, setCloudConsent] = useState(false);
  const [autoSend, setAutoSend] = useState(false);
  const [setupBusy, setSetupBusy] = useState(false);
  const [error, setError] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [level, setLevel] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [active, setActive] = useState(false);
  const [ended, setEnded] = useState(false);
  const [note, setNote] = useState('');
  const [appointment, setAppointment] = useState('');
  const [source, setSource] = useState('Henüz başlamadı');
  const [latency, setLatency] = useState<number | null>(null);
  const [heard, setHeard] = useState('');
  const [llm, setLlm] = useState('');
  const recorder = useRef(new TurnRecorder());
  const audio = useRef<HTMLAudioElement | null>(null);
  const audioUrl = useRef<string | null>(null);
  const generation = useRef(0);
  const activeRef = useRef(false);
  const sessionRef = useRef('');
  const requestAbort = useRef<AbortController | null>(null);
  const scrollEnd = useRef<HTMLDivElement>(null);
  const sendRef = useRef<(text: string) => Promise<void>>(async () => {});
  const listenRef = useRef<() => void>(() => {});
  const preferences = useRef({stt, cloudConsent, autoSend});
  preferences.current = {stt, cloudConsent, autoSend};
  // Görüşmenin yönü hangi asistanın sesini düzenlediğini belirler.
  const role: VoiceRole = direction === 'incoming' ? 'receiver' : 'caller';
  const roleState = live?.roles?.[role];
  const appliedRole = useRef<string>('');
  const selectedVoice = voices.find(v => v.id === voiceId);
  const busy = ['thinking', 'transcribing', 'speaking', 'listening'].includes(phase);
  const voiceReady = (voiceEngine === 'local' || (connected && !!voiceId && cloudConsent)) && (stt !== 'elevenlabs' || (connected && cloudConsent));
  const voiceLabel = voiceEngine === 'local' ? 'Piper · Yerel Türkçe' : selectedVoice?.name || 'ElevenLabs · ses seçilmedi';

  async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API}/voice-studio${path}`, {...options, headers: {
      Authorization: `Bearer ${token}`, ...(options.body instanceof FormData ? {} : {'Content-Type': 'application/json'}), ...options.headers,
    }});
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'İşlem tamamlanamadı. Lütfen tekrar deneyin.');
    }
    return response.headers.get('content-type')?.includes('audio/') ? await response.blob() as T : await response.json() as T;
  }

  useEffect(() => {
    let cancelled = false;
    api<{connected: boolean; llm_model: string}>('/status').then(async status => {
      if (cancelled) return;
      setConnected(status.connected); setLlm(status.llm_model);
      if (status.connected) {
        const data = await api<{voices: Voice[]; next_page_token: string | null}>('/voices');
        if (!cancelled) {setVoices(data.voices); setPageToken(data.next_page_token);}
      }
    }).catch(e => {if (!cancelled) setError(e.message);});
    return () => {cancelled = true; stopAll();};
  }, [token]);
  useEffect(() => {
    // Kliniğin canlı görüşmelerde kullandığı sesler — stüdyo onların üstüne
    // çalışsın, "burada duyduğun ses" ile "hastanın duyduğu ses" ayrışmasın.
    let cancelled = false;
    api<LiveVoice>('/profile').then(current => {
      if (cancelled) return;
      setLive(current); setUseInCalls(current.tts_provider === 'elevenlabs');
    }).catch(() => {/* profil okunamazsa stüdyo varsayılanlarla çalışır */});
    return () => {cancelled = true;};
  }, [token]);
  useEffect(() => {
    // Yön değiştiğinde o tarafın kayıtlı sesi forma gelir; kullanıcının
    // düzenlemesini ezmemek için aynı rol ikinci kez uygulanmaz.
    const saved = live?.roles?.[role]?.profile;
    if (!saved || appliedRole.current === role + JSON.stringify(saved)) return;
    appliedRole.current = role + JSON.stringify(saved);
    setVoiceId(saved.voice_id ?? '');
    if (saved.model) setModel(saved.model);
    setSpeed(typeof saved.speed === 'number' ? saved.speed : 1);
    setStability(typeof saved.stability === 'number' ? saved.stability : 0.45);
    setStyle(typeof saved.style === 'number' ? saved.style : 0);
  }, [live, role]);
  useEffect(() => {scrollEnd.current?.scrollIntoView({behavior: 'smooth', block: 'nearest'});}, [messages, phase]);

  function stopAudio() {
    if (audio.current) {audio.current.pause(); audio.current.onended = null; audio.current.onerror = null; audio.current = null;}
    if (audioUrl.current) {URL.revokeObjectURL(audioUrl.current); audioUrl.current = null;}
  }
  function stopAll() {
    generation.current++; activeRef.current = false;
    recorder.current.stop(true); requestAbort.current?.abort(); stopAudio();
  }
  function endCall() {stopAll(); setActive(false); setPhase('idle'); setLevel(0);}

  async function speak(text: string, resume: boolean) {
    const current = generation.current;
    stopAudio(); setPhase('speaking');
    const controller = new AbortController(); requestAbort.current = controller;
    try {
      const blob = await api<Blob>('/speech', {method: 'POST', signal: controller.signal,
        body: JSON.stringify({text, provider: voiceEngine, voice_id: voiceEngine === 'local' ? 'local-piper' : voiceId, model, speed, stability, style, cloud_consent: cloudConsent})});
      if (generation.current !== current) return;
      const url = URL.createObjectURL(blob); audioUrl.current = url;
      const player = new Audio(url); audio.current = player;
      player.onended = () => {
        if (current !== generation.current) return;
        stopAudio(); setPhase('idle');
        if (resume && activeRef.current) listenRef.current();
        else if (!resume) {activeRef.current = false; setActive(false);}
      };
      player.onerror = () => {if (current === generation.current) {endCall(); setError('Ses çalınamadı. Seçili sesi tekrar önizleyin.');}};
      await player.play();
    } catch (e) {
      if (generation.current !== current) return;
      endCall(); setError(e instanceof Error ? e.message : 'Ses üretilemedi. Yazılı olarak devam edebilirsiniz.');
    }
  }

  function listen() {
    if (!activeRef.current) return;
    setError(''); setPhase('listening');
    const current = generation.current;
    void recorder.current.start(async blob => {
      if (generation.current !== current) return;
      setPhase('transcribing'); setLevel(0);
      const form = new FormData(); form.append('file', blob, blob.type.includes('mp4') ? 'speech.mp4' : 'speech.webm');
      form.append('provider', preferences.current.stt); form.append('cloud_consent', String(preferences.current.cloudConsent));
      const controller = new AbortController(); requestAbort.current = controller;
      try {
        const result = await api<{text: string; confidence: number | null; processing_ms: number}>('/transcribe', {method: 'POST', body: form, signal: controller.signal});
        if (generation.current !== current) return;
        if (!result.text.trim()) throw new Error('Konuşma anlaşılamadı. Tekrar deneyebilir veya yazabilirsiniz.');
        setHeard(result.text); setDraft(result.text); setPhase('review');
        if (preferences.current.autoSend && (result.confidence === null || result.confidence >= 0.65)) await sendRef.current(result.text);
      } catch (e) {if (generation.current === current) {setPhase('idle'); setError(e instanceof Error ? e.message : 'Ses çözümlenemedi.');}}
    }, message => {if (generation.current === current) {setPhase('idle'); setError(message); setLevel(0);}}, setLevel);
  }
  listenRef.current = listen;

  async function start(withVoice: boolean) {
    endCall(); setError(''); setMessages([]); setNote(''); setAppointment(''); setDraft(''); setHeard(''); setEnded(false); setSessionId(''); sessionRef.current = '';
    const current = generation.current; setPhase('thinking');
    try {
      const result = await api<Reply>('/sessions', {method: 'POST', body: JSON.stringify({direction, company, brand, purpose})});
      if (current !== generation.current) return;
      sessionRef.current = result.id; setSessionId(result.id); setSource(result.source);
      setMessages([{role: 'assistant', content: result.reply}]); setPhase('idle');
      if (withVoice) {activeRef.current = true; setActive(true); await speak(result.reply, true);}
    } catch (e) {if (current === generation.current) {setPhase('idle'); setError(e instanceof Error ? e.message : 'Görüşme başlatılamadı.');}}
  }

  async function send(text: string) {
    if (!text.trim() || !sessionRef.current) return;
    const current = generation.current;
    recorder.current.stop(true); setError(''); setPhase('thinking'); setDraft('');
    const controller = new AbortController(); requestAbort.current = controller;
    try {
      const result = await api<Reply>(`/sessions/${sessionRef.current}/messages`, {method: 'POST', signal: controller.signal, body: JSON.stringify({text})});
      if (current !== generation.current) return;
      setMessages(prev => [...prev, {role: 'user', content: text}, {role: 'assistant', content: result.reply}]);
      setNote(result.note ?? ''); setAppointment(result.appointment_request ?? ''); setSource(result.source); setLatency(result.processing_ms ?? null);
      setEnded(result.stage === 'ended'); setPhase('idle');
      if (activeRef.current) await speak(result.reply, result.stage !== 'ended');
    } catch (e) {if (current === generation.current) {setDraft(text); setPhase('review'); setError(e instanceof Error ? e.message : 'Mesaj gönderilemedi.');}}
  }
  sendRef.current = send;

  async function connect() {
    setSetupBusy(true); setError('');
    try {
      const data = await api<{voices: Voice[]; next_page_token: string | null}>('/connection', {method: 'POST', body: JSON.stringify({api_key: apiKey})});
      setConnected(true); setVoiceEngine('elevenlabs'); setVoices(data.voices); setPageToken(data.next_page_token); setApiKey('');
    } catch (e) {setError(e instanceof Error ? e.message : 'Bağlantı kurulamadı.');}
    finally {setSetupBusy(false);}
  }
  async function loadVoices(more = false) {
    setSetupBusy(true); setError('');
    try {
      const data = await api<{voices: Voice[]; next_page_token: string | null}>(`/voices?search=${encodeURIComponent(search)}${more && pageToken ? `&page_token=${encodeURIComponent(pageToken)}` : ''}`);
      setVoices(prev => more ? [...prev, ...data.voices] : data.voices); setPageToken(data.next_page_token);
    } catch (e) {setError(e instanceof Error ? e.message : 'Sesler alınamadı.');}
    finally {setSetupBusy(false);}
  }
  async function saveProfile() {
    setSetupBusy(true); setError(''); setSaveNote('');
    try {
      const saved = await api<LiveVoice>('/profile', {method: 'PUT', body: JSON.stringify({
        role, voice_id: voiceId, model, speed, stability, style, use_in_calls: useInCalls})});
      setLive(saved);
      setSaveNote(saved.roles[role].live
        ? `Kaydedildi. ${roleLabels[role]} artık bu sesle konuşuyor (hasta ses rızası verdiği sürece).`
        : 'Kaydedildi. Canlı görüşmelerin bu sese geçmesi için aşağıdaki eksikler kapanmalı.');
    } catch (e) {setError(e instanceof Error ? e.message : 'Ses kaydedilemedi.');}
    finally {setSetupBusy(false);}
  }
  function exportConversation() {
    const text = `CogniVault · ${direction === 'incoming' ? 'Gelen' : 'Giden'} görüşme demosu\nGerçek arama / takvim kaydı yapılmadı.\n\n` + messages.map(m => `${m.role === 'assistant' ? 'Asistan' : 'Kullanıcı'}: ${m.content}`).join('\n\n');
    const url = URL.createObjectURL(new Blob([text], {type: 'text/plain;charset=utf-8'}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'cognivault-gorusme.txt'; anchor.click(); URL.revokeObjectURL(url);
  }

  return <div className="vs-shell">
    <header className="vs-top"><Link to="/operator" className="vs-brand"><span className="vs-logomark">c</span> cognivault<span className="vs-divider"/> <span>Voice Studio</span></Link><span className="vs-demo"><i/> Canlı demo ortamı</span><Link to="/c/demo-klinik">Klinik demosu ↗</Link></header>
    <main className="vs-main">
      <div className="vs-heading"><div><p className="vs-eyebrow">İYİ BİR GÖRÜŞME, İYİ BİR MERHABA İLE BAŞLAR.</p><h1>Konuşsun. Dinlesin.<br/><em>Bağlantı kursun.</em></h1><p>Şirketinin sesini seç. Gelen mesajları karşıla,<br className="vs-desktop"/> giden görüşmelerin ilk merhabasını tasarla.</p></div><div className="vs-mode-note"><span>01 / GÖRÜŞME LABORATUVARI</span><p>Burada karşı taraf sensin.<br/>Gerçek bir numara aranmaz.</p></div></div>
      <div className="vs-layout">
        <aside className="vs-settings">
          <section className="vs-card"><div className="vs-section-title"><span>01</span><h2>Görüşmenin yönü</h2></div>
            <div className="vs-directions" role="group" aria-label="Görüşme yönü">
              <button disabled={active || busy} className={direction === 'incoming' ? 'selected' : ''} onClick={() => setDirection('incoming')}><b>↙ Gelen</b><small>Karşıla & mesaj al</small></button>
              <button disabled={active || busy} className={direction === 'outgoing' ? 'selected' : ''} onClick={() => setDirection('outgoing')}><b>↗ Giden</b><small>Tanış & görüşme iste</small></button>
            </div>
            <label>Şirketin<input disabled={active || busy} maxLength={100} value={brand} onChange={e => setBrand(e.target.value)}/></label>
            {direction === 'outgoing' && <label>Aranacak şirket<input disabled={active || busy} maxLength={100} value={company} onChange={e => setCompany(e.target.value)}/></label>}
            <label>Görüşmenin amacı<textarea disabled={active || busy} maxLength={400} rows={3} value={purpose} onChange={e => setPurpose(e.target.value)}/></label>
            <p className="vs-help">Değişiklikler yeni görüşmede uygulanır.</p>
          </section>
          <section className="vs-card"><div className="vs-section-title"><span>02</span><h2>Ses karakteri</h2><span className="vs-provider">{voiceEngine === "local" ? "Yerel ses" : "ElevenLabs"}</span></div>
            <p className="vs-role-tag">{roleLabels[role]}</p>
            <p className="vs-help">Her iki tarafın sesi ayrı saklanır; yönü değiştirince o tarafın kayıtlı sesi gelir.</p>
            <label>Ses sağlayıcısı<select disabled={busy || active} value={voiceEngine} onChange={e => setVoiceEngine(e.target.value as "local" | "elevenlabs")}><option value="local">Piper · Yerel Türkçe deneme</option><option value="elevenlabs">ElevenLabs · Kendi sesini seç</option></select></label>
            {!connected ? <><p className="vs-help">Hesabını bağla; kendi ses kitaplığından bir ses seç ve Türkçe dinle.</p><label>ElevenLabs API anahtarı<input type="password" autoComplete="off" placeholder="Anahtarını buraya yapıştır" value={apiKey} onChange={e => setApiKey(e.target.value)}/></label><button className="vs-secondary vs-full" disabled={setupBusy || apiKey.length < 10} onClick={() => void connect()}>{setupBusy ? 'Bağlanıyor…' : 'Hesabı bağla ↗'}</button><p className="vs-help">Anahtar tarayıcıya veya dosyaya kaydedilmez; bu bağlantı 4 saat geçerlidir.</p></> : <><p className="vs-connected">● ElevenLabs bağlı</p><div className="vs-search"><input aria-label="Ses ara" placeholder="Ses adı ara…" value={search} onChange={e => setSearch(e.target.value)}/><button disabled={setupBusy || busy || active} onClick={() => void loadVoices()}>Ara</button></div><label>Ses seç<select disabled={busy || active} value={voiceId} onChange={e => setVoiceId(e.target.value)}><option value="">Kitaplığından bir ses seç</option>{voices.map(v => <option key={v.id} value={v.id}>{v.name}{v.labels.language ? ` · ${v.labels.language}` : ''}</option>)}</select></label>{pageToken && <button className="vs-text-button" disabled={setupBusy} onClick={() => void loadVoices(true)}>Daha fazla ses yükle</button>}{selectedVoice && <p className="vs-help">{selectedVoice.description || Object.values(selectedVoice.labels).join(' · ')}</p>}<button className="vs-text-button" disabled={busy || active || setupBusy} onClick={async () => {try {const result = await api<{connected: boolean}>('/connection', {method: 'DELETE'}); setConnected(result.connected); if (!result.connected) {setVoices([]); setVoiceId('');}} catch(e) {setError((e as Error).message);}}}>Oturum bağlantısını kaldır</button></>}
            <label>ElevenLabs ses modeli<select disabled={busy || active} value={model} onChange={e => setModel(e.target.value)}><option value="eleven_multilingual_v2">Multilingual v2 · Doğallık</option><option value="eleven_flash_v2_5">Flash v2.5 · Hız</option></select></label>
            <label className="vs-range-label">Konuşma hızı <span>{speed.toFixed(2)}×</span><input disabled={busy || active} type="range" min="0.7" max="1.2" step="0.05" value={speed} onChange={e => setSpeed(Number(e.target.value))}/></label>
            <label className="vs-range-label">Tonlama kararlılığı <span>{stability.toFixed(2)}</span><input disabled={busy || active || voiceEngine === 'local'} type="range" min="0" max="1" step="0.05" value={stability} onChange={e => setStability(Number(e.target.value))}/></label>
            <p className="vs-help">Düşük değer daha canlı ve tonlamalı, yüksek değer daha düz okur. Robotik geliyorsa 0,40–0,50 aralığını dene.</p>
            <label className="vs-range-label">İfade gücü <span>{style.toFixed(2)}</span><input disabled={busy || active || voiceEngine === 'local'} type="range" min="0" max="1" step="0.05" value={style} onChange={e => setStyle(Number(e.target.value))}/></label>
            <p className="vs-help">Vurguyu artırır; yükseldikçe yanıt gecikmesi de artar. Resepsiyon için 0–0,20 yeterli.</p>
            <label className="vs-check"><input type="checkbox" disabled={busy || active} checked={cloudConsent} onChange={e => setCloudConsent(e.target.checked)}/><span>Demo yanıtlarının ve ElevenLabs ses tanımayı seçersem mikrofon kayıtlarımın ElevenLabs ile işlenmesini istiyorum.</span></label>
            <button className="vs-secondary vs-full" disabled={!voiceReady || busy || active} onClick={() => void speak(`Merhaba, ben ${brand} yapay zekâ asistanıyım. Size nasıl yardımcı olabilirim?`, false)}>▷ Seçili sesi dinle</button>
            <div className="vs-save">
              <p className="vs-live-state">{roleState?.live
                ? `Canlı: ElevenLabs · ${roleState.profile?.voice_id ?? '—'}`
                : 'Canlı: yerel Piper sesi'} · {roleLabels[role]}</p>
              {roleState && roleState.blockers.length > 0 &&
                <p className="vs-warn">Canlı sese geçiş için: {roleState.blockers.join(' ')}</p>}
              {live?.can_go_live
                ? <label className="vs-check"><input type="checkbox" disabled={busy || active || !voiceId} checked={useInCalls} onChange={e => setUseInCalls(e.target.checked)}/><span>Bu sesi canlı görüşmelerde kullan (ElevenLabs sınır-ötesi işleme açılır).</span></label>
                : <p className="vs-help">Sesi seçip kaydedebilirsin. Canlı görüşmelere almayı (sınır-ötesi işleme) yalnızca yönetici açar.</p>}
              <button className="vs-secondary vs-full" disabled={setupBusy || busy || active || !voiceId} onClick={() => void saveProfile()}>{setupBusy ? 'Kaydediliyor…' : `${roleLabels[role].split(' (')[0]} sesini kaydet`}</button>
              {saveNote && <p className="vs-help">{saveNote}</p>}
            </div>
          </section>
          <section className="vs-card"><div className="vs-section-title"><span>03</span><h2>Dinleme tercihi</h2></div><label>Konuşmayı anlama<select disabled={busy || active} value={stt} onChange={e => setStt(e.target.value)}><option value="local">Yerel Whisper · Cihazında</option><option value="elevenlabs" disabled={!connected}>ElevenLabs Scribe v2</option></select></label><label className="vs-check"><input type="checkbox" checked={autoSend} onChange={e => setAutoSend(e.target.checked)}/><span>Konuşmam bitince otomatik yanıtla</span></label><p className="vs-help">Kapalıyken duyulan metni düzeltip gönderirsin. Duraklamalar için 1,4 saniye beklenir.</p></section>
        </aside>
        <div className="vs-conversation-column">
          <section className="vs-call-card"><div className="vs-call-header"><div><span className="vs-eyebrow">{direction === 'outgoing' ? 'GİDEN GÖRÜŞME' : 'GELEN İLETİŞİM'}</span><h2>{direction === 'outgoing' ? company || 'Şirket görüşmesi' : `${brand || 'Şirket'} resepsiyonu`}</h2></div><span className="vs-pill">{active ? '● Görüşme açık' : 'Tarayıcı demosu'}</span></div>
            <div className={`vs-stage ${phase}`}><div className="vs-orb"><div className="vs-orb-core"/><div className="vs-wave">{Array.from({length: 15}, (_, i) => <span key={i} style={{height: `${12 + Math.sin(i * 1.9) ** 2 * (20 + level * 65)}px`, animationDelay: `${i * 0.07}s`}}/>)}</div></div><h3>{labels[phase]}</h3><p>{active ? 'Rahatça konuş. Seni dinlemek için buradayım.' : voiceLabel}</p>
              <div className="vs-call-actions">{active ? <><button className="vs-end" onClick={endCall}>■ Görüşmeyi durdur</button>{phase === 'listening' ? <button className="vs-secondary" onClick={() => recorder.current.stop()}>Konuşmam bitti</button> : (phase === 'idle' || phase === 'review' || phase === 'speaking') && <button className="vs-secondary" onClick={() => {generation.current++; requestAbort.current?.abort(); stopAudio(); recorder.current.stop(true); setDraft(''); listen();}}>{phase === 'speaking' ? 'Araya gir & konuş' : 'Tekrar dinle'}</button>}</> : <><button className="vs-primary" disabled={!voiceReady || busy || company.trim().length < 2 || brand.trim().length < 2 || purpose.trim().length < 5} onClick={() => void start(true)}>↗ Sesli demoyu başlat</button><button className="vs-secondary" disabled={busy || brand.trim().length < 2 || purpose.trim().length < 5 || company.trim().length < 2} onClick={() => void start(false)}>Yazıyla dene</button></>}</div>
              {!connected && <p className="vs-small-note">Yerel Türkçe ses hazır. ElevenLabs için hesabını bağlayıp ses seç.</p>}
            </div>
            {error && <div className="vs-error" role="alert">{error}<button onClick={() => setError('')} aria-label="Uyarıyı kapat">×</button></div>}
            <div className="vs-transcript"><div className="vs-transcript-title"><h3>Görüşme akışı</h3>{messages.length > 0 && <button onClick={exportConversation}>Metni indir ↓</button>}</div><div className="vs-messages" aria-live="polite">{messages.length === 0 ? <div className="vs-empty"><span>“</span><p>{direction === 'outgoing' ? `Merhaba, ${company} ile mi görüşüyorum?` : `Merhaba, ${brand} yapay zekâ asistanına hoş geldiniz.`}</p><small>İlk cümle hazır. Görüşmeyi başlatarak devam et.</small></div> : messages.map((m, i) => <article key={i} className={`vs-message ${m.role}`}><span>{m.role === 'assistant' ? 'C' : 'S'}</span><div><b>{m.role === 'assistant' ? 'Asistan' : 'Sen'}</b><p>{m.content}</p></div></article>)}<div ref={scrollEnd}/></div>
              {heard && <p className="vs-heard">Son duyulan: “{heard}”</p>}
              <form className="vs-compose" onSubmit={e => {e.preventDefault(); if (!busy && !ended) void send(draft);}}><input aria-label="Mesajın" placeholder={phase === 'review' ? 'Duyduğumu düzelt veya gönder…' : 'Mesajını yaz veya sesle söyle…'} value={draft} disabled={!sessionId || ended || busy} onChange={e => setDraft(e.target.value)} maxLength={2000}/><button aria-label="Mesajı gönder" disabled={!draft.trim() || busy || !sessionId || ended}>↑</button></form>
              {ended && <p className="vs-help">Görüşme tamamlandı. Yeniden denemek için yeni demo başlat.</p>}
            </div>
          </section>
          <div className="vs-bottom-grid"><section className="vs-card"><div className="vs-section-title"><span>↙</span><h2>Alınan mesaj</h2></div><p className={note ? 'vs-record' : 'vs-help'}>{note || '“Bir mesaj bırakmak istiyorum” de. Mesajın burada, söylediğin gibi görünsün.'}</p><small>Oturumluk demo notu · Metni indirerek sakla</small></section><section className="vs-card"><div className="vs-section-title"><span>↗</span><h2>Görüşme talebi</h2></div><p className={appointment ? 'vs-record' : 'vs-help'}>{appointment || 'Uygun olduğun gün ve saati söyle. Görüşme tercihin burada görünsün.'}</p><small>Talep taslağı · Takvim onayı değildir</small></section></div>
          <footer className="vs-diagnostics"><span>Yanıt: {source}</span><span>{llm}</span><span>{latency !== null ? `${(latency / 1000).toFixed(1)} sn yanıt` : '— sn'}</span><span>Ses: {voiceLabel}</span></footer>
        </div>
      </div>
    </main>
  </div>;
}
