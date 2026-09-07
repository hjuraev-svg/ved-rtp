import { useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading, Panel } from '../components/ui'
import { useLiveData, useToast } from '../store'
import type { Integration } from '../types'
import { fmtDateTime } from '../util'

export default function Integrations() {
  const { notify } = useToast()
  const [busy, setBusy] = useState('')
  const { data, error, reload } = useLiveData<Integration[]>(() => api.get('/api/integrations'), [])

  async function run(action: 'gmail' | 'sync' | 'telegram') {
    setBusy(action)
    try {
      if (action === 'gmail') {
        const result = await api.post<{ authorization_url: string }>('/api/integrations/gmail/authorize')
        window.location.assign(result.authorization_url)
        return
      }
      if (action === 'sync') {
        const result = await api.post<{ imported: number }>('/api/integrations/gmail/sync')
        notify(`Gmail: ${result.imported} ta yangi xabar olindi`)
      } else {
        const result = await api.post<{ status: string; bot_username: string; error: string }>('/api/integrations/telegram/test')
        notify(result.status === 'connected' ? `Telegram bot @${result.bot_username} ulandi` : (result.error || 'Telegram ulanmagan'), result.status === 'connected' ? 'ok' : 'err')
      }
      reload()
    } catch (e: any) {
      notify(e?.message ?? 'Integratsiya xatosi', 'err')
    } finally {
      setBusy('')
    }
  }

  if (error) return <ErrorBox message={error} />
  if (!data) return <Loading />
  const gmail = data.find((x) => x.provider === 'gmail')
  const telegram = data.find((x) => x.provider === 'telegram')
  const state = (item?: Integration) => item?.status === 'connected' ? 'green' : item?.status === 'error' ? 'red' : ''

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 900 }}>
      <Panel title="Gmail — bitta kompaniya pochtasi" actions={<span className={`badge ${state(gmail)}`}>{gmail?.status ?? 'not_configured'}</span>}>
        <p className="small faint" style={{ marginTop: 0 }}>
          Xatlar bitim kartasidan yuboriladi, Inbox esa qo‘lda sinxronlanadi. OAuth tokeni shifrlangan holda faqat server bazasida saqlanadi.
        </p>
        {gmail?.label && <p className="small">Ulangan pochta: <b>{gmail.label}</b></p>}
        {gmail?.last_synced_at && <p className="small faint">Oxirgi sinxronlash: {fmtDateTime(gmail.last_synced_at)}</p>}
        {gmail?.last_error && <p className="error-box">{gmail.last_error}</p>}
        <div className="row wrap">
          <button className="btn primary" disabled={!!busy} onClick={() => run('gmail')}>
            {busy === 'gmail' ? 'Ochilyapti…' : gmail?.configured ? 'Gmail’ni qayta ulash' : 'Gmail’ni ulash'}
          </button>
          <button className="btn" disabled={!!busy || !gmail?.configured} onClick={() => run('sync')}>
            {busy === 'sync' ? 'Sinxronlanmoqda…' : 'Inbox sinxronlash'}
          </button>
        </div>
      </Panel>

      <Panel title="Telegram — bitta Bot API" actions={<span className={`badge ${state(telegram)}`}>{telegram?.status ?? 'not_configured'}</span>}>
        <p className="small faint" style={{ marginTop: 0 }}>
          Bot xabarlari webhook orqali qabul qilinadi. Har bir yetkazib beruvchi uchun uning Telegram chat ID sini «Поставщики» kartasida kiriting.
        </p>
        {telegram?.label && <p className="small">Bot: <b>@{telegram.label}</b></p>}
        {telegram?.last_error && <p className="error-box">{telegram.last_error}</p>}
        <div className="row wrap">
          <button className="btn primary" disabled={!!busy} onClick={() => run('telegram')}>
            {busy === 'telegram' ? 'Tekshirilmoqda…' : 'Bot ulanishini tekshirish'}
          </button>
        </div>
      </Panel>

      <Panel title="Ishga tushirish uchun kerak bo‘ladi">
        <ol className="small faint" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
          <li>`.env` ichida `INTEGRATION_ENCRYPTION_KEY` yarating.</li>
          <li>Google Cloud’da Gmail API va OAuth Web client yarating, callback URL ni ruxsat bering.</li>
          <li>@BotFather’dan token oling, `TELEGRAM_BOT_TOKEN` hamda webhook secret kiriting.</li>
          <li>Public HTTPS manzilda Telegram webhook URL sini `setWebhook` orqali bir marta ulang.</li>
        </ol>
      </Panel>
    </div>
  )
}
