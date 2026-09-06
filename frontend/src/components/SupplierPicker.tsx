import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth, useToast } from '../store'
import type { Supplier } from '../types'
import SupplierForm, { BLANK_SUPPLIER, type NewSupplier } from './SupplierForm'

const ADD = '__add__'

/**
 * Supplier dropdown with inline creation.
 *
 * Picking «＋ Новый поставщик…» opens the same form the Поставщики page uses,
 * and the newly created supplier is selected straight away — so adding one
 * never means abandoning a half-filled deal or КП.
 */
export default function SupplierPicker({
  value,
  onChange,
  placeholder = '— не выбран —',
  disabled,
  showCountry = true,
}: {
  value: number | string | null
  onChange: (id: number | null) => void
  placeholder?: string
  disabled?: boolean
  showCountry?: boolean
}) {
  const { canEdit } = useAuth()
  const { notify } = useToast()
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = () =>
    api
      .get<Supplier[]>('/api/suppliers')
      .then(setSuppliers)
      .catch(() => undefined)

  useEffect(() => {
    load()
  }, [])

  async function create(form: Supplier | NewSupplier) {
    if (!form.name.trim()) return notify('Укажите название', 'err')
    setBusy(true)
    try {
      const created = await api.post<Supplier>('/api/suppliers', {
        ...form,
        name: form.name.trim(),
      })
      setSuppliers((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)))
      onChange(created.id)
      setCreating(false)
      notify(`Поставщик «${created.name}» добавлен`)
    } catch (e: any) {
      notify(e?.message ?? 'Не удалось добавить', 'err')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <select
        className="select"
        value={value === null || value === undefined ? '' : String(value)}
        disabled={disabled}
        onChange={(e) => {
          if (e.target.value === ADD) {
            setCreating(true)
            return
          }
          onChange(e.target.value ? Number(e.target.value) : null)
        }}
      >
        <option value="">{placeholder}</option>
        {suppliers.map((s) => (
          <option key={s.id} value={s.id}>
            {showCountry && s.country ? `${s.name} (${s.country})` : s.name}
          </option>
        ))}
        {canEdit && !disabled && <option value={ADD}>＋ Новый поставщик…</option>}
      </select>

      {suppliers.length === 0 && canEdit && !disabled && (
        <button
          type="button"
          className="btn sm"
          style={{ marginTop: 6, alignSelf: 'flex-start' }}
          onClick={() => setCreating(true)}
        >
          ＋ Добавить первого поставщика
        </button>
      )}

      {creating && (
        <SupplierForm
          supplier={{ ...BLANK_SUPPLIER }}
          busy={busy}
          onClose={() => setCreating(false)}
          onSave={create}
        />
      )}
    </>
  )
}
