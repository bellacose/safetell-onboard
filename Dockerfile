FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV ONBOARD_DATA=/data
VOLUME /data
EXPOSE 5055
CMD ["gunicorn", "-b", "0.0.0.0:5055", "-w", "2", "--timeout", "600", "wsgi:app"]
