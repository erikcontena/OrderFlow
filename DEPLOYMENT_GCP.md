# Panduan Deployment Google Cloud Platform (GCE VM + Docker Compose + PostgreSQL)

Panduan langkah-demi-langkah untuk mendeploy **OrderFlow HFT Engine** ke Google Cloud Platform menggunakan **Google Compute Engine (GCE VM)** dan **Docker Compose** dengan database **PostgreSQL**.

---

## 1. Spesifikasi Infrastruktur GCP Direkomendasikan

- **Layanan**: Google Compute Engine (GCE VM)
- **Tipe Mesin**: `e2-standard-2` (2 vCPU, 8 GB RAM) atau `e2-medium` (1-2 vCPU, 4 GB RAM)
- **Sistem Operasi**: Ubuntu 22.04 LTS x86_64
- **Lokasi Region**: 
  - `asia-southeast1` (Singapura) — **Sangat direkomendasikan** untuk latensi terendah (< 5-15ms) ke server bursa Binance, Bybit, Hyperliquid, dan Lighter.
- **Firewall Rules**:
  - Allow HTTP (Port 80)
  - Allow HTTPS (Port 443)
  - Allow Port 8000 (Backend API & WebSocket /ws/telemetry)

---

## 2. Cara Cepat Membuat Instance VM di GCP

Anda dapat membuat VM melalui **Google Cloud Console (Web)** atau menggunakan perintah **`gcloud CLI`**:

### Opsi A: Menggunakan Google Cloud Console (Web GUI)
1. Buka [Google Cloud Console](https://console.cloud.google.com/).
2. Masuk ke menu **Compute Engine** > **VM instances** > klik **Create Instance**.
3. Atur konfigurasi:
   - **Name**: `orderflow-engine`
   - **Region**: `asia-southeast1 (Singapore)`
   - **Machine Type**: `e2-standard-2`
   - **Boot disk**: Ubuntu 22.04 LTS (50 GB SSD)
   - **Firewall**: Centang ☑ **Allow HTTP traffic** dan ☑ **Allow HTTPS traffic**.
4. Klik **Create**.

### Opsi B: Menggunakan Google Cloud SDK (`gcloud CLI`)
```bash
gcloud compute instances create orderflow-engine \
    --project="YOUR_PROJECT_ID" \
    --zone="asia-southeast1-a" \
    --machine-type="e2-standard-2" \
    --image-family="ubuntu-2204-lts" \
    --image-project="ubuntu-os-cloud" \
    --boot-disk-size="50GB" \
    --boot-disk-type="pd-ssd" \
    --tags="http-server,https-server,orderflow-ports"

# Buka firewall untuk port 80, 443, dan 8000
gcloud compute firewall-rules create allow-orderflow \
    --allow=tcp:80,tcp:443,tcp:8000 \
    --target-tags="orderflow-ports" \
    --description="Allow HTTP, HTTPS, and OrderFlow Backend ports"
```

---

## 3. Setup di dalam Server VM (Hanya 1 Kali)

Setelah VM aktif, masuk ke VM via SSH:
```bash
gcloud compute ssh orderflow-engine --zone="asia-southeast1-a"
```

### 1. Install Docker & Docker Compose
Jalankan perintah ini di terminal VM:
```bash
# Update sistem
sudo apt update && sudo apt upgrade -y

# Install Docker engine
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install -y docker-compose-plugin git
```
*(Catatan: Keluar dari SSH dan login kembali agar izin grup docker aktif).*

### 2. Salin / Clone Repositori OrderFlow
```bash
git clone <URL_GITHUB_REPOSITORY_ANDA> OrderFlow
cd OrderFlow
```

### 3. Konfigurasi Environment (`.env`)
Salin template konfigurasi:
```bash
cp backend/.env.example backend/.env
nano backend/.env
```
Pastikan mengisi kredensial Lighter Anda:
```env
LIGHTER_MODE="testnet"               # "testnet" atau "mainnet"
LIGHTER_ACCOUNT_INDEX="275"          # Nomor Account Index Lighter Anda
LIGHTER_API_KEY_INDEX="4"            # API Key Index (4-254)
LIGHTER_PRIVATE_KEY="dc63e9..."      # Private key L1 / Lighter API key
LIGHTER_PAPER_TRADING="False"        # False untuk Real Execution, True untuk Paper
```

---

## 4. Menjalankan Sistem (1 Perintah)

Jalankan seluruh stack (PostgreSQL + Backend FastAPI + Node Signer + Frontend Nginx):
```bash
docker compose up -d --build
```

### Memeriksa Status Container:
```bash
docker compose ps
```
Hasil:
- `orderflow-postgres`: Aktif di port `5432` (healthy)
- `orderflow-backend`: Aktif di port `8000` (FastAPI + Node Signer :3001)
- `orderflow-frontend`: Aktif di port `80` (Nginx + React Vite)

### Melihat Log Realtime:
```bash
# Log seluruh sistem
docker compose logs -f

# Khusus log bot dan execution
docker compose logs -f backend
```

---

## 5. Mengakses Dashboard

Buka browser Anda dan akses:
- **Dashboard UI**: `http://<IP_EXTERNAL_VM>`
- **API & Swagger Docs**: `http://<IP_EXTERNAL_VM>:8000/docs`
- **Riwayat Order di DB**: `http://<IP_EXTERNAL_VM>:8000/api/history/orders`
- **Riwayat Trade di DB**: `http://<IP_EXTERNAL_VM>:8000/api/history/trades`
- **Historis Analitik VPIN & MLOFI**: `http://<IP_EXTERNAL_VM>:8000/api/history/analytics`

---

## 6. Setup Domain & SSL Gratis (Cloudflare / Certbot)

Untuk mengamankan koneksi WebSocket dan Web UI menggunakan HTTPS/WSS:
1. Hubungkan Domain Anda (misal `orderflow.domainanda.com`) ke IP External VM di DNS manager (seperti Cloudflare).
2. Nyalakan mode **Cloudflare Proxy (Orange Cloud)**.
3. Anda langsung mendapatkan **SSL gratis (HTTPS & WSS aman)** tanpa perlu konfigurasi sertifikat manual!
