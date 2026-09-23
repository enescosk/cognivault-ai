import { useEffect, useRef, useState } from 'react';
import { automotiveRequest } from '../../api/automotive';
import { useAuth } from '../../context/AuthContext';

type Service = { id: string; title: string; group: string; icon: string; description: string; prompt: string; mobile: boolean };
type Team = { id: string; name: string; kind: string; distance_km: number };
type Location = { latitude: number; longitude: number; address: string; source: string };
type Case = { id: string; version: number; service: string; service_title: string; customer: string; channel: string;
  status: string; status_label: string; vehicle: string; destination: string; safe: boolean | null;
  location: Location | null; share_permission: boolean; assigned_team: Team | null; eta_minutes: number | null;
  handoff: { map_url: string; vehicle: string; destination: string; location: Location; delivery_status: string } | null;
  messages: { role: string; text: string; at: string }[]; audit: { action: string; at: string; detail: string }[] };
const sequence = ['intake', 'needs_location', 'ready', 'offered', 'accepted', 'en_route', 'arrived', 'transporting', 'completed'];
const stages: Record<string, string> = { intake: 'Karşılama', needs_location: 'Konum', ready: 'Hazır', offered: 'Teklif', accepted: 'Kabul', en_route: 'Yolda', arrived: 'Ulaştı', transporting: 'Taşıma', completed: 'Teslim' };
const newKey = () => crypto.randomUUID();

