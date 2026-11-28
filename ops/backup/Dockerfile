# Il servizio di backup: pg_dump della stessa versione del server (Postgres 16),
# age per cifrare, rclone per portare il file fuori dalla VM.
#
#   docker build -t delir-backup ops/backup
FROM pgvector/pgvector:pg16

RUN apt-get update \
    && apt-get install -y --no-install-recommends age rclone python3-minimal ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --chmod=0755 backup.sh restore.sh run.sh /backup/
WORKDIR /backup

# Ne' segreti ne' chiavi nell'immagine: tutto arriva dall'ambiente. La chiave
# privata age non entra mai qui: serve solo per ripristinare, fuori dalla VM.
ENTRYPOINT ["/backup/run.sh"]
CMD ["schedule"]
