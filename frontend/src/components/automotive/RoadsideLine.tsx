import { useEffect, useRef, useState } from 'react';
import { automotiveRequest } from '../../api/automotive';
import { useAuth } from '../../context/AuthContext';

type Msg = { id: string; direction: 'in' | 'out'; audience: string; purpose: string; form: string; body: string;
  delivery_status: string; error: string | null; buttons: [string, string][]; location_request: boolean; at: string };
type TeamInfo = { id: string; name: string; kind: string };
type Catalog = { teams: TeamInfo[]; whatsapp_connected: boolean; telephony_connected: boolean;
  simulator_enabled: boolean; offer_timeout_minutes: number };
type CaseRow = { id: string; version: number; service_title: string; status: string; status_label: string;
  priority?: string; assigned_team: { id: string; name: string; distance_km?: number } | null; eta_minutes: number | null;
  vehicle: string; destination: string; location: { latitude: number; longitude: number } | null; contact?: string; channel: string };

const STEPS = ['intake', 'needs_location', 'ready', 'offered', 'accepted', 'en_route', 'arrived', 'transporting', 'completed'];
const STEP_LABELS: Record<string, string> = { intake: 'Karşılama', needs_location: 'Konum', ready: 'Hazır', offered: 'Teklif',
  accepted: 'Kabul', en_route: 'Yolda', arrived: 'Ulaştı', transporting: 'Taşıma', completed: 'Teslim' };
const DELIVERY: Record<string, string> = { demo_only: 'Demo · gönderilmedi', queued: 'Kuyrukta', accepted: 'Sağlayıcı kabul etti',
  sent: 'Gönderildi', delivered: 'İletildi', read: 'Okundu', failed: 'Başarısız', blocked_no_template: 'Şablon yok · gitmedi' };
const QUICK = ['Yolda kaldım, çekici lazım', 'Aküm bitti, araba çalışmıyor', 'Lastiğim patladı', 'Kaza yaptım, yaralı yok', 'Çekici nerede?', 'İptal edin, hallettim'];
const randomPhone = () => `+90532${String(Math.floor(1_000_000 + Math.random() * 8_999_999))}`;

function Bubble({ m, own }: { m: Msg; own: boolean }) {
  return <div className={own ? 'rs-bubble own' : 'rs-bubble'}>
    <p>{m.body}</p>
    {!own && <small>{m.form === 'template' ? 'Şablon · ' : ''}{DELIVERY[m.delivery_status] ?? m.delivery_status}</small>}
  </div>;
}

