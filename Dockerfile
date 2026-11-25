FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings DEBUG=false
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DEBUG=true DJANGO_SECRET_KEY=build-only-static-files python manage.py collectstatic --noinput && useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["sh", "start.sh"]
