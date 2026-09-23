import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { automotiveRequest, type Demo, type Decision, type Outcome, type Preview, type Rehearsal } from '../../api/automotive';
import { useAuth } from '../../context/AuthContext';
import './automotive.css';
import { RoadsideLine } from './RoadsideLine';
import { ServiceOperations } from './ServiceOperations';

const labels: Record<Decision['status'], string> = {
  ready: 'Taslak hazırlanabilir', review: 'Kayıt incelenmeli', blocked: 'Temas engellendi', not_due: 'Henüz zamanı değil',
};
const outcomes: [Outcome, string][] = [
  ['interested', 'Randevu istiyorum'], ['already_serviced', 'Bakımı yaptırdım'], ['price', 'Fiyat nedir?'],
  ['opt_out', 'Bir daha yazmayın'], ['wrong_person', 'Yanlış kişi'], ['urgent', 'Güvenlik riski var'], ['human', 'Danışmana bağlayın'],
];

export function AutomotivePilot() {
  const [view, setView] = useState<'line' | 'operations' | 'maintenance'>('line');
  const { token } = useAuth();
  const [demo, setDemo] = useState<Demo | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [selected, setSelected] = useState('demo-01');
  const [result, setResult] = useState<Rehearsal | null>(null);
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [isDemo, setIsDemo] = useState(true);
  const requestVersion = useRef(0);

  useEffect(() => {
    if (!token) return;
    let active = true;
    automotiveRequest<Demo>('demo', token).then(data => {
      if (!active) return;
      setDemo(data); setPreview(data.preview); setInput(JSON.stringify(data.input, null, 2));
    }).catch(err => { if (active) setError((err as Error).message); });
    return () => { active = false; requestVersion.current++; };
  }, [token]);

  function selectVehicle(id: string) {
    requestVersion.current++; setSelected(id); setResult(null); setBusy(false); setError('');
  }

  async function run(outcome: Outcome) {
    if (!token) return;
    const version = ++requestVersion.current;
    setBusy(true); setError(''); setResult(null);
    try {
      const reply = await automotiveRequest<Rehearsal>('rehearsal', token, { vehicle_id: selected, outcome });
      if (version === requestVersion.current) setResult(reply);
    } catch (err) { if (version === requestVersion.current) setError((err as Error).message); }
    finally { if (version === requestVersion.current) setBusy(false); }
  }

  async function evaluate() {
    if (!token) return;
    const version = ++requestVersion.current;
    setBusy(true); setError(''); setResult(null);
    try {
      const next = await automotiveRequest<Preview>('preview', token, JSON.parse(input));
      if (version !== requestVersion.current) return;
      setPreview(next); setSelected(next.decisions[0]?.vehicle_id ?? ''); setIsDemo(false);
    } catch (err) { if (version === requestVersion.current) setError((err as Error).message); }
    finally { if (version === requestVersion.current) setBusy(false); }
  }

  function reset() {
    if (!demo) return;
    requestVersion.current++; setPreview(demo.preview); setSelected('demo-01'); setResult(null);
    setInput(JSON.stringify(demo.input, null, 2)); setIsDemo(true); setBusy(false); setError('');
  }
  const row = preview?.decisions.find(d => d.vehicle_id === selected);

  return <main className="auto-pilot">
    <header className="auto-header"><div><Link to="/operator">← Çalışma alanına dön</Link>
      <p className="auto-eyebrow">COGNIVAULT · SEKTÖR PİLOTU</p><h1>Atlas Oto Servis</h1>
      <p>Servis, çekici ve yol yardımı operasyon merkezi.</p></div>
      <span className="auto-badge">Kurgusal şirket · Yerel pilot</span></header>
    <nav className="auto-tabs" aria-label="Servis çalışma alanları">
      <button type="button" aria-pressed={view === 'line'} onClick={() => setView('line')}>Yol yardım hattı</button>
      <button type="button" aria-pressed={view === 'operations'} onClick={() => setView('operations')}>Servis ve yol yardımı</button>
      <button type="button" aria-pressed={view === 'maintenance'} onClick={() => setView('maintenance')}>Bakım hatırlatmaları</button>
    </nav>
    {view === 'line' ? <RoadsideLine /> : view === 'operations' ? <ServiceOperations /> : <>
    <p className="auto-notice">Bu ekran aday seçimini ve görüşme akışını dener. Arama veya mesaj göndermez; randevu ve iletişim reddi kaydetmez.</p>
    {error && <p role="alert" className="auto-error">{error}</p>}
    {!preview && !error && <p role="status">Servis örneği yükleniyor…</p>}
    {preview && <>
      <section className="auto-metrics" aria-label="Adaylık özeti">
        {(Object.keys(labels) as Decision['status'][]).map(status => <article key={status}>
          <strong>{preview.summary[status]}</strong><span>{labels[status]}</span></article>)}
      </section>
      <div className="auto-columns">
        <section className="auto-card"><h2>Bakım adayları</h2><p>Değerlendirme: {preview.as_of} · {isDemo ? 'Tamamen örnek kayıtlar' : 'Girdiğiniz kayıtların önizlemesi'}</p>
          <div className="auto-vehicles">{preview.decisions.map(item => <button type="button" key={item.vehicle_id}
            onClick={() => selectVehicle(item.vehicle_id)} aria-pressed={selected === item.vehicle_id}
            className={selected === item.vehicle_id ? 'auto-vehicle selected' : 'auto-vehicle'}>
            <span><strong>{item.customer_label}</strong><small>{item.vehicle_label}</small></span>
            <span className={`auto-status ${item.status}`}>{labels[item.status]}</span>
          </button>)}</div>
        </section>
        <section className="auto-card" aria-label="Karar ve görüşme provası"><h2>{row?.customer_label ?? 'Bir kayıt seçin'}</h2>
          {row && <><p>{row.reason}</p><ul>{row.evidence.map(line => <li key={line}>{line}</li>)}</ul>
            {row.draft ? <blockquote>{row.draft}</blockquote> : <p className="auto-notice">Bu kayıt için iletişim taslağı oluşturulmadı.</p>}
            {isDemo && <><h3>Müşteri böyle yanıt verirse</h3><div className="auto-actions">{outcomes.map(([outcome, label]) =>
              <button key={outcome} type="button" disabled={busy || (outcome === 'interested' && row.status !== 'ready')}
                onClick={() => void run(outcome)}>{label}</button>)}</div></>}
            {busy && <p role="status">Değerlendiriliyor…</p>}
            {result && <div aria-live="polite" className="auto-result"><h3>Asistanın yanıtı</h3><p>{result.reply}</p>
              <h3>Canlı bağlantıda gereken adımlar</h3><ol>{result.required_steps.map(step => <li key={step}>{step}</li>)}</ol>
              <small>Prova sonucu · İşlem yapılmadı, randevu oluşmadı.</small></div>}
          </>}
        </section>
      </div>
      <section className="auto-card auto-integration"><h2>Servisinize bağlama planı</h2>
        <div className="auto-flow"><span>Servis kayıtları</span><span>→ İzin ve bakım kontrolü</span><span>→ Görüşme</span><span>→ Canlı takvim</span><span>→ Sonucun kaydı</span></div>
        <p>İlk aşama: servis programından kayıt eşleme ve danışman kontrolü. Ardından izin kaynağı, telefon/SMS bağlantısı ve gerçek servis kapasitesi bağlanır. Bakım aralığı araç üreticisinin planından veya servisin doğrulanmış kaydından gelir.</p>
        <details><summary>Örnek veriyle kuralları dene</summary>
          <p>Bu alan geliştirme provası içindir. Anonimleştirilmiş örnekler kullanın. Veriler bu modül tarafından saklanmaz; dış model veya mesaj sağlayıcısına gönderilmez.</p>
          <label htmlFor="auto-data">Servis kayıtları (JSON)</label><textarea id="auto-data" value={input} onChange={e => setInput(e.target.value)} spellCheck={false}/>
          <div className="auto-actions"><button type="button" disabled={busy} onClick={() => void evaluate()}>Kuralları çalıştır</button>
            <button type="button" disabled={busy} onClick={reset}>Demo kayıtlarına dön</button></div>
        </details>
      </section>
    </>}
    </>}
  </main>;
}
