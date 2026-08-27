# Imagen base oficial de Python
FROM python:3.12-slim

# Evita archivos .pyc y fuerza salida inmediata en terminal
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia todo tu proyecto dentro del contenedor
COPY . .

# Instala pip actualizado y dependencias
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Comando que se ejecutará al iniciar el contenedor
CMD ["python", "main.py"]
