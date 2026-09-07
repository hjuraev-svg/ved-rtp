# Gmail va Telegram integratsiyasi

Loyiha bitta kompaniya Gmail pochtasi va bitta Telegram bot uchun tayyorlangan.
Kalitlar `.env` ichida qoladi: ular `.gitignore` bilan himoyalangan, API ham
ularni qaytarmaydi. Gmail refresh-tokeni PostgreSQL bazasiga Fernet bilan
shifrlanib saqlanadi.

## 1. `.env` ni to‘ldirish

`.env.example` dan quyidagi qiymatlarni oling. Shifrlash kalitini bir marta
yarating va yo‘qotmang — u o‘zgarsa avvalgi Gmail tokenini o‘qib bo‘lmaydi.

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`PUBLIC_BASE_URL` lokal ish uchun `http://localhost:8090`, public server uchun
esa haqiqiy tashqi manzil bo‘ladi (bu loyiha uchun masalan
`https://jnslabsonline.uz/ved`). Production’da `GMAIL_REDIRECT_URI`
odatda bo‘sh qoldiriladi: tizim o‘zi
`$PUBLIC_BASE_URL/api/integrations/gmail/callback` ni ishlatadi.

## 2. Gmail

Google Cloud Console’da yangi loyiha yarating, **Gmail API** ni yoqing va
**OAuth client ID → Web application** yarating. Authorized redirect URI sifatida
quyidagini kiriting:

```
https://sizning-domeningiz/api/integrations/gmail/callback
```

Client ID va Client secret’ni `.env` ga yozib Docker stack’ni qayta ishga
tushiring. So‘ng administrator sifatida tizimdagi **Почта и Telegram** sahifasiga
kiring va **Gmail’ni ulash** ni bosing. Google ruxsatidan keyin kompaniya
pochtasi ulanadi.

Gmail inbox ish paytida `GMAIL_POLL_INTERVAL_MINUTES=5` bo‘yicha avtomatik
tekshiriladi; `0` manual rejimni yoqadi. Yuborilgan xatlarga `X-VED-Deal`
sarlavhasi qo‘shiladi. Kiruvchi xat esa avval shu sarlavha, bo‘lmasa supplier
emaili orqali aktiv bitimga bog‘lanadi.

## 3. Telegram

@BotFather ichida bot yarating va tokenini `TELEGRAM_BOT_TOKEN` ga qo‘ying.
`TELEGRAM_WEBHOOK_SECRET` uchun faqat harf, raqam, `_` va `-` dan iborat uzun
tasodifiy qiymat yarating. Public HTTPS domen bo‘lsa, **Bot ulanishini
tekshirish** tugmasi `setWebhook` ni o‘zi chaqiradi.

Har bir yetkazib beruvchi avval botga `/start` yozishi kerak. Keyin uning chat
ID sini **Поставщики → Telegram chat ID** maydoniga kiriting. Shundan keyin
bitim kartasidagi **Почта и Telegram** tabidan xabar yuborish va kelgan javoblarni
shu bitimda ko‘rish mumkin.

Telegram webhook faqat HTTPS public URL bilan xabar qabul qiladi. Lokal
`localhost` Internetdan ko‘rinmagani uchun, lokal testda yuborish ishlaydi,
ammo kiruvchi webhook uchun public Caddy domeni (yoki vaqtinchalik tunnel)
kerak bo‘ladi.

## Xavfsizlik va cheklovlar

* Gmail uchun OAuth — parol yoki App Password saqlanmaydi.
* Telegram bot tokeni faqat backend environment’da turadi va UI’da chiqmaydi.
* Telegram Bot API botni birinchi bo‘lib yozmagan foydalanuvchiga xabar yubora
  olmaydi; bu Telegram qoidasi.
* Hozirgi yechim Bot API. Shaxsiy Telegram akkaunti (MTProto) alohida, yuqori
  xavfli autentifikatsiya va session boshqaruvini talab qiladi; u bu tizimga
  ataylab qo‘shilmagan.