export function ServiceOperations() {
  const { token } = useAuth();
  const [services, setServices] = useState<Service[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [selectedService, setSelectedService] = useState('tow');
  const [active, setActive] = useState<Case | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [vehicle, setVehicle] = useState('');
  const [destination, setDestination] = useState('Atlas Oto Servis');
  const [safe, setSafe] = useState('unknown');
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [address, setAddress] = useState('');
  const [message, setMessage] = useState('');
  const [eta, setEta] = useState('25');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const service = services.find(s => s.id === (active?.service ?? selectedService));
  const editable = !!active && ['intake', 'needs_location', 'ready'].includes(active.status);
  const closed = !!active && ['completed', 'cancelled'].includes(active.status);

  useEffect(() => {
    if (!token) return;
    let disposed = false;
    Promise.all([automotiveRequest<{ services: Service[] }>('operations/catalog', token), automotiveRequest<Case[]>('operations/cases', token)])
      .then(([catalog, rows]) => { if (!disposed) { setServices(catalog.services); setCases(rows); } })
      .catch(err => { if (!disposed) setError((err as Error).message); });
    return () => { disposed = true; generation.current++; };
  }, [token]);

  useEffect(() => {
    setTeams([]);
    if (!token || !active?.location || active.status !== 'ready') return;
    let disposed = false;
    automotiveRequest<Team[]>(`operations/cases/${active.id}/teams`, token)
      .then(rows => { if (!disposed) setTeams(rows); })
      .catch(err => { if (!disposed) setError((err as Error).message); });
    return () => { disposed = true; };
  }, [token, active?.id, active?.version]);

  function storeCase(row: Case) {
    setActive(row);
    setCases(old => [row, ...old.filter(c => c.id !== row.id)].slice(0, 100));
  }
  function openCase(row: Case) {
    generation.current++; setBusy(false); setError(''); setActive(row); setMessage('');
    setVehicle(row.vehicle); setDestination(row.destination || 'Atlas Oto Servis');
    setSafe(row.safe === true ? 'safe' : row.safe === false ? 'unsafe' : 'unknown');
    setLat(row.location ? String(row.location.latitude) : ''); setLon(row.location ? String(row.location.longitude) : '');
    setAddress(row.location?.address ?? '');
  }
  async function create() {
    if (!token || busy) return;
    setBusy(true); setError('');
    const current = ++generation.current;
    try {
      const row = await automotiveRequest<Case>('operations/cases', token, { request_key: newKey(), service: selectedService, customer: 'Örnek müşteri', channel: 'phone' });
      if (current !== generation.current) return;
      storeCase(row); setVehicle(''); setDestination('Atlas Oto Servis'); setSafe('unknown'); setLat(''); setLon(''); setAddress(''); setMessage('');
    } catch (err) { if (current === generation.current) setError((err as Error).message); }
    finally { if (current === generation.current) setBusy(false); }
  }
  async function act(kind: string, fields: Record<string, unknown> = {}, whatsapp = false) {
    if (!token || !active || busy) return;
    const id = active.id;
    const current = ++generation.current;
    setBusy(true); setError('');
    try {
      const row = await automotiveRequest<Case>(`operations/cases/${id}/${whatsapp ? 'whatsapp-location' : 'actions'}`, token,
        { event_key: newKey(), version: active.version, ...(whatsapp ? {} : { kind }), ...fields });
      if (current !== generation.current) return;
      storeCase(row); if (kind === 'message') setMessage('');
    } catch (err) {
      if (current === generation.current) {
        setError((err as Error).message);
        try { const fresh = await automotiveRequest<Case>(`operations/cases/${id}`, token); if (current === generation.current) storeCase(fresh); } catch { /* original error remains visible */ }
      }
    } finally { if (current === generation.current) setBusy(false); }
  }
  function location() {
    if (!lat.trim() || !lon.trim() || !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon))) {
      setError('Enlem ve boylamı geçerli sayı olarak girin.'); return;
    }
    void act('location', { latitude: Number(lat), longitude: Number(lon), address }, true);
  }

  return <section className="service-ops">
    <div className="ops-intro"><div><p className="auto-eyebrow">TEK KARŞILAMA · TÜM SERVİS TALEPLERİ</p>
      <h2>Yolda da, serviste de yanınızda.</h2><p>“Atlas Yol Yardım’a hoş geldiniz. Size nasıl yardımcı olabilirim?”</p></div>
      <div className="ops-connection"><span>● Yerel kayıt açık</span><small>Telefon ve WhatsApp bağlantısı bekleniyor</small></div></div>
    <p className="auto-notice">Talep ve işlem geçmişi bu kullanıcı için kaydedilir. Ekipler örnektir; konum hiçbir çekiciye gönderilmez ve gerçek sevk yapılmaz. Ekip düğmeleri operatör provasıdır.</p>
    <div className="ops-catalog" aria-label="Hizmetler">{services.map(item => <button type="button" key={item.id} disabled={busy}
      className={selectedService === item.id ? 'ops-service selected' : 'ops-service'} aria-pressed={selectedService === item.id}
      onClick={() => { setSelectedService(item.id); }}>
      <span className="ops-icon">{item.icon}</span><strong>{item.title}</strong><small>{item.description}</small></button>)}</div>
    <div className="ops-launch"><div><strong>{services.find(s => s.id === selectedService)?.title}</strong><p>Yeni çağrı karşılamasını ve iş akışını başlat.</p></div>
      <button type="button" className="ops-primary" disabled={busy || !services.length} onClick={() => void create()}>Yeni örnek talep aç</button></div>
    {error && <p role="alert" className="auto-error">{error}</p>}
    <div className="ops-workspace">
      <aside className="auto-card ops-queue"><h3>Talep panosu <small>({cases.length})</small></h3>
        {!cases.length && <p>İlk talep açıldığında burada görünür.</p>}
        {cases.map(row => <button type="button" key={row.id} disabled={busy} onClick={() => openCase(row)}
          className={active?.id === row.id ? 'ops-case selected' : 'ops-case'} aria-pressed={active?.id === row.id}>
          <strong>{row.service_title}</strong><span>{row.customer} · {row.id.slice(0, 6)}</span><small>{row.status_label}</small></button>)}
      </aside>
      <section className="auto-card ops-main"><h2>{active ? active.service_title : 'Gelen çağrıyı deneyin'}</h2>
        {!active ? <p>Yukarıdan hizmet seçip örnek talep açın. Karşılama, bilgi toplama, konum ve ekip adımlarını aynı ekranda takip edin.</p> : <>
          <p><span className="auto-badge">{active.status_label}</span> <small>Talep #{active.id.slice(0, 8)} · Yerel prova</small></p>
          {service?.mobile && <div className="ops-progress" aria-label="Sevk adımları">{sequence.map((stage, i) => <span key={stage}
            className={sequence.indexOf(active.status) >= i ? 'done' : ''}>{stages[stage]}</span>)}</div>}
          <div className="ops-chat" aria-label="Görüşme geçmişi">{active.messages.map((item, i) => <div key={i} className={`ops-bubble ${item.role}`}>
            <small>{item.role === 'assistant' ? 'Atlas asistan' : 'Müşteri'}</small><p>{item.text}</p></div>)}</div>
          {!closed && <form className="ops-message" onSubmit={e => { e.preventDefault(); void act('message', { text: message }); }}>
            <label htmlFor="ops-message">Müşteri ne söylüyor?</label><input id="ops-message" value={message} maxLength={1200} onChange={e => setMessage(e.target.value)} placeholder={service?.prompt}/>
            <button type="submit" disabled={busy || !message.trim()}>Yanıtı dene</button>
          </form>}
          {editable && <div className="ops-details"><h3>1. Araç ve güvenlik</h3>
            <label htmlFor="ops-vehicle">Araç / model / gerekli ekipman</label><input id="ops-vehicle" value={vehicle} maxLength={120} onChange={e => setVehicle(e.target.value)} placeholder="Örn. binek araç, otomatik, tekerler dönüyor"/>
            <label htmlFor="ops-destination">Hedef servis veya hizmet yeri</label><input id="ops-destination" value={destination} maxLength={200} onChange={e => setDestination(e.target.value)}/>
            {service?.mobile && <><label htmlFor="ops-safe">Müşterinin güvenlik beyanı</label><select id="ops-safe" value={safe} onChange={e => setSafe(e.target.value)}>
              <option value="unknown">Henüz sorulmadı</option><option value="safe">Güvendeyim; yaralanma / yakın tehlike yok</option><option value="unsafe">Güvende değilim / acil risk var</option></select></>}
            <button type="button" disabled={busy || !vehicle.trim()} onClick={() => void act('details', { vehicle, destination, safe: safe === 'unknown' ? null : safe === 'safe' })}>Bilgileri kaydet</button>
            {service?.mobile && <><h3>2. WhatsApp konumu</h3><p>Müşterinin paylaştığı tek konum pini alınır. Canlı konum izleme yapılmaz.</p>
              <div className="ops-coordinates"><div><label htmlFor="ops-lat">Enlem</label><input id="ops-lat" inputMode="decimal" value={lat} onChange={e => setLat(e.target.value)}/></div>
                <div><label htmlFor="ops-lon">Boylam</label><input id="ops-lon" inputMode="decimal" value={lon} onChange={e => setLon(e.target.value)}/></div></div>
              <label htmlFor="ops-address">Adres, yol yönü ve erişim notu</label><input id="ops-address" value={address} maxLength={300} onChange={e => setAddress(e.target.value)}/>
              <div className="auto-actions"><button type="button" disabled={busy} onClick={() => { setLat('41.010'); setLon('29.070'); setAddress('Kurgusal örnek konum · İstanbul'); }}>Örnek pin doldur</button>
                <button type="button" disabled={busy || !lat || !lon} onClick={location}>WhatsApp konumu gelmesini dene</button></div>
              {active.location && <><p>Alınan pin: {active.location.latitude}, {active.location.longitude} · {active.location.address}</p>
                <div className="auto-actions"><button type="button" disabled={busy || active.share_permission} onClick={() => void act('share', { permission: true })}>Bu konumu yardım ekibiyle paylaşmayı kabul et</button>
                  <button type="button" disabled={busy} onClick={() => void act('share', { permission: false })}>Paylaşımı reddet</button></div></>}
            </>}
          </div>}
          {active.status === 'ready' && service?.mobile && <section><h3>3. Uygun ekip</h3><p>Örnek ekiplerin ekipmanı ve kapsama alanı kontrol edilir. Mesafe kuş uçuşudur, varış süresi değildir.</p>
            {!teams.length && <p>Bu konum / hizmet için uygun örnek ekip yok. Danışmana aktarabilirsiniz.</p>}
            {teams.map(team => <div className="ops-team" key={team.id}><div><strong>{team.name}</strong><p>{team.kind} · {team.distance_km} km kuş uçuşu</p></div>
              <button type="button" disabled={busy || !active.share_permission} onClick={() => void act('offer', { team_id: team.id })}>Konumlu görev hazırla</button></div>)}</section>}
          {active.status === 'offered' && <section><h3>Ekip yanıtı — prova</h3><label htmlFor="ops-eta">Ekibin bildirdiği tahmini varış (dakika)</label>
            <input id="ops-eta" type="number" min="1" max="300" value={eta} onChange={e => setEta(e.target.value)}/>
            <div className="auto-actions"><button type="button" disabled={busy || !eta} onClick={() => void act('accept', { eta_minutes: Number(eta) })}>Ekip kabul etti</button>
              <button type="button" disabled={busy} onClick={() => void act('decline')}>Ekip uygun değil</button></div></section>}
          <div className="auto-actions ops-dispatch-actions">
            {['human', 'emergency'].includes(active.status) && active.assigned_team && <button type="button" disabled={busy} onClick={() => void act('cancel_confirmed')}>Ekip iptali teyit etti (prova)</button>}
            {active.status === 'accepted' && <button type="button" disabled={busy} onClick={() => void act('en_route')}>Ekip yola çıktı</button>}
            {active.status === 'en_route' && <button type="button" disabled={busy} onClick={() => void act('arrived')}>Ekip konuma ulaştı</button>}
            {active.status === 'arrived' && <button type="button" disabled={busy} onClick={() => void act(['tow', 'ev', 'accident'].includes(active.service) ? 'transport' : 'complete')}>{['tow', 'ev', 'accident'].includes(active.service) ? 'Araç taşıma başladı' : 'Yerinde yardım tamamlandı'}</button>}
            {active.status === 'transporting' && <button type="button" disabled={busy} onClick={() => void act('complete')}>Araç servise teslim edildi</button>}
            {!closed && <><button type="button" disabled={busy} onClick={() => void act('human')}>Danışmana aktarım talebi</button>
              <button type="button" disabled={busy} onClick={() => void act('cancel')}>İptal talebi</button></>}
          </div>
          {busy && <p role="status">Talep güncelleniyor…</p>}
        </>}
      </section>
      <aside className="auto-card ops-handoff"><h3>Ekip iş kartı</h3>
        {active?.handoff ? <><span className="auto-badge">Hazırlandı · Gönderilmedi</span><h3>{active.assigned_team?.name}</h3>
          <p>{active.handoff.vehicle}</p><p>Hedef: {active.handoff.destination}</p><p>{active.handoff.location.address}</p>
          <p>{active.handoff.location.latitude}, {active.handoff.location.longitude}</p>
          <a href={active.handoff.map_url} target="_blank" rel="noreferrer">Konumu haritada aç ↗</a>
          <p><small>Haritayı açmak koordinatları Google Maps’e iletir.</small></p>
          <p>Varış tahmini: {active.eta_minutes ? `${active.eta_minutes} dk (ekip beyanı)` : 'Henüz yok'}</p></>
          : <p>Konum paylaşımı onaylanıp uygun ekip seçildiğinde yalnız gerekli bilgileri içeren iş kartı burada görünür.</p>}
        <h3>İşlem geçmişi</h3><div className="ops-audit">{active?.audit.map((event, i) => <div key={i}><small>{new Date(event.at).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}</small><p>{event.detail}</p></div>)}</div>
      </aside>
    </div>
  </section>;
}
