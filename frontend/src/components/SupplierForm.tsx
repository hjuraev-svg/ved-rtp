import { useState } from 'react'
import type { Supplier } from '../types'
import { Field, Modal } from './ui'

export type NewSupplier = Omit<Supplier, 'id'>

export const BLANK_SUPPLIER: NewSupplier = {
  name: '',
  country: '',
  category: '',
  contact_person: '',
  email: '',
  phone: '',
  messenger: '',
  telegram_chat_id: '',
  notes: '',
  is_active: true,
}

/** Shared create/edit form — used by the Поставщики page and by SupplierPicker. */
export default function SupplierForm({
  supplier,
  onClose,
  onSave,
  busy,
  categories = [],
}: {
  supplier: Supplier | NewSupplier
  onClose: () => void
  onSave: (s: Supplier | NewSupplier) => void
  busy?: boolean
  /** Categories already in use — offered as suggestions, not enforced. */
  categories?: string[]
}) {
  const [form, setForm] = useState(supplier)
  const set = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Modal
      title={'id' in supplier ? 'Поставщик' : 'Новый поставщик'}
      onClose={onClose}
      footer={
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>
            Отмена
          </button>
          <button className="btn primary" onClick={() => onSave(form)} disabled={busy}>
            {busy ? 'Сохранение…' : 'Сохранить'}
          </button>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 13 }}>
        <Field label="Название">
          <input
            className="input"
            value={form.name}
            autoFocus
            placeholder="Ningbo Aroma Industrial Co., Ltd"
            onChange={(e) => set('name', e.target.value)}
          />
        </Field>
        <div className="grid-2">
          <Field label="Страна">
            <input
              className="input"
              value={form.country}
              placeholder="Китай"
              onChange={(e) => set('country', e.target.value)}
            />
          </Field>
          <Field label="Категория">
            <input
              className="input"
              value={form.category}
              list="supplier-categories"
              placeholder="Парфюмерия"
              onChange={(e) => set('category', e.target.value)}
            />
            <datalist id="supplier-categories">
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Контактное лицо">
            <input
              className="input"
              value={form.contact_person}
              onChange={(e) => set('contact_person', e.target.value)}
            />
          </Field>
          <Field label="Email">
            <input className="input" value={form.email} onChange={(e) => set('email', e.target.value)} />
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Телефон">
            <input className="input" value={form.phone} onChange={(e) => set('phone', e.target.value)} />
          </Field>
          <Field label="Мессенджер / канал связи">
            <input
              className="input"
              value={form.messenger}
              placeholder="WhatsApp / WeChat / Telegram"
              onChange={(e) => set('messenger', e.target.value)}
            />
          </Field>
        </div>
        <Field label="Telegram chat ID (для бота)">
          <input
            className="input"
            value={form.telegram_chat_id}
            placeholder="Например: 123456789 или -100..."
            onChange={(e) => set('telegram_chat_id', e.target.value.trim())}
          />
        </Field>
        <Field label="Примечания">
          <textarea className="textarea" value={form.notes} onChange={(e) => set('notes', e.target.value)} />
        </Field>
        <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={form.is_active}
            style={{ width: 16, height: 16, accentColor: 'var(--green)' }}
            onChange={(e) => set('is_active', e.target.checked)}
          />
          <span className="small">Активен</span>
        </label>
      </div>
    </Modal>
  )
}
