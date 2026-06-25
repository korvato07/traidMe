FROM python:3.12-slim

WORKDIR /app

# Installer les dépendances système pour la compilation (numpy/pandas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Exposer le port
EXPOSE 8000

# Lancer l'application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