export function RoadsideLine() {
  const { token } = useAuth();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [phone, setPhone] = useState(randomPhone);
  const [row, setRow] = useState<CaseRow | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState('');
  const [speech, setSpeech] = useState('Aracım çalışmıyor, çekici lazım');
  const [call, setCall] = useState<{ sid: string; attempt: number; lines: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const customerEnd = useRef<HTMLDivElement>(null);
  const teamEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) return;
    automotiveRequest<Catalog>('operations/catalog', token).then(setCatalog).catch(e => setError((e as Error).message));
  }, [token]);
  useEffect(() => { customerEnd.current?.scrollIntoView({ block: 'nearest' }); teamEnd.current?.scrollIntoView({ block: 'nearest' }); }, [messages]);

  async function refresh(caseRow: CaseRow | null) {
    if (!token || !caseRow) return;
    setRow(caseRow);
    setMessages(await automotiveRequest<Msg[]>(`operations/cases/${caseRow.id}/messages`, token));
  }
  async function run(step: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError('');
    try { await step(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const customer = (body: Record<string, unknown>) => run(async () => {
    const r = await automotiveRequest<{ case: CaseRow }>('operations/simulate/customer', token!, { phone, ...body });
    await refresh(r.case);
  });
  const team = (teamId: string, replyId: string) => run(async () => {
    const r = await automotiveRequest<{ case: CaseRow }>('operations/simulate/team', token!, { team_id: teamId, reply_id: replyId });
    await refresh(r.case);
  });
  const dial = () => run(async () => {
    const r = await automotiveRequest<{ call_sid: string; say: string; ask_again: boolean; case: CaseRow | null }>(
      'operations/simulate/call', token!, { phone, speech, call_sid: call?.sid ?? '', attempt: call?.attempt ?? 1 });
    setCall(old => ({ sid: r.call_sid, attempt: r.ask_again ? 2 : 1, lines: [...(old?.lines ?? []), `🗣 ${speech}`, `🤖 ${r.say}`] }));
    if (r.case) await refresh(r.case);
  });
  const expire = () => run(async () => {
    await automotiveRequest('operations/simulate/expire-offers', token!, {});
    if (row) await refresh(await automotiveRequest<CaseRow>(`operations/cases/${row.id}`, token!));
  });
  function sendLocation() {
    // Örnek ekiplerin kapsama alanında (İstanbul, Anadolu yakası) küçük sapmalı bir pin.
    const jitter = () => (Math.random() - 0.5) * 0.02;
    void customer({ kind: 'location', latitude: +(41.01 + jitter()).toFixed(5), longitude: +(29.07 + jitter()).toFixed(5),
      address: 'Simülasyon konumu · İstanbul' });
  }
  function newCustomer() { setPhone(randomPhone()); setRow(null); setMessages([]); setCall(null); setText(''); setError(''); }

  if (catalog && !catalog.simulator_enabled) {
    return <section className="rs-line"><p className="auto-notice">Canlı WhatsApp hattı açık; simülatör güvenlik gereği kapalı.
      Gelen işleri “Servis ve yol yardımı” sekmesinden izleyin.</p></section>;
  }

  const customerMsgs = messages.filter(m => m.audience === 'customer');
  const teamMsgs = messages.filter(m => m.audience.startsWith('team:'));
  const lastCustomerOut = [...customerMsgs].reverse().find(m => m.direction === 'out');
  // Ekibe giden SON mesajın düğmeleri: reddedilmiş eski teklifin "Kabul" düğmesi ekranda kalmamalı.
  const lastTeamOut = [...teamMsgs].reverse().find(m => m.direction === 'out');
  const teamName = (audience: string) => catalog?.teams.find(t => `team:${t.id}` === audience)?.name ?? audience;
  const closed = !!row && ['completed', 'cancelled'].includes(row.status);
  const outgoing = messages.filter(m => m.direction === 'out');

  return <section className="rs-line">
    <div className="ops-intro"><div><p className="auto-eyebrow">TELEFON · WHATSAPP · ÇEKİCİ</p>
      <h2>Arayan ya da yazan müşteri, en yakın çekiciye.</h2>
      <p>Konum WhatsApp’tan gelir, uygun ekibe otomatik teklif gider; müşteriye “yola çıktı” yalnız ekip yola çıkınca söylenir.</p></div>
      <div className="ops-connection"><span>● Demo modu</span>
        <small>Telefon {catalog?.telephony_connected ? 'bağlı' : 'bağlı değil'} · WhatsApp {catalog?.whatsapp_connected ? 'bağlı' : 'bağlı değil'}</small></div></div>
    <p className="auto-notice">Mesajlar hiçbir numaraya gitmez. İki telefon simülasyondur; akış canlıdaki kodun aynısından geçer.
      Ekipler örnektir. Yanıtsız teklif {catalog?.offer_timeout_minutes ?? 5} dakikada sıradaki ekibe geçer.</p>
    {error && <p role="alert" className="auto-error">{error}</p>}

    <div className="rs-grid">
      <section className="rs-phone" aria-label="Müşteri WhatsApp simülasyonu">
        <header><strong>Müşteri</strong><small>{phone}</small>
          <button type="button" onClick={newCustomer} disabled={busy}>Yeni müşteri</button></header>
        <div className="rs-thread" aria-live="polite">
          {!customerMsgs.length && <p className="rs-empty">Müşteri gibi yazın ya da arayın.</p>}
          {customerMsgs.map(m => <Bubble key={m.id} m={m} own={m.direction === 'in'} />)}
          <div ref={customerEnd} />
        </div>
        {lastCustomerOut && !closed && (lastCustomerOut.buttons.length > 0 || lastCustomerOut.location_request) &&
          <div className="rs-choices">
            {lastCustomerOut.buttons.map(([id, title]) => <button type="button" key={id} disabled={busy}
              onClick={() => void customer({ kind: 'reply', reply_id: id, text: title })}>{title}</button>)}
            {lastCustomerOut.location_request && <button type="button" disabled={busy} onClick={sendLocation}>📍 Konumu gönder</button>}
          </div>}
        <form className="rs-compose" onSubmit={e => { e.preventDefault(); if (text.trim()) { void customer({ text }); setText(''); } }}>
          <label htmlFor="rs-text" className="rs-sr">Müşteri mesajı</label>
          <input id="rs-text" value={text} maxLength={1200} onChange={e => setText(e.target.value)} placeholder="Mesaj yazın…" />
          <button type="submit" disabled={busy || !text.trim()}>Gönder</button>
        </form>
        <div className="rs-quick">{QUICK.map(q => <button type="button" key={q} disabled={busy} onClick={() => void customer({ text: q })}>{q}</button>)}</div>
        <details className="rs-call"><summary>📞 Bunun yerine telefonla ara</summary>
          <label htmlFor="rs-speech">Arayanın ilk cümlesi</label>
          <input id="rs-speech" value={speech} maxLength={300} onChange={e => setSpeech(e.target.value)} />
          <button type="button" disabled={busy || !speech.trim()} onClick={() => void dial()}>{call?.attempt === 2 ? 'Tekrar söyle' : 'Aramayı başlat'}</button>
          {call && <div className="rs-transcript">{call.lines.map((l, i) => <p key={i}>{l}</p>)}</div>}
        </details>
      </section>

      <section className="auto-card rs-case" aria-label="İş durumu">
        {!row ? <p>İş, müşterinin ilk mesajı ya da aramasıyla açılır.</p> : <>
          <h3>{row.service_title}</h3>
          <p><span className="auto-badge">{row.status_label}</span>{row.priority === 'high' && <span className="rs-priority">Öncelikli · şeritte</span>}</p>
          <div className="ops-progress" aria-label="Sevk adımları">{STEPS.map((s, i) => <span key={s}
            className={STEPS.indexOf(row.status) >= i ? 'done' : ''}>{STEP_LABELS[s]}</span>)}</div>
          <dl className="rs-facts">
            <dt>Kanal</dt><dd>{row.channel === 'phone' ? 'Telefon' : 'WhatsApp'} · {row.contact}</dd>
            <dt>Araç</dt><dd>{row.vehicle || '—'}</dd>
            <dt>Varış yeri</dt><dd>{row.destination || '—'}</dd>
            <dt>Konum</dt><dd>{row.location ? `${row.location.latitude}, ${row.location.longitude}` : 'Bekleniyor'}</dd>
            <dt>Ekip</dt><dd>{row.assigned_team ? `${row.assigned_team.name}${row.assigned_team.distance_km ? ` · ${row.assigned_team.distance_km} km` : ''}` : '—'}</dd>
            <dt>Varış tahmini</dt><dd>{row.eta_minutes ? `${row.eta_minutes} dk (ekip beyanı)` : '—'}</dd>
          </dl>
          {row.status === 'offered' && <button type="button" className="rs-expire" disabled={busy} onClick={() => void expire()}>
            Ekip yanıt vermedi — teklif süresini doldur</button>}
          <h3>Giden mesajlar</h3>
          <ul className="rs-deliveries">{outgoing.map(m => <li key={m.id}>
            <span>{m.audience === 'customer' ? 'Müşteri' : teamName(m.audience)}</span>
            <small>{m.form === 'template' ? 'Şablon' : 'Serbest'} · {DELIVERY[m.delivery_status] ?? m.delivery_status}</small>
            {m.error && <small className="rs-warn">{m.error}</small>}</li>)}</ul>
        </>}
      </section>

      <section className="rs-phone" aria-label="Çekici WhatsApp simülasyonu">
        <header><strong>Çekici şoförü</strong><small>{row?.assigned_team?.name ?? 'Teklif bekleniyor'}</small></header>
        <div className="rs-thread" aria-live="polite">
          {!teamMsgs.length && <p className="rs-empty">Konum ve paylaşım izni gelince en yakın uygun ekibe iş teklifi buraya düşer.</p>}
          {teamMsgs.map(m => <div key={m.id}>{m.direction === 'out' && <small className="rs-to">→ {teamName(m.audience)}</small>}
            <Bubble m={m} own={m.direction === 'in'} /></div>)}
          <div ref={teamEnd} />
        </div>
        {lastTeamOut && lastTeamOut.buttons.length > 0 && <div className="rs-choices">{lastTeamOut.buttons.map(([id, title]) => <button type="button" key={id} disabled={busy}
          onClick={() => void team(lastTeamOut.audience.slice(5), id)}>{title}</button>)}</div>}
      </section>
    </div>
    {busy && <p role="status">İşleniyor…</p>}
  </section>;
}
