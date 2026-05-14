# Sosyal Medya Icerik Uretimi

Telegram kontrollu video uretim, onay, render ve yayin kuyrugu otomasyonu.

## Lokal ortam

Python 3.11 veya 3.12 kullanin.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Runtime bagimliliklari `requirements.txt` icinde, test ve gelistirme bagimliliklari `requirements-dev.txt` icinde tutulur.

## Test

```powershell
python -m pytest -q
```

`pytest` ortamda yoksa once `python -m pip install -r requirements-dev.txt` calistirin.

## Calistirma

Tek seferlik manuel uretim:

```powershell
python -m src.app.main
```

Telegram bot ile kontrollu uretim:

```powershell
python -m src.app.bot
```

Zamani gelen TikTok yayinlarini manuel tetikleme:

```powershell
python tools\publish_due_tiktok.py
```

## Docker ile calistirma

Docker Compose iki servis baslatir:

- `postgres`: Video gecmisi, metadata ve yayin kuyrugunu saklar.
- `bot`: Telegram komut botunu ayakta tutar.
- `tiktok-due`: Her 5 dakikada bir zamani gelen TikTok kaydi var mi diye kontrol eder.

```powershell
docker compose up -d --build
```

Loglari izleme:

```powershell
docker compose logs -f bot
docker compose logs -f tiktok-due
```

Servisleri durdurma:

```powershell
docker compose down
```

`tiktok-due` kontrol araligi `docker-compose.yml` icindeki `TIKTOK_DUE_CHECK_INTERVAL_SECONDS` ile ayarlanir. Basarili veya basarisiz TikTok denemeleri Telegram'a bildirilir; zamani gelen kayit yoksa sadece log'a yazilir.

## SQLite verisini PostgreSQL'e tasima

Eski `video_history.db` dosyasi silinmez; migration sadece okur ve Postgres'e kopyalar. Docker servislerini ilk kez Postgres ile baslattiktan sonra tek sefer calistirin:

```powershell
docker compose up -d postgres
docker compose run --rm bot python tools/migrate_sqlite_to_postgres.py
docker compose up -d --build
```

Migration sirasinda `outputs`, `assets` ve `user_data` altindaki eski Windows yollari Docker runtime yolu olan `/app/...` formatina cevrilir.

Postgres sifre hatasi alirsaniz ve henuz migration basarili olmadiysa Postgres volume'u sifirlayip tekrar deneyin:

```powershell
docker compose down -v
docker compose up -d postgres
docker compose build bot tiktok-due
docker compose run --rm bot python tools/migrate_sqlite_to_postgres.py
docker compose up -d
```

Bu komut proje klasorundeki `video_history.db`, `outputs/` veya `user_data/` dosyalarini silmez; sadece Docker'in `postgres_data` volume'unu sifirlar.

## Telegram komutlari

- `/start` sistemi baslatir.
- `/generate N` N adet video uretim-onay dongusu baslatir.
- `/stop` mevcut kritik isi guvenli bitirir, yeni video uretmez.
- `/pause` mevcut isi bitirip bekler.
- `/resume` duraklatilan sistemi devam ettirir.
- `/status` mevcut durumu gosterir.
- `/queue` planlanan YouTube ve lokal TikTok yayinlarini gosterir.
- `/publish_due` zamani gelen lokal TikTok yayinlarini yukler.

## TikTok yayin modeli

TikTok zamanlama v1'de lokal veritabani kuyrugu ile calisir. Uretim sonunda TikTok kaydi `video_history.db` icindeki lokal queue'ya yazilir. Gercek upload, `/publish_due` komutu veya `tools\publish_due_tiktok.py` ile zamani gelen kayitlar icin tetiklenir.

Scheduler kurulumunu testler ve manuel smoke test basarili olmadan acmayin.

## Secret dosyalari

API tokenlari ve client secret dosyalari `.env` ve `user_data/` altinda kalmalidir. Bunlar repo'ya eklenmez.
