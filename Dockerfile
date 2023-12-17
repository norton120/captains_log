FROM python:3.11 as app
COPY ./app /app
ENV PYTHONPATH=/app
WORKDIR /app
RUN apt update
RUN apt install ffmpeg --no-install-recommends -y
RUN pip install -r requirements.txt
CMD ["python3", "src"]

FROM keinos/sqlite3 as db
